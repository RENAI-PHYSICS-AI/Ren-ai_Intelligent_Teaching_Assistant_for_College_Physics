from __future__ import annotations

import base64
import sys
import unittest
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from storage import image_data_url


class ImageDataUrlTests(unittest.TestCase):
    def test_png_bytes_are_embedded_instead_of_using_media_path(self):
        raw = b"\x89PNG\r\n\x1a\n" + b"test-png"
        source = image_data_url({"data": raw, "mime": "image/png"})

        self.assertTrue(source.startswith("data:image/png;base64,"))
        self.assertNotIn("/media/", source)
        self.assertEqual(base64.b64decode(source.split(",", 1)[1]), raw)

    def test_signature_overrides_incorrect_declared_mime(self):
        source = image_data_url({
            "data": b"\xff\xd8\xff" + b"test-jpeg",
            "mime": "image/png",
        })
        self.assertTrue(source.startswith("data:image/jpeg;base64,"))

    def test_serialized_base64_is_supported(self):
        raw = b"RIFF\x08\x00\x00\x00WEBPtest"
        source = image_data_url({
            "data": base64.b64encode(raw).decode("ascii"),
            "mime": "image/webp",
        })
        self.assertTrue(source.startswith("data:image/webp;base64,"))
        self.assertEqual(base64.b64decode(source.split(",", 1)[1]), raw)

    def test_existing_data_url_is_revalidated(self):
        raw = b"\x89PNG\r\n\x1a\n" + b"test-png"
        supplied = "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
        self.assertEqual(image_data_url({"data": supplied}), supplied)

    def test_invalid_or_unsafe_image_is_not_embedded(self):
        self.assertEqual(image_data_url({"data": "not base64", "mime": "image/png"}), "")
        self.assertEqual(image_data_url({"data": b"<svg></svg>", "mime": "image/svg+xml"}), "")
        self.assertEqual(image_data_url({"data": b"not-png", "mime": "image/png"}), "")
        oversized = b"\x89PNG\r\n\x1a\n" + b"x" * (20 * 1024**2)
        self.assertEqual(image_data_url({"data": oversized, "mime": "image/png"}), "")


if __name__ == "__main__":
    unittest.main()
