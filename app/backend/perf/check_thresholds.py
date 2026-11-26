"""Parse Locust CSV results and fail if performance thresholds are exceeded."""

import csv
import sys

THRESHOLDS = {
    "p95_response_time": 500,   # ms
    "p99_response_time": 1000,  # ms
    "failure_rate": 0.01,       # 1%
}


def check(csv_path: str) -> bool:
    """
    Read the Locust stats CSV and verify aggregate metrics against thresholds.

    Returns True if all thresholds pass, False otherwise.
    """
    passed = True
    found_aggregated = False

    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["Name"] == "Aggregated":
                found_aggregated = True
                p95 = float(row["95%"])
                p99 = float(row["99%"])
                failures = int(row["Failure Count"])
                total = int(row["Request Count"])
                error_rate = failures / total if total > 0 else 0

                print(f"p95: {p95}ms (threshold: {THRESHOLDS['p95_response_time']}ms)")
                print(f"p99: {p99}ms (threshold: {THRESHOLDS['p99_response_time']}ms)")
                print(f"Error rate: {error_rate:.2%} (threshold: {THRESHOLDS['failure_rate']:.2%})")
                print(f"Total requests: {total}")
                print(f"Failed requests: {failures}")

                if p95 > THRESHOLDS["p95_response_time"]:
                    print(
                        f"FAIL: p95 {p95}ms > {THRESHOLDS['p95_response_time']}ms"
                    )
                    passed = False
                if p99 > THRESHOLDS["p99_response_time"]:
                    print(
                        f"FAIL: p99 {p99}ms > {THRESHOLDS['p99_response_time']}ms"
                    )
                    passed = False
                if error_rate > THRESHOLDS["failure_rate"]:
                    print(
                        f"FAIL: error rate {error_rate:.2%} > "
                        f"{THRESHOLDS['failure_rate']:.2%}"
                    )
                    passed = False

    if not found_aggregated:
        print("FAIL: No 'Aggregated' row found in CSV results.")
        return False

    return passed


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_thresholds.py <path_to_stats_csv>")
        sys.exit(2)

    if not check(sys.argv[1]):
        sys.exit(1)
    print("All performance thresholds passed.")
