#!/usr/bin/env python3
"""Status + logs for the dolphinpod Vast box. HTTP only. Redacts secrets."""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deploy import V0, LABEL, VastHTTP, api, get_instance, list_instances, load_key  # noqa: E402

KEEP = (
    "id",
    "actual_status",
    "cur_state",
    "intended_status",
    "status_msg",
    "gpu_name",
    "label",
    "geolocation",
    "public_ipaddr",
    "dph_total",
    "machine_id",
    "image_uuid",
)
REDACT = re.compile(
    r"(https://v2\.dphn\.ai/api/worker/bootstrap/[^\s\"']+|dp-[A-Za-z0-9_-]+|Bearer\s+\S+)",
    re.I,
)


def scrub(s: str) -> str:
    return REDACT.sub("[redacted]", s)


def fetch_url(url: str, timeout: int = 30) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read().decode(errors="replace")


def wait_result(url: str, tries: int = 8) -> str:
    last = ""
    for _ in range(tries):
        time.sleep(3)
        try:
            last = fetch_url(url)
        except Exception as e:
            last = str(e)
            continue
        if last.strip():
            return last
    return last


def main() -> None:
    key = load_key()
    print(f"vast key present (len {len(key)})")
    target = None
    for i in list_instances(key):
        lab = i.get("label") or ""
        print(
            i.get("id"),
            i.get("actual_status"),
            i.get("cur_state"),
            i.get("gpu_name"),
            lab or "(no label)",
            "m" + str(i.get("machine_id")),
        )
        if LABEL in lab:
            target = i.get("id")
    if not target:
        sys.exit("no dolphinpod instance")
    row = get_instance(key, target) or {}
    slim = {k: row.get(k) for k in KEEP}
    ip = str(slim.get("public_ipaddr") or "")
    if ip.startswith("47."):
        slim["egress_risk"] = "47.x"
    print("detail", json.dumps(slim, default=str))

    try:
        logs = api(
            "PUT",
            f"{V0}/instances/request_logs/{target}/",
            key,
            {"tail": "200"},
        )
        url = logs.get("result_url")
        print("container logs url present:", bool(url))
        if url:
            print("--- container logs ---")
            print(scrub(wait_result(url))[-4000:])
    except VastHTTP as e:
        print("request_logs", e.code, e.body[:300])

    try:
        exe = api("PUT", f"{V0}/instances/command/{target}/", key, {"command": "ls -l"})
        url = exe.get("result_url")
        print("ls queued", exe.get("success"), "url present:", bool(url))
        if url:
            print("--- ls ---")
            print(scrub(wait_result(url, tries=10))[-2000:])
    except VastHTTP as e:
        print("execute ls", e.code, e.body[:400])


if __name__ == "__main__":
    main()
