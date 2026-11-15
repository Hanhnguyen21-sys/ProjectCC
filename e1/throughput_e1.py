import json
from pathlib import Path
from statistics import mean, stdev

trial_values = []

for trial in range(1, 6):
    path = Path(f"data/e1/e1_b1_reno_t{trial}.json")

    with path.open() as f:
        data = json.load(f)

    if data.get("error"):
        raise ValueError(f"{path}: {data['error']}")

    # get interval >=5 
    rates = [
        interval["sum"]["bits_per_second"] / 1_000_000
        for interval in data["intervals"]
        if interval["sum"]["start"] >= 5
    ]

    if not rates:
        raise ValueError(f"{path}: không có dữ liệu sau giây 5")

    throughput = mean(rates)
    trial_values.append(throughput)
    print(f"t{trial}: {throughput:.2f} Mbps")

print(
    f"Mean ± SD: {mean(trial_values):.2f} "
    f"± {stdev(trial_values):.2f} Mbps"
)
