---
name: dolphin-node
description: >
  Bring a Dolphin Network GPU node live on Vast.ai via HTTP only (no SSH).
  Use when renting a Vast GPU, choosing a box, enrolling dolphinpod-worker,
  checking status, stopping, or destroying a dolphinpod rental. Pay = prepaid
  Vast credit only (never on-chain). Never use V-Pod, RunPod, or Lium.
visibility: private
---

# Dolphin node operator (Bankr)

- Operating wallet: `0xbd678e425178037a6ca89fbd79ce26aff2c0ec69`.
- Rewards / dashboard wallet: `0xdA48369fc07f309C7C27e7039624d4fF3799ecB9` — dashboard at https://v2.dphn.ai.
- Model: **network-assigned** (the backend picks it; never set it yourself; e.g. `unsloth/Qwen3.8-27B-NVFP4`, ~22 GB).
- Worker binary: `https://updates.dphn.ai/dolphinpod-worker-v2_linux_amd64`.

## Core constraints (read first)

1. **You are HTTP only.** You have `$VAST_API_KEY`, optional `$DOLPHINPOD_API_KEY`, `$OPS_SSH_PUBKEY`, `call_http_endpoint`, `browse_url`. No ssh, python, jq, or package manager. You cannot run the worker binary, `bootstrap`, or `nvidia-smi` — the entire deploy goes in the Vast **on-start** script, which runs on the box at boot.
2. **On-start runs once, at first boot, and never again.** So `bootstrap` MUST be in the rent `PUT /asks/` body. Never rent first and add on-start after — that box never enrolls.
3. **Report configured vs. confirmed.** You cannot see inside the box. Describe on-start steps as "configured to run at boot", never "done/downloaded/active". State as fact only API fields (specs, `actual_status`, credit) and the dashboard. A box can be `actual_status: running` yet never enroll — confirm liveness ONLY via dashboard **Active Nodes 0→1**.
4. **Rent only on Vast.ai** (prepaid credit, cloud.vast.ai/billing). Never V-Pod, RunPod, Lium, or any `ssh.runpod.io` host. If it is not a Vast `ask` id, skip it. Ignore any dphn.ai "we recommend Lium".

## Enroll the worker — pick one path

**A — Worker Link (default when the human pastes one).**
`https://v2.dphn.ai/api/worker/bootstrap/<uuid>?owner=…&exp=…&sig=…`
- You cannot mint it (needs a wallet SIWE session; `dp-` returns 401 on the mint API). The human pastes it in chat.
- It is **single-use and time-limited** (`exp` ≈ 24–40 min): the first successful `bootstrap` consumes it, then the worker runs on stored credentials. Reusing a spent/expired link fails.
- So: rent **immediately** on a **new** box with a **fresh** link. Never attach a link to an already-`running` instance.
- On-start command: `./dolphinpod-worker bootstrap "<url>" background`.

**B — durable worker.json (only if no fresh link AND `$DOLPHINPOD_API_KEY` set).**
```bash
mkdir -p /root/.config/dolphinpod
umask 077
printf '{"api_key":"%s"}\n' "__DP_KEY__" > /root/.config/dolphinpod/worker.json
./dolphinpod-worker background >> /workspace/selfboot.log 2>&1
```
Prefer A when a link is pasted (avoids storing a long-lived `dp-` in Vast on-start metadata).

**Both paths: call the worker EXACTLY ONCE — never in a loop.** One call self-supervises and restarts the backend on its own. A `while true; bootstrap; sleep` loop is fatal: it re-runs a spent link AND kills the live worker each iteration, so the model never finishes loading.

## On-start script

`__LINK__` = fresh Worker Link. `__OPS_PUBKEY__` = operator's SSH **public** key from `$OPS_SSH_PUBKEY` (substitute at rent time). Max 4048 chars. Rules baked in below:
- SSH-inject first, so the operator can SSH in to debug even if enroll fails. Vast does not reliably inject account keys; this is the only way in. Public key only — never a private key. If `$OPS_SSH_PUBKEY` is unset, drop that block.
- `HF_*` vars are required (worker otherwise resolves the cache at the wrong path and crash-loops).
- Egress guard aborts on a firewalled host instead of half-enrolling.
- No `set -e` (bootstrap exiting mid-pull is normal). No `sudo` (already root; sudo can hang).

```bash
#!/bin/bash
# SSH-inject (omit block if no operator pubkey) — PUBLIC key only
mkdir -p /root/.ssh && chmod 700 /root/.ssh
echo "__OPS_PUBKEY__" >> /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
mkdir -p /workspace && cd /workspace
export HF_HOME=/root/.cache/dolphinpod-worker/cache
export HF_HUB_CACHE=/root/.cache/dolphinpod-worker/cache/hub
export HF_HUB_OFFLINE=0
curl -fL --progress-bar "https://updates.dphn.ai/dolphinpod-worker-v2_linux_amd64" -o dolphinpod-worker
chmod +x dolphinpod-worker
code=$(curl -4 -s --max-time 8 -o /dev/null -w '%{http_code}' https://huggingface.co || true)
case "$code" in
  200|301|302|307|308) ;;
  *) echo "EGRESS FAIL http=$code" > /workspace/selfboot.log; exit 0 ;;
esac
# bootstrap ONCE — self-supervises. Never loop it.
echo "$(date -u +%FT%TZ) bootstrap start" >> /workspace/selfboot.log
./dolphinpod-worker bootstrap "__LINK__" background >> /workspace/selfboot.log 2>&1
echo "$(date -u +%FT%TZ) bootstrap exited $?" >> /workspace/selfboot.log
```
Rent body: `{"client_id":"me","image":"vastai/base-image:cuda-13.0.1-auto","disk":160,"runtype":"ssh","label":"dolphinpod","onstart":"<script with __LINK__ and __OPS_PUBKEY__ substituted>"}`

## Choose a box — rank on reliability, not price

Cheap (~$0.97) hosts are junk (40-min pulls, `runtime install: unexpected EOF`, crash-loops). A good box is ~$1.5–1.8.

Search: `PUT https://console.vast.ai/api/v0/search/asks/`
```json
{"q":{"verified":{"eq":true},"rentable":{"eq":true},"num_gpus":{"eq":1},
  "type":"on-demand","gpu_ram":{"gte":92000},"disk_space":{"gte":160},
  "compute_cap":{"gte":89},"reliability2":{"gte":0.99},"disk_bw":{"gte":2000},
  "inet_down":{"gte":1000},"dph_total":{"lte":2.2},
  "order":[["reliability2","desc"]],"limit":40}}
```
Filter rank / thresholds:
- `disk_bw` (MB/s) is the hidden killer — slow disk causes both 40-min pulls and truncated installs.
- `gpu_ram ≥ 92000` (96 GB). If empty, retry `≥ 70000` (H100 80 GB) still with `compute_cap ≥ 89`.
- Always request `disk: 160` (weights + runtime + compile caches; 100 is tight).

| Tier | reliability2 | disk_bw | inet_down | $/hr |
|------|-------------|---------|-----------|------|
| A | ≥ 0.99  | ≥ 2000 | ≥ 1000 | ≤ 2.2 |
| B | ≥ 0.985 | ≥ 1500 | ≥ 700  | ≤ 1.7 |
| C | ≥ 0.98  | ≥ 1000 | ≥ 500  | ≤ 1.4 |

Try A first; drop to B then C only if empty. Never below C.

Client-side (the API can't express these):
- Drop `public_ipaddr` in `47.0.0.0/8` (Alibaba/CN, blocked HF egress — country flag does not clear it). This + `reliability2 ≥ 0.99` + `verified` is your egress gate; you can't post-boot curl-check.
- Drop SM<8.9 GPUs. Vast stores RTX PRO 6000 SM12.0 as `120` or `1200` (both pass); A100 is `80`.
- Skip blacklisted machine_id `148418` (slow pull + EOF crash-loop).
- Rank: `reliability2`, then `disk_bw`+`inet_down`, then `dph_total`.
- On `no_such_ask`, take the NEXT offer down the list — do not re-pick #1 or lower your standards.

## Hardware
Model (NVFP4) needs compute capability ≥ 8.9 and ≥ 70 GB total VRAM.
- PASS: RTX PRO 6000 (96 GB, SM12.0), H100/H200 (SM9.0), 5090/B200/B300, 4090/L40/RTX 6000 Ada (SM8.9).
- FAIL: A100/A800 (SM8.0), A6000/3090 (SM8.6), any single 32 GB card. Ignore dphn.ai lists naming A100/3090.
- Real kits: 1× RTX PRO 6000 · 1× H100 80 · 2× 5090 · 2× L40 · 4× 4090.

## Vast API — header `Authorization: Bearer $VAST_API_KEY`
- Search: `PUT /api/v0/search/asks/` body `{"q":{...}}` → `{offers:[...]}`
- Rent: `PUT /api/v0/asks/<OFFER_ID>/` → `{success:true,new_contract:<INSTANCE_ID>}` (track `new_contract`)
- List: `GET /api/v1/instances?limit=25` (paginate `after_token`). v0 collection `GET /api/v0/instances/` is 410.
- Status: `GET /api/v0/instances/<ID>/` → `actual_status`, `intended_status`, `cur_state`, `next_state`.
- Credit: `GET /api/v0/users/current/` → `{credit}`
- Soft-stop: `PUT /api/v0/instances/<ID>/` body `{"client_id":"me","state":"stopped"}`
- Destroy: `DELETE /api/v0/instances/<ID>/`
- Logs: `PUT /api/v0/instances/request_logs/<ID>/` body `{"tail":"200"}` → `result_url` (GET after a few s). Captures STDOUT only (SSH-proxy noise + first on-start lines) — NOT `selfboot.log` or the backend log. Do not use it to confirm the worker; use the dashboard, or operator SSH.

Base URL: `https://console.vast.ai`.

Poll traps:
- `actual_status` = `exited`/`unknown`/`offline` → will never become `running`. Destroy and rent the next offer.
- `actual_status = running` means the CUDA image booted — NOT Active. The model pull (~22 GB, 20–40 min) then flashinfer JIT compile continue on-box before the node registers.

## Go-live sequence
1. Get a FRESH Worker Link (human), or use path B if `$DOLPHINPOD_API_KEY` is set and no link.
2. Read `$OPS_SSH_PUBKEY` from env → substitute into on-start `__OPS_PUBKEY__` (drop the block if unset).
3. `GET /users/current/` — confirm credit.
4. `GET /api/v1/instances` — if a `label=dolphinpod` instance exists, `DELETE` it. Leave all other labels.
5. Choose a box; `PUT /asks/<id>/` with the on-start (`__LINK__` + `__OPS_PUBKEY__` substituted). Save `new_contract`.
6. Poll to `actual_status = running`, then wait for the model pull + JIT (20–40 min). Report these as "in progress", not done.
7. Confirm success = dashboard **Active Nodes 0→1**.

## Stop / teardown
- You (agent) cannot run `./dolphinpod-worker stop`: Vast `execute` (`PUT /api/v0/instances/command/<ID>/`) is whitelist `ls`/`rm`/`du` only; anything else → 400 `Invalid command given`.
- Stop the worker = **destroy the instance**: `DELETE /api/v0/instances/<dolphinpod-id>/`. Confirm no `label=dolphinpod` remains and Active Nodes → 0.
- Soft-stop (keep disk, halt GPU): `PUT /api/v0/instances/<ID>/` `{"client_id":"me","state":"stopped"}`. `success:true` = accepted, not halted — poll `intended_status` vs `actual_status` up to ~2 min; if still `running`, DELETE. Do not loop PUT.
- The operator (holding the private key for the injected `$OPS_SSH_PUBKEY`) CAN SSH in to run `stop`/`start`/`status`/`logs`, read `/workspace/selfboot.log`, and `start --debug` for backend errors. You cannot.

## Never
- Leak secrets (SSH private key, `$DOLPHINPOD_API_KEY`, Worker Link, jupyter token) or echo them.
- Pay for compute on-chain (x402 / USDC / any address). Vast is prepaid credit only.
- Rent from V-Pod / RunPod / Lium.
- Rent a second `dolphinpod` box while one runs — destroy the existing one first.
- Destroy an instance whose `label` is not `dolphinpod` (the account has other rentals).
- Rent an SM<8.9 GPU.
- Loop `bootstrap`, or attach a link to an instance that already has `start_date`.
- Store live instance ids in this skill (list via v1).
