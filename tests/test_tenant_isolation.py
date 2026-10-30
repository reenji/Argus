"""In the hosted process no user's work may touch shared files or another user's state."""

import os
import unittest
from unittest.mock import patch

from core import tenant
from core.tenant import tenant_scope


class HostedModeTests(unittest.TestCase):
    def setUp(self):
        tenant.enable_hosted_mode()
        self.addCleanup(tenant.disable_hosted_mode)

    def test_stores_refuse_shared_files_without_a_tenant(self):
        from core.secret_store import get_secret_store
        from memory import answer_cache, config_manager, memory_manager, task_history

        with patch.dict(os.environ, {"GEMINI_API_KEY": "operator-key"}):
            for name, call in (
                ("memory", memory_manager.load_memory),
                ("memory save", lambda: memory_manager.save_memory({"notes": {}})),
                ("gemini key", config_manager.get_gemini_key),
                ("api keys", config_manager.load_api_keys),
                ("answer cache", lambda: answer_cache.get_cached_answer("What is polymorphism?")),
                ("task history", task_history.get_history),
                ("secret store", get_secret_store),
            ):
                with self.subTest(name), self.assertRaises(tenant.MissingTenantError):
                    call()

    def test_the_desktop_app_keeps_its_local_files(self):
        from memory import memory_manager

        tenant.disable_hosted_mode()
        self.assertIsInstance(memory_manager.load_memory(), dict)

    def test_the_api_runs_in_hosted_mode_while_serving(self):
        from fastapi.testclient import TestClient

        from api.server import app

        tenant.disable_hosted_mode()
        with TestClient(app):
            self.assertTrue(tenant.hosted_mode_enabled())
        self.assertFalse(tenant.hosted_mode_enabled())


class TaskQueueIsolationTests(unittest.TestCase):
    def _queue(self):
        from agent.task_queue import TaskQueue

        return TaskQueue(max_concurrent=2)  # not started: tasks stay pending

    def _job(self, queue, user):
        with tenant_scope(user):
            return queue.submit_job("job", runner=lambda **_kwargs: "done")

    def test_users_only_see_and_cancel_their_own_tasks(self):
        queue = self._queue()
        mine = self._job(queue, "alice")
        theirs = self._job(queue, "bob")
        with tenant_scope("alice"):
            self.assertIsNotNone(queue.get_status(mine))
            self.assertIsNone(queue.get_status(theirs))
            self.assertFalse(queue.cancel(theirs))
            self.assertEqual([item["task_id"] for item in queue.get_all_statuses()], [mine])
        self.assertEqual(queue.get_status(theirs)["status"], "pending")

    def test_each_user_has_a_task_limit(self):
        from agent.task_queue import MAX_TASKS_PER_USER, TaskLimitError

        queue = self._queue()
        for _ in range(MAX_TASKS_PER_USER):
            self._job(queue, "alice")
        with self.assertRaises(TaskLimitError):
            self._job(queue, "alice")
        self._job(queue, "bob")

    def test_a_waiting_user_is_served_before_a_busy_one(self):
        from agent.task_queue import TaskStatus

        queue = self._queue()
        first = self._job(queue, "alice")
        self._job(queue, "alice")
        bobs = self._job(queue, "bob")
        queue._tasks[first].status = TaskStatus.RUNNING
        queue._queue.remove(queue._tasks[first])
        queue._active_count = 1
        self.assertEqual(queue._next_task().task_id, bobs)


class PresentationCooldownTests(unittest.TestCase):
    def test_a_quota_cooldown_only_affects_its_own_user(self):
        from actions import presentation_maker

        with tenant_scope("alice"):
            presentation_maker._mark_presentation_quota_cooldown()
            self.assertTrue(presentation_maker._presentation_quota_cooldown_active())
        with tenant_scope("bob"):
            self.assertFalse(presentation_maker._presentation_quota_cooldown_active())

    def test_an_image_quota_cooldown_only_affects_its_own_user(self):
        from actions.presentations import assets

        with tenant_scope("alice"):
            assets._mark_image_quota_cooldown()
            self.assertTrue(assets._image_quota_cooldown_active())
        with tenant_scope("bob"):
            self.assertFalse(assets._image_quota_cooldown_active())


if __name__ == "__main__":
    unittest.main()
