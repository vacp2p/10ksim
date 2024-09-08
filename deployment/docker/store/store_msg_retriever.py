# Python Imports
import argparse
import logging
import requests
import socket
import time
from typing import Dict, List

logging.basicConfig(level=logging.DEBUG)


def check_dns_time(node: str) -> str:
    start_time = time.time()
    name, port = node.split(":")
    ip_address = socket.gethostbyname(name)
    elapsed = (time.time() - start_time) * 1000
    logging.info(f"{name} DNS Response took {elapsed} ms")

    return f"{ip_address}:{port}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Waku storage retriever")
    parser.add_argument('-c', '--contentTopics', type=str, help='Content topic', default="kubekube")
    parser.add_argument('-p', '--pubsubTopic', type=str, help='Pubsub topic',
                        default="/waku/2/rs/2/0")
    parser.add_argument('-ps', '--pageSize', type=int,
                        help='Number of messages to retrieve per page', default=60)
    parser.add_argument('-cs', '--cursor', type=str,
                        help='Cursor field intended for pagination purposes. ', default="")

    return parser.parse_args()


def next_cursor(data: Dict) -> str | None:
    cursor = data.get('paginationCursor')
    if not cursor:
        logging.info("No more messages")
        return None

    return cursor


def fetch_all_messages(base_url: str, initial_params: Dict, headers: Dict) -> List[str]:
    all_messages = []
    params = initial_params.copy()

    while True:
        response = requests.get(base_url, headers=headers, params=params)
        if response.status_code != 200:
            logging.error(f"Error fetching data: {response.status_code}")
            break

        data = response.json()
        logging.info(data)
        all_messages.extend([message['messageHash'] for message in data['messages']])

        cursor = next_cursor(data)
        if not cursor:
            break
        params["cursor"] = cursor

    return all_messages


def main():
    args = parse_args()
    args_dict = vars(args)
    logging.info(f"Arguments: {args_dict}")

    service = "zerotesting-service:8645"
    node = check_dns_time(service)
    url = f"http://{node}/store/v3/messages"
    logging.info(f"Query to {url}")
    headers = {"accept": "application/json"}

    messages = fetch_all_messages(url, args_dict, headers)
    logging.info("List of messages")
    # We do a print here, so it is easier to parse when reading from victoria logs
    print(messages)


if __name__ == "__main__":
    main()
