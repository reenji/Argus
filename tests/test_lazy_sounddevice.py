import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIO_MODULES = ("main", "actions.tts_engine", "actions.screen_processor", "api.server")


class LazySoundDeviceTests(unittest.TestCase):
    def test_importing_audio_modules_does_not_start_portaudio(self):
        # A fresh interpreter: other tests may already have loaded sounddevice.
        script = (
            "import importlib, sys\n"
            f"for name in {AUDIO_MODULES!r}:\n"
            "    importlib.import_module(name)\n"
            "print('sounddevice' in sys.modules)\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", script], cwd=ROOT, capture_output=True, text=True, timeout=120,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip().splitlines()[-1], "False")


if __name__ == "__main__":
    unittest.main()
