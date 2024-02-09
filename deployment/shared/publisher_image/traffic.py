import time
import os
import base64
import urllib.parse
import argparse
import aiohttp
import asyncio
import socket
from itertools import cycle


async def check_dns_time(node: str) -> str:
    name_to_resolve, port = node.split(":")

    s_time = time.time()

    ip_addr = socket.gethostbyname(name_to_resolve)

    elapsed_ms = (time.time() - s_time) * 1000

    print(f"{name_to_resolve} DNS Response took {elapsed_ms} ms")

    return f"http://{ip_addr}:{port}"


async def send_waku_msg(node: str, kbytes: int, pubsub_topic: str, content_topic: str, debug: bool):
    base64_payload = (base64.b64encode(os.urandom(kbytes*1000)).decode('ascii')).replace("=", "")
    print("size message kBytes", len(base64_payload) * (3/4)/1000, "KBytes")
    body = {
        "payload": base64_payload,
        "contentTopic": content_topic,
        "version": 1
    }

    encoded_pubsub_topic = urllib.parse.quote(pubsub_topic, safe='')

    if debug:
        node = await check_dns_time(node)

    url = f"{node}/relay/v1/messages/{encoded_pubsub_topic}"
    headers = {'content-type': 'application/json'}

    print(f"Waku REST API: {url} PubSubTopic: {pubsub_topic}, ContentTopic: {content_topic}")
    s_time = time.time()

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body, headers=headers) as response:
                response_text = await response.text()
                elapsed_ms = (time.time() - s_time) * 1000
                print('Response from %s: status:%s content:%s [%.4f ms.]' % (
                    node, response.status, response_text, elapsed_ms))
    except Exception as e:
        print(f"Error sending request: {e}")


def pod_generator(n_pods: int) -> str:
    for pod_index in range(0, n_pods):
        yield f"nodes-{pod_index}:8645"


async def inject_message(background_tasks: set, args_namespace: argparse.Namespace, node: str):
    task = asyncio.create_task(send_waku_msg(node, args_namespace.msg_size_kbytes,
                                             args_namespace.pubsub_topic,
                                             args_namespace.content_topic,
                                             args_namespace.debug))
    print(f"Message sent to {node} at {time.strftime('%H:%M:%S')}")
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)


async def main(nodes: cycle[str], args_namespace: argparse.Namespace) -> None:
    background_tasks = set()
    while True:
        for node in nodes:
            await inject_message(background_tasks, args_namespace, node)
            await asyncio.sleep(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='')

    parser.add_argument('-n', '--nodes', type=int, help='Number of nodes')
    parser.add_argument('-d', '--debug', action='store_true',
                        help='To show DNS resolve times')
    parser.add_argument('-c', '--content-topic', type=str, help='content topic',
                        default="kubekube")
    parser.add_argument('-p', '--pubsub-topic', type=str, help='pubsub topic',
                        default="/waku/2/kubetopic")
    parser.add_argument('-s', '--msg-size-kbytes', type=int,
                        help='message size in kBytes', default=10)
    parser.add_argument('-d', '--delay-seconds', type=int,
                        help='delay in second between messages')
    parsed_args = parser.parse_args()

    print(parsed_args)

    return parsed_args


if __name__ == "__main__":

    args = parse_args()

    nodes_cycle_generator = cycle(pod_generator(args.nodes))

    print("Injecting traffic to multiple nodes REST APIs")
    print(f"Injecting from node {0} to node {args.nodes}")

    asyncio.run(main(nodes_cycle_generator, args))
