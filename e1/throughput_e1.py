"""Steady-state throughput (intervals starting at >= 5 s) for each E1 trial.

Usage:  python3 e1/throughput_e1.py [--algo reno|cubic|bbr]
"""
import argparse
import json
from pathlib import Path
from statistics import mean, stdev

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "e1"

ap = argparse.ArgumentParser()
ap.add_argument("--algo", default="reno")
a = ap.parse_args()

# Logs live in data/e1/<algo>/ (older layout: directly in data/e1/)
data_dir = DATA / a.algo if (DATA / a.algo).is_dir() else DATA

trial_values = []

for trial in range(1, 6):
    path = data_dir / f"e1_b1_{a.algo}_t{trial}.json"

    # A file written with `>>` can hold several iperf3 results back to back;
    # the last one is the most recent run.
    text = path.read_text()
    decoder, pos, docs = json.JSONDecoder(), 0, []
    while pos < len(text):
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos == len(text):
            break
        doc, pos = decoder.raw_decode(text, pos)
        docs.append(doc)
    data = docs[-1]
    if len(docs) > 1:
        print(f"note: {path.name} holds {len(docs)} runs; using the last")

    if data.get("error"):
        raise ValueError(f"{path}: {data['error']}")

    # get interval >=5
    rates = [
        interval["sum"]["bits_per_second"] / 1_000_000
        for interval in data["intervals"]
        if interval["sum"]["start"] >= 5
    ]

    if not rates:
        raise ValueError(f"{path}: no intervals after 5 s")

    throughput = mean(rates)
    trial_values.append(throughput)
    print(f"t{trial}: {throughput:.2f} Mbps")

print(
    f"Mean ± SD: {mean(trial_values):.2f} "
    f"± {stdev(trial_values):.2f} Mbps"
)
