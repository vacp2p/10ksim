# Python Imports
import argparse
import logging
import urllib
import requests
import socket
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Dict, List, Optional

logging.basicConfig(level=logging.INFO)


def resolve_dns(address: str) -> str:
    start_time = time.time()
    name, port = address.split(":")
    ip_address = socket.gethostbyname(name)
    elapsed = (time.time() - start_time) * 1000
    logging.info(f"{address} DNS Response took {elapsed} ms")
    logging.info(f"Talking with {address}, ip address: {ip_address}")

    return f"{ip_address}:{port}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Waku filter message retriever")
    parser.add_argument('-c', '--contentTopic', type=str, help='Content topic', default="/my-app/1/dst/proto")
    parser.add_argument('-n', '--numNodes', type=int, help='Number of filter nodes to get messages from', default=1)
    parser.add_argument('-s', '--numShards', type=int, help='Number of shards in the cluster', default=1)

    return parser.parse_args()


def fetch_all_messages(base_url: str, headers: Dict, address: str) -> Optional[List[str]]:
    response = requests.get(base_url, headers=headers)
    if response.status_code != 200:
        logging.error(f"Error fetching data: {response.status_code}")
        logging.error(response.text)
        return None

    data = response.json()
    messages = [message_data['payload'] for message_data in data]
    logging.info(f"Retrieved {len(messages)} messages from {address}")

    return messages


def process_node_messages(address: str, content_topic: str) -> Optional[List[str]]:
    node_ip = resolve_dns(address)
    content_topic = urllib.parse.quote(content_topic, safe='')
    url = f"http://{node_ip}/filter/v2/messages/{content_topic}"
    logging.debug(f"Query to {url}")
    headers = {"accept": "text/plain"}

    return fetch_all_messages(url, headers, address)


def main():
    args = parse_args()
    args_dict = vars(args)
    logging.info(f"Arguments: {args_dict}")

    hostname = "fclient"
    port = "8645"

    addresses = [
        f"{hostname}-{shard}-{node}:{port}"
        for shard in range(args.numShards)
        for node in range(args.numNodes)
    ]

    all_messages = []
    with ProcessPoolExecutor() as executor:
        futures = [executor.submit(process_node_messages, address, args.contentTopic) for address in addresses]

        for future in as_completed(futures):
            result = future.result()
            if result:
                all_messages.extend(result)

    if len(all_messages) > 1:
        it = iter(all_messages)
        len_messages = len(next(it))
        if not all(len(_) == len_messages for _ in it):
            print("False")
        else:
            print("True")
    elif len(all_messages) == 1:
        print("True")
    else:
        print("False")


if __name__ == "__main__":
    main()
