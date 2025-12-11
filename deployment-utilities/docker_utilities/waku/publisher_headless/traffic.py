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
import dns.resolver
from typing import Tuple, List


async def load_service_endpoints(service: str, namespace: str) -> List[Tuple[str, str, str]]:
    fqdn = f"{service}.{namespace}.svc.cluster.local"
    srv_query = f"_rest._tcp.{fqdn}"

    try:
        answers = dns.resolver.resolve(srv_query, "SRV")
    except Exception as e:
        raise RuntimeError(f"Failed SRV query for service {service}: {e}")

    endpoints = []

    for ans in answers:
        hostname = str(ans.target).rstrip(".")
        try:
            ip = socket.gethostbyname(hostname)
        except Exception as e:
            raise RuntimeError(f"Failed resolving pod hostname {hostname}: {e}")

        # hostname = rln-0-1.rln-nodes.rln-test.svc.cluster.local
        short = hostname.split(".")[0]  # rln-0-1
        shard = short.split("-")[1]     # 0

        endpoints.append((ip, short, shard))

    if not endpoints:
        raise RuntimeError(f"No endpoints discovered for service {service}")

    logging.info(f"Discovered {len(endpoints)} endpoints for service {service}: {endpoints}")
    return endpoints


async def send_to_relay(args: argparse.Namespace, endpoints):
    node_ip, node_host, node_shard = random.choice(endpoints)

    topic = urllib.parse.quote(args.pubsub_topic + node_shard, safe="")
    url = f"http://{node_ip}:{args.port}/relay/v1/messages/{topic}"

    payload = base64.b64encode(os.urandom(args.msg_size_kbytes * 1000)).decode("ascii").rstrip("=")
    headers = {"Content-Type": "application/json"}
    body = {"payload": payload, "contentTopic": args.content_topic, "version": 1}

    return url, headers, body, node_host


async def send_to_lightpush(args: argparse.Namespace, endpoints):
    node_ip, node_host, shard = random.choice(endpoints)

    url = f"http://{node_ip}:{args.port}/lightpush/v3/message"

    payload = base64.b64encode(os.urandom(args.msg_size_kbytes * 1000)).decode("ascii").rstrip("=")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    body = {
        "pubsubTopic": args.pubsub_topic + shard,
        "message": {"payload": payload, "contentTopic": args.content_topic, "version": 1},
    }

    return url, headers, body, node_host


service_dispatcher = {
    'relay': send_to_relay,
    'lightpush': send_to_lightpush
}



async def send_waku_msg(args, stats, i, endpoints):
    index = random.choice(range(len(args.protocols)))
    protocol = args.protocols[index]
    protocol_function = service_dispatcher[protocol]

    url, headers, body, node_hostname = await protocol_function(args, endpoints)

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

                success_rate = stats['success'] / stats['total'] * 100
                logging.info(f"{log_line}"
                    f"Time: [{elapsed_time:.4f} ms], "
                    f"Success: {stats['success']}, Failure: {stats['failure']}, "
                    f"Success Rate: {success_rate:.2f}%")
    except Exception as e:
        elapsed_time = (time.time() - start_time) * 1000
        stats['failure'] += 1
        stats['total'] += 1
        success_rate = stats['success'] / stats['total'] * 100
        logging.info(
            f"Exception during message {i} sent to {node_hostname}: {str(e)}, "
            f"Time: [{elapsed_time:.4f} ms], Url: {url}, headers: {headers}, body: {body}, "
            f"Success Rate: {success_rate:.2f}%"
        )


async def inject_message(background_tasks, args, stats, i, endpoints):
    task = asyncio.create_task(send_waku_msg(args, stats, i, endpoints))
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)


async def main(args: argparse.Namespace):
    logging.info("Loading service endpoints...")
    endpoints = await load_service_endpoints(args.service_names[0])
    logging.info(f"Using endpoints: {endpoints}")

    background_tasks = set()
    stats = {'success': 0, 'failure': 0, 'total': 0}

    for i in range(args.messages):
        await inject_message(background_tasks, args, stats, i, endpoints)
        await asyncio.sleep(args.delay_seconds)

    await asyncio.gather(*background_tasks)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Waku message injector")
    parser.add_argument('-pt', '--pubsub-topic', type=str, help='Pubsub topic',
                        default='/waku/2/rs/2/')
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
    parser.add_argument('-sn', '--service-names', help='K8s services used inject messages', nargs="+", default=['rln-nodes'], )
    parser.add_argument('-p', '--port', help='Waku REST port', type=int, default=8645)
    parser.add_argument('--log-level', default='info')
    return parser.parse_args()


def configure_logging(level: str):
    numeric = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=numeric, format="%(asctime)s [%(levelname)s] %(message)s")


if __name__ == "__main__":
    args = parse_args()
    configure_logging(args.log_level)
    logging.info(f'{args}')
    asyncio.run(main(args))

# Todo: extraer las ips de todos los servicios, porque pueden usarse varios.