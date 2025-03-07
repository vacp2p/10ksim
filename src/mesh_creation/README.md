# Mesh Creation Module

This module provides functionality to create and configure network topologies in Kubernetes clusters, specifically designed for peer-to-peer network experiments. It supports different node protocols (currently Waku and LibP2P) and various network topology types.

## Overview

The mesh creation module consists of three main components:

1. **TopologyManager**: Orchestrates the overall process of creating and configuring the network topology
2. **PodManager**: Handles Kubernetes pod operations and statefulset management
3. **NodeProtocol**: Abstract interface for different node protocols (Waku, LibP2P)

## Components

### TopologyManager (`topology_creation.py`)

The TopologyManager is responsible for:
- Creating network topologies using NetworkX
- Managing pod deployment and configuration
- Coordinating the connection setup between nodes

Supported topology types:
- Random (Erdős-Rényi)
- Scale-free (Barabási-Albert)
- Small-world (Watts-Strogatz)
- Custom topologies via Pajek format

Example usage:
```python
from test_topology_creation import TopologyManager
from node_protocol import WakuProtocol

# Initialize manager with Waku protocol
manager = TopologyManager(
    kube_config="your_kube_config.yaml",
    namespace="your_namespace",
    protocol=WakuProtocol(port=8645)
)

# Deploy nodes
manager.setup_nodes(["statefulset.yaml"])

# Create and apply topology
config = manager.read_config("topology_config.yaml")
graph = manager.generate_topology(
    config["topology_type"],
    **config["parameters"]
)
manager.configure_node_connections(graph)
```

### PodManager (`pod_manager.py`)

The PodManager handles Kubernetes-related operations:
- Deploying and managing StatefulSets
- Monitoring pod readiness
- Executing commands in pods
- Managing pod identifiers and connections

Key features:
- Automatic pod readiness detection
- StatefulSet creation and updates
- Pod command execution with proper error handling
- Support for different container runtimes

### NodeProtocol (`node_protocol.py`)

Abstract interface for different node protocols with concrete implementations for:
- Waku nodes
- LibP2P nodes (example)

Each protocol implementation provides:
- Node identifier retrieval
- Connection command generation
- Response parsing

## Configuration

### Topology Configuration (`topology_config.yaml`)

Example configuration for different topology types:
```yaml
# Random topology
topology_type: "random"
parameters:
  n: 10  # number of nodes
  p: 0.2  # connection probability

# Scale-free topology
topology_type: "scale_free"
parameters:
  n: 10  # number of nodes
  m: 2   # number of edges per new node

# Small-world topology
topology_type: "small_world"
parameters:
  n: 10  # number of nodes
  k: 4   # nearest neighbors to connect
  p: 0.1 # rewiring probability
```

### StatefulSet Configuration

Your StatefulSet YAML should define:
- Pod specifications
- Container configurations
- Required ports and protocols
- Any necessary volumes or configurations

## Usage

1. **Prepare Configuration Files**
   - Create your StatefulSet YAML
   - Create topology configuration YAML
   - Ensure Kubernetes cluster access

2. **Create Network Topology**
   ```python
   from test_topology_creation import TopologyManager
   from node_protocol import WakuProtocol

   # Initialize
   manager = TopologyManager(protocol=WakuProtocol(port=8645))

   # Deploy nodes
   manager.setup_nodes(["your_statefulset.yaml"])

   # Configure topology
   config = manager.read_config("topology_config.yaml")
   graph = manager.generate_topology(
       config["topology_type"],
       **config["parameters"]
   )
   manager.configure_node_connections(graph)
   ```
