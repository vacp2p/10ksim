"""One-time (or re-run anytime) seeding of experiments via the API.

Experiments are managed exclusively through the API now - config.yaml no
longer defines them. This script reads a JSON file of experiment definitions
(see seed_data/experiments.json, extracted from the old config.yaml) and
POSTs each one through POST /experiments, same as any other client would.
`id` is server-assigned on create, so the seed file doesn't (and shouldn't)
include one; a 409 means an experiment with that title already exists.

Usage:
    DST_ADMIN_TOKEN=<token from /admin/token> uv run python -m dst_dashboard.scripts.seed_experiments

    or:

    uv run python -m dst_dashboard.scripts.seed_experiments \\
        --api-url http://localhost:8000 \\
        --token <token> \\
        --seed-file dst_dashboard/scripts/seed_data/experiments.json
"""

import argparse
import json
import os
import sys
from pathlib import Path

import requests

DEFAULT_SEED_FILE = Path(__file__).parent / "seed_data" / "experiments.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--api-url",
        default=os.environ.get("DST_API_URL", "http://localhost:8000"),
        help="Base URL of the running DST Dashboard API (default: %(default)s, or DST_API_URL)",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("DST_ADMIN_TOKEN"),
        help="Admin bearer token from /admin/token (default: DST_ADMIN_TOKEN env var)",
    )
    parser.add_argument(
        "--seed-file",
        default=DEFAULT_SEED_FILE,
        type=Path,
        help="JSON file with an 'experiments:' list (default: %(default)s)",
    )
    args = parser.parse_args()

    if not args.token:
        print(
            "Error: an admin token is required (--token or DST_ADMIN_TOKEN). "
            "Get one from GET /admin/token.",
            file=sys.stderr,
        )
        sys.exit(1)

    with open(args.seed_file, "r", encoding="utf-8") as f:
        seed_data = json.load(f)

    experiments = seed_data.get("experiments", [])
    if not experiments:
        print(f"No experiments found in {args.seed_file}")
        return

    headers = {"Authorization": f"Bearer {args.token}"}
    created, skipped, failed = 0, 0, 0

    for experiment in experiments:
        title = experiment.get("title", "<unknown>")
        response = requests.post(
            f"{args.api_url}/experiments", json=experiment, headers=headers, timeout=120
        )

        if response.status_code == 201:
            new_id = response.json().get("id")
            print(f"Created '{title}' (id={new_id})")
            created += 1
        elif response.status_code == 409:
            print(f"Skipped '{title}' (title already exists)")
            skipped += 1
        else:
            print(f"Failed '{title}': {response.status_code} {response.text}", file=sys.stderr)
            failed += 1

    print(f"\nDone: {created} created, {skipped} skipped, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
