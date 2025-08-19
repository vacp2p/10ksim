# Python Imports
import argparse
import datetime
import json
import logging
import socket
import time
import traceback
from argparse import Namespace
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests
from pydantic import BaseModel, Field, PositiveInt


class UTCFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        # Get UTC time and format with milliseconds
        utc_dt = datetime.datetime.utcfromtimestamp(record.created)
        if datefmt:
            s = utc_dt.strftime(datefmt)
            # Add milliseconds
            s = s + f".{int(record.msecs):03d}"
            return s
        else:
            t = utc_dt.strftime("%Y-%m-%d %H:%M:%S")
            s = f"{t}.{int(record.msecs):03d}"
            return s


# Usage
logfmt = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
datefmt = "%Y-%m-%d %H:%M:%S"

handler = logging.StreamHandler()
handler.setFormatter(UTCFormatter(logfmt, datefmt=datefmt))

logging.basicConfig(level=logging.INFO, handlers=[handler])

logger = logging.getLogger(__file__)


def next_cursor(data: Dict) -> str | None:
    cursor = data.get("paginationCursor")
    if not cursor:
        logger.info("No more messages")
        return None

    return cursor


def fetch_all_messages(base_url: str, initial_params: Dict, headers: Dict) -> List[str]:
    all_messages = []
    params = initial_params.copy()

    while True:
        logger.info(
            f"requests.get: url: `{base_url}` init_params: `{initial_params}` params: `{params}`"
        )
        response = requests.get(base_url, headers=headers, params=params)
        logger.info(f"response: `{response.text}`")
        if response.status_code != 200:
            logger.error(f"Error fetching data: {response.status_code}")
            logger.error(response.text)
            break

        data = response.json()
        logger.info(data)
        if data["statusCode"] != 200:
            logger.info(f"failed. statusCode: `{data['statusCode']}`")
        paged_messages = [message["messageHash"] for message in data["messages"]]
        logger.info(f"Retrieved {len(paged_messages)} messages")
        all_messages.extend([message["messageHash"] for message in data["messages"]])

        cursor = next_cursor(data)
        if not cursor:
            break
        params["cursor"] = cursor
    return all_messages


def dict_extract(obj: dict, path: Path):
    def extract(obj: Any, parts: list, is_list=False):
        if isinstance(obj, list):
            results = []
            for item in obj:
                results.extend(extract(item, parts, is_list=True))
            return results
        if not parts:
            return [obj] if is_list else obj
        next_obj = obj[parts[0]]
        return extract(next_obj, parts[1:], is_list)

    return extract(obj, path.parts)


def paged_request(request: dict, max_attempts: PositiveInt, page_request_delay: float) -> dict:
    """
    GET request with a "paged" param.

    :param request: Must contain "params":dict.
    """
    attempt_num = 1

    url = request["url"]
    all_messages = []
    pages_data = []
    params = request["params"]
    status_codes = []
    inner_status_codes = []
    while True:
        time.sleep(page_request_delay)

        logger.info(f"Making paged request. request: `{request}`, params=`{params}`")
        response = requests.get(url, headers=request["headers"], params=params)

        try:
            data = response.json()
        except requests.exceptions.JSONDecodeError:
            data = response.text

        status_codes.append(response.status_code)
        pages_data.append(data)

        logger.info(f"response to paged request: `{response}`")
        if response.status_code != 200:
            logger.error(
                f"Error fetching paged data. status_code: `{response.status_code}` data: `{data}`"
            )
            break

        inner_status_codes.append(data["statusCode"])
        logger.info(f"Response data: `{data}`")

        if data["statusCode"] != 200:
            logger.info(
                f"inner_status_code != 200: status_code: `{data['statusCode']}`, attempt: `{attempt_num}`"
            )

            if attempt_num >= max_attempts:
                logger.info(f"Exhausted all attempts: `{attempt_num}`")
                break
            attempt_num += 1
            continue

        logger.info(f"inner_status_code == 200: attempt: `{attempt_num}`")
        if attempt_num > 1:
            logger.info("A previous attempt failed, but now it worked.")

        paged_data = dict_extract(data, request.get("extract_keys", Path()))
        logger.info(f"Retrieved {len(paged_data)} messages on attempt `{attempt_num}`")
        all_messages.extend(paged_data)

        cursor = next_cursor(data)
        if not cursor:
            logger.info(f"page request finished with !cursor on attempt `{attempt_num}`")
            break
        params["cursor"] = cursor

        attempt_num = 1

    logger.info("finished page request")
    return {
        "request": request,
        "response": {
            "statusCodes": status_codes,
            "inner_statusCodes": inner_status_codes,
            "messages": all_messages,
            "pages": pages_data,
            "attempt_num": attempt_num,
        },
    }


def api_request(action, request) -> dict:
    url = request["url"]
    response = action(url, request["headers"], request.get("params"))

    try:
        data = response.json()
    except requests.exceptions.JSONDecodeError:
        data = response.text

    if response.status_code != 200:
        logger.error(f"Error fetching data: {response.status_code}")
        logger.error(data)

    return {
        "request": request,
        "response": {
            "statusCode": response.status_code,
            "contents": data,
        },
    }


def get_node_info(
    name: str, node: str, api_args: dict, delay_between_requests=0.3
) -> Dict[str, dict]:
    all_requests = {
        "debug": {
            "headers": {"accept": "text/plain"},
            "params": {"logLevel": "DEBUG"},
            "url": "http://{node}/admin/v1/log-level/DEBUG",
            "type": "POST",
        },
        "info": {
            "url": "http://{node}/debug/v1/info",
            "headers": {"accept": "application/json"},
            "type": "GET",
        },
        "peers": {
            "url": "http://{node}/admin/v1/peers",
            "headers": {"accept": "application/json"},
            "type": "GET",
        },
        "mesh": {
            "url": "http://{node}/admin/v1/peers/mesh",
            "headers": {"accept": "application/json"},
            "type": "GET",
        },
        "stats": {
            "url": "http://{node}/admin/v1/peers/stats",
            "headers": {"accept": "application/json"},
            "type": "GET",
        },
        "connected": {
            "url": "http://{node}/admin/v1/peers/connected",
            "headers": {"accept": "application/json"},
            "type": "GET",
        },
        "service": {
            "url": "http://{node}/admin/v1/peers/service",
            "headers": {"accept": "application/json"},
            "type": "GET",
        },
        "store_messages": {
            "url": f"http://{node}/store/v3/messages",
            "headers": {"accept": "application/json"},
            "paged": True,
            "params": api_args,
            "extract_keys": Path("messages", "messageHash"),
        },
    }

    request_data = {}
    for key, node_request in all_requests.items():
        request = deepcopy(node_request)
        request["url"] = request["url"].format(node=node)
        request["node"] = name
        if request.get("type") == "POST":
            action = lambda url, headers, params: requests.post(url, data=params, headers=headers)
        elif request.get("type") == "GET":
            action = lambda url, headers, params: requests.get(url, headers=headers, params=params)

        try:
            if request.get("paged"):
                result = paged_request(request=request, max_attempts=1, page_request_delay=0)
            else:
                result = api_request(action, request)
            request_data[key] = result
        except Exception as e:
            error = traceback.format_exc()
            logger.error(
                f"Exception attempting API request. request: `{request}`, exception: `{e}`, error: `{error}`"
            )
            request_data[key] = {
                "request": request,
                "exception": error,
            }

        time.sleep(delay_between_requests)

    return request_data


def serializer(obj):
    if isinstance(obj, Path):
        return obj.as_posix()
    if isinstance(obj, set):
        return list(obj)
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")


def resolve_dns(node: str) -> Tuple[str, str]:
    start_time = time.time()
    name, port = node.split(":")
    ip_address = socket.gethostbyname(name)
    entire_hostname = socket.gethostbyaddr(ip_address)
    hostname = entire_hostname[0].split(".")[0]
    elapsed = (time.time() - start_time) * 1000
    logger.info(f"{node} DNS Response took {elapsed} ms")
    logger.info(f"Talking with {hostname}, ip address: {ip_address}")

    return (entire_hostname, f"{ip_address}:{port}")


class NodeType(BaseModel):
    name_template: str
    """Format string for node name. Eg. fserver-0-{index}"""
    service: str
    count_key: str
    namespace: str = Field(default="zerotesting")

    def dns_name(self, index: PositiveInt) -> str:
        """Return name for DNS lookup.
        <pod-name>.<headless-service-name>
        """
        return f"{self.get_node_name(index)}.{self.service}"

    def get_node_name(self, index: PositiveInt) -> str:
        return self.name_template.format(index=index)


node_types = [
    NodeType(
        name_template="store-0-{index}",
        service="zerotesting-store",
        count_key="store",
    ),
    NodeType(
        # Note the plural "nodes" with an 's'!
        # This is to match the name used in regression tests.
        name_template="nodes-0-{index}",
        service="zerotesting-service",
        count_key="relay",
    ),
    NodeType(
        name_template="fserver-0-{index}",
        service="zerotesting-filter",
        count_key="filter_server",
    ),
    NodeType(
        name_template="fclient-0-{index}",
        service="zerotesting-filter",
        count_key="filter_client",
    ),
    NodeType(
        name_template="lpserver-0-{index}",
        service="zerotesting-lightpush-server",
        count_key="lightpush_server",
    ),
    NodeType(
        name_template="lpclient-0-{index}",
        service="zerotesting-lightpush-client",
        count_key="lightpush_client",
    ),
    NodeType(
        name_template="bootstrap-{index}",
        service="zerotesting-bootstrap",
        count_key="bootstrap",
    ),
]


def get_ips_by_type(args: dict, *, namespace=None) -> List[Tuple[str, str]]:
    """
    Get node ips based on type flags (--store, --relay, etc) starting at start_index for each node type.

    :return: (name, ip) tuples for node specified.
    :rtype: List[str, str]
    """
    # TODO: Handle multiple shards.

    results = []
    for node_type in node_types:
        start_index = args.get("start_index", 0)
        if args[node_type.count_key] == "all":
            try:
                _, _, ip_list = socket.gethostbyname_ex(node_type.service)
                count = len(ip_list) - start_index
            except socket.gaierror:
                # This happens when either:
                # 1. The service doesn't exist.
                # 2. No pods with the matching app selector exist, thus though the service exists, it isn't running on any pod.
                count = 0
            # TODO: Check at the end if all `count` ips have been found.
            # TODO: Add "unknown-{index}" for ips not in {nodetype}-0-{index}
            # Note that if node types share the same service, count will be set to the total.
            # for example fserver/fclient both use zerotesting-filter.
        else:
            try:
                count = int(args[node_type.count_key])
            except (KeyError, TypeError):
                logger.info(f"No count for nodetype specified. `{node_type}`")
                continue

        logger.info(
            f"Getting {count} IPs from nodes of type `{node_type.name_template}` starting at index {start_index}"
        )
        for index in range(start_index, start_index + count):
            dns = node_type.dns_name(index)
            try:
                _, _, ips = socket.gethostbyname_ex(dns)
                results.append((node_type.get_node_name(index), ips[0]))
            except Exception as e:
                error = traceback.format_exc()
                logger.error(
                    f"Failed to resolve dns. dns: `{dns}`, node_type: `{node_type}`, exception: `{e}`, error: {error}"
                )

    return results


def get_api_args(args_dict: dict) -> dict:
    """These are the arguments that should be passed on to the GET request for store messages."""
    return {
        key: value
        for key, value in args_dict.items()
        if key
        in [
            "contentTopics",
            "pubsubTopic",
            "pageSize",
            "cursor",
        ]
    }


def positive_int_or_all(value):
    if value == "all":
        return value
    try:
        int_value = int(value)
        assert int_value >= 0
        return int_value
    except (ValueError, AssertionError):
        raise argparse.ArgumentTypeError(f"{value} is not an integer or 'all'.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Waku storage retriever")
    parser.add_argument(
        "-c", "--contentTopics", type=str, help="Content topic", default="/my-app/1/dst/proto"
    )
    parser.add_argument(
        "-p", "--pubsubTopic", type=str, help="Pubsub topic", default="/waku/2/rs/2/0"
    )
    parser.add_argument(
        "-ps", "--pageSize", type=int, help="Number of messages to retrieve per page", default=60
    )
    parser.add_argument(
        "-cs",
        "--cursor",
        type=str,
        help="Cursor field intended for pagination purposes. ",
        default="",
    )

    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="",
        dest="debug",
    )

    parser.add_argument(
        "-rd",
        "--request-delay",
        type=float,
        default=0.3,
        help="Delay between each REST API call on a node. Only applicable in --debug mode.",
        dest="delay_between_requests",
    )

    parser.add_argument(
        "-t",
        "--select-types",
        action="store_true",
        help="If specified, gathers ips for nodes of the types indicated by additional flags (e.g., --store, --relay). If not specified, selects a random node of any type.",
        dest="select_types",
    )

    parser.add_argument(
        "-s",
        "--store",
        type=positive_int_or_all,
        help="Number of store nodes",
        dest="store",
    )
    parser.add_argument(
        "-r",
        "--relay",
        type=positive_int_or_all,
        help="Number of plain relay nodes",
        dest="relay",
    )
    parser.add_argument(
        "-fs",
        "--filter-server",
        type=positive_int_or_all,
        help="Number of fserver nodes",
        dest="filter_server",
    )
    parser.add_argument(
        "-fc",
        "--filter-client",
        type=positive_int_or_all,
        help="Number of fclient nodes",
        dest="filter_client",
    )
    parser.add_argument(
        "-lps",
        "--lightpush-server",
        type=positive_int_or_all,
        help="Number of lpserver nodes",
        dest="lightpush_server",
    )
    parser.add_argument(
        "-lpc",
        "--lightpush-client",
        type=positive_int_or_all,
        help="Number of lpclient nodes",
        dest="lightpush_client",
    )
    parser.add_argument(
        "-bn",
        "--bootstrap",
        type=positive_int_or_all,
        help="Number of bootstrap nodes",
        dest="bootstrap",
    )

    parser.add_argument(
        "-si",
        "--start-index",
        type=int,
        default=0,
        help="Start looking for at index: {nodetype}-0-{index}",
        dest="start_index",
    )

    args = parser.parse_args()
    assert args.select_types == any(
        [
            args.relay,
            args.store,
            args.filter_server,
            args.filter_client,
            args.lightpush_server,
            args.lightpush_client,
            args.bootstrap,
        ]
    ), "--select-types should be True if any node types have been specified and False otherwise."

    return args


def main(args: Namespace):
    args_dict = vars(args)
    api_args = get_api_args(args_dict)

    logger.info(f"Arguments: {args_dict}")

    nodes = get_ips(args)

    messages = []
    for index, (name, node) in enumerate(nodes):
        try:
            logger.info(
                f"fetching messages. name: `{name}` url: `{node}` index: {index+1}/{len(nodes)} ({100* (index+1) / len(nodes):.2f}%)"
            )

            url = f"http://{node}/store/v3/messages"
            logger.info(f"Query to {url}")
            headers = {"accept": "application/json"}
            new_messages = fetch_all_messages(url, api_args, headers)
            messages.extend(new_messages)

        except Exception as e:
            error = traceback.format_exc()
            print(f"exception while fetching messages. exception: `{e}`, error: `{error}`")

    logger.info("List of messages")
    # # We do a print here, so it is easier to parse when reading from victoria logs
    print(messages)


def get_ips(args) -> Tuple[str, str]:
    port = 8645
    if args.select_types:
        ips = get_ips_by_type(vars(args))
        logger.info(f"ips: ({len(ips)}): ```{ips}```")
        return [(name, f"{ip}:{port}") for name, ip in ips]
    else:
        service = f"zerotesting-service:{port}"
        return [resolve_dns(service)]


def main_debug(args: Namespace):
    args_dict = vars(args)
    api_args = get_api_args(args_dict)

    logger.info(f"Arguments: {args_dict}")

    nodes = get_ips(args)
    for name, node in nodes:
        attempt = 1
        max_attempts = 10
        delay = 0.5
        while True:
            time.sleep(delay)
            try:
                logger.info(f"fetching messages. name: `{name}` url: `{node}` attempt: `{attempt}`")
                logger.info(f"fetching messages. name: `{name}` url: `{node}`")
                node_info = get_node_info(name, node, api_args, args.delay_between_requests)
                node_info["attempt"] = attempt
                logger.info(
                    f"store_msg_retriever::node_info: ```{json.dumps(node_info, default=serializer)}```"
                )
                if all(
                    code == 200
                    for code in node_info["store_messages"]["response"]["inner_statusCodes"]
                ):
                    logging.info("No inner status failures")
                    if attempt > 1:
                        logger.info("main::A previous attempt failed, but now it worked.")
                    break
                logging.info("Inner status failures detected")
                if attempt >= max_attempts:
                    break
                attempt += 1

            except Exception as e:
                error = traceback.format_exc()
                logging.error(
                    f"exception while fetching messages. exception: `{e}`, error: `{error}`"
                )


if __name__ == "__main__":
    args = parse_args()
    if args.debug:
        main_debug(args)
    else:
        main(args)
