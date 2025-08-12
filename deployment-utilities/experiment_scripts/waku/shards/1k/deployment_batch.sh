#!/bin/bash

# Paths to YAML templates
NODES_TEMPLATE="nodes_template.yaml"
PUBLISHER_YAML="publisher_testing.yaml"

# Kubeconfig and namespace
KUBECONFIG="<kubeconfig>"
NAMESPACE="zerotesting"

# List of numbers of shards
SHARD_COUNTS=(1 2 4 8 16 32 64)  # Replace these with the desired numbers of shards

# Directory to store shard YAML files
SHARD_YAML_DIR="shard_yamls"
mkdir -p $SHARD_YAML_DIR

# Process each number of shards in the list
for NUM_SHARDS in "${SHARD_COUNTS[@]}"; do
    echo "Processing $NUM_SHARDS shards..."

    # Generate the --shard arguments string for connections
    SHARD_CONNECTIONS=""
    for ((i=0; i<NUM_SHARDS; i++)); do
        SHARD_CONNECTIONS+=" --shard=$i"
    done
    SHARD_CONNECTIONS="${SHARD_CONNECTIONS# }"  # Remove leading space

    # Generate processed bootstrap.yaml with substituted values
PROCESSED_BOOTSTRAP="${SHARD_YAML_DIR}/bootstrap_${NUM_SHARDS}_shards.yaml"
sed -e "s#\$shardsconnections#$SHARD_CONNECTIONS#g" -e "s/\$shards/$NUM_SHARDS/g" bootstrap.yaml > "$PROCESSED_BOOTSTRAP"

    # Apply bootstrap
    kubectl --kubeconfig $KUBECONFIG apply -f "$PROCESSED_BOOTSTRAP"
    kubectl --kubeconfig $KUBECONFIG rollout status --watch --timeout=30000s statefulset/bootstrap -n $NAMESPACE

    # Create and apply nodes configuration for each shard
    for shard in $(seq 0 $((NUM_SHARDS - 1))); do
        # Generate YAML for the shard by substituting $shard in the template
        SHARD_YAML="$SHARD_YAML_DIR/nodes_nshards${NUM_SHARDS}_shard$shard.yaml"
        sed "s/\$shard/$shard/g" $NODES_TEMPLATE > $SHARD_YAML

        # Apply the generated YAML
        kubectl --kubeconfig $KUBECONFIG apply -f $SHARD_YAML
    done

    # Rollout status for all statefulsets for this number of shards
    for shard in $(seq 0 $((NUM_SHARDS - 1))); do
        kubectl --kubeconfig $KUBECONFIG rollout status --watch --timeout=30000s statefulset/nodes-$shard -n $NAMESPACE
    done
done

# Pause before applying the publisher configuration
sleep 30

# Apply publisher configuration
kubectl --kubeconfig $KUBECONFIG apply -f $PUBLISHER_YAML
sleep 10
kubectl --kubeconfig $KUBECONFIG wait --for=condition=ready=False pod/publisher -n $NAMESPACE --timeout=-1s
sleep 20

# Cleanup: Delete all statefulsets and the publisher pod
kubectl --kubeconfig $KUBECONFIG delete --all statefulset -n $NAMESPACE
kubectl --kubeconfig $KUBECONFIG delete pod -n $NAMESPACE publisher
