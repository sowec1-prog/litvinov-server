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
    def test_uses_main_score_cells_not_period_breakdown(self):
        html = '''<table><tr>
          <td class="preview__name text-right">HC VERVA Litvínov</td>
          <td class="preview__score"><span>1</span></td>
          <td class="preview__period">ST 16. 09. <span>(0:0, 1:0, 0:0)</span></td>
          <td class="preview__score preview__score--right"><span>0</span></td>
          <td class="preview__name">HC Kometa Brno</td>
        </tr></table>'''
        self.assertEqual(server.zpracuj_html(html), "HC Verva\n1:0\nKometa Brno")
    def test_normalizes_long_partner_team_names_for_api_and_oled(self):
        self.assertEqual(
            server.normalize_team_name("Banes Motor Č. Budějovice Č. Budějovice CEB"),
            "Motor Č. Budějovice",
        )
        self.assertEqual(
            server.normalize_team_name("BYD Energie Karlovy Vary KVA"),
            "Energie K.V.",
        )
        self.assertEqual(
            server.display_team_name("Banes Motor Č. Budějovice Č. Budějovice CEB", "CEB"),
            "Motor C. Budejovice",
        )

    def test_parses_normalized_team_name_into_api_payload(self):
        html = '''<table><tr class="js-preview__link" data-href="/zapas/123">
          <td class="preview__name"><a>Banes Motor Č. Budějovice Č. Budějovice CEB</a></td>
          <td class="preview__desktop">NE 27. 09. 16:00</td>
          <td class="preview__name"><a>HC VERVA Litvínov LIT</a></td>
        </tr></table>'''
        with patch("server.parse_scheduled_epoch", return_value=(0, 0, False)):
            match = server.parse_next_match(html)
        self.assertEqual(match["home"], "Motor Č. Budějovice")
        self.assertEqual(match["home_display"], "Motor C. Budejovice")


if __name__ == "__main__":
    unittest.main()
