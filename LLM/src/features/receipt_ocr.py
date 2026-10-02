"""영수증 이미지에서 글자·위치·신뢰도를 읽는 OCR.

기본 엔진은 PaddleOCR PP-OCRv5 한국어 모델이다. 실제 영수증 5장 실측(2026-10-02)에서
Tesseract보다 정확하고(정답 34개 중 33개 vs 28개) 빨랐다(5장 12.1초 vs 25.9초).
paddle을 불러오지 못하면(설치 누락·모델 다운로드 실패 등) 종전 Tesseract 경로로 읽는다.
측정 내용: Docs/OCR_PPOCRV5_BENCHMARK.md

LLM은 이 결과(글자)만 받아 해석한다. 이미지를 직접 보고 값을 채우는 Vision 방식보다
같은 이미지에 같은 결과가 나오고, 읽은 자리와 인식 신뢰도를 남길 수 있다.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from io import BytesIO
from typing import Any

import numpy as np
from PIL import Image, ImageFilter, ImageOps

OCR_LANGUAGES = "kor+eng"
# 영수증 전체를 하나의 텍스트 블록으로 본다. 금액 줄("60,000원")을 가장 잘 읽었다.
OCR_PAGE_SEGMENTATION_MODE = "6"
# 한글은 글자마다 별도 단어로 잘려 나오므로, 이 비율보다 좁은 간격이면 띄어쓰기 없이 붙인다.
WORD_GAP_RATIO = 0.3
# 한 번의 tesseract 실행이 걸리는 시간. 2000px로 줄인 사진은 보통 1~8초면 끝나므로,
# 이보다 훨씬 길게 걸리면 재시도로 시간을 더 쓰기보다 그 실행만 포기하는 게 낫다.
OCR_TIMEOUT_SECONDS = 15.0
# run_ocr() 전체(전처리 3종 + 회전 재시도)가 쓸 수 있는 시간. 호출자(Backend)가
# LLM_TIMEOUT_OCR로, 프런트엔드가 업로드 요청 자체로 각각 제한 시간을 두고 있어
# OCR만 그보다 오래 끌면 호출자가 먼저 포기하고, 그 뒤 OCR이 끝나 봐야 아무도 보지
# 못한 채 그대로 저장(또는 목 값으로 대체)돼 버린다(2026-09-24). 이미 만든 후보 중
# 가장 나은 것을 쓰는 것이 회전을 마저 시도하는 것보다 항상 안전하므로, 예산을 넘기면
# 남은 회전 시도를 건너뛴다.
OCR_TOTAL_BUDGET_SECONDS = 25.0
MIN_TEXT_CHARACTERS = 8
# 휴대폰 사진(수천 px)은 글자가 필요 이상으로 크고 배경 잡음이 많아 이 길이로 줄여 읽는다.
# 실제 영수증 6장 실측에서 2600px보다 2000px이 인식률·속도 모두 좋았다(2026-09-24).
MAX_LONG_SIDE = 2000
# 반대로 너무 작은 사진은 글자가 뭉개져 확대해야 읽힌다.
MIN_LONG_SIDE = 1200
# 감열지 영수증의 점 노이즈를 지우고(median) 흐린 획을 세운다(unsharp).
MEDIAN_FILTER_SIZE = 3
UNSHARP_RADIUS = 2
UNSHARP_PERCENT = 150
UNSHARP_THRESHOLD = 3
# 이 정도면 방향이 맞다고 보고 회전 재시도를 건너뛴다.
GOOD_MEAN_CONFIDENCE = 55.0
GOOD_TEXT_LENGTH = 30
RETRY_ROTATIONS = (90, 270, 180)
# 방향·전처리 후보를 비교할 때 이보다 신뢰도가 낮은 줄은 세지 않는다. 옆으로 누운 사진을 읽으면
# 뜻 없는 글자가 수백 자 쏟아지는데, 이걸 다 더하면 제대로 읽은 방향보다 점수가 높아진다.
SCORE_MIN_LINE_CONFIDENCE = 60.0
# 지역(적응형) 이진화: 이 칸 안의 평균 밝기보다 C 이상 어두운 픽셀만 검게 남긴다. 감열지 영수증은
# 위아래 밝기가 고르지 않아, 사진 전체에 같은 임계값을 쓰는 전역 이진화(Otsu)는 시험해 보니
# 흐린 글자를 통째로 날렸다. 조명이 나쁜 사진에서 특히 효과가 커, 실측(2026-09-24)에서 유효
# 글자 수가 +23.8%(6장 합계 810→1003자) 늘었다.
LOCAL_THRESHOLD_BLOCK = 35
LOCAL_THRESHOLD_C = 10

# ---- PP-OCRv5 한국어(기본 엔진) 설정: 실측(2026-10-02)에서 정확도를 유지하며 가장 빨랐던 조합 ----
# 검출은 가벼운 mobile 모델(기본 server 모델과 정확도가 같고 1.8배 빠름). 한국어 인식 모델은 mobile뿐이다.
PADDLE_DET_MODEL = "PP-OCRv5_mobile_det"
PADDLE_REC_MODEL = "korean_PP-OCRv5_mobile_rec"
# 검출에 쓰는 긴 변 상한. 1280px부터는 작은 품목명을 놓쳐 1600px로 둔다.
PADDLE_DET_LIMIT_SIDE = 1600
# 다른 컨테이너와 CPU를 나눠 쓰는 환경에서 4개가 2·6·8개보다 빨랐다. 서버 코어 수에 맞춰 바꿀 수 있다.
PADDLE_CPU_THREADS = int(os.getenv("OCR_CPU_THREADS", "4"))
# 같은 줄로 묶는 기준: 두 글자 상자의 세로 중심 차이가 글자 높이의 이 비율 이하면 한 줄로 본다.
# PP-OCR은 "베이컨토마토", "5,480", "1"을 따로 돌려주므로, 영수증 한 줄로 묶어야 LLM이 품목과 금액을 짝짓는다.
ROW_CENTER_RATIO = 0.5

_logger = logging.getLogger(__name__)
_paddle_pipeline: Any = None
_paddle_failed = False
# 파이프라인 생성과 추론을 한 번에 하나씩만 한다(모델 중복 로드 방지, 추론 객체는 스레드 안전이 보장되지 않음).
_paddle_lock = threading.Lock()


class OcrUnavailableError(RuntimeError):
    """OCR 엔진이 없거나 실행에 실패해 글자를 읽지 못했다."""


@dataclass(frozen=True)
class OcrLine:
    """한 줄로 묶인 글자와 위치(원본 이미지 픽셀), 인식 신뢰도(0~100)."""

    index: int
    text: str
    confidence: float
    left: int
    top: int
    width: int
    height: int


@dataclass(frozen=True)
class OcrResult:
    lines: list[OcrLine]
    image_width: int
    image_height: int

    @property
    def text_length(self) -> int:
        return sum(len(line.text.replace(" ", "")) for line in self.lines)

    @property
    def mean_confidence(self) -> float:
        """글자 수로 가중한 평균 신뢰도(0~100). 줄이 없으면 0."""
        total = sum(len(line.text) for line in self.lines)
        if not total:
            return 0.0
        return sum(line.confidence * len(line.text) for line in self.lines) / total

    def as_prompt_text(self) -> str:
        """LLM에 넘기는 번호 붙은 줄 목록."""
        return "\n".join(
            f"[{line.index}] {line.text}  (신뢰도 {round(line.confidence)}%)"
            for line in self.lines
        )


def run_ocr(image_bytes: bytes) -> OcrResult:
    """영수증 이미지의 글자를 줄 단위로 돌려준다. 읽지 못하면 OcrUnavailableError.

    PP-OCRv5 한국어로 읽고, paddle을 쓸 수 없거나 실행에 실패하면 Tesseract로 읽는다.
    """
    image = _open_image(image_bytes)
    pipeline = _get_paddle_pipeline()
    if pipeline is not None:
        try:
            return _run_paddle(pipeline, image)
        except Exception:  # paddle 내부 오류는 종류가 다양해 모두 Tesseract로 넘긴다
            _logger.exception("PP-OCR failed; falling back to Tesseract")
    return run_tesseract_ocr(image_bytes)


def warm_up() -> bool:
    """서버 시작 직후 모델을 미리 불러와 첫 영수증이 로딩 시간을 기다리지 않게 한다."""
    pipeline = _get_paddle_pipeline()
    if pipeline is None:
        return False
    try:
        _run_paddle(pipeline, Image.new("RGB", (320, 120), "white"))
    except Exception:
        _logger.exception("PP-OCR warm-up failed")
        return False
    return True


def _get_paddle_pipeline() -> Any:
    """PP-OCR 파이프라인을 처음 한 번만 만든다. 만들 수 없으면 None(이후 다시 시도하지 않는다)."""
    global _paddle_pipeline, _paddle_failed
    if _paddle_pipeline is not None or _paddle_failed:
        return _paddle_pipeline
    with _paddle_lock:
        if _paddle_pipeline is not None or _paddle_failed:
            return _paddle_pipeline
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        try:
            from paddleocr import PaddleOCR

            _paddle_pipeline = PaddleOCR(
                text_detection_model_name=PADDLE_DET_MODEL,
                text_recognition_model_name=PADDLE_REC_MODEL,
                # 옆으로 누운 사진이 많아 문서 방향 분류는 켠다. 글줄 방향 분류는 효과 없이 느려 끈다.
                use_doc_orientation_classify=True,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                text_det_limit_type="max",
                text_det_limit_side_len=PADDLE_DET_LIMIT_SIDE,
                cpu_threads=PADDLE_CPU_THREADS,
            )
        except Exception:
            _logger.exception("PP-OCR unavailable; using Tesseract")
            _paddle_failed = True
        return _paddle_pipeline


def _run_paddle(pipeline: Any, image: Image.Image) -> OcrResult:
    bgr = np.ascontiguousarray(np.asarray(image.convert("RGB"))[:, :, ::-1])
    with _paddle_lock:
        results = list(pipeline.predict(bgr))
    words: list[tuple[str, float, float, float, float, float]] = []
    for result in results:
        data = result.json.get("res", result.json)
        texts = data.get("rec_texts") or []
        scores = data.get("rec_scores") or []
        boxes = data.get("rec_boxes") or []
        for text, score, box in zip(texts, scores, boxes):
            text = str(text).strip()
            if text:
                x1, y1, x2, y2 = (float(v) for v in box)
                words.append((text, float(score) * 100, x1, y1, x2, y2))
    return OcrResult(
        lines=_group_rows(words), image_width=image.width, image_height=image.height
    )


def _group_rows(words: list[tuple[str, float, float, float, float, float]]) -> list[OcrLine]:
    """글자 상자(text, 신뢰도, x1, y1, x2, y2)를 세로 위치가 같은 것끼리 한 줄로 묶는다.

    줄은 위→아래, 줄 안의 상자는 왼→오른 순서로 잇는다. 줄 신뢰도는 글자 수로 가중한 평균.
    """
    rows: list[list[tuple[str, float, float, float, float, float]]] = []
    for word in sorted(words, key=lambda w: (w[3] + w[5]) / 2):
        center, height = (word[3] + word[5]) / 2, word[5] - word[3]
        if rows:
            row = rows[-1]
            row_center = sum((w[3] + w[5]) / 2 for w in row) / len(row)
            row_height = sum(w[5] - w[3] for w in row) / len(row)
            if abs(center - row_center) <= ROW_CENTER_RATIO * min(height, row_height):
                row.append(word)
                continue
        rows.append([word])

    lines: list[OcrLine] = []
    for row in rows:
        row.sort(key=lambda w: w[2])
        chars = sum(len(w[0]) for w in row)
        left, top = min(w[2] for w in row), min(w[3] for w in row)
        right, bottom = max(w[4] for w in row), max(w[5] for w in row)
        lines.append(
            OcrLine(
                index=len(lines) + 1,
                text=" ".join(w[0] for w in row),
                confidence=sum(w[1] * len(w[0]) for w in row) / chars,
                left=round(left),
                top=round(top),
                width=round(right - left),
                height=round(bottom - top),
            )
        )
    return lines


def run_tesseract_ocr(image_bytes: bytes) -> OcrResult:
    """(대체 경로) 영수증 이미지를 보정해 Tesseract로 읽는다. 읽지 못하면 OcrUnavailableError.

    휴대폰 사진은 EXIF 회전 정보만 있고 실제 픽셀은 옆으로 누워 있는 경우가 많다. 회전을 적용하고,
    그래도 잘 읽히지 않으면 90/270/180도로 돌려 가며 가장 잘 읽힌 결과를 쓴다.

    전처리는 세 가지를 쓴다. 노이즈 제거 + 샤픈(_enhance), 대비 보정만 한 것(_plain), 지역
    적응형 이진화(_local_threshold)인데, 실제 영수증으로 재보니 사진마다 잘 읽히는 쪽이 갈려
    하나만 쓸 수 없었다(2026-09-24). 특히 조명이 고르지 않은 사진은 _local_threshold가 크게
    나아서, 0도에서 바로 통과해 회전 재시도(최악의 경우 수십 초)를 건너뛰게 해 준다.
    """
    started = time.monotonic()
    gray = _prepare_image(image_bytes)
    enhanced, plain = _enhance(gray), _plain(gray)

    # 똑바로 놓인 사진이 대부분이므로 0도에서는 세 전처리를 모두 읽고 가장 나은 것을 쓴다.
    best = _ocr_image(enhanced)
    best = _better(best, _ocr_image(plain))
    best = _better(best, _ocr_image(_local_threshold(gray)))
    if _is_good(best):
        return best

    # 여기까지 왔으면 사진이 누웠을 가능성이 크다. 회전은 기본 전처리로만 훑되,
    # 예산을 넘기면 지금까지 중 가장 나은 결과로 만족한다.
    for angle in RETRY_ROTATIONS:
        if time.monotonic() - started >= OCR_TOTAL_BUDGET_SECONDS:
            break
        best = _better(best, _ocr_image(enhanced.rotate(angle, expand=True)))
        if _is_good(best):
            break
    return best


def _better(left: OcrResult, right: OcrResult) -> OcrResult:
    return right if _score(right) > _score(left) else left


def _prepare_image(image_bytes: bytes) -> Image.Image:
    """EXIF 회전을 적용하고 흑백으로 바꾼 뒤 읽기 좋은 크기로 맞춘다.

    큰 휴대폰 사진은 줄이고(MAX_LONG_SIDE), 반대로 너무 작은 사진은 글자가 뭉개지므로
    키운다(MIN_LONG_SIDE).
    """
    gray = ImageOps.grayscale(_open_image(image_bytes))
    long_side = max(gray.size)
    ratio = 0.0
    if long_side > MAX_LONG_SIDE:
        ratio = MAX_LONG_SIDE / long_side
    elif long_side < MIN_LONG_SIDE:
        ratio = MIN_LONG_SIDE / long_side
    if ratio:
        gray = gray.resize((round(gray.width * ratio), round(gray.height * ratio)), Image.LANCZOS)
    return gray


def _open_image(image_bytes: bytes) -> Image.Image:
    """이미지를 열고 휴대폰 사진의 EXIF 회전 정보를 실제 픽셀에 적용한다."""
    try:
        image = Image.open(BytesIO(image_bytes))
        image.load()
        return ImageOps.exif_transpose(image)
    except Exception as exc:  # 손상된 파일, 지원하지 않는 형식, 지나치게 큰 이미지
        raise OcrUnavailableError("image could not be decoded") from exc


def _plain(gray: Image.Image) -> Image.Image:
    """대비만 늘린다(종전 방식). 선명한 사진에서는 이쪽이 더 잘 읽히기도 한다."""
    return ImageOps.autocontrast(gray, cutoff=1)


def _enhance(gray: Image.Image) -> Image.Image:
    """대비 보정 + 점 노이즈 제거 + 획 선명화. 기본 경로로 쓴다."""
    enhanced = ImageOps.autocontrast(gray, cutoff=1)
    enhanced = enhanced.filter(ImageFilter.MedianFilter(size=MEDIAN_FILTER_SIZE))
    return enhanced.filter(
        ImageFilter.UnsharpMask(
            radius=UNSHARP_RADIUS, percent=UNSHARP_PERCENT, threshold=UNSHARP_THRESHOLD
        )
    )


def _local_threshold(gray: Image.Image) -> Image.Image:
    """칸(LOCAL_THRESHOLD_BLOCK)마다 그 주변 평균 밝기를 기준으로 흑백을 나눈다.

    전역 임계값(Otsu)은 사진 전체에 같은 기준을 쓰므로 조명이 고르지 않은 감열지
    영수증에서 흐린 쪽 글자를 통째로 날린다. 적분영상(누적합)으로 칸마다 평균을
    구해 사진 전체를 한 번만 훑고 빠르게 계산한다.
    """
    array = np.asarray(gray, dtype=np.float32)
    block, half = LOCAL_THRESHOLD_BLOCK, LOCAL_THRESHOLD_BLOCK // 2
    padded = np.pad(array, half, mode="reflect")
    cumsum = np.pad(np.cumsum(np.cumsum(padded, axis=0), axis=1), ((1, 0), (1, 0)))
    height, width = array.shape
    local_sum = (
        cumsum[block:block + height, block:block + width]
        - cumsum[:height, block:block + width]
        - cumsum[block:block + height, :width]
        + cumsum[:height, :width]
    )
    local_mean = local_sum / (block * block)
    binary = np.where(array > local_mean - LOCAL_THRESHOLD_C, 255, 0).astype(np.uint8)
    return Image.fromarray(binary)


def _ocr_image(image: Image.Image) -> OcrResult:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return _run_tesseract(buffer.getvalue())


def _score(result: OcrResult) -> float:
    """믿을 만한 줄의 신뢰도 가중 글자 수. 방향이 맞을수록 크다."""
    return sum(
        line.confidence * len(line.text)
        for line in result.lines
        if line.confidence >= SCORE_MIN_LINE_CONFIDENCE
    )


def _is_good(result: OcrResult) -> bool:
    return (
        result.mean_confidence >= GOOD_MEAN_CONFIDENCE
        and result.text_length >= GOOD_TEXT_LENGTH
    )


def _run_tesseract(image_bytes: bytes) -> OcrResult:
    try:
        completed = subprocess.run(
            [
                "tesseract",
                "stdin",
                "stdout",
                "-l",
                OCR_LANGUAGES,
                "--psm",
                OCR_PAGE_SEGMENTATION_MODE,
                "tsv",
            ],
            input=image_bytes,
            capture_output=True,
            timeout=OCR_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as exc:
        raise OcrUnavailableError("tesseract is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise OcrUnavailableError("tesseract timed out") from exc

    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()[:200]
        raise OcrUnavailableError(f"tesseract failed: {detail}")
    return _parse_tsv(completed.stdout.decode("utf-8", errors="replace"))


def _parse_tsv(tsv: str) -> OcrResult:
    image_width = image_height = 0
    grouped: dict[tuple[int, int, int], list[tuple[int, str, float, int, int, int, int]]] = {}

    for row in tsv.splitlines()[1:]:
        cells = row.split("\t")
        if len(cells) < 12:
            continue
        try:
            level = int(cells[0])
            block, paragraph, line_no, word_no = (int(cells[i]) for i in (2, 3, 4, 5))
            left, top, width, height = (int(cells[i]) for i in (6, 7, 8, 9))
            confidence = float(cells[10])
        except ValueError:
            continue
        if level == 1:
            image_width, image_height = width, height
            continue
        text = cells[11].strip()
        if level != 5 or not text or confidence < 0:
            continue
        grouped.setdefault((block, paragraph, line_no), []).append(
            (word_no, text, confidence, left, top, width, height)
        )

    lines: list[OcrLine] = []
    for key in sorted(grouped):
        words = sorted(grouped[key])
        left = min(w[3] for w in words)
        top = min(w[4] for w in words)
        right = max(w[3] + w[5] for w in words)
        bottom = max(w[4] + w[6] for w in words)
        lines.append(
            OcrLine(
                index=len(lines) + 1,
                text=_join_words(words, bottom - top),
                confidence=sum(w[2] for w in words) / len(words),
                left=left,
                top=top,
                width=right - left,
                height=bottom - top,
            )
        )
    return OcrResult(lines=lines, image_width=image_width, image_height=image_height)


def _join_words(words: list[tuple[int, str, float, int, int, int, int]], line_height: int) -> str:
    """단어 사이 간격이 글자 높이에 비해 넓을 때만 공백을 넣는다."""
    threshold = max(2.0, line_height * WORD_GAP_RATIO)
    pieces = [words[0][1]]
    for previous, current in zip(words, words[1:]):
        gap = current[3] - (previous[3] + previous[5])
        pieces.append((" " if gap > threshold else "") + current[1])
    return "".join(pieces)
