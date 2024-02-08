import time
import os
import base64
import urllib.parse
import argparse
import aiohttp
import asyncio
import socket
from itertools import cycle


def check_dns_time(node: str):
    name_to_resolve = node.split(":")[1]

    s_time = time.time()

    ip_addr = socket.gethostbyname(name_to_resolve[2:])

    elapsed_ms = (time.time() - s_time) * 1000

    print(f"DNS Response took {elapsed_ms} ms")

    return f"http://{ip_addr}:{node.split(':')[2]}"


async def send_waku_msg(node_address, kbytes, pubsub_topic, content_topic, debug):
    # TODO dirty trick .replace("=", "")
    base64_payload = (base64.b64encode(os.urandom(kbytes*1000)).decode('ascii')).replace("=", "")
    print("size message kBytes", len(base64_payload) * (3/4)/1000, "KBytes")
    body = {
        "payload": base64_payload,
        "contentTopic": content_topic,
        "version": 1,  # You can adjust the version as needed
        #"timestamp": int(time.time())
    }

    encoded_pubsub_topic = urllib.parse.quote(pubsub_topic, safe='')

    if debug:
        node_address = check_dns_time(node_address)

    url = f"{node_address}/relay/v1/messages/{encoded_pubsub_topic}"
    headers = {'content-type': 'application/json'}

    print(f"Waku REST API: {url} PubSubTopic: {pubsub_topic}, ContentTopic: {content_topic}")
    s_time = time.time()

    response = None

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body, headers=headers) as response:
                response_text = await response.text()
                elapsed_ms = (time.time() - s_time) * 1000
                print('Response from %s: status:%s content:%s [%.4f ms.]' % (
                    node_address, response.status, response_text, elapsed_ms))
    except Exception as e:
        print(f"Error sending request: {e}")


def pod_generator(n_pods):
    for pod_index in range(0, n_pods):
        yield f"http://nodes-{pod_index}:8645"


async def main(nodes, args):
    background_tasks = set()
    while True:
        for node in nodes:
            task = asyncio.create_task(send_waku_msg(node, args.msg_size_kbytes, args.pubsub_topic,
                                                     args.content_topic, args.debug))
            print(f"Message sent to {node} at {time.strftime('%H:%M:%S')}")
            background_tasks.add(task)
            task.add_done_callback(background_tasks.discard)
            await asyncio.sleep(1)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='')

    parser.add_argument('-n', '--nodes', type=int, help='Number of nodes')
    parser.add_argument('--debug', default=False, type=bool)
    parser.add_argument('-c', '--content-topic', type=str, help='content topic', default="kubekube")
    parser.add_argument('-p', '--pubsub-topic', type=str, help='pubsub topic',
                        default="/waku/2/kubetopic")
    parser.add_argument('-s', '--msg-size-kbytes', type=int, help='message size in kBytes',
                        default=10)
    parser.add_argument('-d', '--delay-seconds', type=int, help='delay in second between messages')
    args = parser.parse_args()

    print(args)

    nodes = cycle(pod_generator(args.nodes))

    print("Injecting traffic to multiple nodes REST APIs")
    print(f"Injecting from node {0} to node {args.nodes}")

    asyncio.run(main(nodes, args))
