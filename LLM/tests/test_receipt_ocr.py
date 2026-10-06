"""receipt_ocr: 엔진 선택(PP-OCR → Tesseract 대체)·PP-OCR 줄 묶기·방향 점수·전처리 후보 선택·시간 예산·TSV 파싱.

paddle 파이프라인과 tesseract 실행(`_ocr_image`)은 대역으로 바꿔, 설치 여부와 무관하게 선택 로직만 검증한다.
"""

import asyncio
import threading
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


# ---- run_tesseract_ocr(대체 경로) 선택 흐름 ----


def _patch_ocr_calls(monkeypatch: pytest.MonkeyPatch, results: list[OcrResult]) -> list[int]:
    calls: list[int] = []
    queue = list(results)

    def fake_ocr_image(_image: Image.Image) -> OcrResult:
        calls.append(1)
        return queue.pop(0)

    monkeypatch.setattr(ocr, "_ocr_image", fake_ocr_image)
    return calls


def test_tesseract_picks_best_of_three_candidates_and_skips_rotation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    good_line = ("결제금액 29,210 2026-07-27 청정원 베이컨 토마토 5,480", 80.0)
    weak = _result(("결제금액", 70.0))
    best = _result(good_line, good_line)
    calls = _patch_ocr_calls(monkeypatch, [weak, weak, best])

    result = ocr.run_tesseract_ocr(_png_bytes(800, 1200))

    assert result is best
    # 0도에서 세 전처리(enhance·plain·local_threshold)만 읽고 회전 재시도는 하지 않는다.
    assert len(calls) == 3


def test_tesseract_stops_rotating_when_time_budget_is_spent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    weak = _result(("?", 30.0))
    calls = _patch_ocr_calls(monkeypatch, [weak] * 10)
    # 0도 세 번을 읽는 사이 10분이 흘렀다고 가정한다(어떤 예산이든 넘는 시간).
    elapsed = 600.0
    assert ocr.OCR_TOTAL_BUDGET_SECONDS < elapsed
    clock = iter([0.0] + [elapsed] * 5)
    monkeypatch.setattr(ocr.time, "monotonic", lambda: next(clock))

    ocr.run_tesseract_ocr(_png_bytes(800, 1200))

    # 예산을 넘겼으므로 0도 세 번 이후 회전 재시도는 한 번도 하지 않는다.
    assert len(calls) == 3


def test_tesseract_tries_rotations_within_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    weak = _result(("?", 30.0))
    calls = _patch_ocr_calls(monkeypatch, [weak] * 10)
    monkeypatch.setattr(ocr.time, "monotonic", lambda: 0.0)

    ocr.run_tesseract_ocr(_png_bytes(800, 1200))

    assert len(calls) == 3 + len(ocr.RETRY_ROTATIONS)


# ---- 엔진 선택: PP-OCRv5가 기본, 쓸 수 없거나 실패하면 Tesseract ----


class _FakePaddleResult:
    def __init__(self, texts, scores, boxes):
        self.json = {"res": {"rec_texts": texts, "rec_scores": scores, "rec_boxes": boxes}}


class _FakePaddle:
    def __init__(self, results=None, error=None):
        self.results, self.error, self.inputs = results or [], error, []

    def predict(self, image):
        self.inputs.append(image)
        if self.error:
            raise self.error
        return iter(self.results)


def test_run_ocr_uses_paddle_and_groups_boxes_into_receipt_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    # PP-OCR은 품목명·단가·수량을 따로 돌려준다. 같은 높이의 상자는 왼→오른 순서로 한 줄이 된다.
    fake = _FakePaddle([_FakePaddleResult(
        ["5,480", "베이컨토마토", "합계", "1", "29,210"],
        [0.9, 0.8, 0.95, 0.7, 0.99],
        [[300, 102, 360, 122], [10, 100, 120, 124], [10, 200, 60, 222], [400, 101, 410, 121], [300, 201, 380, 221]],
    )])
    monkeypatch.setattr(ocr, "_get_paddle_pipeline", lambda: fake)
    monkeypatch.setattr(ocr, "run_tesseract_ocr", lambda _b: pytest.fail("Tesseract should not run"))

    result = ocr.run_ocr(_png_bytes(500, 300))

    assert [line.text for line in result.lines] == ["베이컨토마토 5,480 1", "합계 29,210"]
    assert [line.index for line in result.lines] == [1, 2]
    # 신뢰도는 0~1 → 0~100으로 바꾸고 글자 수로 가중 평균한다.
    assert result.lines[1].confidence == pytest.approx((95 * 2 + 99 * 6) / 8)
    assert (result.lines[0].left, result.lines[0].width) == (10, 400)
    assert (result.image_width, result.image_height) == (500, 300)
    # paddle에는 BGR 3채널 배열을 넘긴다.
    assert fake.inputs[0].shape == (300, 500, 3)


def test_run_ocr_falls_back_to_tesseract_when_paddle_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    fallback = _result(("합계 1,000", 90.0))
    monkeypatch.setattr(ocr, "_get_paddle_pipeline", lambda: None)
    monkeypatch.setattr(ocr, "run_tesseract_ocr", lambda _b: fallback)

    assert ocr.run_ocr(_png_bytes(100, 100)) is fallback


def test_run_ocr_falls_back_to_tesseract_when_paddle_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    fallback = _result(("합계 1,000", 90.0))
    monkeypatch.setattr(ocr, "_get_paddle_pipeline", lambda: _FakePaddle(error=RuntimeError("boom")))
    monkeypatch.setattr(ocr, "run_tesseract_ocr", lambda _b: fallback)

    assert ocr.run_ocr(_png_bytes(100, 100)) is fallback


def test_run_ocr_rejects_undecodable_bytes_before_any_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ocr, "_get_paddle_pipeline", lambda: pytest.fail("engine should not load"))

    with pytest.raises(OcrUnavailableError):
        ocr.run_ocr(b"not an image")


def test_run_ocr_shrinks_large_photo_before_paddle(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakePaddle()
    monkeypatch.setattr(ocr, "_get_paddle_pipeline", lambda: fake)

    result = ocr.run_ocr(_png_bytes(4000, 1000))

    assert fake.inputs[0].shape == (500, 2000, 3)
    assert (result.image_width, result.image_height) == (2000, 500)


# ---- run_ocr_limited: 전용 스레드·대기열 상한·대기 시간 상한 ----


def test_run_ocr_limited_returns_result_and_frees_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = _result(("합계 1,000", 90.0))
    monkeypatch.setattr(ocr, "run_ocr", lambda _b: expected)

    async def scenario() -> OcrResult:
        result = await ocr.run_ocr_limited(b"image")
        await asyncio.sleep(0)  # 완료 콜백이 대기열 자리를 돌려줄 기회를 준다.
        return result

    assert asyncio.run(scenario()) is expected
    assert ocr._ocr_pending == 0


def test_run_ocr_limited_rejects_when_queue_is_full(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ocr, "_ocr_pending", ocr.OCR_MAX_PENDING)
    monkeypatch.setattr(ocr, "run_ocr", lambda _b: pytest.fail("OCR should not run"))

    with pytest.raises(ocr.OcrBusyError):
        asyncio.run(ocr.run_ocr_limited(b"image"))


def test_run_ocr_limited_times_out_but_keeps_slot_until_ocr_ends(monkeypatch: pytest.MonkeyPatch) -> None:
    release = threading.Event()
    monkeypatch.setattr(ocr, "OCR_WAIT_SECONDS", 0.05)
    monkeypatch.setattr(ocr, "run_ocr", lambda _b: release.wait(5) and _result(("합계", 90.0)))

    async def scenario() -> tuple[int, int]:
        with pytest.raises(TimeoutError):
            await ocr.run_ocr_limited(b"image")
        still_running = ocr._ocr_pending
        release.set()
        for _ in range(100):
            if ocr._ocr_pending == 0:
                break
            await asyncio.sleep(0.01)
        return still_running, ocr._ocr_pending

    try:
        assert asyncio.run(scenario()) == (1, 0)
    finally:
        release.set()


def test_group_rows_keeps_rows_apart_when_vertical_gap_is_large() -> None:
    lines = ocr._group_rows([
        ("둘째 줄", 90.0, 0, 40, 50, 60),
        ("첫째 줄", 90.0, 0, 0, 50, 20),
    ])

    assert [line.text for line in lines] == ["첫째 줄", "둘째 줄"]


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
