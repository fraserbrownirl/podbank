---
name: dolphin-node
description: >
  Bring a Dolphin Network GPU node live on Vast.ai via HTTP only (no SSH).
  Use when renting a Vast GPU, choosing a box, starting dolphinpod-worker,
  checking status, stopping, or destroying a dolphinpod rental. Pay = prepaid Vast
  credit only (never on-chain). Never use V-Pod, RunPod, or Lium.
visibility: private
---

# Dolphin node operator (Bankr)

- Operating wallet: `0xbd678e425178037a6ca89fbd79ce26aff2c0ec69`.
- Node rewards / dashboard wallet: `0xdA48369fc07f309C7C27e7039624d4fF3799ecB9` (https://v2.dphn.ai).
- Model: `nvidia/Qwen3.6-35B-A3B-NVFP4`.
- Binary: `https://updates.dphn.ai/dolphinpod-worker-v2_linux_amd64` (v2 / vllm 0.23.0).

## Your sandbox = HTTP only
You have `$VAST_API_KEY`, optional `$DOLPHINPOD_API_KEY`, `$OPS_SSH_PUBKEY`, `call_http_endpoint`, `browse_url`.
**No ssh, no python, no jq, no package manager.**
You cannot SSH in to run bootstrap, `nvidia-smi`, or `nohup`. Bake the entire deploy into the Vast
**on-start** script. The box self-enrolls at boot. Ready = v2.dphn.ai **Active Nodes** 0→1.
`runtype: ssh` is Vast’s launch mode (ports). You still do not SSH.

**At setup, read `$OPS_SSH_PUBKEY` from env and inject it into the on-start** (substitute it for
`__OPS_PUBKEY__`; see §On-start self-boot). You can't SSH, but the human operator can — this is how
they read `/workspace/selfboot.log`, run `status`/`logs`, or `start --debug` when a node misbehaves.
`$OPS_SSH_PUBKEY` is a **public** key (safe to place in on-start); never inject a private key.
If it's unset, omit the SSH block and proceed.

## Marketplace — Vast only
Rent **only** on Vast.ai. Prepaid credit on cloud.vast.ai/billing.

**Never** V-Pod (v-pod.com), RunPod, Lium, or any SSH that is `ssh.runpod.io`. V-Pod returns
RunPod-proxy boxes; our key cannot open them; spend is burned. If it is not a Vast `ask` id, skip it.
Do not follow dphn.ai “we recommend Lium.”

## #1 rule — enroll the worker (pick one)

**A — Worker Link (default when the human pastes one).** Brand-new signed URL from v2.dphn.ai → Worker Link:

`https://v2.dphn.ai/api/worker/bootstrap/<uuid>?owner=…&exp=…&sig=…`

- You CANNOT mint it. It needs a wallet SIWE session; the `dp-` key returns `401` on the mint API.
- Human clicks Worker Link, **pastes the URL in this chat**, you rent **immediately** on a **new** box. First boot is the only time on-start runs.
- The Worker Link is **not** `$DOLPHINPOD_API_KEY` and **not** an env you poll later. If the human puts the URL in env, do **not** rent first and `PUT` on-start afterwards. On-start on a live contract does not re-run. That box will never enroll.
- The link is **single-use AND time-limited**: the first successful `bootstrap` consumes it (worker then runs on stored credentials); the signed URL also expires (`exp`, ~24-40 min). Reusing a spent/expired link fails. Mint FRESH, use ONCE, immediately. Do not patch on-start on an already-`running` instance.
- Bake into on-start **in the rent `PUT /asks/` body**, called **exactly once** (see §On-start self-boot — NEVER loop `bootstrap`, it self-supervises): `./dolphinpod-worker bootstrap "<url>" background`.

**B — durable worker.json (only if no fresh link AND `$DOLPHINPOD_API_KEY` is set).**
`dp-` authenticates the binary on the GPU. It does **not** mint a Worker Link. Bake this into
on-start (not into Bankr chat):

```bash
mkdir -p /root/.config/dolphinpod
umask 077
printf '{"api_key":"%s"}\n' "__DP_KEY__" > /root/.config/dolphinpod/worker.json
./dolphinpod-worker start >> /workspace/selfboot.log 2>&1
```

Prefer A when a link is pasted so a long-lived `dp-` is not stored in Vast `onstart` metadata.

## Never
- Leak: SSH private key, `DOLPHINPOD_API_KEY`, the Worker Link, jupyter token. Do not echo them.
- Pay for compute on-chain (x402 / USDC / any external address). **Vast is PREPAID CREDIT only.**
- Rent from V-Pod / RunPod / Lium.
- Rent a second **dolphinpod** box while one is running — destroy the dolphinpod instance first.
- Destroy Vast instances whose `label` is **not** `dolphinpod`. This account may have other rentals. Leave them.
- Rent an SM<8.9 GPU for this model (see Hardware). Ignore dphn.ai lists that still name A100 / 3090.
- Run the worker binary or `bootstrap` inside your sandbox — it runs on the box via on-start.
- Call Vast `execute` with `./dolphinpod-worker stop` (or tail/ps/nvidia-smi). Whitelist is `ls` / `rm` / `du` only; anything else is 400 `Invalid command given.`
- Read a Worker Link from env and attach it to an instance that already has `start_date`. Rent and bootstrap are one `PUT /asks/`.

## HOW TO CHOOSE A BOX  ← this is where every wheel-spin happened; get it right
**Rank on Vast's own reliability signals, NOT price.** The cheap ~$0.97 hosts are junk; a reliable box
is ~$1.5–1.8 and worth it. Cheap hosts: 40-min image pulls, apt-build stuck, `runtime install: unexpected EOF`.

**Hard filters — put these in the search `q`:**
- `reliability2 ≥ 0.99` — Vast's uptime score. Junk hosts sit at ~0.93 and drop mid-deploy.
- `disk_bw ≥ 2000` (MB/s) — **THE hidden killer.** Slow disk causes BOTH 40-min image pulls AND
  truncated runtime installs (`runtime install: unexpected EOF` → endless crash-loop).
- `inet_down ≥ 1000` (Mbps) — low bandwidth = 40+ min image pull.
- `gpu_ram ≥ 92000` (96 GB class). Model needs ≥70 GB VRAM; a single 32 GB card OOMs.
  If this search is empty, retry `gpu_ram ≥ 70000` (H100 80 GB) still with `compute_cap ≥ 89`.
- `disk_space ≥ 160` — **always request `disk: 160`.** 80 GB fills (weights + runtime + compile caches). 100 is tight.
- `compute_cap ≥ 89`
- `verified: true`, `rentable: true`, `num_gpus: 1`, `type: on-demand`, `dph_total ≤ 2.2`.
- `order: [["reliability2","desc"]]`.

Exact search body (Tier A):
```json
{"q":{"verified":{"eq":true},"rentable":{"eq":true},"num_gpus":{"eq":1},
  "type":"on-demand","gpu_ram":{"gte":92000},"disk_space":{"gte":160},
  "compute_cap":{"gte":89},"reliability2":{"gte":0.99},"disk_bw":{"gte":2000},
  "inet_down":{"gte":1000},"dph_total":{"lte":2.2},
  "order":[["reliability2","desc"]],"limit":40}}
```

**Then filter/rank client-side (the API can't express these):**
- Drop any `public_ipaddr` in `47.0.0.0/8` — Alibaba/CN, blocked HF/Google egress. **US/KR/AE country
  flags do NOT clear this.** Third 47.x skip → keep walking the ranked list; do not retry 47.x.
- Drop SM<8.9 GPUs (A100/A800 SM8.0, A6000/3090 SM8.6) and names containing those strings.
  Vast may store RTX PRO 6000 SM12.0 as `120` or `1200`; both pass. A100 is `80`.
- Skip blacklisted `machine_id`s. Known bad: **`148418`** (slow pull + EOF crash-loop).
- Rank survivors: `reliability2` first, then `disk_bw` + `inet_down`, `dph_total` breaks ties.

**Tiered fallback — so you never spin on junk AND never come back empty:**
| Tier | reliability2 | disk_bw | inet_down | $/hr |
|------|-------------|---------|-----------|------|
| A (best)  | ≥ 0.99  | ≥ 2000 | ≥ 1000 | ≤ 2.2 |
| B (solid) | ≥ 0.985 | ≥ 1500 | ≥ 700  | ≤ 1.7 |
| C (ok)    | ≥ 0.98  | ≥ 1000 | ≥ 500  | ≤ 1.4 |
Try A first; only drop to B, then C, if the higher tier returns nothing. **Never go below C.**

**Egress defense for your sandbox:** you can't post-SSH curl-check HF/Google, so
`reliability2 ≥ 0.99` + `verified` + not-`47.x` IS your egress gate.
(The on-start script also self-aborts if HF is unreachable.)

**Reality + rotation:** reliable RTX PRO 6000 supply is thin. Offers rotate constantly: if a rent
returns `no_such_ask`, take the NEXT offer down the ranked list — do not re-pick #1 and do not
drop your standards to grab something cheaper.

## Hardware (verified — worker v2 / vllm 0.23.0)
Model needs `modelopt_mixed` → compute capability ≥ 8.9, and ≥ 70 GB total VRAM.
- PASS: RTX PRO 6000 (96 GB, SM12.0), H100/H200 (SM9.0), 5090/B200/B300, 4090/L40/RTX 6000 Ada (SM8.9).
- FAIL: A100/A800 (SM8.0), A6000/3090 (SM8.6), any single 32 GB card.
- Real kits: 1× RTX PRO 6000 · 1× H100 80 · 2× 5090 · 2× L40 · 4× 4090.

## Vast API — header `Authorization: Bearer $VAST_API_KEY`
`onstart` max 4048 chars.

- Search: `PUT https://console.vast.ai/api/v0/search/asks/` body `{"q":{...}}` → `{offers:[...]}`
- Rent: `PUT https://console.vast.ai/api/v0/asks/<OFFER_ID>/` → `{success:true,new_contract:<INSTANCE_ID>}`
- List: `GET https://console.vast.ai/api/v1/instances?limit=25` (paginate `after_token`).
  **v0 collection `GET /api/v0/instances/` is 410 — do not call it.**
- Status: `GET https://console.vast.ai/api/v0/instances/<INSTANCE_ID>/`
  If 404/410, find that `id` in the v1 list. Track `new_contract` from the rent response.
  Print `actual_status`, `intended_status`, `cur_state`, `next_state` — they diverge during stop.
- Credit: `GET https://console.vast.ai/api/v0/users/current/` → `{credit}`
- Logs: `PUT https://console.vast.ai/api/v0/instances/request_logs/<ID>/` body `{"tail":"200"}` → `result_url` (S3). Wait a few seconds, GET the URL. This is how you read container logs with no SSH.
- Soft-stop: `PUT https://console.vast.ai/api/v0/instances/<ID>/` body `{"client_id":"me","state":"stopped"}`
- Destroy: `DELETE https://console.vast.ai/api/v0/instances/<INSTANCE_ID>/`

Poll trap: if `actual_status` is `exited`, `unknown`, or `offline`, it will never become `running`.
Destroy **that dolphinpod instance** and rent the next offer.

`actual_status=running` means the CUDA image booted. It is **not** Active Nodes. The ~24 GB model pull continues on-box; dashboard often stays 0 for 20–40 min. Crash-loop during that pull is normal.

## Stop the worker (HTTP only)  ← execute cannot run the binary

Human may say `./dolphinpod-worker stop`. **You cannot run that.**

`PUT /api/v0/instances/command/<ID>/` (`vastai execute`) is a **whitelist**: `ls`, `rm`, `du` only (max 512 chars).
`./dolphinpod-worker stop` → HTTP **400** `{"error":"invalid_args","msg":"Invalid command given."}`
Same 400 for `tail`, `ps`, `nvidia-smi`, `bash -c …`. Do not retry execute with a “simpler” worker command.

**Reliable stop = destroy the dolphinpod instance:**

```
DELETE https://console.vast.ai/api/v0/instances/<dolphinpod-id>/
```

Confirm via `GET /api/v1/instances` that no `label=dolphinpod` remains, and v2.dphn.ai **Active Nodes** → 0.

**Soft-stop (keep disk, halt GPU):**

```
PUT https://console.vast.ai/api/v0/instances/<id>/
{"client_id":"me","state":"stopped"}
```

- `client_id: me` is required. Body `{"state":"stopped"}` alone can return `{"success":true}` while `actual_status` stays `running` (no-op).
- `success: true` means Vast **accepted** the request, not that the container has halted. Poll `intended_status` vs `actual_status` for up to ~2 min.
- If still `running` after that, **DELETE**. Do not loop PUT stop.

Never destroy a non-`dolphinpod` label.

## On-start self-boot (`__LINK__` = the fresh Worker Link, `__OPS_PUBKEY__` = operator SSH pubkey)
Runs as root at boot. `HF_*` is the crash-loop fix (worker otherwise offline-resolves the cache
at the wrong path). Egress guard aborts on a firewalled host instead of half-enrolling.

**Do not `set -e`.** Bootstrap exiting during the 24 GB pull is normal; `set -e` kills on-start and the node never goes Active.
**Do not `sudo`.** Vast images are already root; `sudo` can hang on a tty/password and the worker never starts.
**Call `bootstrap` EXACTLY ONCE — NEVER in a loop.** `bootstrap` enrolls the worker and starts a
self-supervising background process (`dolphinpod-worker supervise`) that restarts the inference
backend on its own. A `while true; bootstrap; sleep 8` loop is FATAL for two compounding reasons —
this was the root cause of every "running but never Active" box:
1. **The Worker Link is single-use.** The first `bootstrap` consumes it; every later loop iteration
   re-runs a **spent** link. (See §#1 rule.)
2. **Each new `bootstrap` kills the running worker.** The supervisor is a grandchild of the loop, so
   it gets `SIGTERM` every ~8 s and never survives long enough to download the model — GPU stays cold
   (idle temp, 0 % util), the HF cache stays empty, `worker.log` freezes at `selected GPUs`, and the
   node never goes Active. (The real backend errors go to a UDS log, not `worker.log`; `start --debug`
   in the foreground is the only way to see them — hence SSH below.)

**SSH-inject for debugging (recommended).** Vast does NOT reliably inject account SSH keys into the
container, so without this you cannot SSH in to read `/workspace/selfboot.log`, run `status`/`logs`,
or `start --debug` to see the real backend error. Inject the operator's OWN pubkey, substituted at
rent time from a secret (`$OPS_SSH_PUBKEY` → `__OPS_PUBKEY__`) — NEVER a hardcoded personal key and
NEVER a private key: whoever holds the matching private key gets root on every node this skill spins
up. If `$OPS_SSH_PUBKEY` is unset, drop the SSH block entirely. (Repo is private, so a single
eng-owned ops pubkey inline is also acceptable — still never a private key.)

```bash
#!/bin/bash
# SSH-inject (omit this block if no operator pubkey). __OPS_PUBKEY__ = a PUBLIC key only.
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
# bootstrap ONCE — it self-supervises and restarts the backend on its own. Do NOT loop it.
echo "$(date -u +%FT%TZ) bootstrap start" >> /workspace/selfboot.log
./dolphinpod-worker bootstrap "__LINK__" background >> /workspace/selfboot.log 2>&1
echo "$(date -u +%FT%TZ) bootstrap exited $?" >> /workspace/selfboot.log
```
Rent body: `{"client_id":"me","image":"vastai/base-image:cuda-13.0.1-auto","disk":160,"runtype":"ssh","label":"dolphinpod","onstart":"<script above with __LINK__ and __OPS_PUBKEY__ replaced>"}`

**Verify/debug over SSH** (once the box is `running` and `__OPS_PUBKEY__` was injected):
`ssh -i <your_key> -p <ssh_port> root@<ssh_host>` then on the box:
`cd /workspace && ./dolphinpod-worker status` · `du -sh /root/.cache/dolphinpod-worker/cache`
(should grow toward ~15-24 GB) · `pgrep -af aphrodite` (backend up) ·
`nvidia-smi` (util/temp rise when the model loads) · for the real error, stop then
`./dolphinpod-worker stop && ./dolphinpod-worker start --debug` in the foreground.

## Go-live sequence
1. Human mints a FRESH Worker Link (wallet), or you use path B if `$DOLPHINPOD_API_KEY` is set and no link.
2. **Read `$OPS_SSH_PUBKEY` from env** and substitute it into the on-start `__OPS_PUBKEY__` (so the operator can SSH in for logs/debug later). If unset, drop the SSH block.
3. `GET /users/current/` — confirm credit.
4. `GET /api/v1/instances` — if a `label=dolphinpod` instance exists, `DELETE` it. Leave every other label.
5. Choose a box. `PUT /asks/<id>/` with the on-start (`__LINK__` + `__OPS_PUBKEY__` substituted, `bootstrap` called ONCE — never looped). Save `new_contract`.
6. Poll until `actual_status = running` (image pull). Then wait — the ~24 GB model pull continues on-box (20–40 min), then flashinfer JIT-compiles Blackwell kernels before the node registers.
7. Success = dashboard v2.dphn.ai **Active Nodes 0→1**. You cannot read the box log via execute. Confirm on the dashboard (or `request_logs` → `result_url`, or have the operator SSH in with their key).
8. Stop worker / teardown = `DELETE /instances/<that dolphinpod id>/`. Do not `execute` `./dolphinpod-worker stop`.

## Notes
- A crash-loop DURING the ~24 GB model download is normal; judge only after it finishes (often 20–40 min).
- Do not store live instance ids in this skill; they go stale. List via v1.
- An operator with SSH could run `./dolphinpod-worker stop` or read `/workspace/selfboot.log`. **You are not that operator.**
  Stop = DELETE. Logs = `request_logs`. Ready = dashboard.
