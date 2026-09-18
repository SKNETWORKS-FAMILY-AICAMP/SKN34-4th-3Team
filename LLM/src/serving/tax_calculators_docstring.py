"""
tax_calculators_docstring.py

국세청 공개 자료 기반 MVP용 deterministic 세금 계산기.
각 함수의 파라미터 설명은 함수 내부 docstring의 Args 섹션에 정리되어 있습니다.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Literal


Money = int | float | str | Decimal

StartupCategory = Literal[
    "startup_sme",
    "youth_or_livelihood",
]

StartupRegion = Literal[
    "capital_overconcentration",
    "capital_region_other",
    "outside_capital_region",
]

SimplifiedVatIndustry = Literal[
    "retail_recycling_food",
    "manufacturing_agriculture_forestry_fishery_small_cargo",
    "lodging",
    "construction_transport_storage_information",
    "finance_professional_support_real_estate",
    "other_services",
]

CalculationType = Literal[
    "income_tax",
    "startup_tax_reduction",
    "general_vat",
    "simplified_vat_output_tax",
    "withholding_tax",
]


class TaxCalculationError(ValueError):
    """세금 계산 입력값 오류."""


def _to_decimal(value: Money, *, name: str) -> Decimal:
    """
    Args:
        value (Money): Decimal로 변환할 숫자 값.
        name (str): 오류 메시지에 표시할 입력값 이름.

    Returns:
        Decimal: 변환된 Decimal 값.
    """
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise TaxCalculationError(f"{name} 값이 숫자가 아닙니다: {value!r}") from exc

    if number < 0:
        raise TaxCalculationError(f"{name} 값은 0 이상이어야 합니다.")

    return number


def _money_string(value: Decimal) -> str:
    """
    Args:
        value (Decimal): 문자열로 변환할 금액.

    Returns:
        str: 소수점 둘째 자리까지 표현한 금액 문자열.
    """
    return format(value.quantize(Decimal("0.01")), "f")


# ===========================================================================
# 1. 종합소득세
# ===========================================================================

INCOME_TAX_BRACKETS_2023_2025 = (
    (Decimal("0"), Decimal("14000000"), Decimal("0.06"), Decimal("0")),
    (Decimal("14000000"), Decimal("50000000"), Decimal("0.15"), Decimal("1260000")),
    (Decimal("50000000"), Decimal("88000000"), Decimal("0.24"), Decimal("5760000")),
    (Decimal("88000000"), Decimal("150000000"), Decimal("0.35"), Decimal("15440000")),
    (Decimal("150000000"), Decimal("300000000"), Decimal("0.38"), Decimal("19940000")),
    (Decimal("300000000"), Decimal("500000000"), Decimal("0.40"), Decimal("25940000")),
    (Decimal("500000000"), Decimal("1000000000"), Decimal("0.42"), Decimal("35940000")),
    (Decimal("1000000000"), None, Decimal("0.45"), Decimal("65940000")),
)


def calculate_income_tax(
    tax_base_krw: Money,
    *,
    tax_year: int = 2025,
) -> dict:
    """
    종합소득 과세표준을 기준으로 산출세액을 계산한다.

    Args:
        tax_base_krw (Money):
            종합소득 과세표준 금액(원).
            매출액이나 총수입이 아니라 공제 등을 반영한 뒤 확정된 과세표준을 입력한다.
            예: 50_000_000

        tax_year (int):
            귀속연도.
            현재 지원 범위는 2023, 2024, 2025.
            기본값은 2025.

    Returns:
        dict:
            적용 세율, 누진공제액, 종합소득 산출세액 등을 반환한다.
    """
    if tax_year not in (2023, 2024, 2025):
        raise TaxCalculationError(
            "현재 종합소득세 계산기는 2023~2025 귀속만 지원합니다."
        )

    base = _to_decimal(tax_base_krw, name="과세표준")

    for minimum, maximum, rate, deduction in INCOME_TAX_BRACKETS_2023_2025:
        if base >= minimum and (maximum is None or base <= maximum):
            tax = max(base * rate - deduction, Decimal("0"))

            return {
                "calculation_type": "income_tax",
                "tax_year": tax_year,
                "tax_base_krw": _money_string(base),
                "rate": str(rate),
                "rate_percent": str(rate * 100),
                "progressive_deduction_krw": _money_string(deduction),
                "calculated_income_tax_krw": _money_string(tax),
            }

    raise TaxCalculationError("과세표준 구간을 찾지 못했습니다.")


# ===========================================================================
# 2. 청년창업 / 창업중소기업 세액감면
# ===========================================================================

STARTUP_REDUCTION_RATES_2026: dict[str, dict[str, Decimal | None]] = {
    "startup_sme": {
        "capital_overconcentration": None,
        "capital_region_other": Decimal("0.25"),
        "outside_capital_region": Decimal("0.50"),
    },
    "youth_or_livelihood": {
        "capital_overconcentration": Decimal("0.50"),
        "capital_region_other": Decimal("0.75"),
        "outside_capital_region": Decimal("1.00"),
    },
}

STARTUP_ANNUAL_REDUCTION_CAP_KRW_2026 = Decimal("500000000")


def get_startup_reduction_rate(
    *,
    category: StartupCategory,
    region: StartupRegion,
) -> Decimal:
    """
    창업 유형과 지역을 기준으로 기본 세액감면율을 반환한다.

    Args:
        category (StartupCategory):
            창업 감면 유형.
            "startup_sme" = 일반 창업중소기업
            "youth_or_livelihood" = 청년창업 또는 생계형 창업

        region (StartupRegion):
            사업장 지역 구분.
            "capital_overconcentration" = 수도권 과밀억제권역
            "capital_region_other" = 수도권이지만 과밀억제권역 밖
            "outside_capital_region" = 수도권 밖

    Returns:
        Decimal:
            감면율.
            예: Decimal("0.50") = 50%
    """
    try:
        rate = STARTUP_REDUCTION_RATES_2026[category][region]
    except KeyError as exc:
        raise TaxCalculationError(
            f"지원하지 않는 감면 조건입니다: category={category}, region={region}"
        ) from exc

    if rate is None:
        raise TaxCalculationError(
            "현재 확보한 국세청 요약자료만으로 해당 조건의 감면율을 확정할 수 없습니다."
        )

    return rate


def calculate_startup_tax_reduction(
    eligible_tax_krw: Money,
    *,
    category: StartupCategory,
    region: StartupRegion,
    startup_year: int = 2026,
    annual_cap_krw: Money = STARTUP_ANNUAL_REDUCTION_CAP_KRW_2026,
) -> dict:
    """
    청년창업 또는 창업중소기업의 세액감면액을 계산한다.

    Args:
        eligible_tax_krw (Money):
            감면 적용 전 세액(원).
            매출액이나 소득금액이 아니라 감면 대상이 되는 세액을 입력한다.
            예: 3_000_000

        category (StartupCategory):
            창업 감면 유형.
            "startup_sme" = 일반 창업중소기업
            "youth_or_livelihood" = 청년창업 또는 생계형 창업

        region (StartupRegion):
            사업장 지역 구분.
            "capital_overconcentration" = 수도권 과밀억제권역
            "capital_region_other" = 수도권이지만 과밀억제권역 밖
            "outside_capital_region" = 수도권 밖

        startup_year (int):
            창업연도.
            현재 함수는 2026년 이후 창업 기준.
            기본값은 2026.

        annual_cap_krw (Money):
            연간 감면 한도(원).
            기본값은 500_000_000원.

    Returns:
        dict:
            감면율, 감면 전 세액, 감면액, 감면 후 세액 등을 반환한다.
    """
    if startup_year < 2026:
        raise TaxCalculationError(
            "현재 이 함수는 2026.1.1 이후 창업 기준 감면율을 사용합니다."
        )

    eligible_tax = _to_decimal(eligible_tax_krw, name="감면 대상 세액")
    cap = _to_decimal(annual_cap_krw, name="연간 감면 한도")

    rate = get_startup_reduction_rate(
        category=category,
        region=region,
    )

    raw_reduction = eligible_tax * rate
    reduction = min(raw_reduction, cap)
    tax_after_reduction = max(eligible_tax - reduction, Decimal("0"))

    return {
        "calculation_type": "startup_tax_reduction",
        "startup_year": startup_year,
        "category": category,
        "region": region,
        "eligible_tax_krw": _money_string(eligible_tax),
        "reduction_rate": str(rate),
        "reduction_rate_percent": str(rate * 100),
        "raw_reduction_krw": _money_string(raw_reduction),
        "annual_cap_krw": _money_string(cap),
        "reduction_amount_krw": _money_string(reduction),
        "tax_after_reduction_krw": _money_string(tax_after_reduction),
    }


# ===========================================================================
# 3. 일반과세자 부가가치세
# ===========================================================================

VAT_GENERAL_RATE = Decimal("0.10")


def calculate_general_vat(
    taxable_sales_supply_value_krw: Money,
    *,
    deductible_input_tax_krw: Money = 0,
    tax_credit_krw: Money = 0,
    prepaid_tax_krw: Money = 0,
    penalty_tax_krw: Money = 0,
) -> dict:
    """
    일반과세자의 기본 부가가치세를 계산한다.

    Args:
        taxable_sales_supply_value_krw (Money):
            부가가치세가 제외된 과세 공급가액(원).
            예: 10_000_000

        deductible_input_tax_krw (Money):
            공제 가능한 매입세액(원).
            값이 없으면 0.
            예: 400_000

        tax_credit_krw (Money):
            적용 가능한 세액공제 금액(원).
            값이 없으면 0.

        prepaid_tax_krw (Money):
            이미 납부한 세액(원).
            값이 없으면 0.

        penalty_tax_krw (Money):
            가산세 금액(원).
            값이 없으면 0.

    Returns:
        dict:
            매출세액, 공제가능 매입세액, 조정 전 세액,
            세액공제, 기납부세액, 가산세, 최종 계산세액을 반환한다.
    """
    sales = _to_decimal(
        taxable_sales_supply_value_krw,
        name="과세 공급가액",
    )
    input_tax = _to_decimal(
        deductible_input_tax_krw,
        name="공제가능 매입세액",
    )
    credit = _to_decimal(
        tax_credit_krw,
        name="세액공제",
    )
    prepaid = _to_decimal(
        prepaid_tax_krw,
        name="기납부세액",
    )
    penalty = _to_decimal(
        penalty_tax_krw,
        name="가산세",
    )

    output_tax = sales * VAT_GENERAL_RATE
    before_adjustments = output_tax - input_tax
    final_tax = before_adjustments - credit - prepaid + penalty

    return {
        "calculation_type": "general_vat",
        "taxable_sales_supply_value_krw": _money_string(sales),
        "vat_rate": str(VAT_GENERAL_RATE),
        "vat_rate_percent": "10",
        "output_tax_krw": _money_string(output_tax),
        "deductible_input_tax_krw": _money_string(input_tax),
        "tax_before_adjustments_krw": _money_string(before_adjustments),
        "tax_credit_krw": _money_string(credit),
        "prepaid_tax_krw": _money_string(prepaid),
        "penalty_tax_krw": _money_string(penalty),
        "final_tax_krw": _money_string(final_tax),
        "status": "payable" if final_tax > 0 else "refund_or_zero",
    }


# ===========================================================================
# 4. 간이과세자 부가가치세
# ===========================================================================

SIMPLIFIED_VAT_VALUE_ADDED_RATIOS: dict[str, Decimal] = {
    "retail_recycling_food": Decimal("0.15"),
    "manufacturing_agriculture_forestry_fishery_small_cargo": Decimal("0.20"),
    "lodging": Decimal("0.25"),
    "construction_transport_storage_information": Decimal("0.30"),
    "finance_professional_support_real_estate": Decimal("0.40"),
    "other_services": Decimal("0.30"),
}


def calculate_simplified_vat_output_tax(
    sales_amount_krw: Money,
    *,
    industry_group: SimplifiedVatIndustry,
) -> dict:
    """
    간이과세자의 기본 매출세액을 계산한다.

    Args:
        sales_amount_krw (Money):
            부가가치세를 포함한 공급대가(원).
            예: 20_000_000

        industry_group (SimplifiedVatIndustry):
            간이과세 업종 그룹.
            "retail_recycling_food"
                = 소매업·재생용 재료수집 및 판매업·음식점업

            "manufacturing_agriculture_forestry_fishery_small_cargo"
                = 제조업·농업·임업·어업·소화물 전문 운송업

            "lodging"
                = 숙박업

            "construction_transport_storage_information"
                = 건설업·운수 및 창고업·정보통신업

            "finance_professional_support_real_estate"
                = 금융·전문서비스·사업지원·부동산 관련 업종

            "other_services"
                = 그 밖의 서비스업

    Returns:
        dict:
            업종별 부가가치율과 기본 매출세액을 반환한다.
            최종 납부세액은 아니다.
    """
    sales = _to_decimal(
        sales_amount_krw,
        name="공급대가",
    )

    try:
        ratio = SIMPLIFIED_VAT_VALUE_ADDED_RATIOS[industry_group]
    except KeyError as exc:
        raise TaxCalculationError(
            "지원하지 않는 간이과세 업종 그룹입니다."
        ) from exc

    output_tax = sales * ratio * VAT_GENERAL_RATE

    return {
        "calculation_type": "simplified_vat_output_tax",
        "sales_amount_krw": _money_string(sales),
        "industry_group": industry_group,
        "industry_value_added_ratio": str(ratio),
        "industry_value_added_ratio_percent": str(ratio * 100),
        "vat_rate": str(VAT_GENERAL_RATE),
        "basic_output_tax_krw": _money_string(output_tax),
    }


# ===========================================================================
# 5. 근로소득 간이세액표
# ===========================================================================

# 아래 상수는 현재 국민연금 보험료 자체를 계산하기 위한 값이 아니라,
# 소득세법 시행령 [별표 2]의 근로소득 간이세액표 산출 결과를 재현하기 위한
# 간이세액표 내부 계산 기준값이다.
WITHHOLDING_PENSION_RATE = Decimal("0.045")
WITHHOLDING_PENSION_MONTHLY_MIN = Decimal("290000")
WITHHOLDING_PENSION_MONTHLY_MAX = Decimal("4490000")


def _floor_won(value: Decimal) -> Decimal:
    """
    금액의 원 미만을 절사한다.

    Args:
        value (Decimal): 절사할 금액.

    Returns:
        Decimal: 원 단위로 절사된 금액.
    """
    return value.quantize(Decimal("1"), rounding="ROUND_DOWN")


def _floor_10_won(value: Decimal) -> Decimal:
    """
    간이세액표 표시 기준에 맞게 10원 미만을 절사한다.

    Args:
        value (Decimal): 절사할 금액.

    Returns:
        Decimal: 10원 단위로 절사된 금액.
    """
    return (_floor_won(value) // Decimal("10")) * Decimal("10")


def _withholding_salary_midpoint(monthly_salary_krw: Decimal) -> Decimal:
    """
    간이세액표 산출에 사용하는 월급여 구간의 중간값을 계산한다.

    Args:
        monthly_salary_krw (Decimal): 비과세소득과 과세되는 학자금을 제외한 월급여액(원).

    Returns:
        Decimal:
            해당 월급여 구간의 중간값.
            월급여 1,000만원은 그대로 1,000만원을 사용한다.
    """
    salary = monthly_salary_krw

    if salary < Decimal("770000"):
        return salary

    if salary < Decimal("1500000"):
        start = Decimal("770000")
        step = Decimal("5000")
    elif salary < Decimal("3000000"):
        start = Decimal("1500000")
        step = Decimal("10000")
    elif salary < Decimal("10000000"):
        start = Decimal("3000000")
        step = Decimal("20000")
    else:
        return Decimal("10000000")

    lower = start + ((salary - start) // step) * step
    return lower + (step / Decimal("2"))


def _calculate_withholding_earned_income_deduction(
    annual_salary_krw: Decimal,
) -> Decimal:
    """
    간이세액표 산출용 근로소득공제를 계산한다.

    Args:
        annual_salary_krw (Decimal): 월급여 구간 중간값을 12개월로 환산한 연간 총급여액.

    Returns:
        Decimal: 근로소득공제액.
    """
    salary = annual_salary_krw

    if salary <= Decimal("5000000"):
        deduction = salary * Decimal("0.70")
    elif salary <= Decimal("15000000"):
        deduction = (
            Decimal("3500000")
            + (salary - Decimal("5000000")) * Decimal("0.40")
        )
    elif salary <= Decimal("45000000"):
        deduction = (
            Decimal("7500000")
            + (salary - Decimal("15000000")) * Decimal("0.15")
        )
    elif salary <= Decimal("100000000"):
        deduction = (
            Decimal("12000000")
            + (salary - Decimal("45000000")) * Decimal("0.05")
        )
    else:
        deduction = (
            Decimal("14750000")
            + (salary - Decimal("100000000")) * Decimal("0.02")
        )
        deduction = min(deduction, Decimal("20000000"))

    return _floor_won(deduction)


def _calculate_withholding_pension_deduction(
    salary_midpoint_krw: Decimal,
) -> Decimal:
    """
    간이세액표 산출에 반영되는 연금보험료공제를 계산한다.

    Args:
        salary_midpoint_krw (Decimal): 월급여 구간의 중간값(원).

    Returns:
        Decimal: 연간 연금보험료공제액.

    Notes:
        이 함수의 4.5%, 29만원, 449만원은 실제 2026년 국민연금 보험료를
        계산하기 위한 값이 아니라 [별표 2]의 표 값을 재현하기 위한 산출 기준이다.
    """
    standard_monthly_income = (
        _floor_won(salary_midpoint_krw / Decimal("1000"))
        * Decimal("1000")
    )
    standard_monthly_income = max(
        WITHHOLDING_PENSION_MONTHLY_MIN,
        min(standard_monthly_income, WITHHOLDING_PENSION_MONTHLY_MAX),
    )

    monthly_contribution = _floor_won(
        standard_monthly_income * WITHHOLDING_PENSION_RATE
    )
    return monthly_contribution * Decimal("12")


def _calculate_withholding_special_deduction(
    annual_salary_krw: Decimal,
    *,
    family_count: int,
) -> Decimal:
    """
    [별표 2]에 정의된 특별소득공제 및 특별세액공제 중 일부의 간이 산식을 계산한다.

    Args:
        annual_salary_krw (Decimal): 연간 총급여액(원).
        family_count (int): 공제대상가족 수. 본인과 배우자도 각각 1명으로 본다.

    Returns:
        Decimal: 간이세액표 산출에 반영할 특별소득공제 등 금액.
    """
    salary = annual_salary_krw

    if family_count == 1:
        base = Decimal("3100000")

        if salary <= Decimal("30000000"):
            deduction = base + salary * Decimal("0.04")
        elif salary <= Decimal("45000000"):
            deduction = (
                base
                + salary * Decimal("0.04")
                - (salary - Decimal("30000000")) * Decimal("0.05")
            )
        elif salary <= Decimal("70000000"):
            deduction = base + salary * Decimal("0.015")
        else:
            deduction = base + salary * Decimal("0.005")

    elif family_count == 2:
        base = Decimal("3600000")

        if salary <= Decimal("30000000"):
            deduction = base + salary * Decimal("0.04")
        elif salary <= Decimal("45000000"):
            deduction = (
                base
                + salary * Decimal("0.04")
                - (salary - Decimal("30000000")) * Decimal("0.05")
            )
        elif salary <= Decimal("70000000"):
            deduction = base + salary * Decimal("0.02")
        else:
            deduction = base + salary * Decimal("0.01")

    else:
        base = Decimal("5000000")

        if salary <= Decimal("30000000"):
            deduction = base + salary * Decimal("0.07")
        elif salary <= Decimal("45000000"):
            deduction = (
                base
                + salary * Decimal("0.07")
                - (salary - Decimal("30000000")) * Decimal("0.05")
            )
        elif salary <= Decimal("70000000"):
            deduction = base + salary * Decimal("0.05")
        else:
            deduction = base + salary * Decimal("0.03")

        if salary > Decimal("40000000"):
            deduction += (
                salary - Decimal("40000000")
            ) * Decimal("0.04")

    return _floor_won(deduction)


def _calculate_withholding_base_tax(
    taxable_income_krw: Decimal,
) -> Decimal:
    """
    간이세액표 산출용 과세표준에 기본세율을 적용한다.

    Args:
        taxable_income_krw (Decimal): 간이세액표 산출용 과세표준(원).

    Returns:
        Decimal: 산출세액.
    """
    base = max(taxable_income_krw, Decimal("0"))

    if base <= Decimal("14000000"):
        tax = base * Decimal("0.06")
    elif base <= Decimal("50000000"):
        tax = (
            Decimal("840000")
            + (base - Decimal("14000000")) * Decimal("0.15")
        )
    elif base <= Decimal("88000000"):
        tax = (
            Decimal("6240000")
            + (base - Decimal("50000000")) * Decimal("0.24")
        )
    elif base <= Decimal("150000000"):
        tax = (
            Decimal("15360000")
            + (base - Decimal("88000000")) * Decimal("0.35")
        )
    elif base <= Decimal("300000000"):
        tax = (
            Decimal("37060000")
            + (base - Decimal("150000000")) * Decimal("0.38")
        )
    elif base <= Decimal("500000000"):
        tax = (
            Decimal("94060000")
            + (base - Decimal("300000000")) * Decimal("0.40")
        )
    elif base <= Decimal("1000000000"):
        tax = (
            Decimal("174060000")
            + (base - Decimal("500000000")) * Decimal("0.42")
        )
    else:
        tax = (
            Decimal("384060000")
            + (base - Decimal("1000000000")) * Decimal("0.45")
        )

    return _floor_won(tax)


def _calculate_withholding_earned_income_tax_credit(
    calculated_tax_krw: Decimal,
    *,
    annual_salary_krw: Decimal,
) -> Decimal:
    """
    근로소득 간이세액표의 산출 기준에 맞춰 근로소득세액공제를 계산한다.

    Args:
        calculated_tax_krw (Decimal): 기본세율을 적용한 산출세액(원).
        annual_salary_krw (Decimal): 연간 총급여액(원).

    Returns:
        Decimal: 간이세액표 산출에 반영할 근로소득세액공제액.

    Notes:
        현재 연말정산용 근로소득세액공제 공식을 그대로 적용하는 함수가 아니라,
        [별표 2]의 공식 세액표 결과를 재현하는 간이세액표 산출 기준을 구현한다.
    """
    tax = calculated_tax_krw
    salary = annual_salary_krw

    if tax <= Decimal("500000"):
        credit = tax * Decimal("0.55")
    else:
        credit = (
            Decimal("275000")
            + (tax - Decimal("500000")) * Decimal("0.30")
        )

    if salary <= Decimal("55000000"):
        limit = Decimal("660000")
    elif salary <= Decimal("70000000"):
        limit = max(
            Decimal("660000")
            - (salary - Decimal("55000000")) * Decimal("0.5"),
            Decimal("630000"),
        )
    else:
        limit = max(
            Decimal("630000")
            - (salary - Decimal("70000000")) * Decimal("0.5"),
            Decimal("500000"),
        )

    return _floor_won(min(credit, limit))


def _calculate_withholding_up_to_10m(
    monthly_salary_krw: Decimal,
    *,
    family_count: int,
) -> dict:
    """
    월급여 1,000만원 이하 구간의 간이세액을 표 조회 없이 산식으로 계산한다.

    Args:
        monthly_salary_krw (Decimal): 비과세소득과 과세되는 학자금을 제외한 월급여액(원).
        family_count (int): 1명 이상 11명 이하의 공제대상가족 수.

    Returns:
        dict: 계산 중간값과 자녀 공제 전 월 간이세액.
    """
    midpoint = _withholding_salary_midpoint(monthly_salary_krw)
    annual_salary = _floor_won(midpoint * Decimal("12"))

    earned_income_deduction = _calculate_withholding_earned_income_deduction(
        annual_salary
    )
    earned_income_amount = max(
        annual_salary - earned_income_deduction,
        Decimal("0"),
    )
    basic_deduction = Decimal("1500000") * Decimal(family_count)
    pension_deduction = _calculate_withholding_pension_deduction(midpoint)
    special_deduction = _calculate_withholding_special_deduction(
        annual_salary,
        family_count=family_count,
    )

    taxable_income = max(
        earned_income_amount
        - basic_deduction
        - pension_deduction
        - special_deduction,
        Decimal("0"),
    )
    calculated_tax = _calculate_withholding_base_tax(taxable_income)
    earned_income_tax_credit = _calculate_withholding_earned_income_tax_credit(
        calculated_tax,
        annual_salary_krw=annual_salary,
    )
    annual_determined_tax = max(
        calculated_tax - earned_income_tax_credit,
        Decimal("0"),
    )
    monthly_tax = _floor_10_won(
        annual_determined_tax / Decimal("12")
    )

    return {
        "salary_midpoint_krw": midpoint,
        "annual_salary_krw": annual_salary,
        "earned_income_deduction_krw": earned_income_deduction,
        "earned_income_amount_krw": earned_income_amount,
        "basic_deduction_krw": basic_deduction,
        "pension_deduction_krw": pension_deduction,
        "special_deduction_krw": special_deduction,
        "taxable_income_krw": taxable_income,
        "calculated_tax_krw": calculated_tax,
        "earned_income_tax_credit_krw": earned_income_tax_credit,
        "annual_determined_tax_krw": annual_determined_tax,
        "monthly_tax_before_child_adjustment_krw": monthly_tax,
    }


def _calculate_withholding_base_for_family(
    monthly_salary_krw: Decimal,
    *,
    family_count: int,
) -> tuple[Decimal, dict]:
    """
    가족 수별 자녀 공제 전 간이세액을 계산한다.

    Args:
        monthly_salary_krw (Decimal): 비과세소득과 과세되는 학자금을 제외한 월급여액(원).
        family_count (int): 공제대상가족 수.

    Returns:
        tuple[Decimal, dict]: 자녀 공제 전 월 간이세액과 계산 상세.
    """
    if family_count <= 11:
        detail = _calculate_withholding_up_to_10m(
            monthly_salary_krw,
            family_count=family_count,
        )
        return detail["monthly_tax_before_child_adjustment_krw"], detail

    tax_10, _ = _calculate_withholding_base_for_family(
        monthly_salary_krw,
        family_count=10,
    )
    tax_11, detail_11 = _calculate_withholding_base_for_family(
        monthly_salary_krw,
        family_count=11,
    )
    extra_family_count = family_count - 11
    adjusted_tax = max(
        tax_11 - (tax_10 - tax_11) * Decimal(extra_family_count),
        Decimal("0"),
    )
    detail_11 = dict(detail_11)
    detail_11["monthly_tax_before_child_adjustment_krw"] = adjusted_tax
    detail_11["family_count_over_11"] = extra_family_count
    return adjusted_tax, detail_11


def _calculate_withholding_over_10m(
    monthly_salary_krw: Decimal,
    *,
    family_count: int,
) -> tuple[Decimal, dict]:
    """
    월급여 1,000만원 초과 구간의 [별표 2] 직접 산식을 적용한다.

    Args:
        monthly_salary_krw (Decimal): 비과세소득과 과세되는 학자금을 제외한 월급여액(원).
        family_count (int): 공제대상가족 수.

    Returns:
        tuple[Decimal, dict]: 자녀 공제 전 월 간이세액과 적용 산식 정보.
    """
    base_tax_10m, _ = _calculate_withholding_base_for_family(
        Decimal("10000000"),
        family_count=family_count,
    )
    salary = monthly_salary_krw

    if salary <= Decimal("14000000"):
        additional_tax = (
            (salary - Decimal("10000000"))
            * Decimal("0.98")
            * Decimal("0.35")
            + Decimal("25000")
        )
        formula_band = "10m_to_14m"
    elif salary <= Decimal("28000000"):
        additional_tax = (
            Decimal("1397000")
            + (salary - Decimal("14000000"))
            * Decimal("0.98")
            * Decimal("0.38")
        )
        formula_band = "14m_to_28m"
    elif salary <= Decimal("30000000"):
        additional_tax = (
            Decimal("6610600")
            + (salary - Decimal("28000000"))
            * Decimal("0.98")
            * Decimal("0.40")
        )
        formula_band = "28m_to_30m"
    elif salary <= Decimal("45000000"):
        additional_tax = (
            Decimal("7394600")
            + (salary - Decimal("30000000")) * Decimal("0.40")
        )
        formula_band = "30m_to_45m"
    elif salary <= Decimal("87000000"):
        additional_tax = (
            Decimal("13394600")
            + (salary - Decimal("45000000")) * Decimal("0.42")
        )
        formula_band = "45m_to_87m"
    else:
        additional_tax = (
            Decimal("31034600")
            + (salary - Decimal("87000000")) * Decimal("0.45")
        )
        formula_band = "over_87m"

    monthly_tax = _floor_10_won(base_tax_10m + additional_tax)

    return monthly_tax, {
        "base_tax_at_10m_krw": base_tax_10m,
        "additional_tax_krw": _floor_won(additional_tax),
        "formula_band": formula_band,
        "monthly_tax_before_child_adjustment_krw": monthly_tax,
    }


def _calculate_withholding_child_adjustment(
    child_count: int | None,
) -> Decimal:
    """
    8세 이상 20세 이하 자녀 수에 따른 월 간이세액 공제액을 계산한다.

    Args:
        child_count (int | None): 8세 이상 20세 이하 공제대상 자녀 수.

    Returns:
        Decimal: 월 간이세액에서 차감할 금액.
    """
    if child_count is None or child_count == 0:
        return Decimal("0")

    if child_count == 1:
        return Decimal("20830")

    if child_count == 2:
        return Decimal("45830")

    return (
        Decimal("45830")
        + Decimal(child_count - 2) * Decimal("33330")
    )


def calculate_withholding_tax(
    monthly_salary_krw: Money,
    *,
    family_count: int,
    child_count: int | None = None,
) -> dict:
    """
    2026.2.27. 개정 [별표 2]의 산출 구조를 이용해 근로소득 간이세액을 계산한다.

    외부 CSV, DB 또는 간이세액표 행 데이터가 필요하지 않다.
    월급여 1,000만원 이하는 표를 만드는 산출 과정을 Python으로 재현하고,
    1,000만원 초과는 [별표 2]에 직접 제시된 초과급여 산식을 적용한다.

    Args:
        monthly_salary_krw (Money):
            비과세소득과 과세되는 학자금을 제외한 월급여액(원).
            예: 3_200_000

        family_count (int):
            공제대상가족 수.
            본인과 배우자도 각각 1명으로 보며 1 이상의 정수를 입력한다.
            예: 1, 2, 3

        child_count (int | None):
            공제대상가족 중 8세 이상 20세 이하 자녀 수.
            값이 없거나 해당 자녀가 없으면 None 또는 0.
            예: 0, 1, 2, 3

    Returns:
        dict:
            월급여, 가족 수, 자녀 수, 적용 계산 방식,
            간이세액 산출 중간값 및 최종 원천징수 소득세액을 반환한다.
    """
    salary = _to_decimal(
        monthly_salary_krw,
        name="월 급여",
    )

    if family_count < 1:
        raise TaxCalculationError(
            "공제대상 가족 수는 1 이상이어야 합니다."
        )

    if child_count is not None and child_count < 0:
        raise TaxCalculationError(
            "8세 이상 20세 이하 자녀 수는 0 이상이어야 합니다."
        )

    if salary <= Decimal("10000000"):
        base_tax, detail = _calculate_withholding_base_for_family(
            salary,
            family_count=family_count,
        )
        calculation_method = "formula_reproduction"
    else:
        base_tax, detail = _calculate_withholding_over_10m(
            salary,
            family_count=family_count,
        )
        calculation_method = "over_10m_statutory_formula"

    child_adjustment = _calculate_withholding_child_adjustment(child_count)
    final_tax = max(base_tax - child_adjustment, Decimal("0"))

    result = {
        "calculation_type": "withholding_tax",
        "tax_table_version": "2026-02-27",
        "calculation_method": calculation_method,
        "monthly_salary_krw": _money_string(salary),
        "family_count": family_count,
        "child_count_8_to_20": child_count,
        "tax_before_child_adjustment_krw": _money_string(base_tax),
        "child_adjustment_krw": _money_string(child_adjustment),
        "withholding_income_tax_krw": _money_string(final_tax),
    }

    for key, value in detail.items():
        if isinstance(value, Decimal):
            result[key] = _money_string(value)
        else:
            result[key] = value

    return result


# ===========================================================================
# 6. LangGraph용 Dispatcher
# ===========================================================================

def calculate_tax(
    calculation_type: CalculationType,
    **kwargs,
) -> dict:
    """
    calculation_type에 따라 적절한 세금 계산 함수를 호출한다.

    Args:
        calculation_type (CalculationType):
            실행할 계산기 종류.

            "income_tax"
                = 종합소득세 산출세액 계산

            "startup_tax_reduction"
                = 청년창업/창업중소기업 세액감면 계산

            "general_vat"
                = 일반과세자 부가가치세 계산

            "simplified_vat_output_tax"
                = 간이과세자 기본 매출세액 계산

            "withholding_tax"
                = 근로소득 간이세액 산식 계산

        **kwargs:
            선택된 계산기 함수에 전달할 파라미터.

            예:
            calculation_type="income_tax"이면

            tax_base_krw=50_000_000
            tax_year=2025

    Returns:
        dict:
            선택된 계산기의 계산 결과.
    """
    calculators = {
        "income_tax": calculate_income_tax,
        "startup_tax_reduction": calculate_startup_tax_reduction,
        "general_vat": calculate_general_vat,
        "simplified_vat_output_tax": calculate_simplified_vat_output_tax,
        "withholding_tax": calculate_withholding_tax,
    }

    try:
        calculator = calculators[calculation_type]
    except KeyError as exc:
        raise TaxCalculationError(
            f"지원하지 않는 calculation_type입니다: {calculation_type}"
        ) from exc

    return calculator(**kwargs)
