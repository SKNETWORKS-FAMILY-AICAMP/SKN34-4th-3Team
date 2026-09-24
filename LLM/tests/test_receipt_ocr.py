"""receipt_ocr: 방향 점수·전처리 후보 선택·시간 예산·TSV 파싱.

tesseract 실행(`_ocr_image`)은 대역으로 바꿔, 설치 여부와 무관하게 선택 로직만 검증한다.
"""

from io import BytesIO

import numpy as np
import pytest
from PIL import Image

import src.features.receipt_ocr as ocr
from src.features.receipt_ocr import OcrLine, OcrResult, OcrUnavailableError


def _result(*lines: tuple[str, float]) -> OcrResult:
    return OcrResult(
        lines=[
            OcrLine(index=i, text=text, confidence=conf, left=0, top=i * 10, width=10, height=10)
            for i, (text, conf) in enumerate(lines, start=1)
        ],
        image_width=100,
        image_height=100,
    )


def _png_bytes(width: int, height: int, color: int = 255) -> bytes:
    buffer = BytesIO()
    Image.new("L", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


# ---- 방향·후보 점수 ----


def test_score_ignores_low_confidence_garbage_lines() -> None:
    # 옆으로 누운 사진을 읽으면 뜻 없는 글자가 쏟아진다. 신뢰도 낮은 줄까지 더하면
    # 이쪽 점수가 더 높아져 틀린 방향을 고르던 버그가 있었다(2026-09-24).
    garbage = _result(*[("SHS y OF 7 aed Qn He HS oe" * 3, 40.0)] * 40)
    correct = _result(("결제금액 29,210", 90.0), ("2026-07-27 19:23", 85.0))

    assert ocr._score(garbage) == 0
    assert ocr._better(garbage, correct) is correct


def test_better_keeps_left_on_tie() -> None:
    left = _result(("합계 1,000", 90.0))
    right = _result(("합계 1,000", 90.0))

    assert ocr._better(left, right) is left


def test_is_good_requires_both_confidence_and_length() -> None:
    long_text = "가" * ocr.GOOD_TEXT_LENGTH

    assert ocr._is_good(_result((long_text, ocr.GOOD_MEAN_CONFIDENCE)))
    assert not ocr._is_good(_result((long_text, ocr.GOOD_MEAN_CONFIDENCE - 1)))
    assert not ocr._is_good(_result(("짧음", 99.0)))


# ---- 전처리 ----


def test_prepare_image_shrinks_large_and_enlarges_small_photos() -> None:
    large = ocr._prepare_image(_png_bytes(4000, 3000))
    small = ocr._prepare_image(_png_bytes(400, 300))

    assert max(large.size) == ocr.MAX_LONG_SIDE
    assert max(small.size) == ocr.MIN_LONG_SIDE
    assert large.mode == "L"


def test_prepare_image_rejects_undecodable_bytes() -> None:
    with pytest.raises(OcrUnavailableError):
        ocr._prepare_image(b"not an image")


def test_local_threshold_keeps_dark_text_on_uneven_background() -> None:
    # 왼쪽은 밝고 오른쪽은 어두운(조명이 고르지 않은) 배경에, 양쪽 모두 배경보다 어두운 글자 줄.
    width, height = 200, 60
    background = np.tile(np.linspace(240, 120, width, dtype=np.float32), (height, 1))
    background[28:32, 10:40] -= 80  # 밝은 쪽 글자
    background[28:32, 160:190] -= 80  # 어두운 쪽 글자
    gray = Image.fromarray(background.clip(0, 255).astype(np.uint8))

    binary = np.asarray(ocr._local_threshold(gray))

    assert binary.shape == (height, width)
    assert set(np.unique(binary)) <= {0, 255}
    # 두 글자 모두 검게 남고, 배경은 어두운 쪽까지 희게 남아야 한다.
    assert binary[30, 20] == 0
    assert binary[30, 175] == 0
    assert binary[10, 175] == 255


# ---- run_ocr 선택 흐름 ----


def _patch_ocr_calls(monkeypatch: pytest.MonkeyPatch, results: list[OcrResult]) -> list[int]:
    calls: list[int] = []
    queue = list(results)

    def fake_ocr_image(_image: Image.Image) -> OcrResult:
        calls.append(1)
        return queue.pop(0)

    monkeypatch.setattr(ocr, "_ocr_image", fake_ocr_image)
    return calls


def test_run_ocr_picks_best_of_three_candidates_and_skips_rotation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    good_line = ("결제금액 29,210 2026-07-27 청정원 베이컨 토마토 5,480", 80.0)
    weak = _result(("결제금액", 70.0))
    best = _result(good_line, good_line)
    calls = _patch_ocr_calls(monkeypatch, [weak, weak, best])

    result = ocr.run_ocr(_png_bytes(800, 1200))

    assert result is best
    # 0도에서 세 전처리(enhance·plain·local_threshold)만 읽고 회전 재시도는 하지 않는다.
    assert len(calls) == 3


def test_run_ocr_stops_rotating_when_time_budget_is_spent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    weak = _result(("?", 30.0))
    calls = _patch_ocr_calls(monkeypatch, [weak] * 10)
    # 0도 세 번을 읽는 사이 10분이 흘렀다고 가정한다(어떤 예산이든 넘는 시간).
    elapsed = 600.0
    assert ocr.OCR_TOTAL_BUDGET_SECONDS < elapsed
    clock = iter([0.0] + [elapsed] * 5)
    monkeypatch.setattr(ocr.time, "monotonic", lambda: next(clock))

    ocr.run_ocr(_png_bytes(800, 1200))

    # 예산을 넘겼으므로 0도 세 번 이후 회전 재시도는 한 번도 하지 않는다.
    assert len(calls) == 3


def test_run_ocr_tries_rotations_within_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    weak = _result(("?", 30.0))
    calls = _patch_ocr_calls(monkeypatch, [weak] * 10)
    monkeypatch.setattr(ocr.time, "monotonic", lambda: 0.0)

    ocr.run_ocr(_png_bytes(800, 1200))

    assert len(calls) == 3 + len(ocr.RETRY_ROTATIONS)


# ---- TSV 파싱 ----


def _tsv_row(level, block, par, line, word, left, top, width, height, conf, text) -> str:
    return "\t".join(
        str(v) for v in (level, 1, block, par, line, word, left, top, width, height, conf, text)
    )


def test_parse_tsv_groups_words_into_lines_and_joins_korean_without_spaces() -> None:
    header = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
    rows = [
        _tsv_row(1, 0, 0, 0, 0, 0, 0, 800, 1200, -1, ""),
        # 한글은 글자마다 잘려 나오므로 간격이 좁으면 붙인다.
        _tsv_row(5, 1, 1, 1, 1, 10, 10, 20, 20, 90, "결"),
        _tsv_row(5, 1, 1, 1, 2, 31, 10, 20, 20, 90, "제"),
        # 간격이 넓으면 띄어 쓴다.
        _tsv_row(5, 1, 1, 1, 3, 200, 10, 60, 20, 80, "29,210"),
        # 신뢰도 -1(글자 아님)은 버린다.
        _tsv_row(5, 1, 1, 2, 1, 10, 50, 20, 20, -1, "|"),
        _tsv_row(5, 1, 1, 2, 2, 40, 50, 40, 20, 70, "합계"),
    ]

    result = ocr._parse_tsv("\n".join([header, *rows]))

    assert (result.image_width, result.image_height) == (800, 1200)
    assert [line.text for line in result.lines] == ["결제 29,210", "합계"]
    assert result.lines[0].confidence == pytest.approx((90 + 90 + 80) / 3)
