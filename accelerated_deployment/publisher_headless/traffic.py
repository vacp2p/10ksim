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

async def send_waku_msg(node: str, kbytes: int, pubsub_topic: str, content_topic: str, debug: bool, stats: dict):
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
            elapsed_time = (time.time() - start_time) * 1000
            if response.status == 200:
                stats['success'] += 1
            else:
                stats['failure'] += 1
            stats['total'] += 1
            success_rate = (stats['success'] / stats['total']) * 100 if stats['total'] > 0 else 0
            print(f"Response from {node}: status:{response.status}, Time: [{elapsed_time:.4f} ms], Success: {stats['success']}, Failure: {stats['failure']}, Success Rate: {success_rate:.2f}%")

async def inject_message(background_tasks: set, args: argparse.Namespace, node: str, stats: dict):
    task = asyncio.create_task(send_waku_msg(node, args.msg_size_kbytes, args.pubsub_topic, args.content_topic, args.debug, stats))
    print(f"Message sent to {node} at {time.strftime('%H:%M:%S')}")
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)

async def main(nodes: cycle, args: argparse.Namespace):
    background_tasks = set()
    stats = {'success': 0, 'failure': 0, 'total': 0}
    while True:
        for node in nodes:
            await inject_message(background_tasks, args, node, stats)
            await asyncio.sleep(args.delay_seconds)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Waku message sender")
    parser.add_argument('--debug', action='store_true', help='Show DNS resolve times')
    parser.add_argument('-c', '--content-topic', type=str, help='Content topic', default="kubekube")
    parser.add_argument('-p', '--pubsub-topic', type=str, help='Pubsub topic', default="/waku/2/kubetopic")
    parser.add_argument('-s', '--msg-size-kbytes', type=int, help='Message size in kBytes', default=10)
    parser.add_argument('-d', '--delay-seconds', type=float, help='Delay between messages', default=1)
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    node = "zerotesting-service:8645"
    nodes_cycle = cycle([node])
    print("Starting message injection to zerotesting-service")
    asyncio.run(main(nodes_cycle, args))
