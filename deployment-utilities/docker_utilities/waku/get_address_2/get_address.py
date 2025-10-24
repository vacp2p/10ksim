#!/usr/bin/env python3
import os
import re
import subprocess
from pathlib import Path
from typing import List, Optional

import requests
from pydantic import BaseModel, Field, PositiveInt


class AddrsConfig(BaseModel):
    """Configuration for address retrieval."""
    num_addrs: PositiveInt = Field(default=1, description="Number of addresses to process")
    service_name: str = Field(default="zerotesting-bootstrap.zerotesting", description="Service name to query")


class EnrConfig(BaseModel):
    """Configuration for ENR retrieval."""
    num_enrs: PositiveInt = Field(default=3, description="Number of ENRs to process")
    service_name: str = Field(default="zerotesting-bootstrap.zerotesting", description="Service name to query")
    output_file: Path = Field(default=Path("/etc/enr/ENR"), description="Output file for ENR data")


def nslookup_ipv4(service_name: str, limit: int) -> List[str]:
    """Retrieve IPv4 addresses using nslookup."""
    result = subprocess.run(["nslookup", service_name], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"nslookup failed for {service_name}: {result.stderr.strip()}")

    addrs = [line.split()[-1] for line in result.stdout.splitlines() if line.strip().startswith("Address")]
    return addrs[:limit]


def fetch_json_field(ip: str, field_name: str) -> Optional[str]:
    """Fetch a specific JSON field from a node's debug endpoint using a regex."""
    url = f"http://{ip}:8645/debug/v1/info"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        pattern = re.compile(rf'"{re.escape(field_name)}":"([^"]+)"')
        match = pattern.search(response.text)
        return match.group(1) if match else None
    except (requests.RequestException, ValueError):
        return None


def validate_addr(addr: str) -> bool:
    """Check if the address starts with '/ip'."""
    return addr.startswith("/ip")


def validate_enr(enr: str) -> bool:
    """Check if the ENR string starts with 'enr:-'."""
    return enr.startswith("enr:-")


def retrieve_addrs(config: AddrsConfig) -> None:
    """Retrieve, validate and store addresses."""
    pod_ips = nslookup_ipv4(config.service_name, config.num_addrs)

    addrs_dir = Path("/etc/addrs")
    addrs_file = addrs_dir / "addrs.env"
    addrs_dir.mkdir(parents=True, exist_ok=True)
    addrs_file.write_text("")  # Clear file

    valid_count = 0

    for pod_ip in pod_ips:
        print(f"Querying IP: {pod_ip}")
        addr = fetch_json_field(pod_ip, "listenAddresses")
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


def retrieve_enrs(config: EnrConfig) -> None:
    """Retrieve, validate and store ENRs."""
    pod_ips = nslookup_ipv4(config.service_name, config.num_enrs)

    config.output_file.parent.mkdir(parents=True, exist_ok=True)
    config.output_file.write_text("")  # Clear file

    valid_count = 0
    base_name = config.output_file.name

    for pod_ip in pod_ips:
        print(f"Querying IP: {pod_ip}")
        enr = fetch_json_field(pod_ip, "enrUri")
        if enr and validate_enr(enr):
            valid_count += 1
            with config.output_file.open("a") as f:
                f.write(f"export {base_name}{valid_count}='{enr}'\n")
            if valid_count == config.num_enrs:
                break
        else:
            print(f"Invalid ENR data received from IP {pod_ip}")

    if valid_count == 0:
        print("No valid ENR data received from any IPs.")
        raise SystemExit(1)

    print(f"ENR data saved successfully to {config.output_file}:")
    print(config.output_file.read_text())


def main() -> None:
    """Main execution function."""
    # Example usage: instantiate configs with defaults or override as needed
    addrs_config = AddrsConfig()
    enr_config = EnrConfig()

    # Retrieve addrs and ENRs
    retrieve_addrs(addrs_config)
    retrieve_enrs(enr_config)


if __name__ == "__main__":
    main()
