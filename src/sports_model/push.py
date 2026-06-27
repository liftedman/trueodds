"""Push the latest prediction snapshot to Supabase.

Builds the same JSON the web dashboard uses (ratings, model params, fixtures,
live scores) and upserts it as a single row (id='latest') into the `snapshot`
table. A scheduled job runs this; apps read the row and render/compute from it.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import requests

from . import config, report


def push_snapshot() -> None:
    url = config.supabase_url()
    key = config.supabase_key()
    if not url or not key:
        raise SystemExit(
            "Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env first "
            "(see .env.example and docs/supabase_schema.sql).")

    data = report._build_data()
    payload = {
        "id": "latest",
        "data": data,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    resp = requests.post(
        f"{url.rstrip('/')}/rest/v1/snapshot",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
        data=json.dumps(payload),
        timeout=90,
    )
    if resp.status_code == 404:
        raise SystemExit(
            "Supabase returned 404 for the 'snapshot' table — it doesn't exist "
            "yet. Open your Supabase project → SQL Editor, paste "
            "docs/supabase_schema.sql, and Run. Then try `push` again.")
    if resp.status_code in (401, 403):
        raise SystemExit(
            "Supabase rejected the key (401/403). Make sure SUPABASE_SERVICE_KEY "
            "is the service_role key (not the anon key).")
    resp.raise_for_status()
    size = len(json.dumps(data))
    print(f"Pushed snapshot ({size:,} bytes) to Supabase at "
          f"{payload['updated_at']}")


if __name__ == "__main__":
    push_snapshot()
