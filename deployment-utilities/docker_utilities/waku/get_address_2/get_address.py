#!/usr/bin/env python3
import os
import re
import subprocess
from pathlib import Path
from typing import List, Optional

import requests
from pydantic import BaseModel, Field, PositiveInt


class Config(BaseModel):
    """Configuration for address retrieval."""

    num_addrs: PositiveInt = Field(default=1, description="Number of addresses to process")
    service_name: str = Field(
        default="zerotesting-bootstrap.zerotesting", description="Service name to query"
    )


def nslookup_ipv4(service_name: str, limit: int) -> List[str]:
    """Retrieve IPv4 addresses using nslookup."""
    result = subprocess.run(["nslookup", service_name], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"nslookup failed for {service_name}: {result.stderr.strip()}")

    addrs = [
        line.split()[-1]
        for line in result.stdout.splitlines()
        if line.strip().startswith("Address")
    ]
    return addrs[:limit]


def fetch_listen_address(ip: str) -> Optional[str]:
    """Fetch the listen address from a node's debug endpoint."""
    url = f"http://{ip}:8645/debug/v1/info"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        match = re.search(r'"listenAddresses":\["([^"]+)"', response.text)
        return match.group(1) if match else None
    except (requests.RequestException, ValueError):
        return None


def validate_addr(addr: str) -> bool:
    """Check if the address starts with '/ip'."""
    return addr.startswith("/ip")


def main() -> None:
    """Resolve IPs, fetch and validate addresses, and write results."""
    config = Config()  # Reads defaults; can also parse CLI args if desired
    pod_ips = nslookup_ipv4(config.service_name, config.num_addrs)

    addrs_dir = Path("/etc/addrs")
    addrs_file = addrs_dir / "addrs.env"
    addrs_dir.mkdir(parents=True, exist_ok=True)

    valid_count = 0
    addrs_file.write_text("")  # Clear file

    for pod_ip in pod_ips:
        print(f"Querying IP: {pod_ip}")
        addr = fetch_listen_address(pod_ip)
        if addr and validate_addr(addr):
            valid_count += 1
            with addrs_file.open("a") as f:
                f.write(f"export addrs{valid_count}='{addr}'\n")
            if valid_count == config.num_addrs:
                break
        else:
            print(f"Invalid or missing addr from {pod_ip}")

    if valid_count == 0:
        print("No valid addrs data received from any IPs.")
        raise SystemExit(1)

    print("addrs data saved successfully:")
    print(addrs_file.read_text())


if __name__ == "__main__":
    main()
