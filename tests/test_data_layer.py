"""Hosted persistence: memory dates, concurrent upserts and dev database upgrades."""

import threading
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from sqlalchemy import create_engine, delete, inspect, select, text, update

from api import repositories
from api.database import SessionLocal, init_db
from api.models import AnswerCacheEntry, MemoryEntry, User, UserConfig, UserSecret
from api.secret_service import get_user_secret, set_user_secret
from core.tenant import tenant_scope
from memory import memory_manager


def _run_together(*jobs):
    """Run jobs in parallel threads and re-raise the first failure."""
    errors = []

    def wrap(job):
        try:
            job()
        except Exception as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=wrap, args=(job,)) for job in jobs]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    if errors:
        raise errors[0]


class DataLayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.user_id = str(uuid.uuid4())
        with SessionLocal.begin() as db:
            db.add(User(
                id=self.user_id,
                email=f"data-{uuid.uuid4().hex}@example.com",
                display_name="Data",
                password_hash="scrypt$unused",
            ))

    def tearDown(self):
        with SessionLocal.begin() as db:
            for model in (AnswerCacheEntry, MemoryEntry, UserConfig, UserSecret):
                db.execute(delete(model).where(model.user_id == self.user_id))
            db.execute(delete(User).where(User.id == self.user_id))

    def _memory_rows(self):
        with SessionLocal() as db:
            return {
                (row.category, row.key): row
                for row in db.scalars(select(MemoryEntry).where(MemoryEntry.user_id == self.user_id))
            }

    def test_saving_one_memory_keeps_the_dates_of_the_others(self):
        with tenant_scope(self.user_id):
            memory_manager.update_memory({"notes": {"a": {"value": "first"}}})
        old = datetime(2020, 1, 1, tzinfo=timezone.utc)
        with SessionLocal.begin() as db:
            db.execute(update(MemoryEntry).where(MemoryEntry.user_id == self.user_id).values(updated_at=old))
        with tenant_scope(self.user_id):
            memory_manager.update_memory({"notes": {"b": {"value": "second"}}})
            memory_manager.forget("missing")
        rows = self._memory_rows()
        self.assertEqual(rows[("notes", "a")].updated_at.replace(tzinfo=timezone.utc), old)
        self.assertIn(("notes", "b"), rows)

    def test_concurrent_memory_updates_keep_both_keys(self):
        barrier = threading.Barrier(2, timeout=10)
        real_load = repositories.load_user_memory

        def load_then_wait(user_id):
            loaded = real_load(user_id)
            barrier.wait()  # both writers have read the same snapshot
            return loaded

        def remember(key):
            with tenant_scope(self.user_id):
                memory_manager.update_memory({"notes": {key: {"value": key}}})

        with patch.object(repositories, "load_user_memory", side_effect=load_then_wait):
            _run_together(lambda: remember("left"), lambda: remember("right"))
        self.assertTrue({("notes", "left"), ("notes", "right")} <= set(self._memory_rows()))

    def test_memory_entries_fit_the_columns(self):
        with tenant_scope(self.user_id):
            memory_manager.update_memory({
                "c" * 200: {"k": {"value": "unknown category"}},
                "notes": {"x" * 300: {"value": "long key"}, "topic": {"nested": {"value": "kept"}}},
            })
        keys = set(self._memory_rows())
        self.assertIn(("notes", "k"), keys)
        self.assertIn(("notes", "x" * 120), keys)
        self.assertIn(("notes", "topic / nested"), keys)
        self.assertTrue(all(len(category) <= 64 and len(key) <= 120 for category, key in keys))

    def test_concurrent_upserts_do_not_collide(self):
        def save_secret(value):
            with SessionLocal() as db:
                set_user_secret(db, self.user_id, "gemini_api_key", value)

        for _ in range(5):
            _run_together(
                lambda: save_secret("A" * 40),
                lambda: save_secret("B" * 40),
                lambda: repositories.save_user_config(self.user_id, {"voice": "puck"}),
                lambda: repositories.save_user_config(self.user_id, {"voice": "kore"}),
                lambda: repositories.put_cached(self.user_id, "q", "Q?", "one"),
                lambda: repositories.put_cached(self.user_id, "q", "Q?", "two"),
            )
        with SessionLocal() as db:
            self.assertIn(get_user_secret(db, self.user_id, "gemini_api_key"), {"A" * 40, "B" * 40})
        self.assertIn(repositories.load_user_config(self.user_id)["voice"], {"puck", "kore"})

    def test_cache_hits_are_counted_in_utc(self):
        repositories.put_cached(self.user_id, "q", "Q?", "answer")
        _run_together(*[lambda: repositories.get_cached(self.user_id, "q") for _ in range(6)])
        with SessionLocal() as db:
            row = db.scalar(select(AnswerCacheEntry).where(AnswerCacheEntry.user_id == self.user_id))
        self.assertEqual(row.hits, 6)
        updated = row.updated_at.replace(tzinfo=row.updated_at.tzinfo or timezone.utc)
        self.assertLess(abs(updated - datetime.now(timezone.utc)), timedelta(minutes=1))


class DevDatabaseUpgradeTests(unittest.TestCase):
    def test_a_database_made_by_create_all_is_brought_to_the_latest_schema(self):
        from alembic import command

        from api.database import alembic_config, migrate_database

        with TemporaryDirectory() as folder:
            url = f"sqlite:///{Path(folder) / 'legacy.db'}"
            # The old dev path: tables from the first migration, no alembic_version.
            command.upgrade(alembic_config(url), "20260813_0001")
            engine = create_engine(url)
            with engine.begin() as connection:
                connection.execute(text("DROP TABLE alembic_version"))

            migrate_database(url)

            inspector = inspect(engine)
            self.assertIn("session_version", {c["name"] for c in inspector.get_columns("users")})
            self.assertTrue(inspector.has_table("alembic_version"))
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
