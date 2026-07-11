import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import main
from config import AppConfig
from sync_service import SyncResult


CONFIG = AppConfig(
    canvas_base_url="https://canvas.test",
    canvas_token="canvas-token",
    smh_base_url="https://drive.test",
    smh_user_token="smh-token",
    smh_jaauth_cookie="",
    save_root="Canvas Files",
    convert_ppt=False,
    max_file_size_mb=1,
    file_extensions={".pdf"},
    convert_extensions=set(),
)


class MainExitCodeTests(unittest.TestCase):
    def run_main_with_result(self, result: SyncResult) -> int:
        course = {"course_id": "1", "semester": "2025-2026-2", "folder": "课程"}
        with (
            patch.object(sys, "argv", ["main.py"]),
            patch("main.load_config", return_value=CONFIG),
            patch("main.get_space_info", return_value={}),
            patch("main.fetch_courses", return_value=[{}]),
            patch("main.parse_course", return_value=course),
            patch("main.sync_course", return_value=result),
            patch.dict("os.environ", {}, clear=False),
        ):
            with self.assertRaises(SystemExit) as raised:
                main.main()
        return raised.exception.code

    def test_exit_codes_distinguish_update_no_change_and_failure(self):
        self.assertEqual(self.run_main_with_result(SyncResult(updated_count=1)), 0)
        self.assertEqual(self.run_main_with_result(SyncResult()), 1)
        self.assertEqual(self.run_main_with_result(SyncResult(failed_count=1)), 2)


if __name__ == "__main__":
    unittest.main()
