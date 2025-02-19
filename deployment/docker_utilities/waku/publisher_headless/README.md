## Waku message injector

This script is designed to send messages to a Waku node
using either the relay or lightpush protocols. 
It allows to specify the number of messages, their size,
delay between messages, and the target pubsub/content topics.

The script performs DNS resolution timing, 
message payload generation, 
and HTTP requests to a Waku REST interface. 
The results, including response times and success rates, are logged.

### Usage


### Arguments
- `-pt` `--pubsub-topic`: Waku pubsub topic
- `-ct` `--content-topic`: Message content topic
- `-s`  `--msg-size-kbytes`: Size of each message in kB
- `-d`  `--delay-seconds`: Delay between messages
- `-m`  `--messages`: Number of messages to send
- `-ps` `--protocols`: Protocols to use (relay, lightpush or both)
- `-p`  `--port`: Waku REST API port

### Example in Kubernetes yaml
```
containers:
  - name: publisher-container
    image: <your-registry>/publisher:v1.0.1
    imagePullPolicy: IfNotPresent
    command:
      - sh
      - -c
      - |
        python /app/traffic.py \
        --messages=75 \
        --msg-size-kbytes=1 \
        --delay-seconds=1 \
        --pubsub-topic="/waku/2/rs/2/" \
        --protocols relay
```

### How It Works
1. **DNS Resolution**:
Determines the IP address of the Waku service (`zerotesting-service` or `zerotesting-lightpush-client`).
Logs how long DNS resolution takes.
Extracts the shard number from the resolved hostname.

2. **Message Preparation**:
Generates a random payload.
Encodes the payload in Base64.
Prepares the HTTP request body.

3. **Sending Messages**:
Selects a protocol (relay, lightpush or both).
Sends the message to the respective Waku endpoint.
Logs the response status, elapsed time, and success/failure rates.

4. **Concurrency Handling**:
Uses `asyncio.create_task` to make sure messages are sent at a constant rate.

### Changelog

- `v1.0.1`:
  - Log url, headers and body when injecting a message
  - Log url, headers and body when raising an exception
- `v1.0.2`:
  - Fixed wrong calculation of success_rate when logging information.