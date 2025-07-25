import aiohttp
import argparse
import asyncio
import base64
import logging
import os
import random
import socket
import time
import urllib.parse
from typing import Tuple, Dict

logging.basicConfig(level=logging.INFO)


async def check_dns_time(service: str) -> tuple[str, str, str]:
    start_time = time.time()
    try:
        ip_address = socket.gethostbyname(service)
        elapsed = (time.time() - start_time) * 1000
        entire_hostname = socket.gethostbyaddr(ip_address)
        try:
            hostname = entire_hostname[0].split('.')[0]
            node_shard = int(hostname.split('-')[1])
            logging.info(f'{service} DNS Response took {elapsed} ms. Resolved to {hostname} with shard {node_shard}.')
            return f'{ip_address}', hostname, f'{node_shard}'
        except Exception as e:
            logging.error(f"Failed. Service: `{service}`\nip_address: {ip_address}\nelapsed: {elapsed}\nentire_hostname: {entire_hostname}: `{e}`")
            raise RuntimeError("Failed to split") from e
    except (IndexError, ValueError) as e:
        logging.error(f"Failed. Service: `{service}`: `{e}`")
        raise RuntimeError("Failed check_dns_time") from e


async def send_to_relay(args: argparse.Namespace) -> Tuple[str, Dict[str, str], Dict[str, str | int], str]:
    node_address, node_hostname, node_shard = await check_dns_time('zerotesting-service')
    topic = urllib.parse.quote(args.pubsub_topic + node_shard, safe='')
    url = f'http://{node_address}:{args.port}/relay/v1/messages/{topic}'

    payload = base64.b64encode(os.urandom(args.msg_size_kbytes * 1000)).decode('ascii').rstrip("=")
    headers = {'Content-Type': 'application/json'}
    body = {'payload': payload, 'contentTopic': args.content_topic, 'version': 1}

    return url, headers, body, node_hostname


async def send_to_lightpush(args: argparse.Namespace) -> Tuple[str, Dict[str, str], Dict[str, dict[str, str | int]], str]:
    node_address, node_hostname, shard = await check_dns_time('zerotesting-lightpush-client')
    url = f'http://{node_address}:{args.port}/lightpush/v3/message'

    payload = base64.b64encode(os.urandom(args.msg_size_kbytes * 1000)).decode('ascii').rstrip("=")
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
    body = {'pubsubTopic': args.pubsub_topic + shard,
            'message': {'payload': payload, 'contentTopic': args.content_topic,
                        'version': 1}}

    return url, headers, body, node_hostname


service_dispatcher = {
    'relay': send_to_relay,
    'lightpush': send_to_lightpush
}


async def send_waku_msg(args: argparse.Namespace, stats: Dict[str, int], i: int):
    protocol = random.choice(args.protocols)
    protocol_function = service_dispatcher[protocol]

    url, headers, body, node_hostname = await protocol_function(args)

    logging.info(f"Message {i + 1} sent at {time.strftime('%H:%M:%S')}")
    start_time = time.time()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body, headers=headers) as response:
                elapsed_time = (time.time() - start_time) * 1000
                response_text = await response.text()
                log_line = f"Response from message {i + 1} sent to {node_hostname} status:{response.status}, {response_text},\n"

                if response.status == 200:
                    stats['success'] += 1
                else:
                    stats['failure'] += 1
                    log_line += f"Url: {url}, headers: {headers}, body: {body},\n"
                stats['total'] += 1

                success_rate = (stats['success'] / stats['total']) * 100 if stats['total'] > 0 else 0
                logging.info(f"{log_line}"
                    f"Time: [{elapsed_time:.4f} ms], "
                    f"Success: {stats['success']}, Failure: {stats['failure']}, "
                    f"Success Rate: {success_rate:.2f}%")
    except Exception as e:
        elapsed_time = (time.time() - start_time) * 1000
        stats['failure'] += 1
        stats['total'] += 1
        success_rate = (stats['success'] / stats['total']) * 100 if stats['total'] > 0 else 0
        logging.info(
            f"Exception during message {i} sent to {node_hostname} : {str(e)}, Time: [{elapsed_time:.4f} ms], "
            f"Url: {url}, headers: {headers}, body: {body}"
            f"Success: {stats['success']}, Failure: {stats['failure']}, "
            f"Success Rate: {success_rate:.2f}%")


async def inject_message(background_tasks: set, args: argparse.Namespace, stats: Dict[str, int], i: int):
    task = asyncio.create_task(send_waku_msg(args, stats, i))
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)


async def main(args: argparse.Namespace):
    background_tasks = set()
    stats = {'success': 0, 'failure': 0, 'total': 0}

    for i in range(args.messages):
        await inject_message(background_tasks, args, stats, i)
        await asyncio.sleep(args.delay_seconds)

    await asyncio.gather(*background_tasks)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Waku message injector")
    parser.add_argument('-pt', '--pubsub-topic', type=str, help='Pubsub topic',
                        default="/waku/2/rs/2/")
    parser.add_argument('-ct', '--content-topic', type=str, help='Content topic',
                        default="/my-app/1/dst/proto")
    parser.add_argument('-s', '--msg-size-kbytes', type=int, help='Message size in kBytes',
                        default=10)
    parser.add_argument('-d', '--delay-seconds', type=float, help='Delay between messages',
                        default=1)
    parser.add_argument('-m', '--messages', type=int, help='Number of messages to inject',
                        default=10)
    parser.add_argument('-ps', '--protocols', nargs='+', default=['relay'],
                        help='Protocols used inject messages')
    parser.add_argument('-p', '--port', type=int, default=8645, help='Waku REST port')

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    logging.info(f'{args}')
    asyncio.run(main(args))
