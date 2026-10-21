"""Uptime checks for the EMode demo and the services it depends on (emode-photonix/emode#654).

Run by .github/workflows/uptime.yml every 10 minutes. Exits non-zero when any
check fails, so GitHub emails the failure. Prints one line per check.
"""

from __future__ import annotations

import datetime as dt
import json
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request

LM = 'https://lm.emodephotonix.com'
SITE = 'https://emodephotonix.com'
TIMEOUT_S = 15
SLOW_S = 5.0
CERT_MIN_DAYS = 14


def request(url: str, method: str = 'GET', body: dict | None = None) -> tuple[int, str, float]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={'Content-Type': 'application/json', 'User-Agent': 'emode-uptime'})
    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            return r.status, r.read().decode('utf-8', 'replace'), time.monotonic() - start
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace'), time.monotonic() - start


def heartbeat(base: str) -> str | None:
    status, text, took = request(f'{base}/user/heartbeat', 'POST', {'session_id': 'uptime-probe', 'email': 'uptime@example.invalid'})
    if status != 401 or 'error' not in text:
        return f'expected 401 JSON, got {status}: {text[:120]}'
    if took > SLOW_S:
        return f'answered in {took:.1f} s'
    return None


def license_api() -> str | None:
    status, text, _ = request(f'{LM}/license_summary?email=uptime@example.invalid')
    return None if status == 401 else f'expected 401 without credentials, got {status}: {text[:120]}'


def home() -> str | None:
    status, _, took = request(f'{SITE}/')
    if status != 200:
        return f'expected 200, got {status}'
    return f'answered in {took:.1f} s' if took > 3 * SLOW_S else None


def versions() -> str | None:
    status, text, _ = request(f'{SITE}/wp-json/custom/v1/versions/')
    if status != 200:
        return f'expected 200, got {status}'
    data = json.loads(text)
    latest = data.get('latest')
    platforms = {p for v in data.get('versions', {}).values() for p in v}
    if not latest or 'Linux-rslab' not in platforms:
        return f'latest={latest!r}, Linux-rslab listed: {"Linux-rslab" in platforms} (the Spaces manifest may be unreadable)'
    return None


def login_restricted() -> str | None:
    status, text, _ = request(f'{SITE}/wp-json/custom/v1/login/', 'POST', {})
    return None if status == 403 else f'expected 403 for an outside address, got {status}: {text[:120]}'


def cert_days(host: str) -> str | None:
    ctx = ssl.create_default_context()
    with socket.create_connection((host, 443), timeout=TIMEOUT_S) as s, ctx.wrap_socket(s, server_hostname=host) as t:
        not_after = t.getpeercert()['notAfter']
    expires = dt.datetime.strptime(not_after, '%b %d %H:%M:%S %Y %Z').replace(tzinfo=dt.timezone.utc)
    days = (expires - dt.datetime.now(dt.timezone.utc)).days
    return None if days > CERT_MIN_DAYS else f'certificate expires in {days} days ({expires:%Y-%m-%d})'


CHECKS = {
    'license server heartbeat': lambda: heartbeat(LM),
    'demo license server heartbeat': lambda: heartbeat(f'{LM}/demo'),
    'license API': license_api,
    'website home page': home,
    'versions list and Spaces manifest': versions,
    'WordPress /login/ refuses outsiders': login_restricted,
    'lm.emodephotonix.com certificate': lambda: cert_days('lm.emodephotonix.com'),
    'emodephotonix.com certificate': lambda: cert_days('emodephotonix.com'),
}


def main() -> int:
    failed = 0
    for name, check in CHECKS.items():
        try:
            problem = check()
        except Exception as e:  # a check that cannot run is a failure too
            problem = f'{type(e).__name__}: {e}'
        print(f'{"FAIL" if problem else "ok  "} {name}' + (f': {problem}' if problem else ''))
        if problem:
            failed += 1
            print(f'::error title={name}::{problem}')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
