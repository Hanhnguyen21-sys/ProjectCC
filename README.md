## E1 — TCP Reno Congestion Window over a Bottleneck Link

### 1. Regenerating the Plot

**Requirements:** Python ≥ 3.8 and matplotlib.

Install matplotlib:

```bash
pip install matplotlib
```

Run the following command from the `project-cc` directory. It reads every
`data/e1/e1_b1_reno_t*_ss.txt` file and writes `plots/e1_reno_cwnd_all.png`:

```bash
python3 e1/analyze_e1.py
```

#### Extraction Rules

- **Time origin (`t0`):** The first timestamp in the file.
- **Sample:** One timestamp and all sockets listed after it, up to the next timestamp.
- **Data socket:** The connection identified by its local and peer addresses and ports with the largest `bytes_acked` value across the entire file. This connection is then tracked in every sample, including early samples before it has acknowledged much data.
- **Missing data:** Samples without the data socket are dropped. Missing `cwnd` values are never replaced with zero or interpolated.
- **Time precision:** `time_s = timestamp − t0` is computed using `decimal.Decimal` to preserve the recorded timestamp precision.

### 2. Plot

The dashed line marks BDP + B = 166 packets (the point where the queue overflows). The dotted line marks BDP = 83 packets.

![TCP Reno congestion window over time](plots/e1_reno_cwnd_all.png)

### 3. Steady-State Throughput: Mean and Standard Deviation

For each trial, steady-state throughput is calculated by averaging the per-interval throughput values, excluding intervals that start before 5 seconds. The mean and sample standard deviation are then calculated across the five trial results.

Run:

```bash
python3 e1/throughput_e1.py
```

Output:

```text
t1: 47.57 Mbps
t2: 46.28 Mbps
t3: 46.27 Mbps
t4: 46.08 Mbps
t5: 45.66 Mbps
Mean ± SD: 46.37 ± 0.71 Mbps
```

Link utilization is calculated as:

$$
U = \frac{\bar{x}}{C} \times 100\%
  = \frac{46.37}{50} \times 100\%
  = \boxed{92.74\%}
$$

Here, $\bar{x}$ is the mean steady-state throughput and $C$ is the bottleneck capacity, both in Mbps.

Reno achieved a steady-state throughput of **46.37 ± 0.71 Mbps** across five trials, equivalent to **92.74%** of the 50 Mbps bottleneck capacity. This result is consistent with application throughput being lower than link capacity due to protocol overhead and congestion control behavior.

### 4. Trends and Deviations

**Setup and model.** C = 50 Mbps, RTT_min = 2 × 10 ms = 20 ms, so BDP = 50 Mbps × 20 ms / (1500 B × 8) ≈ 83 packets, and the buffer is B = 1 BDP = 83 packets. In the model, a single Reno flow fills the queue when cwnd reaches BDP + B = 166 packets. The next loss halves cwnd to 83 = BDP. Reno then adds 1 packet per RTT until the queue overflows again.

#### Trends

1. **AIMD sawtooth between BDP and BDP + B.** After slow start, cwnd rises to 166 packets, halves to 83, and repeats. In trial 1, 17 of the 19 cycles after slow start peak at exactly 166 and fall to exactly 83, the values the drop-tail model predicts.

2. **Each ramp curves (concave) instead of rising in a straight line.** A straight ramp assumes a constant RTT. Here, every packet above the BDP waits in the bottleneck queue. RTT therefore grows from 20 ms at cwnd = 83 to 40 ms at cwnd = 166, a full queue being 83 packets × 0.24 ms = 20 ms. Reno adds one packet per RTT, so in packets per second it grows half as fast at the top of a ramp as at the bottom. The iperf3 RTTs support this: mean RTT ≈ 30 ms, midway between 20 and 40 ms. In trials 1 and 2 the maximum RTT is 40.5 ms, just above the 40 ms that a full queue allows.

3. **The sawtooth period is about 2.6 s.** Integrating dW/dt = 1/RTT(W), with RTT(W) = RTT_min × W / BDP, from 83 to 166 gives a period of RTT_min / (2·BDP) × (166² − 83²) ≈ 2.48 s. The measured median period is 2.59 s in every trial, about 4 % longer. The model uses a nominal RTT_min of exactly 20 ms and 1500 B packets. In reality the measured minimum RTT is 20.2–20.4 ms, because host and switch processing add to the netem delay. HTB also sends 1514 B Ethernet frames, so each queued packet adds 0.242 ms instead of 0.240 ms. Both effects make every RTT on the ramp slightly longer.

4. **Slow start overshoots to about 2 × (BDP + B).** In every trial, cwnd briefly spikes to 304–322 packets (313 ± 8.8), about twice 166. In slow start, cwnd doubles every RTT. The queue overflows when cwnd passes 166, but the sender learns about the loss one RTT later (about 40 ms with a full queue). By then cwnd has doubled again. That burst causes most of trial 1's 241 retransmissions. After recovery, cwnd is about 160, but the queue still holds the burst. A second loss therefore follows almost immediately and brings cwnd to 83, where the steady sawtooth begins. The throughput in section 3 skips the first 5 s to leave out this transient.

5. **Throughput is close to the most the link can deliver.** iperf3 counts only TCP payload. Each 1514 B frame on the wire carries 1448 B of data, so the highest throughput iperf3 can report on a 50 Mbps link is 50 × 1448/1514 ≈ 47.8 Mbps. Reno's 46.37 ± 0.71 Mbps is therefore about 97 % of that ceiling, even though it is 92.7 % of raw capacity. Nearly all of the gap to 50 Mbps is header overhead, not idle link time. That is the behavior expected when B = BDP, because the trough of cwnd = BDP keeps the link busy.

#### Deviations

- **Some losses come before cwnd reaches BDP + B (trial 2, trial 3, and one or two cycles each in trials 1 and 5).** These cycles peak at 100–160 packets instead of 166, and then fall to 50–75, which is below the BDP. A drop-tail queue can overflow early only if packets arrive faster than C, or drain slower than C, for a while. The model assumes a constant drain rate C and a constant propagation delay. The emulation breaks both assumptions, because HTB (rate limiting), netem (delay), iperf3, and the `ss` sampler all share one VM's CPU. When the VM or its packet-processing work is briefly descheduled:
  - the bottleneck stops draining;
  - netem then releases its delayed packets in a burst;
  - the 83-packet queue overflows even though cwnd is below 166.

  The iperf3 RTTs show this. Queueing alone cannot push RTT above 2 × 20 ms = 40 ms, yet the maximum RTT is 112 ms in trial 3, 225 ms in trial 4 and 57 ms in trial 5. The extra time can only come from stalls on the host. Trial 2 has no such RTT spike. iperf3 reports the kernel's smoothed RTT, which averages out stalls of only a few milliseconds, so short stalls can still cause losses without showing up in the maximum. Trials 2–5 all show more retransmissions than trial 1 (378–657 vs. 241) and lower throughput (45.7–46.3 vs. 47.6 Mbps).

- **Troughs below 83 packets are still Reno's normal halving.** Each deep trough is half of the lower peak before it, for example 113 → 56 and 110 → 55. Reno itself is behaving correctly; only the point where loss happens has moved. While cwnd is below the BDP, the queue is empty and the link is briefly idle, which is why the trials with these cycles have lower throughput.

- **Empty stretches and missing tails come from how the sampler was timed.** `t = 0` is the sampler's first timestamp, not the start of the flow. The sampler started 5–17 s before iperf3, which is the empty stretch at the left of each panel. It also stopped before the 60 s flow ended:
  - trials 1–3 cover about 48–50 s of the flow;
  - trials 4–5 cover only about 11 s.

  The cycles visible in trials 4–5 have the same shape (peak 166, trough 83, period about 2.6 s) as trials 1–3. The throughput numbers in section 3 come from the full 60 s iperf3 run, so the sampler cutoff does not affect them. To capture the whole flow in a re-run, start the sampler immediately before iperf3 and run it for at least the test duration + 2 s.
