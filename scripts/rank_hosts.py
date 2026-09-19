#!/usr/bin/env python3
"""Rank Vast offers for Dolphin Network dolphinpod-worker. Bankr cannot run this;
it is for a human/CI with VAST_API_KEY. Same filters as dolphin-node/SKILL.md."""
import json
import os
import urllib.request

KEY = os.environ["VAST_API_KEY"]
BLACKLIST = {148418}

TIERS = [
    dict(name="A-top", reliability2=0.99, inet_down=1000, disk_bw=2000, dph_max=2.2),
    dict(name="B-solid", reliability2=0.985, inet_down=700, disk_bw=1500, dph_max=1.7),
    dict(name="C-ok", reliability2=0.98, inet_down=500, disk_bw=1000, dph_max=1.4),
]


def _search(t):
    q = {
        "verified": {"eq": True},
        "rentable": {"eq": True},
        "num_gpus": {"eq": 1},
        "type": "on-demand",
        "gpu_ram": {"gte": 92000},
        "disk_space": {"gte": 160},
        "reliability2": {"gte": t["reliability2"]},
        "inet_down": {"gte": t["inet_down"]},
        "disk_bw": {"gte": t["disk_bw"]},
        "dph_total": {"lte": t["dph_max"]},
        "order": [["reliability2", "desc"]],
        "limit": 60,
    }
    req = urllib.request.Request(
        "https://console.vast.ai/api/v0/search/asks/",
        data=json.dumps({"q": q}).encode(),
        method="PUT",
        headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"},
    )
    return json.load(urllib.request.urlopen(req, timeout=30)).get("offers", [])


def _usable(o):
    ip = o.get("public_ipaddr") or ""
    return (o.get("geolocation") or "").endswith("US") and not ip.startswith("47.") and o.get("machine_id") not in BLACKLIST


def _score(o):
    return (
        o.get("reliability2", 0) * 100
        + min(o.get("disk_bw", 0), 20000) / 4000
        + min(o.get("inet_down", 0), 20000) / 4000
        - o.get("dph_total", 9) * 0.3
    )


def ranked():
    out, seen = [], set()
    for t in TIERS:
        for o in sorted([x for x in _search(t) if _usable(x)], key=_score, reverse=True):
            if o["id"] in seen:
                continue
            seen.add(o["id"])
            o["_tier"] = t["name"]
            out.append(o)
    return out


if __name__ == "__main__":
    r = ranked()
    print("reliable US hosts (tiered): %d" % len(r))
    print("%-9s %-6s %-7s %-7s %-8s %-7s %-7s %s" % ("id", "$/hr", "rel2", "net", "diskbw", "dur(d)", "tier", "geo | m"))
    for o in r[:15]:
        print(
            "%-9s %-6.3f %-7.4f %-7d %-8d %-7.0f %-7s %s | m%s"
            % (
                o.get("id"),
                o.get("dph_total", 0),
                o.get("reliability2", 0),
                int(o.get("inet_down", 0)),
                int(o.get("disk_bw", 0)),
                o.get("duration", 0) / 86400,
                o.get("_tier"),
                o.get("geolocation"),
                o.get("machine_id"),
            )
        )
