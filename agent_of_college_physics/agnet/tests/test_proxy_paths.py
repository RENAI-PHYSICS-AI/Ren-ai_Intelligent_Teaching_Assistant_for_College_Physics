import sys
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from proxy_paths import public_prefix, with_public_prefix


class ProxyPathTests(unittest.TestCase):
    def test_prefix_from_public_url(self):
        self.assertEqual(public_prefix("https://physics.example/agent/"), "/agent")
        self.assertEqual(with_public_prefix("/admin-login", "https://physics.example/agent"), "/agent/admin-login")

    def test_prefix_from_gateway_setting(self):
        self.assertEqual(with_public_prefix("/analytics", "", "/agent"), "/agent/analytics")
        self.assertEqual(with_public_prefix("/agent/analytics", "", "/agent"), "/agent/analytics")

    def test_root_and_absolute_urls(self):
        self.assertEqual(with_public_prefix("/admin-login", ""), "/admin-login")
        self.assertEqual(with_public_prefix("https://admin.example/analytics", "https://physics.example/agent"), "https://admin.example/analytics")


if __name__ == "__main__":
    unittest.main()
