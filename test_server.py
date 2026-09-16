import unittest
from unittest.mock import patch
import requests
import server


class ServerCacheTests(unittest.TestCase):
    def setUp(self):
        server._last_good_payload = None

    def test_returns_last_good_score_when_hokej_request_times_out(self):
        good = "HC Verva\n0:0\nKometa Brno"
        with patch("server.stahni_a_zpracuj", return_value=good):
            first = server.app.test_client().get("/litvinov")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.get_data(as_text=True), good)

        with patch("server.stahni_a_zpracuj", side_effect=requests.exceptions.ReadTimeout("timeout")):
            second = server.app.test_client().get("/litvinov")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.get_data(as_text=True), good)


if __name__ == "__main__":
    unittest.main()
