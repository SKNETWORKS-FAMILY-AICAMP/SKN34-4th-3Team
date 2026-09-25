"""창업 로드맵 체크 서버 저장 계약."""

import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from ninja.testing import TestClient  # noqa: E402

from api import deps  # noqa: E402
from config.api import api  # noqa: E402
from core.security import create_token  # noqa: E402
from services import user_service  # noqa: E402


client = TestClient(api)


def _headers(user_id: int = 1) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(user_id, 'user')}"}


def _active_user_repo(user_id: int = 1) -> MagicMock:
    repo = MagicMock()
    repo.get_user.return_value = {"id": user_id, "status": "active"}
    return repo


class RoadmapProgressRouteTest(unittest.TestCase):
    def test_requires_login(self):
        self.assertEqual(client.get("/users/me/roadmap-progress").status_code, 401)
        response = client.put("/users/me/roadmap-progress", json={"taskKey": "A:0", "done": True})
        self.assertEqual(response.status_code, 401)

    def test_get_returns_done_keys_of_current_version(self):
        repo = MagicMock()
        repo.list_roadmap_done.return_value = ["A:0", "B:2"]
        with patch.object(deps, "repo", _active_user_repo()), patch.object(user_service, "repo", repo):
            response = client.get("/users/me/roadmap-progress", headers=_headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"version": user_service.ROADMAP_VERSION, "done": ["A:0", "B:2"]})
        repo.list_roadmap_done.assert_called_once_with(1, user_service.ROADMAP_VERSION)

    def test_put_check_and_uncheck_delegate_to_repo(self):
        repo = MagicMock()
        with patch.object(deps, "repo", _active_user_repo()), patch.object(user_service, "repo", repo):
            on = client.put("/users/me/roadmap-progress", json={"taskKey": "C:3", "done": True}, headers=_headers())
            off = client.put("/users/me/roadmap-progress", json={"taskKey": "C:3", "done": False}, headers=_headers())
        self.assertEqual(on.status_code, 200)
        self.assertEqual(off.status_code, 200)
        self.assertEqual(
            [c.args for c in repo.set_roadmap_task.call_args_list],
            [(1, user_service.ROADMAP_VERSION, "C:3", True), (1, user_service.ROADMAP_VERSION, "C:3", False)],
        )

    def test_invalid_task_key_is_422(self):
        repo = MagicMock()
        with patch.object(deps, "repo", _active_user_repo()), patch.object(user_service, "repo", repo):
            for key in ("a:0", "A0", "AB:1", "A:x", ""):
                response = client.put(
                    "/users/me/roadmap-progress", json={"taskKey": key, "done": True}, headers=_headers()
                )
                self.assertEqual(response.status_code, 422, key)
        repo.set_roadmap_task.assert_not_called()

    def test_uses_token_user_id(self):
        repo = MagicMock()
        repo.list_roadmap_done.return_value = []
        with patch.object(deps, "repo", _active_user_repo(7)), patch.object(user_service, "repo", repo):
            client.get("/users/me/roadmap-progress", headers=_headers(7))
            client.put("/users/me/roadmap-progress", json={"taskKey": "A:1", "done": True}, headers=_headers(7))
        repo.list_roadmap_done.assert_called_once_with(7, user_service.ROADMAP_VERSION)
        self.assertEqual(repo.set_roadmap_task.call_args.args[0], 7)


if __name__ == "__main__":
    unittest.main()
