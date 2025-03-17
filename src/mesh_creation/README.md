# Mesh Creation Module

A Python module for creating and managing mesh networks of p2p nodes in Kubernetes, with support for custom topologies and different node protocols.

## Components

### Core Classes

1. `TopologyManager`
   - Generates network topologies
   - Supports custom degree constraints
   - Imports Pajek format networks
   - Configures node connections

2. `PodManager`
   - Manages Kubernetes pod deployments
   - Handles pod-to-pod communication
   - Tracks pod states and identifiers
   - Executes commands in pods

3. `NodeProtocol` (Abstract Base Class)
   - Base class for protocol implementations
   - Defines interface for node communication
   - Handles identifier retrieval and connections

### Protocol Implementations

1. `WakuProtocol`
   - Implementation for Waku nodes
   - Handles ENR URI retrieval
   - Manages node connections via HTTP API

2. `LibP2PProtocol`
   - Generic LibP2P implementation
   - Handles peer ID management
   - Configures direct connections

## Usage Examples

### Basic Node Deployment

```python
from mesh_creation.topology_creation import TopologyManager
from mesh_creation.protocols.waku_protocol import WakuProtocol

# Initialize manager with Waku protocol
manager = TopologyManager(
    kube_config="config.yaml",
    namespace="test",
    protocol=WakuProtocol(port=8645)
)

# Deploy nodes from YAML
manager.setup_nodes("waku-nodes.yaml")

# Generate and configure topology
graph = manager.generate_topology(
    "libp2p_custom",
    n=5,
    d_low=2,
    d_high=4
)
manager.configure_node_connections(graph)
```

### Custom Topology from Pajek

```python
# Read existing topology
graph = manager.read_pajek("topology.net")
manager.configure_node_connections(graph)
```

## Configuration Files

### Node Deployment (YAML)

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: waku-node
spec:
  replicas: 5
  template:
    spec:
      containers:
      - name: waku
        image: wakuorg/node:latest
        ports:
        - containerPort: 8645
```

## Development

### Adding New Protocol Support

1. Create new protocol class:
```python
from mesh_creation.protocols.base_protocol import BaseProtocol

class CustomProtocol(BaseProtocol):
    def get_node_identifier(self) -> List[str]:
        return ["curl", "-s", "http://localhost:8080/id"]

    def get_connection_command(self, identifier: str) -> List[str]:
        return ["curl", "-s", "-X", "POST", f"http://localhost:8080/connect/{identifier}"]

    def parse_identifier_response(self, response: str) -> str:
        return json.loads(response)["id"]
```

2. Use with topology manager:
```python
manager = TopologyManager(protocol=CustomProtocol())
```

### Running Tests

```bash
# Run all mesh_creation tests
pytest src/mesh_creation/tests/

# Run specific test file
pytest src/mesh_creation/tests/test_pod_manager.py
```
