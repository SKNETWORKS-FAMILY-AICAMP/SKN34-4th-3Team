import pytest

from src.serving.tax_calculators_docstring import (
    TaxCalculationError,
    calculate_tax,
)


def test_calculate_tax_dispatches_income_tax() -> None:
    result = calculate_tax(
        "income_tax",
        tax_base_krw=50_000_000,
        tax_year=2025,
    )

    assert result["calculated_income_tax_krw"] == "6240000.00"
    assert result["tax_year"] == 2025


def test_income_tax_rejects_unsupported_year() -> None:
    with pytest.raises(TaxCalculationError, match="2023~2025"):
        calculate_tax(
            "income_tax",
            tax_base_krw=50_000_000,
            tax_year=2026,
        )


def test_calculate_tax_dispatches_general_vat() -> None:
    result = calculate_tax(
        "general_vat",
        taxable_sales_supply_value_krw=10_000_000,
    )

    assert result["output_tax_krw"] == "1000000.00"
    assert result["final_tax_krw"] == "1000000.00"


def test_calculate_tax_dispatches_formula_based_withholding() -> None:
    result = calculate_tax(
        "withholding_tax",
        monthly_salary_krw=3_200_000,
        family_count=1,
        child_count=0,
    )

    assert result["withholding_income_tax_krw"] == "91460.00"
    assert result["calculation_method"] == "formula_reproduction"
    assert result["tax_table_version"] == "2026-02-27"
