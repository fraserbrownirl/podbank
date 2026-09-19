#!/usr/bin/env python3
"""Destroy the dolphinpod Vast instance. Worker dies. GPU + disk billing stop.
Does not touch instances whose label is not dolphinpod.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deploy import V0, LABEL, VastHTTP, api, list_instances, load_key  # noqa: E402


def main() -> None:
    key = load_key()
    ids = [i.get("id") for i in list_instances(key) if LABEL in (i.get("label") or "")]
    if not ids:
        sys.exit("no dolphinpod instance")
    for iid in ids:
        print("destroy", iid)
        try:
            res = api("DELETE", f"{V0}/instances/{iid}/", key)
        except VastHTTP as e:
            sys.exit(f"destroy failed: {e.code} {e.body[:400]}")
        print("api", res)
    time.sleep(3)
    left = [i.get("id") for i in list_instances(key) if LABEL in (i.get("label") or "")]
    print("dolphinpod remaining:", left or "none")


if __name__ == "__main__":
    main()
