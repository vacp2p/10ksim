import time
import os
import base64
import urllib.parse
import argparse
import aiohttp
import asyncio

async def send_waku_msg(node_address, kbytes, pubsub_topic, content_topic):
    # TODO dirty trick .replace("=", "")
    base64_payload = (base64.b64encode(os.urandom(kbytes*1000)).decode('ascii')).replace("=", "")
    print("size message kBytes", len(base64_payload) *(3/4)/1000, "KBytes")
    body = {
        "payload": base64_payload,
        "contentTopic": content_topic,
        "version": 1,  # You can adjust the version as needed
        #"timestamp": int(time.time())
    }

    encoded_pubsub_topic = urllib.parse.quote(pubsub_topic, safe='')

    url = f"{node_address}/relay/v1/messages/{encoded_pubsub_topic}"
    headers = {'content-type': 'application/json'}

    print('Waku REST API: %s PubSubTopic: %s, ContentTopic: %s' % (url, pubsub_topic, content_topic))
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

async def main(nodes, args):
    background_tasks = set()
    while True:
        for node in nodes:
            task = asyncio.create_task(send_waku_msg(node, args.msg_size_kbytes, args.pubsub_topic, args.content_topic))
            print(f"Message sent to {node} at {time.strftime('%H:%M:%S')}")
            background_tasks.add(task)
            task.add_done_callback(background_tasks.discard)
            await asyncio.sleep(1)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='')

    # these flags are mutually exclusive, one or the other, never at once
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-sn', '--single-node', type=str,
                       help='example: http://waku-simulator_nwaku_1:8645')
    group.add_argument('-mn', '--multiple-nodes', type=str,
                       help='example: http://waku-simulator_nwaku_[1..10]:8645')

    # rest of arguments
    parser.add_argument('-c', '--content-topic', type=str, help='content topic', default="kubekube")
    parser.add_argument('-p', '--pubsub-topic', type=str, help='pubsub topic',
                        default="/waku/2/kubetopic")
    parser.add_argument('-s', '--msg-size-kbytes', type=int, help='message size in kBytes',
                        default=10)
    parser.add_argument('-d', '--delay-seconds', type=int, help='delay in second between messages')
    parser.add_argument('-cpp', '--containers-per-pod', type=int,
                        help='number of containers in pod', default=1)
    args = parser.parse_args()

    print(args)

    if args.single_node != None:
        print("Injecting traffic to single node REST API:", args.single_node)

    # this simply converts from http://url_[1..5]:port to
    # [http://url_1:port
    nodes = []
    if args.multiple_nodes:
        range_nodes = args.multiple_nodes.split(":")[1].split("-")[1]
        port_nodes = args.multiple_nodes.split(":")[-1]
        node_placeholder = args.multiple_nodes.replace(range_nodes, "{placeholder}")
        node_placeholder = node_placeholder.replace(port_nodes, "{port}")
        clean_range = range_nodes.replace("[", "").replace("]", "")
        start = int(clean_range.split("..")[0])
        end = int(clean_range.split("..")[1])

        print("Injecting traffic to multiple nodes REST APIs")
        for i in range(start, end):
            for j in range(0, args.containers_per_pod):
                nodes.append(node_placeholder.replace("{placeholder}", str(i)).replace("{port}",
                                                                                       str(8645 + j)))

    for node in nodes:
        print(node)

    asyncio.run(main(nodes, args))

