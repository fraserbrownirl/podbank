# podbank

Bankr custom skill for a [Dolphin Network](https://v2.dphn.ai) GPU node on Vast.ai. HTTP only. Prepaid Vast credit. No SSH.

## Upload to Bankr

1. Put `VAST_API_KEY` in the Bankr agent env. Optional: `DOLPHINPOD_API_KEY` for on-start `worker.json` if no Worker Link is pasted.
2. Upload **`SKILL.md`** as a custom skill (replace any older `podminer` / `dolphin-node` copy).
3. Paste a fresh **Worker Link** from v2.dphn.ai into Bankr chat and tell it to bring a node up.

`DOLPHINPOD_API_KEY` (`dp-…`) authenticates `dolphinpod-worker`. It does not mint a Worker Link.

## Local (Mac/CI — not the Bankr sandbox)

```bash
export VAST_API_KEY=…   # do not echo
python3 scripts/rank_hosts.py
python3 scripts/deploy.py '<Worker Link>'
python3 scripts/status.py
python3 scripts/stop.py      # soft-stop; DELETE if still running
python3 scripts/destroy.py   # kills the worker (only label=dolphinpod)
```

## Files

| Path | Role |
|---|---|
| `SKILL.md` | Upload this to Bankr |
| `onstart.sh` | Vast on-start template (`__LINK__`) |
| `scripts/deploy.py` | Rent + bootstrap |
| `scripts/status.py` | Status + `request_logs` |
| `scripts/stop.py` | `PUT state=stopped` |
| `scripts/destroy.py` | `DELETE` dolphinpod instance |
| `scripts/rank_hosts.py` | Same ranking as the skill |
