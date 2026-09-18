"""Saved tax trace에서 필요한 조문의 검색 단계별 도달 여부를 집계한다.

Targets are manually chosen from each failed turn's question and missing_information.
This is a title-level diagnostic, not a check of article text or legal validity.
"""

import json
import re
from collections import Counter
from pathlib import Path


TRACE = Path(__file__).parent / "results" / "tax_legal14_stage_probe_after_general_law_0913.json"
TARGETS = {
    ("holdout-tax-business-transfer", 1): ("부가가치세법", "10"),
    ("holdout-tax-business-expense", 1): ("소득세법", "27"),
    ("holdout-tax-business-expense", 2): ("소득세법", "27"),
    ("holdout-tax-invoice-issue", 1): ("부가가치세법", "34"),
    ("holdout-tax-invoice-issue", 2): ("부가가치세법", "60"),
    ("holdout-tax-withholding-deadline", 1): ("소득세법", "128"),
    ("holdout-tax-withholding-deadline", 2): ("소득세법", "164"),
    ("holdout-tax-corporate-expense", 1): ("법인세법 시행령", "45"),
    ("holdout-tax-corporate-expense", 2): ("법인세법", "25"),
    ("holdout-tax-startup-reduction-law", 1): ("조세특례제한법", "6"),
    ("holdout-tax-startup-reduction-law", 2): ("조세특례제한법", "6"),
}
STAGES = ("dense", "bm25", "rrf", "rerank")


def title_matches(title: str, law: str, article: str) -> bool:
    return bool(re.match(rf"^{re.escape(law)}\s+제\s*{article}조(?!\d)", title))


def main() -> None:
    turns = json.loads(TRACE.read_text(encoding="utf-8"))["turns"]
    counts: Counter[str] = Counter()
    print("target | first hop | any hop | final reason")
    for turn in turns:
        key = (turn["scenario_id"], turn["turn"])
        if key not in TARGETS:
            continue
        law, article = TARGETS[key]
        hops = turn["retrieval_trace"]
        first = []
        any_hop = []
        for stage in STAGES:
            found_first = any(
                title_matches(doc["title"], law, article)
                for doc in hops[0][stage]
            )
            found_any = any(
                title_matches(doc["title"], law, article)
                for hop in hops for doc in hop[stage]
            )
            if found_first:
                first.append(stage)
                counts[f"first_{stage}"] += 1
            if found_any:
                any_hop.append(stage)
                counts[f"any_{stage}"] += 1
        print(f"{key} {law} 제{article}조 | {','.join(first) or '-'} | "
              f"{','.join(any_hop) or '-'} | {turn['actual']['termination_reason']}")
    print(f"Total annotated failed turns: {len(TARGETS)}")
    for stage in STAGES:
        print(f"{stage}: first={counts[f'first_{stage}']}, "
              f"any={counts[f'any_{stage}']}")


if __name__ == "__main__":
    main()
