#!/bin/bash

# Array of nodes YAML files
# NODES_YAML=("lazy/nodes_3k.yaml" "lazy/nodes_2k.yaml" "lazy/nodes_1k.yaml")
NODES_YAML=("lazy/nodes_test.yaml" "lazy/nodes_test.yaml")

# Array of publisher YAML files
# PUBLISHER_YAML=("lazy/publisher_msg1s.yaml" "lazy/publisher_msg5s.yaml" "lazy/publisher_msg10s.yaml")
PUBLISHER_YAML=("lazy/publisher_test.yaml" "lazy/publisher_test.yaml")

# Kubeconfig and namespace
KUBECONFIG="/home/alber/.kube/rubi.yaml"
NAMESPACE="zerotesting"

# Counters for unique log file names
node_counter=1
publisher_counter=1

# Nested loops to iterate over nodes and publisher files
for nodes_file in "${NODES_YAML[@]}"; do
  for publisher_file in "${PUBLISHER_YAML[@]}"; do
    # Apply bootstrap and midstrap configurations
    kubectl --kubeconfig $KUBECONFIG apply -f bootstrap.yaml
    kubectl --kubeconfig $KUBECONFIG rollout status --watch --timeout=30000s statefulset/bootstrap -n $NAMESPACE
    kubectl --kubeconfig $KUBECONFIG apply -f midstrap.yaml
    kubectl --kubeconfig $KUBECONFIG rollout status --watch --timeout=30000s statefulset/midstrap -n $NAMESPACE

    # Apply nodes configuration
    kubectl --kubeconfig $KUBECONFIG apply -f $nodes_file
    kubectl --kubeconfig $KUBECONFIG rollout status --watch --timeout=30000s statefulset/nodes -n $NAMESPACE

    # Apply publisher configuration
    kubectl --kubeconfig $KUBECONFIG apply -f $publisher_file
    # sleep 2300
    sleep 8
    kubectl --kubeconfig ~/.kube/rubi.yaml wait --for=condition=ready=False pod/publisher -n zerotesting --timeout=-1s

    # Retrieve and save logs
    log_file="publisher_${node_counter}_${publisher_counter}.log"
    kubectl --kubeconfig $KUBECONFIG logs publisher -n $NAMESPACE > $log_file

    # Wait for the publisher pod to complete (Pod doesnt have condition complete)
    # kubectl --kubeconfig $KUBECONFIG wait --for=condition=complete pod/publisher -n $NAMESPACE --timeout=-1s
    # kubectl --kubeconfig ~/.kube/rubi.yaml wait --for=condition=ready=False pod/publisher -n zerotesting --timeout=-1s

    sleep 10
    kubectl --kubeconfig $KUBECONFIG delete --all statefulset -n $NAMESPACE
    kubectl --kubeconfig $KUBECONFIG delete pod -n $NAMESPACE publisher
    # sleep 300
    sleep 60
  done
done
