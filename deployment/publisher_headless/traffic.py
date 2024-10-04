import time
import os
import base64
import urllib.parse
import asyncio
import aiohttp
import argparse
import socket


async def check_dns_time(node: str) -> (str, str):
    start_time = time.time()
    name, port = node.split(":")
    ip_address = socket.gethostbyname(name)
    elapsed = (time.time() - start_time) * 1000
    print(f"{name} DNS Response took {elapsed} ms")
    return f"{ip_address}:{port}"


async def get_node_shard(ip_port: str) -> str:
    ip, port = ip_port.split(":")
    hostname = socket.gethostbyaddr(ip)
    node_shard = hostname[0].split('.')[0].split('-')[1]
    return node_shard


async def send_waku_msg(node: str, kbytes: int, pubsub_topic: str, content_topic: str, debug: bool,
                        stats: dict, shard_messages: dict, shards: int, i: int):
    payload = base64.b64encode(os.urandom(kbytes * 1000)).decode('ascii').rstrip("=")
    # print("Message size:", len(payload) * 3 / 4 / 1000, "KBytes")
    body = {"payload": payload, "contentTopic": content_topic, "version": 1}
    node = await check_dns_time(node) if debug else node
    node_shard = await get_node_shard(node) if shards > 1 else '0'
    topic = urllib.parse.quote(pubsub_topic+node_shard, safe='')
    url = f"http://{node}/relay/v1/messages/{topic}"
    # print(f"Waku REST API: {url} PubSubTopic: {pubsub_topic}, ContentTopic: {content_topic}")
    print(f"Message {i+1} sent to {node}, shard {node_shard} at {time.strftime('%H:%M:%S')}")
    start_time = time.time()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body,
                                    headers={'Content-Type': 'application/json'}) as response:
                elapsed_time = (time.time() - start_time) * 1000
                if response.status == 200:
                    stats['success'] += 1
                    shard_messages[node_shard] = shard_messages.get(node_shard, 0) + 1
                else:
                    stats['failure'] += 1
                stats['total'] += 1
                success_rate = (stats['success'] / stats['total']) * 100 if stats['total'] > 0 else 0
                response_text = await response.text()
                print(
                    f"Response from message {i+1} sent to {node} shard {node_shard}: status:{response.status}, {response_text}, Time: [{elapsed_time:.4f} ms], "
                    f"Success: {stats['success']}, Failure: {stats['failure']}, "
                    f"Success Rate: {success_rate:.2f}%")
    except Exception as e:
        elapsed_time = (time.time() - start_time) * 1000
        stats['failure'] += 1
        stats['total'] += 1
        success_rate = (stats['success'] / stats['total']) * 100 if stats['total'] > 0 else 0
        print(
            f"Exception during message {i} sent to {node}: {str(e)}, Time: [{elapsed_time:.4f} ms], "
            f"Success: {stats['success']}, Failure: {stats['failure']}, "
            f"Success Rate: {success_rate:.2f}%")


async def inject_message(background_tasks: set, args: argparse.Namespace, node: str, stats: dict, shard_messages: dict,
                         i: int):
    task = asyncio.create_task(
        send_waku_msg(node, args.msg_size_kbytes, args.pubsub_topic, args.content_topic, args.debug,
                      stats, shard_messages, args.shards, i))
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)


async def main(service: str, args: argparse.Namespace):
    background_tasks = set()
    stats = {'success': 0, 'failure': 0, 'total': 0}
    shard_messages = {}

    for i in range(args.messages):
        await inject_message(background_tasks, args, service, stats, shard_messages, i)
        await asyncio.sleep(args.delay_seconds)

    await asyncio.gather(*background_tasks)

    print(shard_messages)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Waku message sender")
    parser.add_argument('--debug', action='store_true', help='Show DNS resolve times')
    parser.add_argument('-c', '--content-topic', type=str, help='Content topic', default="kubekube")
    parser.add_argument('-p', '--pubsub-topic', type=str, help='Pubsub topic',
                        default="/waku/2/rs/2/")
    parser.add_argument('-s', '--msg-size-kbytes', type=int, help='Message size in kBytes',
                        default=10)
    parser.add_argument('-d', '--delay-seconds', type=float, help='Delay between messages',
                        default=1)
    parser.add_argument('-m', '--messages', type=int, help='Number of messages to inject',
                        default=10)
    parser.add_argument('-sh', '--shards', type=int, help='Number of shards',
                        default=1)

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    service = "zerotesting-service:8645"
    print(f"Starting message injection to {service}. {args}")
    asyncio.run(main(service, args))
