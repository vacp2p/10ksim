## libp2p message injector

This script is designed to send messages to libp2p nodes.
It allows specifying the number of messages, their size,
inter-message delay, and the target pubsub topics.

It also allows sequential (id-based) or a random (service-based) peer selection. The script is available with both, async `traffic.py` and sync `traffic_sync.py` operations.

The script informs selected publishers about message details, and logs details like message success rate.

### Usage


### Arguments
- `-t` `--pubsub-topic` — Pubsub topic (default: `test`)
- `-l` `--msg-length-bytes` — Message size in bytes (default: `1000`)
- `-d` `--delay-seconds` — Delay in seconds between messages (default: `1`)
- `-m` `--messages` — Number of messages to inject (default: `10`)
- `-s` `----peer-selection` — Use DNS service or id-based peer selection (default: `id`)
- `-p` `--port`: libp2p testnode REST port (default: `8645`)
- `-n` `--network-size`: Number of peers in the network (default: `100`)


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
Selects publisher and determines its IP address, message endpoint. 
Depends on provided publisher list, or Uses libp2p service (`nimp2p-service`) to determine ip address for random peers. 

2. **Message Preparation**:
Prepares the HTTP POST requests with:
- Target topic
- Message size (bytes)
- Protocol version

3. **Sending Messages**:
Selects a publisher and sends the message using HTTP endpoint.
Logs the response status, elapsed time, and success/failure rates.

4. **Concurrency Handling**:
`traffic.py` Uses `asyncio.create_task` to make sure messages are sent at a constant rate.