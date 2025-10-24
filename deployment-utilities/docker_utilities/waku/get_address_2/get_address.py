#!/usr/bin/env python3
import re
import subprocess
from pathlib import Path
from typing import List, Optional, Callable

import requests
from pydantic import BaseModel, Field, PositiveInt


class BaseConfig(BaseModel):
    """Base config for retrieval operation."""
    num_items: PositiveInt = Field(default=1, description="Number of items to retrieve")
    service_name: str = Field(default="zerotesting-bootstrap.zerotesting", description="Service name to query")
    output_file: Path = Field(default=Path("/dev/null"), description="File to write output")


def nslookup_ipv4(service_name: str, limit: int) -> List[str]:
    """Retrieve IPv4 addresses using nslookup."""
    result = subprocess.run(["nslookup", service_name], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"nslookup failed for {service_name}: {result.stderr.strip()}")
    addrs = [line.split()[-1] for line in result.stdout.splitlines() if line.strip().startswith("Address")]
    return addrs[:limit]


def fetch_json_field(ip: str, field_name: str, regex_prefix: Optional[str] = None) -> Optional[str]:
    """Fetch a specific JSON field from node debug endpoint with optional prefix filtering."""
    url = f"http://{ip}:8645/debug/v1/info"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        pattern = re.compile(rf'"{re.escape(field_name)}":\["?([^"\]]+)"?\]')
        match = pattern.search(response.text)
        value = match.group(1) if match else None

        if value and regex_prefix:
            return value if value.startswith(regex_prefix) else None
        return value
    except (requests.RequestException, ValueError):
        return None


def retrieve_and_store(
    config: BaseConfig,
    json_field: str,
    valid_prefix: str,
    export_var_name: Optional[str] = None,
) -> None:
    """
    Unified function to retrieve, validate, and store data from service endpoints.

    - config: Configuration instance
    - json_field: The JSON field key to retrieve from debug endpoint
    - valid_prefix: String prefix for simple validation of extracted values
    - export_var_name: Base name for exported variables in output file, defaults to file basename
    """
    pod_ips = nslookup_ipv4(config.service_name, config.num_items)
    output_path = config.output_file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("")  # Clear the file

    base_var_name = export_var_name or output_path.name
    valid_count = 0

    for pod_ip in pod_ips:
        print(f"Querying IP: {pod_ip}")
        value = fetch_json_field(pod_ip, json_field, regex_prefix=valid_prefix)
        if value:
            valid_count += 1
            with output_path.open("a") as f:
                f.write(f"export {base_var_name}{valid_count}='{value}'\n")
            if valid_count == config.num_items:
                break
        else:
            print(f"Invalid or missing data from IP {pod_ip}")

    if valid_count == 0:
        print("No valid data received from any IPs.")
        raise SystemExit(1)

    print(f"Data saved successfully to {output_path}:")
    print(output_path.read_text())


def main() -> None:
    """Main execution entrypoint with two example configs for addrs and ENRs."""

    addrs_config = BaseConfig(
        num_items=1,
        service_name="zerotesting-bootstrap.zerotesting",
        output_file=Path("/etc/addrs/addrs.env"),
    )

    enr_config = BaseConfig(
        num_items=3,
        service_name="zerotesting-bootstrap.zerotesting",
        output_file=Path("/etc/enr/ENR"),
    )

    # Retrieve listenAddresses starting with "/ip"
    retrieve_and_store(
        addrs_config,
        json_field="listenAddresses",
        valid_prefix="/ip",
        export_var_name="addrs",
    )

    # Retrieve enrUri starting with "enr:-"
    retrieve_and_store(
        enr_config,
        json_field="enrUri",
        valid_prefix="enr:-",
        export_var_name=enr_config.output_file.name,
    )


if __name__ == "__main__":
    main()
