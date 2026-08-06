"""Push the Markets snapshot to Supabase.

Mirrors sports_model/push.py, but writes to a DIFFERENT row of the same
`snapshot` table: id='markets'. Two rows rather than one merged blob so the two
modes stay independent - Markets failing to build never takes Sports down with
it, and the app can load whichever mode the user opened without paying for both.

Reuses the sports side's SUPABASE_URL / SUPABASE_SERVICE_KEY, since it is the
same project and the same table.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import requests

from . import report

ROW_ID = "markets"


def _creds() -> tuple[str, str]:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise SystemExit(
            "Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env first "
            "(the same values the sports snapshot uses)."
        )
    return url, key


def push_snapshot(timeframes: list[str] | None = None) -> None:
    url, key = _creds()

    data = report.build_data(timeframes=timeframes)
    payload = {
        "id": ROW_ID,
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
            "Supabase returned 404 for the 'snapshot' table - run "
            "docs/supabase_schema.sql in the SQL Editor first."
        )
    if resp.status_code in (401, 403):
        raise SystemExit(
            "Supabase rejected the key (401/403). SUPABASE_SERVICE_KEY must be "
            "the service_role key, not the anon key."
        )
    resp.raise_for_status()

    size = len(json.dumps(data))
    print(f"Pushed markets snapshot ({size:,} bytes) as id='{ROW_ID}' at "
          f"{payload['updated_at']}")
    print()
    print(report.summarise(data))


if __name__ == "__main__":
    push_snapshot()
