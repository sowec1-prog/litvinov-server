import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch
import requests
import server


class ServerCacheTests(unittest.TestCase):
    def setUp(self):
        server._last_good_payload = None
        server._last_good_status = None
        server._manual_cue = None

    def test_manual_goal_requires_secret_and_emits_baseline_then_goal(self):
        sample = {
            "state": "scheduled", "home_code": "LIT", "away_code": "SPA",
            "home_display": "HC Verva Litvinov", "away_display": "Sparta",
            "score_home": 0, "score_away": 0, "event_id": "", "audio_cue": "",
        }
        client = server.app.test_client()
        with patch.dict("os.environ", {"LITVINOV_COMMAND_TOKEN": "secret"}, clear=False):
            denied = client.post("/api/command/gol")
            self.assertEqual(denied.status_code, 401)
            accepted = client.post("/api/command/gol", headers={"X-Litvinov-Command-Token": "secret"})
        self.assertEqual(accepted.status_code, 202)
        with patch("server.time.time", return_value=server._manual_cue["cue_at"] - 1):
            armed = server.manual_cue_payload(sample)
        with patch("server.time.time", return_value=server._manual_cue["cue_at"] + 1):
            goal = server.manual_cue_payload(sample)
        self.assertEqual(armed["state"], "live")
        self.assertEqual(armed["audio_cue"], "")
        self.assertTrue(armed["event_id"].startswith("manual-arm-"))
        self.assertEqual(goal["audio_cue"], "lit_goal")
        self.assertTrue(goal["event_id"].startswith("manual-gol-"))

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

    def test_live_api_returns_retry_screen_on_first_upstream_outage(self):
        client = server.app.test_client()
        with patch("server.stahni_live_stav", side_effect=requests.exceptions.ReadTimeout("timeout")):
            response = client.get("/api/live")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["state"], "scheduled")
        self.assertTrue(payload["cached"])
        self.assertTrue(payload["source_unavailable"])
        self.assertEqual(payload["away_display"], "ZDROJ NEDOSTUPNY")
        self.assertEqual(payload["game_clock"], "ZKUSIM ZNOVU")

    def test_reads_table_position_from_official_club_table(self):
        html = '''<table><tr><td>8.</td><td>HC VERVA Litvínov</td></tr></table>'''
        self.assertEqual(server.get_litvinov_table_position(html), 8)
        self.assertEqual(server.STANDINGS_URL, "https://www.hcverva.cz/standings/MUZ")

    def test_finished_payload_keeps_final_score_for_ten_minutes(self):
        match = {"home": "HC VERVA Litvinov LIT", "away": "Trinec TRI"}
        payload = server.finished_payload(match, {}, 1_000_000)
        self.assertEqual(payload["state"], "finished")
        self.assertEqual(payload["game_clock"], "KONEC ZAPASU")
        self.assertEqual(server.FINISHED_DISPLAY_SECONDS, 600)
        self.assertEqual(payload["finished_until_epoch"], 1_000_600)

    def test_uses_known_text_transfer_id_for_trinec_litvinov(self):
        start = datetime(2026, 10, 2, 17, 0, tzinfo=ZoneInfo("Europe/Prague"))
        match = {"match_start_epoch": int(start.timestamp()), "home": "Třinec", "away": "Litvínov"}
        self.assertEqual(server.known_text_transfer_id(match), "2928297")

    def test_uses_official_schedule_when_hokej_schedule_is_blocked(self):
        fallback = {
            "state": "scheduled", "home_code": "TRI", "away_code": "LIT",
            "away_display": "HC VERVA Litvinov", "game_clock": "02. 10. 17:00",
        }
        with patch("server.request_text", side_effect=[requests.exceptions.HTTPError("403"), "<html></html>"]), \
             patch("server.parse_verva_next_match", return_value=dict(fallback)) as parse_fallback:
            status = server.stahni_live_stav()
        parse_fallback.assert_called_once()
        self.assertEqual(status["away_code"], "LIT")
        self.assertIn("oficialni program hcverva.cz", status["source"])

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


    def test_ascii_normalizes_german_umlauts_for_oled(self):
        self.assertEqual(server.odstran_diakritiku("KÄMPF Kämpf Größ"), "KAMPF Kampf Gross")

    def test_uses_known_short_code_for_kladno_without_source_code(self):
        self.assertEqual(server.team_code("Rytíři Kladno"), "KLA")

    def test_commercial_break_is_fixed_thirty_seconds_from_marker(self):
        marker = {"@attributes": {"written": "2026-10-04 18:00:00"}, "time": "15:27", "message": "Hra je přerušena a následuje komerční přestávka."}
        resumed = {"@attributes": {"written": "2026-10-04 18:00:10"}, "time": "15:51", "message": "Další herní akce."}
        start = int(datetime(2026, 10, 4, 18, 0, 0, tzinfo=ZoneInfo("Europe/Prague")).timestamp())
        self.assertEqual(server.commercial_break_until_epoch([resumed, marker], now_epoch=start + 20), start + 30)
        self.assertEqual(server.commercial_break_until_epoch([resumed, marker], now_epoch=start + 31), 0)

    def test_finds_last_litvinov_scorer_from_match_detail(self):
        html = """<table><tr><td>10:00</td><td>LIT</td><td><a href='/hrac/1'>Ondřej Kaše</a></td></tr><tr><td>12:00</td><td>KLA</td><td><a href='/hrac/2'>Niko Ojamäki</a></td></tr></table>"""
        goal = server.parse_last_goal(html, "HC VERVA Litvínov")
        self.assertEqual(goal["scorer"], "Ondřej Kaše")
        self.assertEqual(goal["team"], "home")

    def test_opponent_goal_is_shown_only_for_fifteen_seconds_then_lit_goal_returns(self):
        lit_goal = {"event_id": "lit", "team": "home", "written_epoch": 1_000}
        away_goal = {"event_id": "away", "team": "away", "written_epoch": 1_010}
        self.assertTrue(server.show_opponent_goal_temporarily(away_goal, "home", 1_024))
        self.assertFalse(server.show_opponent_goal_temporarily(away_goal, "home", 1_025))
        self.assertFalse(server.show_opponent_goal_temporarily(lit_goal, "home", 1_005))

    def test_converts_cumulative_live_clock_to_current_period_clock(self):
        self.assertEqual(server.display_period_clock("19:59"), "19:59")
        self.assertEqual(server.display_period_clock("20:01"), "00:01")
        self.assertEqual(server.display_period_clock("39:59"), "19:59")
        self.assertEqual(server.display_period_clock("40:01"), "00:01")

    def test_intermission_does_not_roll_to_tomorrow_seconds_after_start(self):
        with patch("server.datetime") as clock:
            clock.now.return_value = datetime(2026, 10, 4, 18, 23, 10, tzinfo=ZoneInfo("Europe/Prague"))
            active, until, note = server.parse_intermission("Další třetina začne přibližně v 18:23.")
        self.assertTrue(active)
        self.assertEqual(note, "PRESTAVKA DO 18:23")
        self.assertEqual(datetime.fromtimestamp(until, ZoneInfo("Europe/Prague")).date().isoformat(), "2026-10-04")

    def test_intermission_survives_newer_period_summary(self):
        summary = {"@attributes": {"score1": "2", "score2": "0"}, "time": {"@attributes": {"period": "1INT"}}, "details": [], "message": "Shrnutí první třetiny."}
        announcement = {"@attributes": {"score1": "2", "score2": "0"}, "time": {"@attributes": {"period": "1INT"}}, "details": [], "message": "Další třetina začne přibližně v 18:23."}
        match = {"home": "HC VERVA Litvínov", "away": "Rytíři Kladno", "score_home": 0, "score_away": 0, "match_id": "2928307"}
        with patch("server.datetime") as clock:
            clock.now.return_value = datetime(2026, 10, 4, 18, 5, tzinfo=ZoneInfo("Europe/Prague"))
            payload = server.extract_live_state({"comments": {"comment": [summary, announcement]}}, match)
        self.assertTrue(payload["intermission"])
        self.assertEqual(payload["intermission_note"], "PRESTAVKA DO 18:23")

    def test_uses_known_text_transfer_id_for_litvinov_kladno(self):
        start = datetime(2026, 10, 4, 17, 30, tzinfo=ZoneInfo("Europe/Prague"))
        match = {"match_start_epoch": int(start.timestamp()), "home": "HC VERVA Litvínov", "away": "Rytíři Kladno"}
        self.assertEqual(server.known_text_transfer_id(match), "2928307")


if __name__ == "__main__":
    unittest.main()
