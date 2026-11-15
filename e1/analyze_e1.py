#!/usr/bin/env python3
"""
E1: plot cwnd(t) of the data socket for every trial as small multiples.

For each data/e1/e1_b1_<algo>_t<k>_ss.txt:
  t    = timestamp line - first timestamp in the file
  cwnd = `cwnd:` of the iperf3 data socket (packets). The data socket is the
         connection with the largest bytes_acked (the other one is iperf3's
         control connection). Samples without it are skipped, not set to 0.

Output: plots/e1_<algo>_cwnd_all.png

Usage:  python3 e1/analyze_e1.py [--algo reno] [--bw 50] [--delay-ms 10] [--buf 1]
"""
import argparse
import re
import sys
from decimal import Decimal
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA, PLOTS = ROOT / "data" / "e1", ROOT / "plots"
MTU = 1500

TS_RE = re.compile(r"^\s*(\d+\.\d+)\s*$")                 # sample timestamp
SOCK_RE = re.compile(r"^[A-Z][A-Z0-9-]*\s+\d+\s+\d+\s+(\S+)\s+(\S+)")
CWND_RE = re.compile(r"\bcwnd:(\d+)\b")
ACKED_RE = re.compile(r"\bbytes_acked:(\d+)\b")


def load_trace(path):
    """Return (times_s, cwnds) of the data socket in one sampler log."""
    samples = []                 # [(timestamp str, {(local, peer): [cwnd, acked]})]
    sock = None
    with open(path, errors="replace") as fh:
        for line in fh:
            if m := TS_RE.match(line):
                samples.append((m.group(1), {}))
                sock = None
            elif samples and (m := SOCK_RE.match(line)):
                sock = samples[-1][1].setdefault((m.group(1), m.group(2)), [None, 0])
            elif sock is not None and line[:1].isspace():
                if sock[0] is None and (c := CWND_RE.search(line)):
                    sock[0] = int(c.group(1))
                if a := ACKED_RE.search(line):
                    sock[1] = max(sock[1], int(a.group(1)))
    if not samples:
        sys.exit(f"{path}: no timestamp lines")

    acked = {}
    for _, socks in samples:
        for key, (_, ack) in socks.items():
            acked[key] = max(acked.get(key, 0), ack)
    if not acked:
        sys.exit(f"{path}: no sockets")
    data_key = max(acked, key=acked.get)

    t0 = Decimal(samples[0][0])
    ts, cw = [], []
    for stamp, socks in samples:
        c = socks.get(data_key, [None])[0]
        if c is not None:
            ts.append(float(Decimal(stamp) - t0))
            cw.append(c)
    return ts, cw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--algo", default="reno")
    ap.add_argument("--bw", type=float, default=50)
    ap.add_argument("--delay-ms", type=float, default=10)
    ap.add_argument("--buf", type=float, default=1)
    a = ap.parse_args()

    # Reference lines: BDP and BDP + B (queue overflow point)
    bdp = a.bw * 1e6 * (2 * a.delay_ms / 1000) / (MTU * 8)
    peak = bdp + max(1, int(a.buf * bdp))

    logs = sorted(DATA.glob(f"e1_b1_{a.algo}_t*_ss.txt"),
                  key=lambda p: int(re.search(r"_t(\d+)_", p.name).group(1)))
    if not logs:
        sys.exit(f"no {a.algo} logs in {DATA}")
    traces = [(int(re.search(r"_t(\d+)_", p.name).group(1)), *load_trace(p))
              for p in logs]

    xmax = max(max(ts) for _, ts, _ in traces)
    ymax = max(max(cw) for _, _, cw in traces) * 1.08
    fig, axs = plt.subplots(len(traces), 1, figsize=(10, 1.9 * len(traces)),
                            dpi=150, sharex=True, squeeze=False)
    for ax, (k, ts, cw) in zip(axs[:, 0], traces):
        ax.plot(ts, cw, color="#1f6fb4", lw=0.8)
        ax.axhline(peak, color="#6b6b6b", ls="--", lw=0.9)
        ax.axhline(bdp, color="#6b6b6b", ls=":", lw=0.9)
        if k == traces[0][0]:
            ax.text(xmax, peak + 4, f"BDP + B = {peak:.0f}", ha="right",
                    va="bottom", fontsize=8, color="#6b6b6b")
            ax.text(xmax, bdp - 4, f"BDP = {bdp:.0f}", ha="right",
                    va="top", fontsize=8, color="#6b6b6b")
        ax.text(0.005, 0.92, f"trial {k}", transform=ax.transAxes,
                fontsize=9, va="top")
        ax.set_ylim(0, ymax)
        ax.set_ylabel("cwnd (packets)")
        ax.grid(True, color="#d9d9d9", linewidth=0.6)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)

    axs[-1, 0].set_xlim(0, xmax * 1.01)
    axs[-1, 0].set_xlabel("Time since first sample in sampler file (s)")
    fig.suptitle(f"E1 - {a.algo}: cwnd(t) for all {len(traces)} trials",
                 fontsize=11)
    fig.tight_layout()
    PLOTS.mkdir(exist_ok=True)
    out = PLOTS / f"e1_{a.algo}_cwnd_all.png"
    fig.savefig(out)
    print("saved", out)


if __name__ == "__main__":
    main()
