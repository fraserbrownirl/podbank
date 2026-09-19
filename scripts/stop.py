#!/usr/bin/env python3
"""Stop the dolphinpod worker by stopping the Vast instance.

Vast execute only allows ls/rm/du — it cannot run ./dolphinpod-worker stop.
PUT state=stopped halts the container (worker dies). Disk is kept; GPU billing stops.
Does not destroy the instance. Does not touch non-dolphinpod labels.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deploy import V0, LABEL, VastHTTP, api, get_instance, list_instances, load_key  # noqa: E402


def main() -> None:
    key = load_key()
    ids = [i.get("id") for i in list_instances(key) if LABEL in (i.get("label") or "")]
    if not ids:
        sys.exit("no dolphinpod instance")
    for iid in ids:
        print("stop instance (halts worker)", iid)
        try:
            res = api(
                "PUT",
                f"{V0}/instances/{iid}/",
                key,
                {"client_id": "me", "state": "stopped"},
            )
        except VastHTTP as e:
            sys.exit(f"stop failed: {e.code} {e.body[:400]}")
        print("api", res)
        for _ in range(24):
            time.sleep(5)
            row = get_instance(key, iid) or {}
            actual = row.get("actual_status")
            print(
                "status",
                "actual=",
                actual,
                "intended=",
                row.get("intended_status"),
                "cur=",
                row.get("cur_state"),
                "next=",
                row.get("next_state"),
            )
            if actual in ("stopped", "exited") or row.get("cur_state") == "stopped":
                print("worker is down. instance kept (disk still billed). DELETE to destroy.")
                return
        print("still running after stop — Vast did not halt. run: python3 scripts/destroy.py")


if __name__ == "__main__":
    main()
