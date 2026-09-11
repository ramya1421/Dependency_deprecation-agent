"""Warmup script for Render free-tier cold starts.

Render free-tier instances spin down after 15 minutes of inactivity, causing
roughly a 50-second cold start on the next request. This script can be run
on a cron or pinged by an uptime monitor to keep the instance warm.

Usage:
    python scripts/warmup.py [--url https://your-app.onrender.com]

Behaviour:
- Hits /health and logs the response.
- Exits 0 on success, 1 on failure — suitable for CI or cron alerting.
- Does NOT trigger a scan or write any data; read-only.
"""
import argparse
import sys

import httpx

_DEFAULT_URL = "http://localhost:8000"


def warmup(base_url: str) -> bool:
    url = f"{base_url.rstrip('/')}/health"
    try:
        response = httpx.get(url, timeout=60.0)
        response.raise_for_status()
        data = response.json()
        print(f"OK  {url}  status={data.get('status')}  "
              f"qdrant={data.get('qdrant')}  llm={data.get('llm')}")
        return True
    except Exception as exc:
        print(f"FAIL  {url}  {exc}", file=sys.stderr)
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Warm up the DDA API")
    parser.add_argument("--url", default=_DEFAULT_URL, help="Base URL of the API")
    args = parser.parse_args()
    success = warmup(args.url)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
