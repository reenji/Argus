"""Hosted (cloud-safe) tools must not reach the server's files, network or desktop."""

import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import main
from core.tenant import tenant_scope


def _cloud_engine():
    argus = main.ArgusLive.__new__(main.ArgusLive)
    argus.cloud_safe = True
    argus.ui = SimpleNamespace(set_state=lambda _state: None, muted=False, current_file="/etc/hosts")
    argus.speak = lambda _text: True
    return argus


def _run_tool(argus, name, args):
    call = SimpleNamespace(id="call", name=name, args=args)
    return asyncio.run(argus._execute_tool(call))


class CloudToolPolicyTests(unittest.TestCase):
    def test_desktop_bound_tools_are_not_offered_in_the_cloud(self):
        names = {item["name"] for item in main.get_tool_declarations(cloud_safe=True)}
        self.assertEqual(names, {"web_search", "deep_research", "code_generator", "create_presentation"})
        for name in ("email_control", "flight_finder", "youtube_video"):
            response = _run_tool(_cloud_engine(), name, {})
            self.assertIn("unavailable in cloud-safe mode", response.response["result"])

    def test_cloud_declarations_hide_path_and_url_parameters(self):
        declarations = {item["name"]: item for item in main.get_tool_declarations(cloud_safe=True)}
        for name, blocked in main.CLOUD_BLOCKED_ARGUMENTS.items():
            properties = declarations[name]["parameters"]["properties"]
            self.assertFalse(blocked & set(properties), name)
        # Desktop declarations keep every parameter.
        desktop = {item["name"]: item for item in main.get_tool_declarations()}
        self.assertIn("source_urls", desktop["create_presentation"]["parameters"]["properties"])

    def test_presentation_arguments_are_sanitized_before_running(self):
        seen = {}

        def fake_request(*, parameters, **_kwargs):
            seen.update(parameters)
            return "queued"

        with patch.object(main, "request_presentation", side_effect=fake_request):
            _run_tool(_cloud_engine(), "create_presentation", {
                "topic": "Quarterly results",
                "source_urls": ["http://169.254.169.254/latest/meta-data/"],
                "source_file": "/app/api/config.py",
                "source_files": ["../../etc/passwd"],
                "template_file": "/root/template.pptx",
                "model_source_file": "/root/model.glb",
                "output_path": "/app/README.md",
                "open_after_create": True,
                "execution_mode": "visible",
            })
        self.assertEqual(seen.get("topic"), "Quarterly results")
        self.assertFalse(main.CLOUD_BLOCKED_ARGUMENTS["create_presentation"] & set(seen))
        self.assertEqual(seen.get("execution_mode"), "background")

    def test_research_cannot_write_files_or_open_a_browser(self):
        seen = {}

        def fake_request(*, parameters, **_kwargs):
            seen.update(parameters)
            return "queued"

        with patch.object(main, "request_deep_research", side_effect=fake_request):
            _run_tool(_cloud_engine(), "deep_research", {
                "question": "battery chemistry",
                "output_path": "/tmp/x.md",
                "execution_mode": "visible",
            })
            self.assertNotIn("output_path", seen)
            self.assertEqual(seen.get("execution_mode"), "background")

            seen.clear()
            response = _run_tool(_cloud_engine(), "deep_research", {"result_action": "save_desktop"})
        self.assertEqual(seen, {})
        self.assertIn("read it aloud", response.response["result"])


class TenantKeyTests(unittest.TestCase):
    def test_tools_never_fall_back_to_the_operator_key_for_a_tenant(self):
        from actions import deep_research, web_search

        with patch.dict(os.environ, {"GEMINI_API_KEY": "operator-key-should-not-be-used"}):
            with patch("memory.config_manager.load_api_keys", return_value={}):
                with tenant_scope("tenant-without-key"):
                    with self.assertRaises(Exception):
                        web_search._get_api_key()
                    with self.assertRaises(Exception):
                        deep_research._api_key()


if __name__ == "__main__":
    unittest.main()
