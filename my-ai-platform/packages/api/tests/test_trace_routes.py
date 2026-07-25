import unittest

from src.lib.trace import elapsed_ms


class TraceRouteTests(unittest.TestCase):
    def test_elapsed_ms_supports_high_resolution_iso_timestamps(self):
        self.assertEqual(
            elapsed_ms(
                "2026-07-25T10:00:00.125+08:00",
                "2026-07-25T10:00:01.875+08:00",
            ),
            1750,
        )

    def test_elapsed_ms_supports_legacy_sqlite_timestamps(self):
        self.assertEqual(
            elapsed_ms("2026-07-25 10:00:00", "2026-07-25 10:00:03"),
            3000,
        )


if __name__ == "__main__":
    unittest.main()
