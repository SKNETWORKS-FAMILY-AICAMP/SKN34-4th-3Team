"""Re-evaluate only the 63 policy cases or 62 tax turns from holdout250.

Uses the same HTTP adapters and scorers as src.evaluation.run_evaluation.
Guardrail and roadmap cases are not sent to the API.
"""

import argparse
import asyncio
from pathlib import Path

from src.evaluation.evaluator import evaluate_cases
from src.evaluation.graph_evaluator import evaluate_scenarios
from src.evaluation.run_evaluation import (
    DEFAULT_DATASET,
    HttpChatClient,
    HttpLangGraphClient,
    database_user_context,
    load_evaluation_cases,
    validate_holdout_database,
    validate_users,
)


class PolicyProgressClient:
    def __init__(self, client: HttpLangGraphClient, total: int) -> None:
        self.client = client
        self.total = total
        self.completed = 0

    async def recommend(self, *, user_id: int, question: str, top_k: int):
        result = await self.client.recommend(
            user_id=user_id, question=question, top_k=top_k
        )
        self.completed += 1
        print(f"policy {self.completed}/{self.total}", flush=True)
        return result


class TaxProgressClient:
    def __init__(self, client: HttpChatClient, total: int) -> None:
        self.client = client
        self.total = total
        self.completed = 0

    async def answer(
        self, *, user_id: int, category: str, question: str,
        history: list[dict[str, str]], roadmap_step: str | None,
    ):
        result = await self.client.answer(
            user_id=user_id, category=category, question=question,
            history=history, roadmap_step=roadmap_step,
        )
        self.completed += 1
        print(f"tax {self.completed}/{self.total}", flush=True)
        return result


async def run(mode: str, base_url: str, output: Path) -> None:
    if output.exists():
        raise SystemExit(f"Output already exists: {output}")
    validate_holdout_database()
    if mode == "policy":
        cases = [
            case for case in load_evaluation_cases(
                DEFAULT_DATASET, mode="policy", suite="holdout250"
            )
            if case.relevant_policy_ids and not case.should_block
        ]
        if len(cases) != 63:
            raise SystemExit(f"Expected 63 policy cases, got {len(cases)}")
        validate_users({case.user_id for case in cases}, "db")
        async with HttpLangGraphClient(base_url) as client:
            report = await evaluate_cases(
                cases, PolicyProgressClient(client, len(cases)), k=5
            )
    else:
        scenarios = [
            scenario for scenario in load_evaluation_cases(
                DEFAULT_DATASET, mode="graph", suite="holdout250"
            )
            if scenario.category == "tax"
        ]
        turns = sum(len(scenario.turns) for scenario in scenarios)
        if len(scenarios) != 31 or turns != 62:
            raise SystemExit(
                f"Expected 31 tax scenarios and 62 turns, got {len(scenarios)}, {turns}"
            )
        validate_users({scenario.user_id for scenario in scenarios}, "db")
        async with HttpChatClient(
            base_url, user_context_provider=database_user_context
        ) as client:
            report = await evaluate_scenarios(
                scenarios, TaxProgressClient(client, turns)
            )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    print(f"Saved: {output}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("policy", "tax"), required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8002")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(run(args.mode, args.base_url, args.output))


if __name__ == "__main__":
    main()
