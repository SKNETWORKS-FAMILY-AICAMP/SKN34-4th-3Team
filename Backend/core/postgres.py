"""Postgres + pgvector 연결 상태 확인. 원천 테이블을 비우지 않는다."""

from __future__ import annotations

from core.db import masked_database_url, postgres_connect


def postgres_status() -> dict:
    conn = postgres_connect()
    if conn is None:
        return {"reachable": False, "pgvector": False, "url": masked_database_url()}
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.execute("SELECT extname FROM pg_extension WHERE extname = 'vector'")
            has_vector = cur.fetchone() is not None
            cur.execute("SELECT to_regclass('public.users')")
            users_reg = cur.fetchone()
            has_users = bool(users_reg and next(iter(users_reg.values())))
            chunk_count = 0
            user_count = 0
            if has_users:
                cur.execute("SELECT COUNT(*) FROM users")
                user_count = int(next(iter(cur.fetchone().values())))
            if has_vector:
                cur.execute("SELECT to_regclass('public.rag_documents')")
                rag_reg = cur.fetchone()
                if rag_reg and next(iter(rag_reg.values())):
                    cur.execute("SELECT COUNT(*) FROM rag_documents")
                    chunk_count = int(next(iter(cur.fetchone().values())))
        return {
            "reachable": True,
            "pgvector": bool(has_vector),
            "url": masked_database_url(),
            "ragChunks": chunk_count,
            "users": user_count,
        }
    except Exception:
        return {"reachable": False, "pgvector": False, "url": masked_database_url()}
    finally:
        conn.close()
