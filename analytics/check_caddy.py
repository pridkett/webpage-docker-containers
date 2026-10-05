"""Exercise the analytics backend behind a temporary local Caddy proxy."""

import json
import ipaddress
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid

IMAGE = "caddy:2.11.6-alpine"
ROOT = Path(__file__).resolve().parent.parent


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True).strip()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def main():
    suffix = uuid.uuid4().hex[:10]
    network = "analytics-check-" + suffix
    backend = "analytics-backend-" + suffix
    frontend = "analytics-proxy-" + suffix
    containers = []
    with tempfile.TemporaryDirectory(prefix="analytics-caddy-") as temporary:
        work = Path(temporary)
        site = work / "site"
        logs = work / "logs"
        site.mkdir()
        logs.mkdir()
        (site / "index.html").write_text("<!doctype html><title>Analytics fixture</title>")
        (site / "index.rss").write_text("<rss>fixture</rss>")
        (site / "index.atom").write_text("<feed>fixture</feed>")
        frontend_config = work / "frontend.caddy"
        frontend_config.write_text(":80 {\n reverse_proxy " + backend + ":80\n}\n")
        docker("network", "create", network)
        try:
            subnet = json.loads(docker("network", "inspect", network))[0]["IPAM"]["Config"][0]["Subnet"]
            proxy_ip = str(ipaddress.ip_network(subnet).network_address + 10)
            docker("run", "-d", "--name", backend, "--network", network,
                   "-e", "WEBSITE_TRUSTED_PROXIES=" + proxy_ip + "/32",
                   "-v", str(ROOT / "analytics/Caddyfile") + ":/etc/analytics/Caddyfile:ro",
                   "-v", str(ROOT / "personal-website") + ":/etc/caddy:ro",
                   "-v", str(site) + ":/usr/share/caddy:ro",
                   "-v", str(logs) + ":/var/log/website", IMAGE,
                   "caddy", "run", "--config", "/etc/analytics/Caddyfile", "--adapter", "caddyfile")
            containers.append(backend)
            docker("run", "-d", "--name", frontend, "--network", network,
                   "--ip", proxy_ip,
                   "-p", "127.0.0.1::80", "-v", str(frontend_config) + ":/etc/caddy/Caddyfile:ro", IMAGE)
            containers.append(frontend)
            port = docker("port", frontend, "80/tcp").rsplit(":", 1)[1]
            base = "http://127.0.0.1:" + port
            opener = urllib.request.build_opener(NoRedirect)
            for _ in range(50):
                try:
                    with opener.open(base, timeout=2) as response:
                        assert response.status == 200
                    break
                except (urllib.error.URLError, OSError):
                    time.sleep(0.1)
            else:
                raise RuntimeError("test proxy did not start")

            for spoof in (None, "8.8.8.8"):
                headers = {"User-Agent": "analytics-privacy-check", "Cookie": "secret-cookie",
                           "Authorization": "Bearer secret-token", "Referer": "https://example.com/private?secret=query"}
                if spoof:
                    headers["X-Forwarded-For"] = spoof
                with opener.open(urllib.request.Request(base + "/?secret=query", headers=headers), timeout=5) as response:
                    assert response.status == 200

            for path, mime in (("/index.rss", "application/rss+xml"), ("/index.atom", "application/atom+xml")):
                with opener.open(base + path, timeout=5) as response:
                    assert response.headers["Content-Type"].startswith(mime)
                    assert response.headers["Access-Control-Allow-Origin"] == "*"
                    etag = response.headers["Etag"]
                try:
                    opener.open(urllib.request.Request(base + path, headers={"If-None-Match": etag}), timeout=5)
                    raise AssertionError("expected conditional 304")
                except urllib.error.HTTPError as response:
                    assert response.code == 304
            try:
                opener.open(base + "/weblog/index.rss", timeout=5)
                raise AssertionError("expected redirect")
            except urllib.error.HTTPError as response:
                assert response.code == 308
                assert response.headers["Location"] == "https://patrick.wagstrom.net/index.rss"

            time.sleep(0.1)
            content = (logs / "access.json").read_text()
            entries = [json.loads(line) for line in content.splitlines()]
            privacy = [entry for entry in entries if entry.get("user_agent") == "analytics-privacy-check"]
            assert len(privacy) == 2
            assert privacy[0]["request"]["client_ip"] == privacy[1]["request"]["client_ip"]
            assert privacy[1]["request"]["client_ip"] != "8.8.8.8"
            assert privacy[0]["request"]["client_ip"] != privacy[0]["request"]["remote_ip"]
            assert "secret" not in content
            assert privacy[0]["referrer"] == "https://example.com"
            assert "headers" not in privacy[0]["request"]
            print("Caddy checks passed: forwarded IP/spoof handling, private fields, feeds, 304, legacy redirect")
        finally:
            for container in reversed(containers):
                subprocess.run(["docker", "rm", "-f", container], capture_output=True)
            subprocess.run(["docker", "network", "rm", network], capture_output=True)


if __name__ == "__main__":
    main()
