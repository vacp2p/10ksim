## libp2p message injector

This script is designed to send messages to a libp2p node.
It allows to specify the number of messages, their size,
inter-message delay, and the target pubsub topics.

It also allows selecting the starting and ending peers that publish messages. 
The script rotates between these peers for sending messages. 
Random publisher selection is also possible by setting the starting and ending publisher to 0  
(In this case, the script performs DNS resolution and logs timing).

The script can transfer message payload, or simply notify publisher about 
message details and publisher creates and transmit messages. 
The script can also check peer health (mesh size) against specific pubsub topic.
The results, including response times and success rates are logged.

### Usage


### Arguments
- `-pt` `--pubsub-topic` — Pubsub topic (default: `test`)
- `-s` `--msg-size-bytes` — Message size in bytes (default: `1000`)
- `-d` `--delay-seconds` — Delay in seconds between messages (default: `5`)
- `-m` `--messages` — Number of messages to inject (default: `10`)
- `-fs` `--first-sender` — The first peer that starts publishing. Use 0 for random selection (default: `1`)
- `-ls` `--last-sender`: The last peer to publish. Publishers rotate between `first-sender` and `last-sender` (default: `1`)
- `-p` `--port`: libp2p testnode REST port (default: `8645`)


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
Prepares the HTTP request body:
- For `publish` messages, informs publisher about message details, allowing publisher to generate and publish messages.
- For `relay` messages, generates payload and share with publisher (`TODO:` Fetch payload from applications).
- For `health` queries publisher for mesh size against a specific pubsub topic.

3. **Sending Messages**:
Selects a publisher and sends the message using HTTP endpoint.
Logs the response status, elapsed time, and success/failure rates.

4. **Concurrency Handling**:
Uses `asyncio.create_task` to make sure messages are sent at a constant rate.