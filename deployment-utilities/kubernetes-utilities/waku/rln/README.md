## Summary of the Experiment Flow
Only `deploy_rln_env.sh` needs to be run manually. Then the following flow will be executed:
1. It automatically creates the Kubernetes namespace that will be used
2. Deploy Anvil with its own service into the cluster (`anvil-deployment.yaml`)
3. Run RLN bootstrap job (`rln-bootstrap.yaml`)
   - Image with contract installed
   - Connects to Anvil
   - Deploy basic TestToken
   - Deploy PriceCalculator
   - Deploy TestStableToken (with proxy)
   - Deploy RLN contracts (using broadcast files)
   - Grant minter privileges to deployer
   - Mint tokens to deployer
   - Approve RLN contract to spend tokens
   - Minting and approving tokens for derived Waku pod keys
   - Populates K8s secrets/configmaps
4. Deploy Waku RLN StatefulSet (`nwaku-bootstrap.yaml` for bootstrapping and `waku-rln-statefulset.yaml`)
   - Each node performs GENERATE_TIMES RLN registrations in a loop
   - Then starts Waku with RLN relay
   - Optionally monitor balances and allowances via the sidecar (`balance-watcher`)
5. Run the publisher (`publisher.yaml`)
    - Resolves node endpoints
    - Injects traffic
    - Measures success rate and latency
6. Use cleanup.sh to reset and run another experiment

## Overview of the Workflow

The full system operates in the following sequence:

### 1. Deploy the in-cluster Anvil RPC
File: `anvil-deployment.yaml`

- Launches an Anvil node inside Kubernetes
- Exposes it as a ClusterIP service (anvil-rpc)
- Uses a deterministic mnemonic so all accounts are predictable
- Provides effectively unlimited ETH for contract deployments and RLN registrations
- Used by both the bootstrap container and the Waku nodes
- This RPC must be fully ready before executing the RLN bootstrap script.

### 2. Run the RLN Bootstrap Job
Files: `docker_utilities/waku/rln_bootstrap/Dockerfile`
`docker_utilities/waku/rln_bootstrap/entrypoint.sh`
`kubernetes-utilities/waku/rln/rln-bootstrap.yaml`

This job performs all blockchain-related setup:

__Responsibilities:__

1. Wait for Anvil to become responsive

2. Deploy all required smart contracts, in order:
   - TestToken
   - LinearPriceCalculator
   - TestStableToken (proxy)
   - RLNv2 implementation
   - RLN proxy contract
3. Grant minter rights and mint test tokens
4. Derive a private key per Waku node, using the shared mnemonic
5. Fund each derived address
6. Mint tokens and set allowances so each node can pay RLN membership fees
7. Output configuration (contract addresses, RPC URLs, chain ID).
These values are stored into Kubernetes Secrets / ConfigMaps for use by the StatefulSet.

The output ensures all Waku nodes point to the correct chain and contract.

### 3. Launch the Waku RLN Node Cluster

File: `waku-rln-statefulset.yaml`

This StatefulSet is the core of the experiment.

__Key Features:__

- One pod per Waku node
- Each pod gets its own deterministic private key, derived from the shared mnemonic
- A pre-start loop runs multiple RLN registrations to fill the Merkle Tree
- The main container then starts wakunode
- A sidecar container (“balance-watcher”) logs:
  - Balance evolution
  - Token allowance
  - Useful for debugging ERC20 failures (insufficient balance / insufficient allowance)

The StatefulSet uses a headless service (rln-nodes) so each pod receives its own DNS entry and can be addressed individually.

### 4. Run the Publisher

File: `publisher.yaml`

This launches a standalone pod that injects traffic into the RLN Waku cluster.

It performs:

- Discovery of available Waku nodes
- Random node selection
- Topic construction (/waku/2/rs/<shard>/)
- Payload generation
- REST publishing using Relay or Lightpush
- Logging success/failure, latency, and load distribution

It also uses SRV lookups to enumerate pods in the headless service for correct shard selection.

### 5. Cleanup Resources

File: `cleanup.sh`

A helper script to remove:

- The StatefulSet
- Bootstrap job
- ConfigMaps / Secrets
- publisher pod

Used for resetting the environment between experiment iterations.
