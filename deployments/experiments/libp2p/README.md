## libp2p Experiments

This directory contains two options for deploying libp2p test nodes:

| File | Purpose |
|------|---------|
| `libp2p_yamls.py` | Standalone YAML generator (requires manual deployment) |
| `libp2p_deploy.py` | Complete experiment deployment |

### 1. libp2p_yamls.py - YAML generator (standalone)

Generates Kubernetes YAML files without deploying. Uses [http message injector](https://github.com/vacp2p/10ksim/tree/master/deployment-utilities/docker_utilities/nimlibp2p/publisher_headless) as publisher.

#### Basic Usage

```bash
cd deployments/experiments/libp2p

# Sample libp2p experiment - 30 test nodes (including 10 mix nodes)
python libp2p_yamls.py --peers 30 \
        --namespace refactor-libp2p \
        --muxer yamux \
        --with-delay \
        --delay-ms 100 \
        --with-mix-nodes \
        --num-mix 10 \
        --output-dir ./out

# View generated files in `output-dir` directory
```

#### All Options

```bash
python libp2p_yamls.py --help
```

| Option | Default | Description |
|--------|---------|-------------|
| `--namespace` | zerotesting-nimlibp2p | Kubernetes namespace |
| `--servicename` | nimp2p-service | Service name for DNS |
| `--statefulset-name` | pod | StatefulSet name |
| `--peers` | 100 | Number of nodes |
| `--muxer` | yamux | Muxer type (mplex/yamux/quic) |
| `--image` | ufarooqstatus/refactored-test-node:v1.0 | Node image |
| `--publisher-image` | ufarooqstatus/libp2p-publisher:v1.0 | Publisher image |
| `--with-delay` | false | Enable network delay |
| `--delay-ms` | 100 | Average link latency in milliseconds |
| `--jitter-ms` | 30 | Average jitter in milliseconds |
| `--with-mix-nodes` | false | Enable mix protocol |
| `--num-mix` | 50 | Number of mix-capable nodes |
| `--mix-d` | 3 | Mix tunnel length |
| `--output-dir` | ./regression | Output directory |


---

### 2. libp2p_deploy.py - Full experiment

Deploys experiment to a Kubernetes cluster using [pod_api_requester](https://github.com/vacp2p/10ksim/tree/master/deployments/pod_api_requester) for HTTP message injection.

#### Usage

```bash
cd deployments

# Create values file
cat > experiments/libp2p/values.yaml << 'EOF'
num_nodes: 30
num_messages: 5
delay_cold_start: 30
delay_after_publish: 1
EOF

# Run experiment
python deployment.py \
        --config <kubeconfig> --values experiments/libp2p/values.yaml \
        libp2p-deployment --namespace refactor-libp2p
```

#### All Options (values.yaml)

| Option | Default | Description |
|--------|---------|-------------|
| `num_nodes` | 10 | Number of nodes |
| `num_messages` | 20 | Number of messages to publish |
| `delay_cold_start` | 60 | Initial wait time for mesh building |
| `delay_after_publish` | 1 | Wait before cleanup |
| `with_mix` | false | Enable mix protocol |
| `num_mix` | 10 | Number of mix-capable nodes |
| `mix_d` | 3 | Mix tunnel length |
| `network_delay_ms` | null | Average link latency in milliseconds |
| `network_jitter_ms` | 30 | Average jitter in milliseconds |


#### Experiment Flow

1. Deploy `pod_api_requester`
2. Deploy libp2p StatefulSet
3. Wait for mesh stabilization (`delay_cold_start`)
4. Publish messages to random nodes via HTTP API
5. Wait for propagation
6. Cleanup

---