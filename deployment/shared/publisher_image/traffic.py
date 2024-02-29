import time
import os
import base64
import urllib.parse
import asyncio
import aiohttp
import argparse
import socket
from itertools import cycle

async def check_dns_time(node: str) -> str:
    start_time = time.time()
    name, port = node.split(":")
    ip_address = socket.gethostbyname(name)
    elapsed = (time.time() - start_time) * 1000
    print(f"{name} DNS Response took {elapsed} ms")
    return f"{ip_address}:{port}"

async def send_waku_msg(node: str, kbytes: int, pubsub_topic: str, content_topic: str, debug: bool):
    payload = base64.b64encode(os.urandom(kbytes * 1024)).decode('ascii').rstrip("=")
    print("Message size:", len(payload) * 3 / 4 / 1024, "KBytes")
    body = {"payload": payload, "contentTopic": content_topic, "version": 1}
    topic = urllib.parse.quote(pubsub_topic, safe='')
    node = await check_dns_time(node) if debug else node
    url = f"http://{node}/relay/v1/messages/{topic}"
    print(f"Waku REST API: {url} PubSubTopic: {pubsub_topic}, ContentTopic: {content_topic}")
    start_time = time.time()
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=body, headers={'Content-Type': 'application/json'}) as response:
            print(f"Response from {node}: status:{response.status} content:{await response.text()} [{(time.time() - start_time) * 1000:.4f} ms]")

async def inject_message(background_tasks: set, args: argparse.Namespace, node: str):
    task = asyncio.create_task(send_waku_msg(node, args.msg_size_kbytes, args.pubsub_topic, args.content_topic, args.debug))
    print(f"Message sent to {node} at {time.strftime('%H:%M:%S')}")
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)

async def main(nodes: cycle, args: argparse.Namespace):
    background_tasks = set()
    while True:
        for node in nodes:
            await inject_message(background_tasks, args, node)
            await asyncio.sleep(args.delay_seconds)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Waku message sender")
    parser.add_argument('-n', '--nodes', type=int, help='Number of nodes', required=True)
    parser.add_argument('--debug', action='store_true', help='Show DNS resolve times')
    parser.add_argument('-c', '--content-topic', type=str, help='Content topic', default="kubekube")
    parser.add_argument('-p', '--pubsub-topic', type=str, help='Pubsub topic', default="/waku/2/kubetopic")
    parser.add_argument('-s', '--msg-size-kbytes', type=int, help='Message size in kBytes', default=10)
    parser.add_argument('-d', '--delay-seconds', type=float, help='Delay between messages', default=1)
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    nodes_cycle = cycle([f"nodes-{i}.zerotesting-service:8645" for i in range(args.nodes)])
    print("Starting message injection to nodes")
    asyncio.run(main(nodes_cycle, args))
