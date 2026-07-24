## Waku Filter Message Retriever

This script retrieves messages from multiple Waku filter nodes
in a Kubernetes environment, resolving their DNS addresses,
fetching messages, and validating that all nodes received the same messages.

Note that this endpoint only returns the last 50 messages,
as explained in the [API documentation](https://waku-org.github.io/waku-rest-api/#get-/filter/v2/messages/-contentTopic-).

It assumes that can get resolutions as `fclient-{shard}-{node}:8645`.

### Features

- Resolves DNS for Waku filter nodes
- Fetches messages from specified content topics
- Uses multiprocessing for parallel requests
- Validates message consistency across nodes

### Usage
Run the script with:
```
python script.py [-c CONTENT_TOPIC] [-n NUM_NODES] [-s NUM_SHARDS]
```

### Arguments 
- `-c`, `--contentTopic`:	Content topic to retrieve messages from	/my-app/1/dst/proto
- `-n`, `--numNodes`:	Number of filter nodes to query	1
- `-s`, `--numShards`:	Number of shards in the cluster	1

### Example in Kubernetes yaml
```
  containers:
    - name: container
      image: <your-registry>/get_filter_messages:v1.0.0
      imagePullPolicy: IfNotPresent
      command:
        - sh
        - -c
        - python /app/filter_msg_retriever.py --contentTopic="/my-app/1/dst/proto" --numNodes=500 --numShards=1
```

### How It Works
The script generates a list of node addresses based on the provided number of shards and nodes.
Each node's DNS is resolved to an IP address.
Requests are sent to fetch messages from each node in parallel.
Retrieved messages are validated for consistency.
The script prints True if all messages have the same length, otherwise False.