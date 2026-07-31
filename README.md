# LiveUGC jobs scraper

A lightweight, always-live feed of UGC jobs. Listings are refreshed automatically
twice a day and rendered as a simple public page, newest first.

- **Live page:** served via GitHub Pages (see repo settings → Pages).
- **Refresh:** `.github/workflows/refresh.yml` runs every 12 hours.
- **Data:** `data/jobs.json` (regenerated on each refresh).

## Local run

```bash
FEED_BASE="<feed base url>" python fetch.py
```

The upstream feed base URL is supplied only via the `FEED_BASE` environment
variable / repository secret and is never stored in the repo.
