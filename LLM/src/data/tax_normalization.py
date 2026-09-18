"""세법 비율 표현을 원문 의미를 보존하며 검색 가능한 형태로 정규화한다."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re


_NUMBER = r"\d+(?:,\d{3})*(?:\.\d+)?"
_LEGAL_FRACTION_PATTERN = re.compile(
    rf"(?P<expression>(?P<denominator>{_NUMBER})\s*분의\s*"
    rf"(?P<numerator>{_NUMBER}))"
    rf"(?P<annotation>\s*\(\s*{_NUMBER}\s*%\s*\))?"
)
_PERCENT_PATTERN = re.compile(rf"(?P<percentage>{_NUMBER})\s*%")
_MAX_PERCENT_DECIMALS = Decimal("0.000001")


def normalize_legal_percentage(text: str | None) -> str | None:
    """`분모분의 분자` 원문 뒤에 계산된 백분율 표기를 추가한다.

    Args:
        text: 정규화할 세법 문자열 또는 None.

    Returns:
        원문 비율과 계산된 `%`가 함께 있는 문자열. 기존 `%` 주석은 중복하지 않는다.
    """
    if text is None:
        return None

    def replace_fraction(match: re.Match[str]) -> str:
        if match.group("annotation"):
            return match.group(0)
        percentage = _fraction_percentage(
            match.group("denominator"),
            match.group("numerator"),
        )
        if percentage is None:
            return match.group(0)
        return f"{match.group('expression')}({_decimal_text(percentage)}%)"

    return _LEGAL_FRACTION_PATTERN.sub(replace_fraction, text)


def extract_legal_percentages(text: str) -> set[Decimal]:
    """법령의 `분의` 표현과 `%` 표현에서 검증 가능한 비율을 추출한다."""
    percentages = {
        percentage
        for match in _LEGAL_FRACTION_PATTERN.finditer(text)
        if (
            percentage := _fraction_percentage(
                match.group("denominator"),
                match.group("numerator"),
            )
        )
        is not None
    }
    for match in _PERCENT_PATTERN.finditer(text):
        try:
            percentages.add(Decimal(match.group("percentage").replace(",", "")))
        except InvalidOperation:
            continue
    return percentages


def extract_legal_ratios(
    text: str,
    *,
    context_window: int = 40,
) -> list[dict[str, object]]:
    """`분모분의 분자` 비율과 주변 문맥을 계산 없이 구조화한다.

    원문을 변경하지 않으며 해당 값이 세율·감면율인지 의미를 단정하지 않는다.
    """
    ratios: list[dict[str, object]] = []
    for match in _LEGAL_FRACTION_PATTERN.finditer(text):
        percentage = _fraction_percentage(
            match.group("denominator"),
            match.group("numerator"),
        )
        if percentage is None:
            continue
        denominator = Decimal(match.group("denominator").replace(",", ""))
        numerator = Decimal(match.group("numerator").replace(",", ""))
        context_start = max(0, match.start() - context_window)
        context_end = min(len(text), match.end() + context_window)
        ratios.append(
            {
                "raw": match.group("expression"),
                "numerator": _json_number(numerator),
                "denominator": _json_number(denominator),
                "percent": _json_number(percentage),
                "decimal": _json_number(percentage / Decimal(100)),
                "context": text[context_start:context_end],
            }
        )
    return ratios


def decimal_text(value: Decimal) -> str:
    """Decimal을 지수나 불필요한 후행 0이 없는 문자열로 변환한다."""
    return _decimal_text(value)


def _fraction_percentage(
    denominator_text: str,
    numerator_text: str,
) -> Decimal | None:
    try:
        denominator = Decimal(denominator_text.replace(",", ""))
        numerator = Decimal(numerator_text.replace(",", ""))
    except InvalidOperation:
        return None
    if denominator == 0:
        return None
    percentage = numerator / denominator * Decimal(100)
    return percentage.quantize(_MAX_PERCENT_DECIMALS, rounding=ROUND_HALF_UP)


def _decimal_text(value: Decimal) -> str:
    normalized = format(value, "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized or "0"


def _json_number(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)
