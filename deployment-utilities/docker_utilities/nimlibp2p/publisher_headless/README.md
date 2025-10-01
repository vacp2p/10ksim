## libp2p message injector

This script requests libp2p nodes to publish messages. It sends HTTP POST requests that specify the message size and topic to selected publishers, who then create and publish the requested messages in the specified topic mesh.

It allows sequential (id-based) or random (service-based) peer selection. The id-based peer selection `--peer-selection id` is intended for the [shadow simulator](https://github.com/shadow/shadow). Whereas, service-based peer selection `--peer-selection service` is intended for k8s.

The script is available with both async `traffic.py` and sync `traffic_sync.py` operations. The sync script `traffic_sync.py` is intended for the shadow simulator, as async HTTP calls halt in the shadow simulator.

This script allows specifying the number of messages, their size, inter-message delay, and the target pubsub topic. It informs selected publishers about message details (message size and topic), which create and publish requested messages.


### Arguments
- `-t` `--pubsub-topic` — Pubsub topic (default: `test`)
- `-s` `--msg-size-bytes` — Message size in bytes (default: `1000`)
- `-d` `--delay-seconds` — Delay in seconds between messages (default: `1`)
- `-m` `--messages` — Number of messages to inject (default: `10`)
- `--peer-selection` — Peer selection method. Choices: `service` (DNS service-based for k8s) or `id` (id-based for shadow simulation). (default: `id`)
- `-p` `--port` — libp2p testnode REST port (default: `8645`)
- `-n` `--network-size` — Number of peers in the network (default: `100`)


### Example in Kubernetes yaml
```
containers:
  - name: publisher-container
    image: <your-registry>/publisher:v1.0.0
    imagePullPolicy: IfNotPresent
    command:
      - sh
      - -c
      - |
        python /app/traffic.py \
        --pubsub-topic="test" \
        --messages 10
```

### How It Works
1. **Getting Publisher Details**:
Select a publisher and determine its IP address and message endpoint. Every message is published by a new publisher. For k8s publisher selection is service-based `--peer-selection service`. It uses the libp2p service `nimp2p-service` to determine IP addresses for random peers. 
For the shadow simulator, publisher selection is id-based `--peer-selection id`. It sequentially selects peers to determine their IP addresses.

2. **Message Preparation**:
Prepares the HTTP POST requests with:
- Target topic
- Message size (bytes)
- Protocol version

3. **Sending Messages**:
Get publisher details and send message publishing request using the HTTP endpoint. The request body contains message size, and topic. The requested publisher then creates and publishes messages in the specified topic meshes.
The script also logs the response status, elapsed time, and success/failure rates.

4. **Concurrency Handling**:
`traffic.py` Uses `asyncio.create_task` to make sure messages are sent at a constant rate.
`traffic_sync.py` Uses sync operation and does not rely on DNS service. However, the [shadow simulation script](https://github.com/vacp2p/dst-libp2p-test-node/tree/master/shadow) applies negligible link latency for the message injector to facilitate almost negligible message injection times.