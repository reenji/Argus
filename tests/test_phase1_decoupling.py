import asyncio
import subprocess
import sys
import unittest
from types import SimpleNamespace

from core.argus_client import ArgusClient
import main


class StubClient:
    def __init__(self):
        self.on_text_command = None
        self.muted = False
        self.current_file = None
        self._voice_combo = None
        self.events = []

    def write_log(self, text):
        self.events.append(("log", text))

    def set_state(self, state):
        self.events.append(("state", state))

    def show_subtitle(self, text):
        self.events.append(("subtitle", text))

    def clear_subtitle(self):
        self.events.append(("subtitle", None))

    def set_theme(self, theme_key):
        self.events.append(("theme", theme_key))

    def set_graphics_quality(self, quality):
        self.events.append(("graphics", quality))

    def sync_voice_display(self, voice_name):
        self.events.append(("voice", voice_name))

    def handle_ui_command(self, action):
        self.events.append(("ui", action))


class PhaseOneDecouplingTests(unittest.TestCase):
    def test_desktop_adapter_exposes_the_engine_contract(self):
        from ui import ArgusUI

        required_members = {
            "on_text_command",
            "muted",
            "current_file",
            "_voice_combo",
            "write_log",
            "set_state",
            "show_subtitle",
            "clear_subtitle",
            "set_theme",
            "set_graphics_quality",
            "sync_voice_display",
            "handle_ui_command",
        }

        self.assertFalse(required_members - set(dir(ArgusUI)))

    def test_client_protocol_and_text_callback_are_wired(self):
        client = StubClient()
        self.assertIsInstance(client, ArgusClient)

        argus = main.ArgusLive(client)

        self.assertIs(argus.client, client)
        self.assertIs(argus.ui, client)
        self.assertEqual(client.on_text_command, argus._on_text_command)

    def test_desktop_mode_keeps_the_complete_tool_inventory(self):
        client = StubClient()
        argus = main.ArgusLive(client)

        self.assertFalse(argus.cloud_safe)
        self.assertEqual(argus.tool_declarations, main.TOOL_DECLARATIONS)

    def test_cloud_safe_mode_loads_only_the_hosted_allowlist(self):
        client = StubClient()
        argus = main.ArgusLive(client, cloud_safe=True)
        names = {item["name"] for item in argus.tool_declarations}

        self.assertEqual(names, main.CLOUD_SAFE_ACTIONS)
        self.assertTrue(names.isdisjoint(main.LOCAL_MACHINE_ONLY_ACTIONS))

    def test_cloud_safe_mode_rejects_unadvertised_local_tool_calls(self):
        client = StubClient()
        argus = main.ArgusLive(client, cloud_safe=True)
        call = SimpleNamespace(id="local-call", name="open_app", args={})

        response = asyncio.run(argus._execute_tool(call))

        self.assertIn("unavailable in cloud-safe mode", response.response["result"])
        self.assertEqual(client.events, [])



class AudioImportTests(unittest.TestCase):
    def test_importing_the_engine_does_not_load_sounddevice(self):
        result = subprocess.run(
            [sys.executable, "-c", "import sys, main; print('sounddevice' in sys.modules)"],
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        self.assertEqual(result.stdout.strip().splitlines()[-1], "False")


if __name__ == "__main__":
    unittest.main()
