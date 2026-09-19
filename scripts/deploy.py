#!/usr/bin/env python3
"""Rent a Vast GPU and self-boot dolphinpod-worker from a Worker Link.

Does not print the Worker Link, API key, or SSH secrets.
Does not touch instances that are not labeled dolphinpod.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEY_FILE = Path.home() / ".vast_api_key"
ENV_FILE = ROOT / ".env"
BLACKLIST = {148418}
FAIL_GPU = ("A100", "A800", "A6000", "3090")
IMAGE = "vastai/base-image:cuda-13.0.1-auto"
DISK = 160
LABEL = "dolphinpod"
WORKER_BIN = "https://updates.dphn.ai/dolphinpod-worker-v2_linux_amd64"
V0 = "https://console.vast.ai/api/v0"
V1 = "https://console.vast.ai/api/v1"
DEAD = {"exited", "unknown", "offline"}

TIERS = [
    dict(name="A-top", reliability2=0.99, inet_down=1000, disk_bw=2000, dph_max=2.2),
    dict(name="B-solid", reliability2=0.985, inet_down=700, disk_bw=1500, dph_max=1.7),
    dict(name="C-ok", reliability2=0.98, inet_down=500, disk_bw=1000, dph_max=1.4),
]


def load_key() -> str:
    key = ""
    if KEY_FILE.is_file():
        key = KEY_FILE.read_text().strip()
    if not key:
        for path in (ENV_FILE,):
            if not path.is_file():
                continue
            for line in path.read_text().splitlines():
                if line.startswith("VAST_API_KEY=") and not line.startswith("VAST_API_KEY=#"):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
            if key:
                break
    key = key or os.environ.get("VAST_API_KEY", "")
    if not key:
        sys.exit("Vast key missing (~/.vast_api_key or VAST_API_KEY)")
    return key


class VastHTTP(RuntimeError):
    def __init__(self, method: str, url: str, code: int, body: str):
        self.method, self.url, self.code, self.body = method, url, code, body
        super().__init__(f"Vast {method} {url} -> HTTP {code}: {body}")


def api(method: str, url: str, key: str, body=None, timeout=45):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        err = e.read().decode(errors="replace")[:800]
        raise VastHTTP(method, url, e.code, err) from e


def compute_cap(o) -> int:
    cc = o.get("compute_cap") or 0
    try:
        cc = float(cc)
    except (TypeError, ValueError):
        return 0
    if 0 < cc < 20:
        return int(round(cc * 10))
    return int(cc)


def usable(o) -> bool:
    ip = o.get("public_ipaddr") or ""
    name = (o.get("gpu_name") or "").upper()
    if ip.startswith("47."):
        return False
    if o.get("machine_id") in BLACKLIST:
        return False
    if any(x in name for x in FAIL_GPU):
        return False
    cc = compute_cap(o)
    if cc and cc < 89:
        return False
    return True


def score(o) -> float:
    return (
        o.get("reliability2", 0) * 100
        + min(o.get("disk_bw", 0), 20000) / 4000
        + min(o.get("inet_down", 0), 20000) / 4000
        - o.get("dph_total", 9) * 0.3
    )


def search_tier(key: str, t: dict) -> list:
    q = {
        "verified": {"eq": True},
        "rentable": {"eq": True},
        "num_gpus": {"eq": 1},
        "type": "on-demand",
        "gpu_ram": {"gte": 70000},
        "disk_space": {"gte": DISK},
        "compute_cap": {"gte": 89},
        "reliability2": {"gte": t["reliability2"]},
        "inet_down": {"gte": t["inet_down"]},
        "disk_bw": {"gte": t["disk_bw"]},
        "dph_total": {"lte": t["dph_max"]},
        "order": [["reliability2", "desc"]],
        "limit": 60,
    }
    return api("PUT", V0 + "/search/asks/", key, {"q": q}).get("offers") or []


def ranked(key: str) -> list:
    out, seen = [], set()
    for t in TIERS:
        offers = sorted([o for o in search_tier(key, t) if usable(o)], key=score, reverse=True)
        for o in offers:
            if o["id"] in seen:
                continue
            seen.add(o["id"])
            o["_tier"] = t["name"]
            out.append(o)
    return out


def onstart(link: str) -> str:
    # No `set -e`: crash-loop during the 24GB pull is normal; the worker must restart.
    # Vast images are root — do not `sudo` (can hang on a tty/password).
    quoted = json.dumps(link)
    return f"""#!/bin/bash
mkdir -p /workspace && cd /workspace
export HF_HOME=/root/.cache/dolphinpod-worker/cache
export HF_HUB_CACHE=/root/.cache/dolphinpod-worker/cache/hub
export HF_HUB_OFFLINE=0
curl -fL --progress-bar "{WORKER_BIN}" -o dolphinpod-worker
chmod +x dolphinpod-worker
code=$(curl -4 -s --max-time 8 -o /dev/null -w '%{{http_code}}' https://huggingface.co || true)
case "$code" in
  200|301|302|307|308) ;;
  *) echo "EGRESS FAIL http=$code" > /workspace/selfboot.log; exit 0 ;;
esac
while true; do
  echo "$(date -u +%FT%TZ) bootstrap start" >> /workspace/selfboot.log
  ./dolphinpod-worker bootstrap {quoted} >> /workspace/selfboot.log 2>&1
  echo "$(date -u +%FT%TZ) bootstrap exited $?" >> /workspace/selfboot.log
  sleep 8
done
"""


def list_instances(key: str) -> list:
    out, token = [], None
    while True:
        qs = {"limit": "25"}
        if token:
            qs["after_token"] = token
        url = V1 + "/instances?" + urllib.parse.urlencode(qs)
        d = api("GET", url, key)
        out.extend(d.get("instances") or [])
        token = d.get("next_token")
        if not token:
            break
    return out


def get_instance(key: str, iid) -> dict | None:
    try:
        st = api("GET", f"{V0}/instances/{iid}/", key)
    except VastHTTP as e:
        if e.code not in (404, 410):
            raise
        st = None
    if st:
        row = st.get("instances")
        if isinstance(row, list) and row:
            return row[0]
        if isinstance(row, dict):
            return row
        if isinstance(st, dict) and st.get("id") == iid:
            return st
    for row in list_instances(key):
        if row.get("id") == iid:
            return row
    return None


def main() -> None:
    if len(sys.argv) != 2 or "worker/bootstrap/" not in sys.argv[1]:
        sys.exit("usage: deploy.py <Worker Link from v2.dphn.ai>")
    link = sys.argv[1].strip().strip('"')
    key = load_key()
    print(f"vast key present (len {len(key)})")

    user = api("GET", V0 + "/users/current/", key)
    credit = user.get("credit") or user.get("balance") or user
    if isinstance(credit, dict):
        print("credit fields:", {k: credit.get(k) for k in list(credit)[:8]})
    else:
        print("vast credit:", credit)

    inst = list_instances(key)
    if not inst:
        print("no instances")
    for i in inst:
        print(
            i.get("id"),
            i.get("actual_status"),
            i.get("cur_state"),
            i.get("gpu_name"),
            i.get("label"),
            "m" + str(i.get("machine_id")),
        )
        lab = (i.get("label") or "")
        if LABEL in lab:
            iid = i.get("id")
            print(f"destroying existing {LABEL} instance {iid}")
            api("DELETE", f"{V0}/instances/{iid}/", key)
            time.sleep(2)

    offers = ranked(key)
    if not offers:
        sys.exit("no ranked offers (tiers A–C, SM>=8.9, not 47.x, not blacklist)")
    print("ranked offers:", len(offers))
    for o in offers[:8]:
        print(
            o.get("id"),
            f"{o.get('dph_total', 0):.3f}/hr",
            o.get("gpu_name"),
            f"rel2={o.get('reliability2')}",
            f"net={int(o.get('inet_down', 0))}",
            f"diskbw={int(o.get('disk_bw', 0))}",
            o.get("_tier"),
            o.get("geolocation"),
            "m" + str(o.get("machine_id")),
            f"sm={compute_cap(o)}",
        )

    last_err = None
    for o in offers[:6]:
        oid = o["id"]
        body = {
            "client_id": "me",
            "image": IMAGE,
            "disk": DISK,
            "runtype": "ssh",
            "label": LABEL,
            "onstart": onstart(link),
        }
        print(f"renting offer {oid} ({o.get('gpu_name')} {o.get('dph_total'):.3f}/hr {o.get('_tier')})")
        try:
            res = api("PUT", f"{V0}/asks/{oid}/", key, body)
        except VastHTTP as e:
            last_err = str(e)
            print("offer gone, next:", last_err[:200])
            continue
        iid = res.get("new_contract") or res.get("instance") or res.get("id")
        if not iid:
            print("unexpected rent response keys:", list(res)[:20])
            last_err = json.dumps({k: res[k] for k in list(res)[:12]})
            continue
        print("new_contract", iid)
        dead = False
        for _ in range(36):
            time.sleep(10)
            try:
                row = get_instance(key, iid)
            except VastHTTP as e:
                print("status poll:", str(e)[:200])
                continue
            if not row:
                print("status missing from v1 list; keep polling")
                continue
            actual = row.get("actual_status") or row.get("status") or ""
            print("status", actual, row.get("cur_state"), row.get("gpu_name"), row.get("status_msg") or "")
            if actual == "running":
                print("box running. model pull + worker bootstrap continue on-box.")
                print("watch Active Nodes on https://v2.dphn.ai (wallet 0xdA4836…ecB9)")
                return
            if actual in DEAD:
                print(f"box {actual} — destroy and try next offer")
                try:
                    api("DELETE", f"{V0}/instances/{iid}/", key)
                except VastHTTP as e:
                    print("destroy:", str(e)[:200])
                dead = True
                break
        if dead:
            continue
        print("still not running after poll window; leave it — pull can take a long time")
        return
    sys.exit(last_err or "all rent attempts failed")


if __name__ == "__main__":
    main()
