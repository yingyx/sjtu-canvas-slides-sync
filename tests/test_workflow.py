import unittest
from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "sync.yml"


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = WORKFLOW.read_text(encoding="utf-8")

    def test_manual_and_scheduled_timeouts_are_configured(self):
        self.assertIn("github.event_name == 'workflow_dispatch' && 360 || 60", self.content)

    def test_concurrency_cache_tests_and_summary_credentials_are_configured(self):
        for expected in (
            "concurrency:",
            "cancel-in-progress: false",
            "actions/cache@v4",
            "python -m unittest discover -s tests -v",
            "JAAuthCookie: ${{ secrets.JAAuthCookie }}",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, self.content)


if __name__ == "__main__":
    unittest.main()
