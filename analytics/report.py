#!/usr/bin/env python3
"""Daily GoAccess cohorts, aggregate SQLite history, and optional Sheets export."""

import argparse
import csv
import datetime as dt
import fcntl
import gzip
import ipaddress
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from urllib.parse import quote, urlsplit
from zoneinfo import ZoneInfo

COHORTS = {"non_crawlers": "--ignore-crawlers", "crawlers": "--crawlers-only"}
HEADERS = ["Date", "Timezone", "Cohort", "Requests", "Estimated daily visitors",
           "Bytes", "Source records", "GoAccess version", "Updated UTC"]
SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_summary (
    date TEXT NOT NULL, timezone TEXT NOT NULL, cohort TEXT NOT NULL,
    requests INTEGER NOT NULL, visitors INTEGER NOT NULL, bytes INTEGER NOT NULL,
    source_records INTEGER NOT NULL, goaccess_version TEXT NOT NULL,
    updated_utc TEXT NOT NULL,
    PRIMARY KEY (date, timezone, cohort)
);
CREATE TABLE IF NOT EXISTS path_summary (
    date TEXT NOT NULL, timezone TEXT NOT NULL, cohort TEXT NOT NULL,
    panel TEXT NOT NULL, path TEXT NOT NULL,
    requests INTEGER NOT NULL, visitors INTEGER NOT NULL, bytes INTEGER NOT NULL,
    PRIMARY KEY (date, timezone, cohort, panel, path)
);
"""


def header(headers, name):
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value[0] if isinstance(value, list) and value else value
    return ""


def normalized(entry):
    """Use Caddy's validated client_ip; never parse X-Forwarded-For ourselves."""
    request = entry["request"]
    client = request.get("client_ip")
    if not client:
        raise ValueError("missing client_ip; configure and verify trusted_proxies")
    ipaddress.ip_address(client)
    headers = request.get("headers", {})
    user_agent = entry.get("user_agent", header(headers, "User-Agent"))
    referrer = entry.get("referrer", header(headers, "Referer"))
    parsed = urlsplit(referrer or "")
    referrer = f"{parsed.scheme}://{parsed.hostname}" if parsed.scheme in ("http", "https") and parsed.hostname else "-"
    # A minimal standard Caddy record works with older GoAccess releases that
    # read remote_ip as well as newer releases that prefer client_ip.
    return {
        "ts": float(entry["ts"]),
        "request": {
            "remote_ip": client, "client_ip": client,
            "proto": request.get("proto", "HTTP/1.1"),
            "method": request["method"], "host": request.get("host", ""),
            "uri": urlsplit(request["uri"]).path or "/",
            "headers": {"User-Agent": [user_agent or "-"], "Referer": [referrer]},
        },
        "duration": float(entry.get("duration", 0)),
        "size": int(entry.get("size", 0)), "status": int(entry["status"]),
        "resp_headers": {"Content-Type": [header(entry.get("resp_headers", {}), "Content-Type") or "-"]},
    }


def prepare(log_directory, output, day, timezone, allow_private=False):
    files = sorted(set(log_directory.glob("access*.json")) | set(log_directory.glob("access*.json.gz")))
    if not files:
        raise ValueError(f"no access logs found in {log_directory}")
    count = 0
    private = 0
    with output.open("w") as destination:
        for path in files:
            opener = gzip.open if path.suffix == ".gz" else open
            with opener(path, "rt", encoding="utf-8") as source:
                for number, line in enumerate(source, 1):
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError as error:
                        # Caddy may be halfway through writing the active final
                        # line. A malformed completed record is an actual error.
                        if path.suffix != ".gz" and not line.endswith("\n"):
                            print(f"Skipping unfinished final record in {path.name}", file=sys.stderr)
                            continue
                        raise ValueError(f"invalid JSON in {path.name}:{number}") from error
                    try:
                        timestamp = dt.datetime.fromtimestamp(float(entry["ts"]), timezone)
                        if timestamp.date() != day:
                            continue
                        record = normalized(entry)
                        if not allow_private and not ipaddress.ip_address(record["request"]["client_ip"]).is_global:
                            private += 1
                            continue
                    except (KeyError, TypeError, ValueError, OverflowError) as error:
                        raise ValueError(f"invalid access record in {path.name}:{number}: {error}") from error
                    destination.write(json.dumps(record, separators=(",", ":")) + "\n")
                    count += 1
    if private and not count:
        raise ValueError("only non-public client_ip values; verify proxy trust or use --allow-private-clients for local testing")
    if private:
        print(f"Excluded {private} requests from non-public clients (internal monitoring or direct backend access)", file=sys.stderr)
    return count


def metric(item, key):
    value = item.get(key, 0)
    return int(value.get("count", 0) if isinstance(value, dict) else value)


def totals(report):
    # General.valid_requests can include excluded crawlers. Daily visitor
    # panel totals reflect the selected cohort. Never subtract its headline.
    rows = report.get("visitors", {}).get("data", [])
    return tuple(sum(metric(row, key) for row in rows) for key in ("hits", "visitors", "bytes"))


def run_goaccess(binary, source, directory, timezone, cohort, version):
    json_path = directory / f"{cohort}.json"
    html_path = directory / f"{cohort}.html"
    result = subprocess.run([
        binary, str(source), "--no-global-config", "--log-format=CADDY",
        f"--tz={timezone}", COHORTS[cohort], "--ignore-panel=HOSTS",
        "--max-items=100000", "--no-progress", "--no-parsing-spinner",
        f"--html-report-title=Website traffic: {cohort}",
        "-o", str(json_path), "-o", str(html_path),
    ], capture_output=True, text=True)
    # GoAccess exits nonzero when every input record belongs to the opposite
    # cohort. Handle only its explicit all-excluded diagnostic as a zero day.
    if result.returncode:
        if "Nothing valid to process" not in result.stderr:
            raise RuntimeError(f"GoAccess {cohort} failed: {result.stderr[-1500:]}")
        report = {"visitors": {"data": []}}
        json_path.write_text(json.dumps(report))
        html_path.write_text(f"<!doctype html><meta charset=utf-8><title>{cohort}</title><p>No requests in this cohort.</p>")
    else:
        report = json.loads(json_path.read_text())
    invalid = report.get("general", {}).get("failed_requests", 0)
    if invalid:
        raise ValueError(f"GoAccess rejected {invalid} records; refusing to save incomplete totals ({version})")
    return report


def save(database, day, timezone, reports, records, version):
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    with sqlite3.connect(database) as connection:
        connection.executescript(SCHEMA)
        for cohort, report in reports.items():
            requests, visitors, size = totals(report)
            connection.execute("""INSERT INTO daily_summary VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date, timezone, cohort) DO UPDATE SET
                requests=excluded.requests, visitors=excluded.visitors, bytes=excluded.bytes,
                source_records=excluded.source_records, goaccess_version=excluded.goaccess_version,
                updated_utc=excluded.updated_utc""",
                (day.isoformat(), timezone, cohort, requests, visitors, size, records, version, now))
            connection.execute("DELETE FROM path_summary WHERE date=? AND timezone=? AND cohort=?",
                               (day.isoformat(), timezone, cohort))
            for panel in ("requests", "static_requests", "not_found"):
                for row in report.get(panel, {}).get("data", []):
                    connection.execute("INSERT INTO path_summary VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (day.isoformat(), timezone, cohort, panel, row["data"],
                         metric(row, "hits"), metric(row, "visitors"), metric(row, "bytes")))


def daily_rows(database):
    if not database.is_file():
        raise ValueError(f"database does not exist: {database}")
    with sqlite3.connect(database) as connection:
        return [HEADERS] + [list(row) for row in connection.execute(
            "SELECT * FROM daily_summary ORDER BY date, timezone, cohort")]


def export_csv(database, output):
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", newline="", dir=output.parent, delete=False) as stream:
            temporary = Path(stream.name)
            csv.writer(stream).writerows(daily_rows(database))
        os.replace(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def publish_report(source, destination):
    # /tmp and the persistent /data volume may be different filesystems.
    # Stage inside the destination directory before an atomic rename.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as stream:
            temporary = Path(stream.name)
        shutil.copyfile(source, temporary)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def sheets_payload(database, sheet_name):
    escaped = sheet_name.replace("'", "''")
    return {"valueInputOption": "RAW", "data": [{"range": f"'{escaped}'!A1",
             "majorDimension": "ROWS", "values": daily_rows(database)}]}


def export_sheets(database, spreadsheet_id, sheet_name, credentials_file):
    if not credentials_file:
        raise ValueError("Sheets export requires --credentials or GOOGLE_APPLICATION_CREDENTIALS")
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession

    credentials = service_account.Credentials.from_service_account_file(
        credentials_file, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    session = AuthorizedSession(credentials)
    base = f"https://sheets.googleapis.com/v4/spreadsheets/{quote(spreadsheet_id, safe='')}"
    response = session.get(base, params={"fields": "sheets.properties"}, timeout=30)
    response.raise_for_status()
    properties = [sheet["properties"] for sheet in response.json().get("sheets", [])]
    payload = sheets_payload(database, sheet_name)
    rows = len(payload["data"][0]["values"])
    existing = next((item for item in properties if item["title"] == sheet_name), None)
    if existing is None:
        response = session.post(base + ":batchUpdate", json={"requests": [
            {"addSheet": {"properties": {"title": sheet_name,
             "gridProperties": {"rowCount": max(1000, rows), "columnCount": len(HEADERS), "frozenRowCount": 1}}}}]}, timeout=30)
        response.raise_for_status()
    elif existing.get("gridProperties", {}).get("rowCount", 1000) < rows:
        response = session.post(base + ":batchUpdate", json={"requests": [
            {"updateSheetProperties": {"properties": {"sheetId": existing["sheetId"],
             "gridProperties": {"rowCount": rows}}, "fields": "gridProperties.rowCount"}}]}, timeout=30)
        response.raise_for_status()
    # This tab belongs to the exporter. Replace the entire retained history,
    # including backfills, so API retries cannot append duplicate dates.
    response = session.post(base + "/values:batchUpdate", json=payload, timeout=30)
    response.raise_for_status()
    print(f"Exported {len(payload['data'][0]['values']) - 1} daily cohort rows to Sheets")


def collect(args):
    timezone = ZoneInfo(args.timezone)
    day = dt.date.fromisoformat(args.date) if args.date else dt.datetime.now(timezone).date() - dt.timedelta(days=1)
    if day >= dt.datetime.now(timezone).date():
        raise ValueError("collect a completed day; today's logs are still changing")
    args.database.parent.mkdir(parents=True, exist_ok=True)
    with args.database.with_suffix(".lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with tempfile.TemporaryDirectory(prefix="website-goaccess-") as temporary:
            work = Path(temporary)
            source = work / "day.json"
            records = prepare(args.logs, source, day, timezone, args.allow_private_clients)
            if not records and not args.allow_empty_day:
                raise ValueError("no records for this date; check log coverage or explicitly use --allow-empty-day")
            version = subprocess.check_output([args.goaccess, "--version"], text=True).splitlines()[0]
            reports = {}
            for cohort in COHORTS:
                if records:
                    reports[cohort] = run_goaccess(args.goaccess, source, work, args.timezone, cohort, version)
                else:
                    reports[cohort] = {"visitors": {"data": []}}
                    (work / f"{cohort}.json").write_text(json.dumps(reports[cohort]))
                    (work / f"{cohort}.html").write_text(f"<!doctype html><meta charset=utf-8><title>{cohort}</title><p>No requests.</p>")
            if sum(totals(report)[0] for report in reports.values()) != records:
                raise ValueError("cohort requests do not add up to source records; refusing incomplete statistics")
            save(args.database, day, args.timezone, reports, records, version)
            destination = args.reports / args.timezone.replace("/", "_") / day.isoformat()
            destination.mkdir(parents=True, exist_ok=True)
            for cohort in COHORTS:
                for extension in ("json", "html"):
                    publish_report(work / f"{cohort}.{extension}", destination / f"{cohort}.{extension}")
        export_csv(args.database, args.database.parent / "daily.csv")
        print(f"Stored {day} ({args.timezone}): " + ", ".join(
            f"{cohort}={totals(report)[0]} requests/{totals(report)[1]} visitors" for cohort, report in reports.items()))
        if args.sheet_id:
            export_sheets(args.database, args.sheet_id, args.sheet_name, args.credentials)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    collection = commands.add_parser("collect", help="summarize yesterday or --date YYYY-MM-DD")
    collection.add_argument("--logs", type=Path, default=Path("/logs"))
    collection.add_argument("--reports", type=Path, default=Path("/data/reports"))
    collection.add_argument("--date")
    collection.add_argument("--timezone", default=os.getenv("ANALYTICS_TIMEZONE", "America/New_York"))
    collection.add_argument("--goaccess", default="goaccess")
    collection.add_argument("--allow-empty-day", action="store_true")
    collection.add_argument("--allow-private-clients", action="store_true")
    export = commands.add_parser("export", help="retry Sheets export from SQLite without rereading logs")
    export.add_argument("--csv", type=Path)
    for command in (collection, export):
        command.add_argument("--database", type=Path, default=Path("/data/traffic.sqlite3"))
        command.add_argument("--sheet-id", default=os.getenv("ANALYTICS_SHEET_ID", ""))
        command.add_argument("--sheet-name", default="Daily traffic")
        command.add_argument("--credentials", default=os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""))
    args = parser.parse_args()
    if args.command == "collect":
        collect(args)
    else:
        if not args.csv and not args.sheet_id:
            parser.error("export requires --csv or --sheet-id")
        with args.database.with_suffix(".lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if args.csv:
                export_csv(args.database, args.csv)
            if args.sheet_id:
                export_sheets(args.database, args.sheet_id, args.sheet_name, args.credentials)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, sqlite3.Error, subprocess.CalledProcessError) as error:
        print(f"Analytics failed: {error}", file=sys.stderr)
        sys.exit(1)
