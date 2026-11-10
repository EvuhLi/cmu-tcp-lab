# Project 2 Lab Report: TCP Meets the Real World

**Name(s):** Eva Li
**Algorithm name (leaderboard):** _TODO_

> Skeleton only. Every `_TODO_` is yours to write. Numbers in the tables are
> copied from `results/`; re-run before submitting and update them.
> Rubric (per section): Before and after (4), Why Reno struggles (6),
> Your design (10). Honest analysis of a partial design earns full credit.

---

## 1. Bufferbloat

### 1.1 Before and after

Local test: 4 Mbps uplink, 20 ms RTT, 30-packet router buffer, 2 MB upload.

| Build | Score | Goodput (Mbps, of 3.88) | Lag p20 / p50 / p95 (ms, target 18.4) | Router drops |
|---|---|---|---|---|
| Checkpoint 2 (`--build baseline`) | 31.5 | 2.18 | 21.2 / 31.4 / 133.1 | 14 |
| My design (`bufferbloat/`) | _TODO_ | _TODO_ | _TODO_ | _TODO_ |

Gradescope: B1 _TODO_ · B2 _TODO_ · B3 _TODO_

### 1.2 Why Reno struggles

_TODO: your explanation, pointing at the evidence below._

Evidence you can cite (baseline run):

- Router queue: two packets of queue at t ≈ 0–0.5 s, then empty until ≈ 3.5 s,
  then hovering around 15 packets with peaks at 30 (see `summary.txt`).
- Test tips: first drop at t = 0.18 s; link used 59%; queue empty 40% of the time.
- gdrive sender cwnd log (`results/cwnd_bb/gdrive-initiator-*.csv`): max cwnd
  94,875 bytes; 5 × 3-dup-ACK; 1 timeout at t ≈ 3.43 s.

_Optional figure: gdrive cwnd over time, with router queue._

### 1.3 My design

_TODO: congestion signal, how it is measured, window update rule, parameters._

_TODO: why it fixes the problem; where it works (local, B1–B3) and where it
falls short._

---

## 2. Incast

### 2.1 Before and after

Local test: 8 workers × 64 KB, 10 Mbps link, 10 ms RTT, 24-packet switch buffer.

| Build | Score | Completion (s, ideal 0.44) | Packets sent / needed | Switch drops |
|---|---|---|---|---|
| Checkpoint 2 (`--build baseline`) | 7.1 | 6.41 | 443 / 384 | 44 |
| My design (`incast/`) | _TODO_ | _TODO_ | _TODO_ | _TODO_ |

Gradescope: I1 _TODO_ · I2 _TODO_ · I3 _TODO_

### 2.2 Why Reno struggles

_TODO: your explanation, pointing at the evidence below._

Evidence you can cite (baseline run):

- Per-reply completion (s): 3.37 3.39 3.39 3.39 3.41 6.33 6.39 6.41.
- 44 drops in the burst at t ≈ 0; test tip: room for ~33 packets in flight.
- Worker cwnd logs (`results/cwnd_incast/incast-initiator-*.csv`, re-run):
  every one of the 8 workers had a timeout at t ≈ 3.2–3.3 s; one had a second
  at 6.36 s. Each had 1–2 × 3-dup-ACK. Max cwnd per worker 12–15 KB.

### 2.3 My design

_TODO: how the receiver side decides the total allowed in flight, how it is
divided among connections, how waiting senders are told they may send._

_TODO: why it fixes the problem; where it works (local, I1–I3) and where it
falls short._

---

## 3. Packet Spraying (optional)

_Not attempted / TODO._
