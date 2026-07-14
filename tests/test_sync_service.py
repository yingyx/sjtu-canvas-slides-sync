import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from config import AppConfig
from sync_service import SyncResult, remote_path, safe_path_parts, sync_course


def make_config() -> AppConfig:
    return AppConfig(
        canvas_base_url="https://canvas.test",
        canvas_token="token",
        smh_base_url="https://drive.test",
        smh_user_token="token",
        smh_jaauth_cookie="",
        save_root="Canvas Files",
        convert_ppt=False,
        max_file_size_mb=1024,
        file_extensions={".pdf"},
        convert_extensions={".ppt", ".pptx"},
    )


class SyncServiceTests(unittest.TestCase):
    def test_remote_path_removes_traversal_and_control_characters(self):
        self.assertEqual(
            remote_path("Canvas Files", "..", "课程", "课件\\第一章", "bad\x00.pdf"),
            "Canvas Files/课程/课件/第一章/bad.pdf",
        )

    def test_safe_path_parts_sanitizes_untrusted_filename(self):
        self.assertEqual(safe_path_parts("../bad\x00/name.pdf"), ["bad", "name.pdf"])
        self.assertEqual(safe_path_parts("../.."), [])

    def test_sync_result_merge(self):
        total = SyncResult(updated_count=1, downloaded_bytes=10)
        total.merge(SyncResult(failed_count=2, downloaded_bytes=5))
        self.assertEqual(total.updated_count, 1)
        self.assertEqual(total.failed_count, 2)
        self.assertEqual(total.downloaded_bytes, 15)

    @patch("sync_service.upload_file")
    @patch("sync_service.request")
    @patch("sync_service.list_remote_dir", return_value=[])
    @patch("sync_service.collect_course_files")
    def test_downloads_in_chunks_and_counts_success(
        self, collect_files, _list_remote, request_mock, upload_mock
    ):
        collect_files.return_value = [{
            "filename": "讲义.pdf",
            "folder_path": "",
            "size": 6,
            "updated_at": "2026-01-01T00:00:00Z",
            "url": "https://canvas.test/file",
        }]
        response = Mock()
        response.iter_content.return_value = [b"abc", b"def"]
        request_mock.return_value = response

        result = sync_course(make_config(), {}, {}, {
            "course_id": "1", "semester": "2025-2026-2", "folder": "课程"
        })

        self.assertEqual(result.updated_count, 1)
        self.assertEqual(result.downloaded_bytes, 6)
        self.assertEqual(result.uploaded_bytes, 6)
        upload_mock.assert_called_once()

    @patch("sync_service.upload_file")
    @patch("sync_service.request")
    @patch("sync_service.list_remote_dir", return_value=[])
    @patch("sync_service.collect_course_files")
    def test_decodes_canvas_filename_before_upload(
        self, collect_files, _list_remote, request_mock, upload_mock
    ):
        collect_files.return_value = [{
            "filename": "%E4%B8%AD%E6%96%87%E8%AE%B2%E4%B9%89.pdf",
            "folder_path": "",
            "size": 3,
            "updated_at": "2026-01-01T00:00:00Z",
            "url": "https://canvas.test/file",
        }]
        response = Mock()
        response.iter_content.return_value = [b"pdf"]
        request_mock.return_value = response

        result = sync_course(make_config(), {}, {}, {
            "course_id": "1", "semester": "2025-2026-2", "folder": "课程"
        })

        self.assertEqual(result.updated_count, 1)
        self.assertTrue(upload_mock.call_args.args[3].endswith("/中文讲义.pdf"))

    @patch("sync_service.upload_file", side_effect=ValueError("missing confirm key"))
    @patch("sync_service.request")
    @patch("sync_service.list_remote_dir", return_value=[])
    @patch("sync_service.collect_course_files")
    def test_upload_failure_is_not_counted_as_update(
        self, collect_files, _list_remote, request_mock, _upload_mock
    ):
        collect_files.return_value = [{
            "filename": "slides.pdf",
            "folder_path": "",
            "size": 3,
            "updated_at": "2026-01-01T00:00:00Z",
            "url": "https://canvas.test/file",
        }]
        response = Mock()
        response.iter_content.return_value = [b"pdf"]
        request_mock.return_value = response

        result = sync_course(make_config(), {}, {}, {
            "course_id": "1", "semester": "2025-2026-2", "folder": "课程"
        })

        self.assertEqual(result.updated_count, 0)
        self.assertEqual(result.uploaded_bytes, 0)
        self.assertEqual(result.failed_count, 1)


if __name__ == "__main__":
    unittest.main()
