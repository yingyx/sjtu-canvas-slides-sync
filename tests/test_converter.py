import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import converter


class ConverterTests(unittest.TestCase):
    @patch("converter.subprocess.run")
    def test_conversion_timeout_becomes_runtime_error(self, run_mock):
        run_mock.side_effect = subprocess.TimeoutExpired("soffice", converter.CONVERSION_TIMEOUT)
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "slides.pptx"
            source.write_bytes(b"ppt")
            with self.assertRaisesRegex(RuntimeError, "超过"):
                converter.convert_to_pdf(source, Path(temp_dir))


if __name__ == "__main__":
    unittest.main()
