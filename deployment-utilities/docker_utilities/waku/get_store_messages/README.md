## Waku Storage Retriever

This Python script retrieves messages 
from a Waku storage service using an HTTP API. 
It supports pagination and resolves DNS for the service host. 
The script is designed to run inside a Docker container.

### Usage
Run the script with:
```
python script.py [-c CONTENT_TOPIC] [-p PUBSUB_TOPIC] [-ps PAGE_SIZE] [-cs CURSOR]
```

### Arguments
- `-c`, `--contentTopics` (default: `/my-app/1/dst/proto`): Content topic to query.
- `-p`, `--pubsubTopic` (default: `/waku/2/rs/2/0`): Pubsub topic.
- `-ps`, `--pageSize` (default: 60): Number of messages per request.
- `-cs`, `--cursor` (optional): Cursor for pagination.

### Example in Kubernetes yaml
```
containers:
  - name: container
    image: <your-registry>/get_store_messages:v1.0.0
    imagePullPolicy: IfNotPresent
    command:
      - sh
      - -c
      - python /app/store_msg_retriever.py --contentTopics=/my-app/1/dst/proto
```

### How It Works
Queries a random waku node by selecting a random ip from `"zerotesting-service:8645"`.
It keeps querying that node until all messages are retrieved.