# Website traffic reports

GoAccess generates two daily reports: `non_crawlers` (`--ignore-crawlers`) and
`crawlers` (`--crawlers-only`). SQLite retains daily totals and per-path aggregates.
An optional Google Sheets exporter mirrors the daily totals to a private sheet.
No browser script, analytics service, or public dashboard is required.

## What the counts mean

The reports include **all HTTP requests reaching the website backend**, including
assets, feeds, redirects, and errors. `Requests` is not a pageview count. The daily
visitor estimate uses GoAccess's IP + user-agent + date definition. Visitors who
share addresses can be merged, changing addresses can be counted twice, and
requests served entirely from browser or upstream caches never reach this log.
Do not sum daily visitor estimates to claim monthly unique people.
Bytes are the backend's recorded response bytes; compression at the frontend
can change the number of bytes ultimately sent over the Internet.

`non_crawlers` means no crawler recognized by the installed GoAccess version,
not verified humans. `crawlers` includes recognized AI agents, search crawlers,
and other known bots; it does not provide a separate AI breakdown. Keep GoAccess
current to update its recognition list. There are no custom UA classification
rules in this initial version.

## Enable logging (when deploying)

The default Compose stack is unchanged. The overlay switches only the website
backend to an analytics Caddyfile, preserving the existing feeds import and file
server, and mounts a private log directory. It pins Caddy 2.11.6 for daily rotation.

1. Inspect the running `caddy-gen` network and its IP:

   ```sh
   docker inspect caddy-gen --format '{{json .NetworkSettings.Networks}}'
   docker network inspect NETWORK_NAME
   ```

2. Set `WEBSITE_TRUSTED_PROXIES` in the existing untracked `.env` to the appropriate
   proxy network CIDR, or a stable proxy address with `/32` (IPv4) or `/128` (IPv6).
   For example, `WEBSITE_TRUSTED_PROXIES=172.18.0.0/16` is valid **only if that is
   your actual proxy network**. Prefer a network limited to trusted services.
   Caddy parses forwarded addresses from right to left. Do not trust arbitrary
   public addresses or unvalidated incoming headers. If there is another proxy
   ahead of `caddy-gen`, its forwarding and trust configuration also needs checking.

3. Prepare storage and build the job:

   ```sh
   mkdir -p analytics/logs analytics/data analytics/secrets
   chmod 700 analytics/logs analytics/data analytics/secrets
   docker compose -f docker-compose.yml -f compose.analytics.yml build website-analytics
   docker compose -f docker-compose.yml -f compose.analytics.yml run --rm --no-deps personal-website caddy validate --config /etc/analytics/Caddyfile --adapter caddyfile
   docker compose -f docker-compose.yml -f compose.analytics.yml up -d --no-deps --force-recreate personal-website
   ```

4. Make a public HTTPS request with a distinctive user agent. Inspect the private
   log locally and verify `request.client_ip` is your public IP, while
   `request.remote_ip` is the proxy. Also send a fake `X-Forwarded-For` value and
   check that it cannot replace the actual client IP. Verify the feeds and legacy
   redirects still work. The reporter refuses non-public client addresses by
   default when all selected addresses are non-public, to catch a missing proxy
   trust configuration. When public traffic exists, internal requests are excluded
   and their count is reported on stderr. `--allow-private-clients`
   is available for internal networks and local tests.

Keep using both Compose files when recreating this service. Using only the base
file restores the original backend configuration and stops analytics logging.

## Run daily and inspect SQLite

After a full day of logging:

```sh
docker compose -f docker-compose.yml -f compose.analytics.yml run --rm --no-deps website-analytics
```

The default date is yesterday in `America/New_York`. Change it with
`ANALYTICS_TIMEZONE` in `.env`. For a retained historical date:

```sh
docker compose -f docker-compose.yml -f compose.analytics.yml run --rm --no-deps website-analytics collect --date 2026-10-03
sqlite3 analytics/data/traffic.sqlite3 'SELECT date, cohort, requests, visitors FROM daily_summary ORDER BY date, cohort;'
sqlite3 analytics/data/traffic.sqlite3 'SELECT date, cohort, path, requests FROM path_summary WHERE panel="requests" ORDER BY date DESC, requests DESC LIMIT 20;'
```

Use the host's cron scheduler, for example at 07:15 UTC (02:15/03:15 New York):

```cron
CRON_TZ=UTC
15 7 * * * cd /ABSOLUTE/PATH/TO/webpage-docker-containers && docker compose -f docker-compose.yml -f compose.analytics.yml run --rm --no-deps website-analytics >> analytics/data/job.log 2>&1
```

Replace the path, ensure the cron user can access Docker, and rotate `job.log`.
Cron implementations without `CRON_TZ` require converting the schedule to the
host's timezone. Only one collection/export process may run against a database
at a time. Configure your normal job monitoring to notice nonzero exits.

Outputs are private and ignored by Git:

- `analytics/data/traffic.sqlite3`: `daily_summary` and `path_summary` tables.
- `analytics/data/daily.csv`: the full daily summary history.
- `analytics/data/reports/America_New_York/YYYY-MM-DD/`: both JSON and HTML reports.

SQLite writes both cohorts in one transaction and replaces their rows when a day
is rerun, including paths that disappeared. GoAccess's headline general request
count may include exclusions; totals come from its cohort-specific daily visitor
panel and must reconcile to all included source records. A failed Sheets export leaves
SQLite, CSV, and reports intact. Missing logs, malformed completed records, and
dates with no records fail rather than silently overwrite history with zeros.
Use `--allow-empty-day` only for a known zero-traffic day with valid log coverage.
The first and last retained days can be partial: the software cannot infer that
an outage or log deletion lost requests. Backfill only complete retained days.

## Google Sheets

Create or select a private spreadsheet, enable the Google Sheets API in a Google
Cloud project, and create a service account for the job. Share **that spreadsheet**
with the service account's email as an editor. No project-wide administrative
role or domain delegation is needed.

Save its downloaded JSON credentials as
`analytics/secrets/google-service-account.json` with mode `600`. Set
`ANALYTICS_SHEET_ID` in `.env` to the ID in the spreadsheet URL. Credentials are
mounted read-only, excluded from Git and the Docker build context, and never
sent to GoAccess.

The exporter creates a tab named `Daily traffic` if necessary. It owns columns
A:I on that tab and writes the entire SQLite summary history with `RAW` values,
ordered by date, timezone, and cohort. Do not put manual data in that range;
put charts or formulas on a separate tab. It expands row capacity as history
grows. Repeated exports and historical backfills do not append duplicates.

To retry export without reading logs:

```sh
docker compose -f docker-compose.yml -f compose.analytics.yml run --rm --no-deps website-analytics export
```

Only summary dates, timezone, cohort, request counts, visitor estimates, bytes,
source record counts, GoAccess version, and update time reach Google. IPs, user
agents, individual requests, and per-path details remain local. Leaving the
sheet ID empty disables Google entirely; SQLite and CSV still work.

## Retention and checks

Access logs retain IPs and user agents. The Caddy encoder drops request headers,
strips URL queries, reduces HTTP referrers to origins, and omits response cookies.
The reporter further reduces referrers to domains and removes queries. GoAccess's
hosts panel is disabled, so reports/SQLite do not retain per-IP host listings.
Information embedded directly in URL paths can still appear in reports.

Caddy rotates logs daily or at 10 MiB, keeping at most 14 backups and seven days
of rolled logs; age cleanup occurs during rotation. Do not copy logs to the public
Hugo directory. Summary history and reports persist until deliberately removed.
Back up SQLite using `sqlite3 ... '.backup ...'`, rather than copying an actively
written database file. These settings govern the new backend log; `caddy-gen` may
also have its own access logs, whose fields and retention need reviewing separately.
Review any privacy notice against the actual collection.

Run unit and real GoAccess integration tests inside the job image:

```sh
docker compose -f docker-compose.yml -f compose.analytics.yml run --rm --no-deps --entrypoint python3 -v "$PWD/analytics:/app:ro" website-analytics -m unittest -v test_report
```

Tests cover crawler separation, daily visitor deduplication, reruns, compressed
logs, local midnight/DST, invalid proxy addresses, SQLite persistence after export
failure, and Sheets request construction. Mocked Sheets tests do not verify live
Google authorization. Validate forwarded IPs and live export during rollout.

To exercise the Caddy configuration behind a real temporary local reverse proxy,
including spoofed forwarded headers, log filtering, feeds, 304s, and redirects:

```sh
python3 analytics/check_caddy.py
```

This creates temporary Docker containers and a network, binds the test proxy to
localhost, and removes the containers and network when finished.
