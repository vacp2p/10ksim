#!/bin/bash

# Array of nodes YAML files
NODES_YAML=("lazy/nodes_3k.yaml" "lazy/nodes_2k.yaml" "lazy/nodes_1k.yaml")

# Array of publisher YAML files
PUBLISHER_YAML=("lazy/publisher_msg1s.yaml" "lazy/publisher_msg5s.yaml" "lazy/publisher_msg10s.yaml")

# Kubeconfig and namespace
NAMESPACE="zerotesting"

# Counters for unique log file names
node_counter=1
publisher_counter=1

# Nested loops to iterate over nodes and publisher files
for nodes_file in "${NODES_YAML[@]}"; do
  for publisher_file in "${PUBLISHER_YAML[@]}"; do
    # Apply bootstrap and midstrap configurations
    kubectl apply -f bootstrap.yaml
    kubectl rollout status --watch --timeout=30000s statefulset/bootstrap -n $NAMESPACE
    kubectl apply -f midstrap.yaml
    kubectl rollout status --watch --timeout=30000s statefulset/midstrap -n $NAMESPACE

    # Apply nodes configuration
    kubectl apply -f $nodes_file
    kubectl rollout status --watch --timeout=30000s statefulset/nodes -n $NAMESPACE

    # Apply publisher configuration
    kubectl apply -f $publisher_file

    sleep 10
    kubectl wait --for=condition=ready=False pod/publisher -n zerotesting --timeout=-1s

    # Retrieve and save logs
    log_file="publisher_${node_counter}_${publisher_counter}.log"
    kubectl logs publisher -n $NAMESPACE > $log_file
    sleep 20

    kubectl delete --all statefulset -n $NAMESPACE
    kubectl delete pod -n $NAMESPACE publisher
    sleep 300

  done
done
