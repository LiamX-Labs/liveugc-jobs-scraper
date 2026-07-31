#!/usr/bin/env python3
"""
Refresh the job feed.

Pulls the latest listings from the upstream feed, keeps everything posted on or
after START_DATE, merges them into data/jobs.json (newest first, de-duplicated),
and writes the file back. Run on a schedule so new listings accumulate over time.

The upstream feed base URL is provided via the FEED_BASE environment variable so
it never lives in the source tree. Nothing else here is feed-specific.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

DATA_FILE = Path(__file__).parent / "data" / "jobs.json"
START_DATE = os.environ.get("START_DATE", "2026-07-20")
PAGE_LIMIT = 100
MAX_PAGES = 200
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def _base() -> str:
    base = os.environ.get("FEED_BASE", "").strip().rstrip("/")
    if not base:
        sys.exit("FEED_BASE environment variable is required")
    return base


def _cutoff() -> datetime:
    return datetime.fromisoformat(START_DATE).replace(tzinfo=timezone.utc)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _get(base: str, page: int) -> dict:
    url = f"{base}/api/jobs?page={page}&limit={PAGE_LIMIT}"
    req = Request(url, headers={**REQUEST_HEADERS, "Referer": base + "/"})
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _clean_apply_url(raw: str | None, feed_host: str) -> str | None:
    """Keep the original marketplace apply link, but never expose an upstream
    URL: drop any link whose host matches the feed we pull from."""
    if not raw:
        return None
    host = urlsplit(raw).netloc.lower()
    if not host or feed_host in host or host in feed_host:
        return None
    return raw


def _shape(job: dict, feed_host: str) -> dict | None:
    title = (job.get("title") or "").strip()
    if not title or job.get("is_active") is False:
        return None
    posted = job.get("posted_at") or job.get("created_at")
    return {
        "id": str(job.get("unique_id") or job.get("ugc_jobs_url") or title),
        "title": title,
        "company": (job.get("company") or "").strip() or None,
        "location": (job.get("location") or "").strip() or None,
        "pay": (job.get("pay") or job.get("pay_range") or "").strip() or None,
        "category": (job.get("category") or "").strip() or None,
        "description": (job.get("description") or "").strip() or None,
        "posted_at": posted,
        "apply_url": _clean_apply_url(job.get("source_url"), feed_host),
    }


def fetch_since(cutoff: datetime) -> list[dict]:
    base = _base()
    feed_host = urlsplit(base).netloc.lower()
    out: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        data = _get(base, page)
        jobs = data.get("jobs") or []
        if not jobs:
            break
        stop = False
        for job in jobs:
            dt = _parse_dt(job.get("posted_at") or job.get("created_at"))
            if dt is not None and dt < cutoff:
                stop = True
                continue
            shaped = _shape(job, feed_host)
            if shaped:
                out.append(shaped)
        if stop or not data.get("pagination", {}).get("hasNextPage"):
            break
        time.sleep(0.4)
    return out


def load_existing() -> list[dict]:
    if not DATA_FILE.exists():
        return []
    try:
        return json.loads(DATA_FILE.read_text()).get("jobs", [])
    except (json.JSONDecodeError, AttributeError):
        return []


def _sort_key(job: dict):
    dt = _parse_dt(job.get("posted_at"))
    return dt or datetime.min.replace(tzinfo=timezone.utc)


def main() -> None:
    cutoff = _cutoff()
    fresh = fetch_since(cutoff)
    merged: dict[str, dict] = {j["id"]: j for j in load_existing()}
    added = 0
    for job in fresh:
        if job["id"] not in merged:
            added += 1
        merged[job["id"]] = job
    jobs = sorted(merged.values(), key=_sort_key, reverse=True)
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(
        json.dumps(
            {
                "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "count": len(jobs),
                "jobs": jobs,
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    print(f"fetched {len(fresh)} in-window, {added} new, {len(jobs)} total")


if __name__ == "__main__":
    main()
