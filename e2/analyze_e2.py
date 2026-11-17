#!/usr/bin/env python3
"""
E2: plot cwnd(t) for every trial of one (algo, buf), and report the
queueing delay and utilization.

Reads data/e2/<algo>/buf<buf>/t<k>_ss.txt and t<k>.json and writes:
  plots/e2/e2_<algo>_buf<buf>_cwnd.png    one panel per trial, like E1

It also prints, per trial and as mean ± SD across trials:
  throughput x (iperf3 intervals starting at >= 5 s, same as E1), U = x / C,
  mean and 95th-percentile queueing delay (ss samples 5-60 s into the flow).

Extraction rules are the same as E1: the data socket is the connection with
the largest bytes_acked; samples without it are skipped, never set to 0.

RTT_min: --rtt-min if given, else the smallest `minrtt` ss reported in any
trial (the propagation delay with an empty queue).

Usage:  python3 e2/analyze_e2.py --algo reno --buf 0.1
"""
import argparse
import json
import re
import sys
from decimal import Decimal
from pathlib import Path
from statistics import mean, stdev

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA, PLOTS = ROOT / "data" / "e2", ROOT / "plots" / "e2"
MTU = 1500
WINDOW = (5.0, 60.0)          # seconds after the flow starts

TS_RE = re.compile(r"^\s*(\d+\.\d+)\s*$")
SOCK_RE = re.compile(r"^[A-Z][A-Z0-9-]*\s+\d+\s+\d+\s+(\S+)\s+(\S+)")
FIELDS = {
    "cwnd": re.compile(r"\bcwnd:(\d+)\b"),
    "rtt": re.compile(r"\brtt:([\d.]+)/"),
    "minrtt": re.compile(r"\bminrtt:([\d.]+)"),
    "acked": re.compile(r"\bbytes_acked:(\d+)\b"),
}


def load_trace(path):
    """Return the data socket's samples: list of (t since flow start, fields)."""
    samples, sock = [], None
    with open(path, errors="replace") as fh:
        for line in fh:
            if m := TS_RE.match(line):
                samples.append((Decimal(m.group(1)), {}))
                sock = None
            elif samples and (m := SOCK_RE.match(line)):
                sock = samples[-1][1].setdefault((m.group(1), m.group(2)), {})
            elif sock is not None and line[:1].isspace():
                for name, rx in FIELDS.items():
                    if name not in sock and (v := rx.search(line)):
                        sock[name] = float(v.group(1))
    # Undo wall-clock steps. The sampler stamps samples with `date`, so if the
    # VM's clock is corrected mid-run (e.g. after the host sleeps), the times
    # jump forward although no time passed. VM freezes also leave gaps, but
    # those are real time (iperf3 sees them too) and last a second or two;
    # the sampler only runs for 65 s, so a gap over 10 s must be a clock step.
    shift, fixed = Decimal(0), []
    for i, (stamp, socks) in enumerate(samples):
        if i and stamp - samples[i - 1][0] > 10:
            step = stamp - samples[i - 1][0] - Decimal("0.015")
            shift += step
            print(f"note: {path.name}: clock jumped {step:.1f} s at "
                  f"{samples[i - 1][0] - samples[0][0]:.1f} s; removed")
        fixed.append((stamp - shift, socks))
    samples = fixed

    acked = {}
    for _, socks in samples:
        for key, s in socks.items():
            acked[key] = max(acked.get(key, 0), s.get("acked", 0))
    if not acked:
        sys.exit(f"{path}: no sockets")
    data_key = max(acked, key=acked.get)
    pts = [(stamp, socks[data_key]) for stamp, socks in samples
           if "cwnd" in socks.get(data_key, {})]
    t0 = pts[0][0]                      # first sample of the data socket
    return [(float(stamp - t0), s) for stamp, s in pts]


def throughput(path):
    """Steady-state Mbps; if `>>` left several runs in the file, use the last."""
    text, dec, pos, data = path.read_text(), json.JSONDecoder(), 0, None
    while pos < len(text):
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos < len(text):
            data, pos = dec.raw_decode(text, pos)
    rates = [iv["sum"]["bits_per_second"] / 1e6 for iv in data["intervals"]
             if iv["sum"]["start"] >= WINDOW[0]]
    return mean(rates), data["end"]["sum_sent"].get("retransmits")


def p95(values):
    s = sorted(values)
    return s[int(0.95 * (len(s) - 1))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--algo", default="reno")
    ap.add_argument("--buf", default="0.1", help="as passed to --buf, e.g. 0.1")
    ap.add_argument("--bw", type=float, default=50)
    ap.add_argument("--delay-ms", type=float, default=10)
    ap.add_argument("--rtt-min", type=float,
                    help="RTT_min in ms (default: smallest ss minrtt)")
    a = ap.parse_args()

    folder = DATA / a.algo / f"buf{a.buf}"
    logs = sorted(folder.glob("t*_ss.txt"),
                  key=lambda p: int(re.search(r"t(\d+)_ss", p.name).group(1)))
    if not logs:
        sys.exit(f"no logs in {folder}")

    # Model: same rules as dumbbell.py
    bdp = a.bw * 1e6 * (2 * a.delay_ms / 1000) / (MTU * 8)
    q = max(1, int(float(a.buf) * bdp))
    peak_ms = q * MTU * 8 / (a.bw * 1e6) * 1000          # B / C

    trials = []
    for ss in logs:
        k = int(re.search(r"t(\d+)_ss", ss.name).group(1))
        x, retx = throughput(ss.with_name(f"t{k}.json"))
        trials.append((k, load_trace(ss), x, retx))

    rtt_min = a.rtt_min or min(s["minrtt"] for _, tr, _, _ in trials
                               for _, s in tr if "minrtt" in s)

    # ---- numbers ---------------------------------------------------------
    print(f"{a.algo}, --buf {a.buf}: BDP = {bdp:.0f} pkts, B = {q} pkts, "
          f"BDP + B = {bdp + q:.0f} pkts")
    print(f"RTT_min = {rtt_min:.2f} ms, predicted peak queueing delay "
          f"B/C = {peak_ms:.2f} ms\n")
    print("trial  throughput     U   mean delay  p95 delay  retransmits")
    xs, means, p95s = [], [], []
    for k, tr, x, retx in trials:
        d = [s["rtt"] - rtt_min for t, s in tr
             if "rtt" in s and WINDOW[0] <= t <= WINDOW[1]]
        xs.append(x)
        means.append(mean(d))
        p95s.append(p95(d))
        print(f"t{k:<5} {x:6.2f} Mbps {100 * x / a.bw:5.1f}%  "
              f"{means[-1]:6.2f} ms  {p95s[-1]:6.2f} ms  {retx:>8}")
    sd = stdev(xs) if len(xs) > 1 else 0.0
    print(f"\nMean ± SD throughput: {mean(xs):.2f} ± {sd:.2f} Mbps, "
          f"U = {100 * mean(xs) / a.bw:.2f}%")
    print(f"Mean queueing delay: {mean(means):.2f} ms, "
          f"p95: {mean(p95s):.2f} ms (predicted peak {peak_ms:.2f} ms)")

    # ---- plots -----------------------------------------------------------
    PLOTS.mkdir(parents=True, exist_ok=True)
    xmax = max(tr[-1][0] for _, tr, _, _ in trials)
    tag = f"e2_{a.algo}_buf{a.buf}"

    def panels(name, ylabel, values, lines, ylim):
        fig, axs = plt.subplots(len(trials), 1, sharex=True, squeeze=False,
                                figsize=(10, 1.9 * len(trials)), dpi=150)
        for ax, (k, tr, _, _) in zip(axs[:, 0], trials):
            ts = [t for t, s in tr if values(s) is not None]
            ys = [values(s) for _, s in tr if values(s) is not None]
            ax.plot(ts, ys, color="#1f6fb4", lw=0.7)
            for y, style, label in lines:
                ax.axhline(y, color="#6b6b6b", ls=style, lw=0.9)
                if k == trials[0][0]:
                    ax.text(xmax, y, f" {label}", ha="right", va="bottom",
                            fontsize=8, color="#6b6b6b")
            ax.text(0.005, 0.92, f"trial {k}", transform=ax.transAxes,
                    fontsize=9, va="top")
            ax.set_ylim(*ylim(ys))
            ax.set_ylabel(ylabel)
            ax.grid(True, color="#d9d9d9", lw=0.6)
            for side in ("top", "right"):
                ax.spines[side].set_visible(False)
        axs[-1, 0].set_xlim(0, xmax * 1.01)
        axs[-1, 0].set_xlabel("Time since flow start (s)")
        fig.suptitle(f"E2 - {a.algo}, --buf {a.buf}: {name} for all "
                     f"{len(trials)} trials", fontsize=11)
        fig.tight_layout()
        out = PLOTS / f"{tag}_{name.split('(')[0].strip().replace(' ', '_')}.png"
        fig.savefig(out)
        plt.close(fig)
        print("saved", out)

    all_cwnd = [s["cwnd"] for _, tr, _, _ in trials for _, s in tr]
    panels("cwnd(t)", "cwnd (packets)", lambda s: s["cwnd"],
           [(bdp + q, "--", f"BDP + B = {bdp + q:.0f}"),
            (bdp, ":", f"BDP = {bdp:.0f}")],
           lambda ys: (0, max(bdp + q, p95(all_cwnd)) * 1.25))


if __name__ == "__main__":
    main()
