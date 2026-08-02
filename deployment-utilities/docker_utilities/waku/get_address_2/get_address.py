#!/usr/bin/env python3
import argparse
import json
import logging
import socket
import traceback
from pathlib import Path
from typing import Any, Callable, Optional

import requests
from pydantic import BaseModel, PositiveInt, ValidationError

logger = logging.getLogger(__name__)


class Config(BaseModel):
    num_items: PositiveInt
    service_name: str
    output_file: Path
    variable_name: str
    websocket: bool


def resolve_ipv4(service_name: str):
    _, _, ip_list = socket.gethostbyname_ex(service_name)
    return ip_list


def extract_address(obj: dict, require_ws: bool) -> object:
    addresses = obj["listenAddresses"]
    if require_ws:
        return next((address for address in addresses if "/ws/" in address))

    return addresses[0]


def fetch_value(ip: str, extractor: Callable[[object], object]) -> Optional[str]:
    url = f"http://{ip}:8645/debug/v1/info"
    response = requests.get(url, timeout=5)
    response.raise_for_status()
    obj = json.loads(response.text)
    return extractor(obj)


def retrieve_and_store(
    num: PositiveInt,
    service_name: str,
    variable_name: str,
    output_path: Path,
    extractor: Callable[[object], object],
) -> None:
    pod_ips = resolve_ipv4(service_name)
    logger.info(f"Matching Pod IPs: {pod_ips}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        logger.warning(f"Replacing environment file with new one. File: `{output_path.as_posix()}`")
    output_path.unlink(missing_ok=True)

    added_count = 0
    for pod_ip in pod_ips:
        logger.info(f"Querying IP: {pod_ip}")
        try:
            value = fetch_value(pod_ip, extractor)
            added_count += 1
            with output_path.open("a") as out_file:
                out_file.write(f"export {variable_name}{added_count}='{value}'\n")
            if added_count == num:
                break
        except (requests.RequestException, ValueError):
            print(f"Invalid or missing data. IP `{pod_ip}` exception: `{traceback.format_exc()}`")

    if added_count == 0:
        print("No valid data received from any IPs.")
        raise SystemExit(1)

    print(f"Data saved successfully to {output_path}:")
    print(output_path.read_text())


def parse_config_args() -> Config:
    parser = argparse.ArgumentParser(description="Retrieve and store ENRs or addrs.")
    parser.add_argument(
        "--num", type=int, default=1, help="Number of addresses to retrieve", dest="num_items"
    )
    parser.add_argument(
        "--service-name",
        type=str,
        help="Service name to query (example: zerotesting-bootstrap.zerotesting)",
        dest="service_name",
    )
    parser.add_argument(
        "--output-file", type=Path, required=True, help="Path for results", dest="output_file"
    )
    parser.add_argument(
        "--var-name",
        type=str,
        required=True,
        help="Name of environment vars (example: ENR or addrs)",
        dest="variable_name",
    )
    parser.add_argument("--websocket", action="store_true")

    args = parser.parse_args()
    args_dict: dict[str, Any] = vars(args)

    try:
        return Config(**args_dict)
    except ValidationError as e:
        print("Configuration validation failed:", e)
        raise SystemExit(1)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
    )

    config = parse_config_args()
    config = Config(
        num_items=1,
        service_name="zerotesting-lightpush-server",
        output_file=Path("/etc/addrs/addrs.env"),
        variable_name="addrs",
        websocket=True,
    )
    retrieve_and_store(
        num=config.num_items,
        service_name=config.service_name,
        variable_name=config.variable_name,
        output_path=config.output_file,
        extractor=lambda obj: extract_address(obj, require_ws=config.websocket),
    )


if __name__ == "__main__":
    main()
