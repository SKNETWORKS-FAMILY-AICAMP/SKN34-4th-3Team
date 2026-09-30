"""구독 플랜 조회·목업 결제 계약."""

import os
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from ninja.testing import TestClient  # noqa: E402

from api import deps  # noqa: E402
from config.api import api  # noqa: E402
from core.security import create_token  # noqa: E402
from services import subscription_service  # noqa: E402


client = TestClient(api)


def _headers(user_id: int = 1) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(user_id, 'user')}"}


def _active_user_repo(user_id: int = 1) -> MagicMock:
    repo = MagicMock()
    repo.get_user.return_value = {"id": user_id, "status": "active"}
    return repo


def _service_repo(subscription=None, policy_chats=0, tax_chats=0) -> MagicMock:
    repo = MagicMock()
    repo.get_subscription.return_value = subscription
    repo.count_chats_this_month.side_effect = lambda user_id, categories: (
        policy_chats if categories == ["policy"] else tax_chats
    )
    return repo


class SubscriptionRouteTest(unittest.TestCase):
    def test_requires_login(self):
        self.assertEqual(client.get("/users/me/subscription").status_code, 401)
        self.assertEqual(client.put("/users/me/subscription", json={"plan": "basic"}).status_code, 401)

    def test_no_row_is_free_plan_with_usage(self):
        repo = _service_repo(policy_chats=2, tax_chats=5)
        with patch.object(deps, "repo", _active_user_repo()), patch.object(subscription_service, "repo", repo):
            response = client.get("/users/me/subscription", headers=_headers())
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["current"]["plan"], "free")
        self.assertIsNone(body["current"]["renewsAt"])
        self.assertEqual(body["usage"], {"policyChat": 2, "policyChatLimit": 3, "taxChat": 5})
        self.assertEqual([p["key"] for p in body["plans"]], ["free", "basic", "pro"])
        self.assertEqual([p["price"] for p in body["plans"]], [0, 9900, 29000])

    def test_pro_plan_has_unlimited_policy_chat(self):
        row = {"plan": "pro", "started_at": datetime(2026, 9, 1), "renews_at": datetime(2026, 10, 1)}
        with patch.object(deps, "repo", _active_user_repo()), \
                patch.object(subscription_service, "repo", _service_repo(row, policy_chats=40)):
            body = client.get("/users/me/subscription", headers=_headers()).json()
        self.assertEqual(body["current"]["plan"], "pro")
        self.assertIsNone(body["usage"]["policyChatLimit"])

    def test_paid_plan_renews_next_month(self):
        repo = _service_repo()
        with patch.object(deps, "repo", _active_user_repo(7)), patch.object(subscription_service, "repo", repo):
            response = client.put("/users/me/subscription", json={"plan": "basic"}, headers=_headers(7))
        self.assertEqual(response.status_code, 200)
        user_id, plan, renews_at = repo.upsert_subscription.call_args.args
        self.assertEqual((user_id, plan), (7, "basic"))
        self.assertGreater(renews_at, datetime.now())

    def test_free_plan_cancels_renewal(self):
        repo = _service_repo()
        with patch.object(deps, "repo", _active_user_repo()), patch.object(subscription_service, "repo", repo):
            client.put("/users/me/subscription", json={"plan": "free"}, headers=_headers())
        repo.upsert_subscription.assert_called_once_with(1, "free", None)

    def test_invalid_plan_is_422(self):
        repo = _service_repo()
        with patch.object(deps, "repo", _active_user_repo()), patch.object(subscription_service, "repo", repo):
            response = client.put("/users/me/subscription", json={"plan": "enterprise"}, headers=_headers())
        self.assertEqual(response.status_code, 422)
        repo.upsert_subscription.assert_not_called()

    def test_next_month_clamps_day(self):
        self.assertEqual(
            subscription_service._next_month(datetime(2026, 1, 31, 10, 0)), datetime(2026, 2, 28, 10, 0)
        )
        self.assertEqual(
            subscription_service._next_month(datetime(2026, 12, 15)), datetime(2027, 1, 15)
        )


if __name__ == "__main__":
    unittest.main()
