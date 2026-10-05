import datetime as dt
import gzip
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import report


def record(timestamp="2026-10-02T16:00:00+00:00", agent="Mozilla/5.0 Chrome/120.0", ip="93.184.216.34", path="/weblog/post/?secret=private"):
    return {
        "ts": dt.datetime.fromisoformat(timestamp).timestamp(),
        "request": {"remote_ip": "172.18.0.2", "client_ip": ip,
                    "method": "GET", "host": "patrick.wagstrom.net", "uri": path},
        "user_agent": agent, "referrer": "https://example.com/search?q=private#secret",
        "status": 200, "size": 100,
        "resp_headers": {"Content-Type": ["text/html; charset=utf-8"]},
    }


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.logs = self.root / "logs"
        self.logs.mkdir()
        self.database = self.root / "traffic.sqlite3"

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, entries, filename="access.json"):
        path = self.logs / filename
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "wt") as stream:
            stream.writelines(json.dumps(entry) + "\n" for entry in entries)
        return path

    def test_normalization_uses_validated_ip_and_strips_sensitive_url_data(self):
        normalized = report.normalized(record())
        self.assertEqual(normalized["request"]["remote_ip"], "93.184.216.34")
        self.assertEqual(normalized["request"]["headers"]["Referer"], ["https://example.com"])
        self.assertEqual(normalized["request"]["uri"], "/weblog/post/")
        self.assertNotIn("secret", json.dumps(normalized))
        missing = record()
        del missing["request"]["client_ip"]
        with self.assertRaisesRegex(ValueError, "trusted_proxies"):
            report.normalized(missing)

    def test_rotated_logs_local_midnight_and_dst(self):
        self.write([record("2026-03-08T04:59:59+00:00"), record("2026-03-08T05:00:00+00:00")], "access-old.json.gz")
        self.write([record("2026-03-09T03:59:59+00:00"), record("2026-03-09T04:00:00+00:00")])
        output = self.root / "input.json"
        count = report.prepare(self.logs, output, dt.date(2026, 3, 8), ZoneInfo("America/New_York"))
        self.assertEqual(count, 2)  # The day has 23 hours, not 24.
        self.assertEqual(len(output.read_text().splitlines()), 2)

    def test_private_proxy_address_and_corrupt_records_fail(self):
        path = self.write([record(ip="172.18.0.2")])
        with self.assertRaisesRegex(ValueError, "non-public client_ip"):
            report.prepare(self.logs, self.root / "input", dt.date(2026, 10, 2), ZoneInfo("UTC"))
        path.write_text("broken JSON\n")
        with self.assertRaisesRegex(ValueError, "invalid JSON"):
            report.prepare(self.logs, self.root / "input", dt.date(2026, 10, 2), ZoneInfo("UTC"))

    def test_internal_monitoring_does_not_abort_public_report(self):
        self.write([record(ip="172.18.0.2"), record()])
        output = self.root / "input"
        self.assertEqual(report.prepare(self.logs, output, dt.date(2026, 10, 2), ZoneInfo("UTC")), 1)
        self.assertEqual(len(output.read_text().splitlines()), 1)

    def test_sqlite_replaces_date_and_paths_and_exports_raw_payload(self):
        def fixture(hits, path):
            row = {"data": path, "hits": {"count": hits}, "visitors": {"count": 1}, "bytes": {"count": 100}}
            return {"general": {"valid_requests": 999}, "visitors": {"data": [row]}, "requests": {"data": [row]}}
        day = dt.date(2026, 10, 2)
        empty = {"visitors": {"data": []}}
        report.save(self.database, day, "UTC", {"non_crawlers": fixture(2, "/old"), "crawlers": empty}, 2, "test")
        report.save(self.database, day, "UTC", {"non_crawlers": fixture(3, "/new"), "crawlers": empty}, 3, "test")
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM daily_summary").fetchone()[0], 2)
            self.assertEqual(connection.execute("SELECT path FROM path_summary").fetchall(), [("/new",)])
        payload = report.sheets_payload(self.database, "Patrick's traffic")
        self.assertEqual(payload["valueInputOption"], "RAW")
        self.assertEqual(payload["data"][0]["range"], "'Patrick''s traffic'!A1")
        self.assertEqual(payload["data"][0]["values"][-1][3], 3)
        self.assertEqual(payload, report.sheets_payload(self.database, "Patrick's traffic"))

    def test_sheets_export_creates_tab_and_replaces_history(self):
        report.save(self.database, dt.date(2026, 10, 2), "UTC",
                    {name: {"visitors": {"data": []}} for name in report.COHORTS}, 0, "test")
        try:
            import google.oauth2.service_account
            import google.auth.transport.requests
        except ImportError:
            self.skipTest("Google auth libraries available in the reporting container")
        session = Mock()
        session.get.return_value.json.return_value = {"sheets": [{"properties": {"title": "Sheet1"}}]}
        with patch("google.oauth2.service_account.Credentials.from_service_account_file"), \
             patch("google.auth.transport.requests.AuthorizedSession", return_value=session):
            report.export_sheets(self.database, "sheet-id", "Daily traffic", "credentials.json")
        self.assertEqual(session.post.call_count, 2)
        calls = session.post.call_args_list
        self.assertTrue(calls[0].args[0].endswith(":batchUpdate"))
        self.assertTrue(calls[1].args[0].endswith("/values:batchUpdate"))
        self.assertEqual(len(calls[1].kwargs["json"]["data"][0]["values"]), 3)

    @unittest.skipUnless(shutil.which("goaccess"), "GoAccess is available in the reporting container")
    def test_real_goaccess_cohorts_rerun_and_failed_export_preserve_sqlite(self):
        self.write([record(), record(path="/style.css"), record(ip="93.184.216.35"),
                    record(agent="Googlebot/2.1 (+http://www.google.com/bot.html)", ip="66.249.66.1")])
        command = ["python3", str(Path(report.__file__)), "collect", "--logs", str(self.logs),
                   "--database", str(self.database), "--reports", str(self.root / "reports"), "--date", "2026-10-02"]
        for _ in range(2):
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        with sqlite3.connect(self.database) as connection:
            values = connection.execute("SELECT cohort, requests, visitors, bytes FROM daily_summary ORDER BY cohort").fetchall()
            self.assertEqual(values, [("crawlers", 1, 1, 100), ("non_crawlers", 3, 2, 300)])
        result = subprocess.run(command + ["--sheet-id", "fake", "--credentials", "/missing-key"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(report.daily_rows(self.database)), 3)
        self.assertTrue((self.root / "daily.csv").is_file())
        self.assertNotIn("93.184", (self.root / "daily.csv").read_text())
        json_report = self.root / "reports/America_New_York/2026-10-02/non_crawlers.json"
        self.assertNotIn("hosts", json.loads(json_report.read_text()))

    @unittest.skipUnless(shutil.which("goaccess"), "GoAccess is available in the reporting container")
    def test_real_goaccess_empty_cohort(self):
        self.write([record()])
        source = self.root / "input.json"
        report.prepare(self.logs, source, dt.date(2026, 10, 2), ZoneInfo("UTC"))
        crawlers = report.run_goaccess("goaccess", source, self.root, "UTC", "crawlers", "test")
        self.assertEqual(report.totals(crawlers), (0, 0, 0))

    @unittest.skipUnless(shutil.which("goaccess"), "GoAccess is available in the reporting container")
    def test_real_goaccess_local_midnight(self):
        self.write([record("2026-03-08T05:00:00+00:00"), record("2026-03-09T03:59:59+00:00")])
        source = self.root / "input.json"
        report.prepare(self.logs, source, dt.date(2026, 3, 8), ZoneInfo("America/New_York"))
        output = report.run_goaccess("goaccess", source, self.root, "America/New_York", "non_crawlers", "test")
        self.assertEqual(report.totals(output), (2, 1, 200))
        self.assertEqual(len(output["visitors"]["data"]), 1)

    def test_sqlite_cohort_failure_rolls_back_both(self):
        day = dt.date(2026, 10, 2)
        empty = {name: {"visitors": {"data": []}} for name in report.COHORTS}
        report.save(self.database, day, "UTC", empty, 0, "before")
        row = {"data": "/duplicate", "hits": {"count": 1}, "visitors": {"count": 1}, "bytes": {"count": 1}}
        invalid = dict(empty)
        invalid["crawlers"] = {"visitors": {"data": [row]}, "requests": {"data": [row, row]}}
        with self.assertRaises(sqlite3.IntegrityError):
            report.save(self.database, day, "UTC", invalid, 1, "after")
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute("SELECT requests, goaccess_version FROM daily_summary").fetchall(), [(0, "before"), (0, "before")])


if __name__ == "__main__":
    unittest.main()
