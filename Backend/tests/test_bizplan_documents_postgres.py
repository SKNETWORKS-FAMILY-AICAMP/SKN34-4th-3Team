"""실제 PostgreSQL 검증. BIZPLAN_DOCUMENT_DB_TESTS=1로 실행, 전용 스키마만 사용한다."""

import os
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import MagicMock, patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from ninja.errors import HttpError  # noqa: E402
from ninja.testing import TestClient  # noqa: E402
from psycopg import sql  # noqa: E402
from psycopg.errors import StringDataRightTruncation  # noqa: E402

from api import deps  # noqa: E402
from config.api import api  # noqa: E402
from core import db, repo  # noqa: E402
from core.security import create_token  # noqa: E402
from services import bizplan_service  # noqa: E402
from test_bizplan_documents import BODY, RAW, RENDERED  # noqa: E402


@unittest.skipUnless(os.getenv("BIZPLAN_DOCUMENT_DB_TESTS") == "1", "PostgreSQL 검증은 명시적으로 활성화")
class BizplanDocumentPostgresTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.connect = staticmethod(db.postgres_connect)
        cls.schema = "bizplan_documents_test_" + uuid.uuid4().hex
        conn = cls.connect()
        if conn is None:
            raise RuntimeError("실제 PostgreSQL에 연결할 수 없습니다.")
        try:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(cls.schema)))
            conn.commit()
            cls.addClassCleanup(cls.drop_schema)
            conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(cls.schema)))
            conn.execute("CREATE TABLE users (id SERIAL PRIMARY KEY)")
            conn.execute(
                "CREATE TABLE bizplan_drafts ("
                "user_id INT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,"
                "data JSONB NOT NULL DEFAULT '{}'::jsonb, updated_at TIMESTAMP DEFAULT now())"
            )
            extras = (Path(__file__).resolve().parents[2] / "DB" / "app_extras.sql").read_text(encoding="utf-8")
            document_ddl = "CREATE TABLE IF NOT EXISTS bizplan_documents" + extras.split(
                "CREATE TABLE IF NOT EXISTS bizplan_documents", 1
            )[1]
            # 저장 기능의 실제 DDL을 두 번 적용해 재실행 안전성도 검증한다.
            conn.execute(document_ddl)
            conn.execute(document_ddl)
            conn.commit()
            index = conn.execute(
                "SELECT indexname FROM pg_indexes WHERE schemaname = %s AND indexname = %s",
                (cls.schema, "idx_bizplan_documents_user"),
            ).fetchone()
            if index is None:
                raise AssertionError("서류 목록 인덱스가 생성되지 않았습니다.")
        finally:
            conn.close()

    @classmethod
    def drop_schema(cls):
        with cls.connect() as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(cls.schema)))

    @classmethod
    def isolated_connection(cls):
        conn = cls.connect()
        if conn is None:
            raise RuntimeError("PostgreSQL 테스트 연결 실패")
        conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(cls.schema)))
        # repo가 SET TRANSACTION을 수행하기 전에 설정용 트랜잭션을 끝낸다.
        conn.commit()
        return conn

    def setUp(self):
        patcher = patch.object(db, "postgres_connect", self.isolated_connection)
        patcher.start()
        self.addCleanup(patcher.stop)
        with db.connection() as conn:
            conn.execute("DELETE FROM users")
            conn.execute("INSERT INTO users (id) VALUES (1), (2)")

    def test_actual_round_trip_ownership_order_and_cascade(self):
        client = TestClient(api)
        auth_repo = MagicMock()
        auth_repo.get_user.side_effect = lambda user_id: {"id": user_id, "status": "active"}
        headers = {"Authorization": f"Bearer {create_token(1, 'user')}"}
        other_headers = {"Authorization": f"Bearer {create_token(2, 'user')}"}
        with patch.object(deps, "repo", auth_repo), patch.object(bizplan_service, "render", return_value=RENDERED):
            first = client.post("/bizplan/documents", json=BODY, headers=headers)
            second = client.post("/bizplan/documents", json=BODY, headers=headers)
            self.assertEqual((first.status_code, second.status_code), (200, 200))
            first_id, second_id = first.json()["id"], second.json()["id"]
            listed = client.get("/bizplan/documents", headers=headers).json()["documents"]
            self.assertEqual([item["id"] for item in listed], [second_id, first_id])
            self.assertNotIn("file_data", listed[0])
            self.assertEqual(client.get("/bizplan/documents", headers=other_headers).json(), {"draft": None, "documents": []})
            self.assertEqual(client.get(f"/bizplan/documents/{first_id}/file", headers=other_headers).status_code, 404)
            self.assertEqual(client.delete(f"/bizplan/documents/{first_id}", headers=other_headers).status_code, 404)
            downloaded = client.get(f"/bizplan/documents/{first_id}/file", headers=headers)
            self.assertEqual(downloaded.status_code, 200)
            self.assertEqual(downloaded.content, RAW)
            self.assertIn("filename*=utf-8''", downloaded["Content-Disposition"])
            self.assertEqual(client.delete(f"/bizplan/documents/{first_id}", headers=headers).json(), {"deleted": True})
            self.assertEqual(client.get(f"/bizplan/documents/{first_id}/file", headers=headers).status_code, 404)
            self.assertEqual(client.delete(f"/bizplan/documents/{first_id}", headers=headers).status_code, 404)
        with db.connection() as conn:
            conn.execute("DELETE FROM users WHERE id = 1")
        self.assertEqual(repo.count_bizplan_documents(1), 0)
        self.assertEqual(db.scalar("SELECT COUNT(*) FROM bizplan_document_files"), 0)

    def test_pair_downloads_ownership_and_delete_are_atomic(self):
        hwpx = b"PK-hwpx-original"
        additional = [{
            "format": "hwpx", "file_name": "한글.hwpx", "mime_type": "application/hwp+zip",
            "file_data": hwpx, "size_bytes": len(hwpx),
        }]
        row = repo.insert_bizplan_document(
            1, BODY["title"], RENDERED["fileName"], "pdf", "application/pdf", RAW, 8,
            additional_files=additional,
        )
        self.assertEqual(repo.count_bizplan_documents(1), 1)
        item = bizplan_service.list_documents(1)["documents"][0]
        self.assertEqual([file["format"] for file in item["files"]], ["hwpx", "pdf"])
        self.assertEqual(bizplan_service.get_document_file(1, row["id"], "pdf")[0], RAW)
        self.assertEqual(bizplan_service.get_document_file(1, row["id"], "hwpx")[0], hwpx)
        self.assertIsNone(repo.get_bizplan_document(2, row["id"], "hwpx"))
        self.assertIsNone(repo.get_bizplan_document(1, row["id"], "txt"))
        self.assertTrue(repo.delete_bizplan_document(1, row["id"]))
        self.assertEqual(db.scalar("SELECT COUNT(*) FROM bizplan_document_files"), 0)
        with self.assertRaises(StringDataRightTruncation):
            repo.insert_bizplan_document(
                1, BODY["title"], RENDERED["fileName"], "pdf", "application/pdf", RAW, 8,
                additional_files=[{**additional[0], "file_name": "x" * 256}],
            )
        self.assertEqual(repo.count_bizplan_documents(1), 0)
        self.assertEqual(db.scalar("SELECT COUNT(*) FROM bizplan_document_files"), 0)

    def test_draft_save_updates_one_summary_and_restores_full_content(self):
        client = TestClient(api)
        auth_repo = MagicMock()
        auth_repo.get_user.side_effect = lambda user_id: {"id": user_id, "status": "active"}
        headers = {"Authorization": f"Bearer {create_token(1, 'user')}"}
        other_headers = {"Authorization": f"Bearer {create_token(2, 'user')}"}
        with patch.object(deps, "repo", auth_repo):
            for title in ("첫 초안", "수정한 초안"):
                data = {"form": {"businessName": title}, "templateInfo": {"contentBase64": "YQ=="}}
                saved = client.put("/bizplan/draft", json={"data": data}, headers=headers)
                self.assertEqual(saved.status_code, 200)
                listed = client.get("/bizplan/documents", headers=headers).json()
                self.assertEqual(listed["documents"], [])
                self.assertEqual(listed["draft"]["title"], title)
                self.assertEqual(set(listed["draft"]), {"title", "updatedAt"})
                restored = client.get("/bizplan/draft", headers=headers).json()
                self.assertEqual(restored["data"], data)
            self.assertEqual(client.get("/bizplan/documents", headers=other_headers).json(), {"draft": None, "documents": []})
        self.assertEqual(db.scalar("SELECT COUNT(*) FROM bizplan_drafts WHERE user_id = ?", (1,)), 1)
        self.assertEqual(repo.count_bizplan_documents(1), 0)

    def test_two_concurrent_saves_at_seven_keep_the_limit(self):
        for _ in range(7):
            self.assertIsNotNone(repo.insert_bizplan_document(
                1, BODY["title"], RENDERED["fileName"], "pdf", "application/pdf", RAW, 8,
            ))
        barrier = Barrier(2)

        def render_after_both_prechecks(body):
            barrier.wait(timeout=10)
            return RENDERED

        def save():
            try:
                bizplan_service.save_document(1, BODY)
                return 200
            except HttpError as error:
                return error.status_code

        with patch.object(bizplan_service, "render", side_effect=render_after_both_prechecks), ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(save), pool.submit(save)]
            statuses = [future.result(timeout=15) for future in futures]
        self.assertEqual(sorted(statuses), [200, 409])
        self.assertEqual(repo.count_bizplan_documents(1), 8)

    def test_failed_insert_rolls_back_and_releases_user_lock(self):
        with self.assertRaises(StringDataRightTruncation):
            repo.insert_bizplan_document(1, "x" * 201, "plan.pdf", "pdf", "application/pdf", RAW, 8)
        self.assertEqual(repo.count_bizplan_documents(1), 0)
        self.assertIsNotNone(repo.insert_bizplan_document(
            1, BODY["title"], RENDERED["fileName"], "pdf", "application/pdf", RAW, 8,
        ))


if __name__ == "__main__":
    unittest.main()
