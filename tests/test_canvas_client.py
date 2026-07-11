import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import canvas_client


class CanvasClientTests(unittest.TestCase):
    def test_fetch_paginated_follows_next_link(self):
        first = Mock()
        first.json.return_value = [{"id": 1}]
        first.links = {"next": {"url": "https://canvas.test/page/2"}}
        second = Mock()
        second.json.return_value = [{"id": 2}]
        second.links = {}

        with patch("canvas_client.request", side_effect=[first, second]) as request_mock:
            result = canvas_client.fetch_paginated(
                "https://canvas.test/items", {"Authorization": "Bearer token"}, {"per_page": 100}
            )

        self.assertEqual(result, [{"id": 1}, {"id": 2}])
        self.assertEqual(request_mock.call_count, 2)
        self.assertIsNone(request_mock.call_args_list[1].kwargs["params"])

    def test_add_folder_paths_keeps_nested_unicode_path(self):
        files = [{"id": 7, "filename": "讲义.pdf", "folder_id": 11}]
        folders = [{"id": 11, "full_name": "course files/课件/第一章"}]

        result = canvas_client.add_folder_paths(files, folders)

        self.assertEqual(result[0]["folder_path"], "课件/第一章")

    def test_add_folder_paths_rejects_unknown_folder(self):
        with self.assertRaises(ValueError):
            canvas_client.add_folder_paths([{"folder_id": 99}], [])

    @patch("canvas_client.fetch_folders")
    @patch("canvas_client.fetch_module_files")
    @patch("canvas_client.fetch_files")
    def test_collect_course_files_falls_back_to_modules(
        self, fetch_files, fetch_module_files, fetch_folders
    ):
        fetch_files.side_effect = canvas_client.requests.RequestException("forbidden")
        fetch_module_files.return_value = [{"folder_id": 3, "filename": "slides.pdf"}]
        fetch_folders.return_value = [{"id": 3, "full_name": "course files/week 1"}]

        result = canvas_client.collect_course_files("https://canvas.test", {}, "42")

        self.assertEqual(result[0]["folder_path"], "week 1")


if __name__ == "__main__":
    unittest.main()
