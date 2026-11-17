#!/usr/bin/env python3
"""Extract data-socket cwnd samples from an ss log and plot cwnd(t)."""

import argparse
import csv
import re
from decimal import Decimal
from pathlib import Path

import matplotlib.pyplot as plt


TIMESTAMP = re.compile(r"^\d+\.\d+$")
SOCKET = re.compile(
    r"^\s*(?:ESTAB|SYN-SENT|SYN-RECV|FIN-WAIT-1|FIN-WAIT-2|"
    r"CLOSE-WAIT|CLOSING|LAST-ACK|TIME-WAIT|CLOSE)\s+"
    r"\d+\s+\d+\s+(\S+)\s+(\S+)"
)


def get_integer(text, field):
    match = re.search(rf"\b{re.escape(field)}:(\d+)\b", text)
    return int(match.group(1)) if match else None


def read_samples(path):
    """Group socket records under their preceding timestamp."""
    samples = []
    timestamp = None
    records = []
    current_record = None

    with path.open(encoding="utf-8") as source:
        for line in source:
            stripped = line.strip()

            if TIMESTAMP.fullmatch(stripped):
                if timestamp is not None:
                    samples.append((timestamp, records))

                timestamp = Decimal(stripped)
                records = []
                current_record = None
                continue

            if timestamp is None:
                continue

            match = SOCKET.match(line)
            if match:
                current_record = {
                    "socket": (match.group(1), match.group(2)),
                    "text": "",
                }
                records.append(current_record)
            elif current_record is not None and stripped:
                if not stripped.startswith("State"):
                    current_record["text"] += " " + stripped

    if timestamp is not None:
        samples.append((timestamp, records))

    return samples


def extract_cwnd(samples):
    """Select the data socket globally, then track it in every sample."""
    if not samples:
        raise ValueError("No timestamps found in the input file.")

    maximum_acked = {}

    for _, records in samples:
        for record in records:
            acked = get_integer(record["text"], "bytes_acked")
            if acked is not None:
                key = record["socket"]
                maximum_acked[key] = max(
                    maximum_acked.get(key, 0), acked
                )

    if not maximum_acked:
        raise ValueError("No bytes_acked fields found.")

    data_socket = max(maximum_acked, key=maximum_acked.get)
    t0 = samples[0][0]
    rows = []

    for timestamp, records in samples:
        for record in records:
            if record["socket"] != data_socket:
                continue

            cwnd = get_integer(record["text"], "cwnd")
            if cwnd is not None:
                rows.append((timestamp, timestamp - t0, cwnd))
                break

    if not rows:
        raise ValueError("No cwnd values found for the data socket.")

    return t0, data_socket, rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Sampler _ss.txt file")
    parser.add_argument(
        "-o", "--output", type=Path, required=True,
        help="Output image path, for example plots/reno_t1.png",
    )
    parser.add_argument(
        "--csv", type=Path,
        help="Optional CSV path; defaults to the image path with .csv",
    )
    args = parser.parse_args()

    samples = read_samples(args.input)
    t0, data_socket, rows = extract_cwnd(samples)

    csv_path = args.csv or args.output.with_suffix(".csv")
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    with csv_path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.writer(target)
        writer.writerow(["timestamp", "time_s", "cwnd_packets"])

        for timestamp, time_s, cwnd in rows:
            writer.writerow([
                format(timestamp, "f"),
                format(time_s, "f"),
                cwnd,
            ])

    # Convert relative times to float only for plotting.
    times = [float(row[1]) for row in rows]
    windows = [row[2] for row in rows]

    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(times, windows, linewidth=1)
    ax.set_xlabel("Time since first sampler timestamp (s)")
    ax.set_ylabel("cwnd (packets)")
    ax.set_title(args.input.stem)
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(args.output, dpi=200)
    plt.close(fig)

    sampler_duration = samples[-1][0] - t0
    observed_span = rows[-1][1] - rows[0][1]

    print(f"Data socket: {data_socket[0]} -> {data_socket[1]}")
    print(f"Timestamp samples: {len(samples)}")
    print(f"Valid cwnd samples: {len(rows)}")
    print(f"Sampler duration: {sampler_duration:.3f} s")
    print(f"First cwnd sample: {rows[0][1]:.3f} s")
    print(f"Last cwnd sample: {rows[-1][1]:.3f} s")
    print(f"Observed cwnd span: {observed_span:.3f} s")
    print(f"CSV: {csv_path}")
    print(f"Plot: {args.output}")


if __name__ == "__main__":
    main()