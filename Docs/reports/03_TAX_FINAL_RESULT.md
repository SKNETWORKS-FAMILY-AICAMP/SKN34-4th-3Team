# 세금 RAG HALF 실평가 결과 — 2026-09-13 21:15

평가 범위: holdout250 세금 **31개 시나리오·62턴**

| 통과 결과 | 시나리오 전체 통과 | 평균 응답 시간 |
| ---: | ---: | ---: |
| 48/62 (77.4%) | 21/31 (67.7%) | 17.69초 |

평가 ID: `holdout-tax-income-year`, `holdout-tax-income-bracket`, `holdout-tax-general-vat-prepaid`, `holdout-tax-general-vat-adjustments`, `holdout-tax-simple-vat-food`, `holdout-tax-simple-vat-transport`, `holdout-tax-withholding-family`, `holdout-tax-withholding-children`, `holdout-tax-startup-seoul`, `holdout-tax-startup-jeonnam`, `holdout-tax-business-transfer`, `holdout-tax-common-input-tax`, `holdout-tax-bookkeeping-penalty`, `holdout-tax-business-expense`, `holdout-tax-invoice-issue`, `holdout-tax-bad-debt-credit`, `holdout-tax-withholding-deadline`, `holdout-tax-corporate-expense`, `holdout-tax-startup-reduction-law`, `holdout-tax-missing-year`, `holdout-tax-sales-vs-base`, `holdout-tax-missing-family`, `holdout-tax-missing-industry`, `holdout-tax-missing-region`, `holdout-tax-missing-input-tax`, `holdout-tax-future-2026`, `holdout-tax-old-2022`, `holdout-tax-future-2027`, `holdout-tax-movie`, `holdout-tax-translation`, `holdout-tax-route-game`

## 실패 턴

- `holdout-tax-startup-seoul` 1턴: status
- `holdout-tax-startup-seoul` 2턴: status
- `holdout-tax-startup-jeonnam` 1턴: status
- `holdout-tax-startup-jeonnam` 2턴: status
- `holdout-tax-business-expense` 1턴: status, grounded
- `holdout-tax-business-expense` 2턴: status, grounded
- `holdout-tax-bad-debt-credit` 2턴: status, grounded
- `holdout-tax-corporate-expense` 1턴: status, grounded
- `holdout-tax-startup-reduction-law` 1턴: status, grounded
- `holdout-tax-startup-reduction-law` 2턴: status, grounded
- `holdout-tax-sales-vs-base` 1턴: status
- `holdout-tax-missing-family` 1턴: status
- `holdout-tax-missing-region` 2턴: status
- `holdout-tax-missing-input-tax` 1턴: status

원시 결과: [세금 JSON](../../LLM/evaluation/results/tax_20260913_205653.json)
