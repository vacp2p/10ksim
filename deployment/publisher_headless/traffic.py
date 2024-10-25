import random
import time
import os
import base64
import urllib.parse
import asyncio
import aiohttp
import argparse
import socket
import logging

logging.basicConfig(level=logging.INFO)


async def check_dns_time(service: str) -> (str, str):
    start_time = time.time()
    ip_address = socket.gethostbyname(service)
    elapsed = (time.time() - start_time) * 1000
    entire_hostname = socket.gethostbyaddr(ip_address)
    hostname = entire_hostname[0].split('.')[0]
    logging.info(f'{service} DNS Response took {elapsed} ms. Resolved to {hostname}.')
    return f'{ip_address}', hostname


async def get_node_shard(ip_port: str) -> str:
    ip, port = ip_port.split(':')
    hostname = socket.gethostbyaddr(ip)
    node_shard = hostname[0].split('.')[0].split('-')[1]
    logging.info(f'Using shard {node_shard}')
    return node_shard


async def send_to_relay(args: argparse.Namespace):
    node_address, node_hostname = await check_dns_time('zerotesting-service') if args.debug \
        else socket.gethostbyname('zerotesting-service')
    node_shard = await get_node_shard(node_address) if args.shards > 1 else '0'
    topic = urllib.parse.quote(args.pubsub_topic + node_shard, safe='')
    url = f'http://{node_address}:{args.port}/relay/v1/messages/{topic}'

    payload = base64.b64encode(os.urandom(args.msg_size_kbytes * 1000)).decode('ascii').rstrip("=")
    headers = {'Content-Type': 'application/json'}
    body = {'payload': payload, 'contentTopic': args.content_topic, 'version': 1}

    return url, headers, body, node_hostname


async def send_to_lightpush(args: argparse.Namespace):
    node_address, node_hostname = await check_dns_time('zerotesting-lightpush-client') if args.debug \
        else socket.gethostbyname('zerotesting-lightpush-client')
    url = f'http://{node_address}:{args.port}/lightpush/v1/message'
    payload = base64.b64encode(os.urandom(args.msg_size_kbytes * 1000)).decode('ascii').rstrip("=")
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
    # TODO HANDLE BETTER THIS SHARD
    body = {'pubsubTopic': args.pubsub_topic+'0', 'message': {'payload': payload, 'contentTopic': args.content_topic,
                                                              'version': 1}}

    return url, headers, body, node_hostname


service_dispatcher = {
    'relay': send_to_relay,
    'lightpush': send_to_lightpush
}


async def send_waku_msg(args: argparse.Namespace, stats: dict, i: int):
    protocol = random.choice(args.protocols)
    protocol_function = service_dispatcher[protocol]

    url, headers, body, node_hostname = await protocol_function(args)

    logging.info(f"Message {i+1} sent at {time.strftime('%H:%M:%S')}")
    start_time = time.time()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body, headers=headers) as response:
                elapsed_time = (time.time() - start_time) * 1000
                if response.status == 200:
                    stats['success'] += 1
                else:
                    stats['failure'] += 1
                stats['total'] += 1
                success_rate = (stats['success'] / stats['total']) * 100 if stats['total'] > 0 else 0
                response_text = await response.text()
                logging.info(
                    f"Response from message {i+1} sent to {node_hostname} status:{response.status}, {response_text}, "
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
            f"Success: {stats['success']}, Failure: {stats['failure']}, "
            f"Success Rate: {success_rate:.2f}%")


async def inject_message(background_tasks: set, args: argparse.Namespace, stats: dict, i: int):
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
    parser.add_argument('--debug', action='store_true', help='Show DNS resolve times')
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
    parser.add_argument('-sh', '--shards', type=int, help='Number of shards',
                        default=1)
    parser.add_argument('-ps', '--protocols', nargs='+', default=['relay'],
                        required=True, help='Protocols used inject messages')
    parser.add_argument('-p', '--port', type=int, default=8645, help='Waku REST port')

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    logging.info(f"{args}")
    asyncio.run(main(args))
