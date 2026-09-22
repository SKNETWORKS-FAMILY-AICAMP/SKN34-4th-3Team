"""영수증 이미지에서 글자·위치·신뢰도를 읽는 Tesseract OCR.

LLM은 이 결과(글자)만 받아 해석한다. 이미지를 직접 보고 값을 채우는 Vision 방식보다
같은 이미지에 같은 결과가 나오고, 읽은 자리와 인식 신뢰도를 남길 수 있다.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps

OCR_LANGUAGES = "kor+eng"
# 영수증 전체를 하나의 텍스트 블록으로 본다. 금액 줄("60,000원")을 가장 잘 읽었다.
OCR_PAGE_SEGMENTATION_MODE = "6"
# 한글은 글자마다 별도 단어로 잘려 나오므로, 이 비율보다 좁은 간격이면 띄어쓰기 없이 붙인다.
WORD_GAP_RATIO = 0.3
OCR_TIMEOUT_SECONDS = 40.0
MIN_TEXT_CHARACTERS = 8
# 휴대폰 사진(수천 px)은 글자가 필요 이상으로 크고 배경 잡음이 많아 이 길이로 줄여 읽는다.
MAX_LONG_SIDE = 2600
# 이 정도면 방향이 맞다고 보고 회전 재시도를 건너뛴다.
GOOD_MEAN_CONFIDENCE = 55.0
GOOD_TEXT_LENGTH = 30
RETRY_ROTATIONS = (90, 270, 180)


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
    """영수증 이미지를 보정해 글자를 읽어 줄 단위로 돌려준다. 읽지 못하면 OcrUnavailableError.

    휴대폰 사진은 EXIF 회전 정보만 있고 실제 픽셀은 옆으로 누워 있는 경우가 많다. 회전을 적용하고,
    그래도 잘 읽히지 않으면 90/270/180도로 돌려 가며 가장 잘 읽힌 결과를 쓴다.
    """
    base = _prepare_image(image_bytes)
    best = _ocr_image(base)
    if _is_good(best):
        return best
    for angle in RETRY_ROTATIONS:
        candidate = _ocr_image(base.rotate(angle, expand=True))
        if _score(candidate) > _score(best):
            best = candidate
        if _is_good(best):
            break
    return best


def _prepare_image(image_bytes: bytes) -> Image.Image:
    """EXIF 회전 적용 후 흑백·대비 보정하고 긴 변을 MAX_LONG_SIDE로 줄인다."""
    try:
        image = Image.open(BytesIO(image_bytes))
        image.load()
        image = ImageOps.exif_transpose(image)
    except Exception as exc:  # 손상된 파일, 지원하지 않는 형식, 지나치게 큰 이미지
        raise OcrUnavailableError("image could not be decoded") from exc
    gray = ImageOps.autocontrast(ImageOps.grayscale(image), cutoff=1)
    long_side = max(gray.size)
    if long_side > MAX_LONG_SIDE:
        ratio = MAX_LONG_SIDE / long_side
        gray = gray.resize((round(gray.width * ratio), round(gray.height * ratio)), Image.LANCZOS)
    return gray


def _ocr_image(image: Image.Image) -> OcrResult:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return _run_tesseract(buffer.getvalue())


def _score(result: OcrResult) -> float:
    """신뢰도로 가중한 글자 수. 방향이 맞을수록 크다."""
    return sum(line.confidence * len(line.text) for line in result.lines)


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
