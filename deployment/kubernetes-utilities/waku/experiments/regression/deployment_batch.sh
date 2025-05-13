#!/bin/bash

NODES_YAML=("nodes_1k.yaml" "nodes_2k.yaml" "nodes_3k.yaml")
PUBLISHER_YAML=("publisher_msg1s.yaml" "publisher_msg5s.yaml" "publisher_msg10s.yaml")

KUBECONFIG="<kubeconfig>"
NAMESPACE="zerotesting"

# Nested loops to iterate over nodes and publisher files
for nodes_file in "${NODES_YAML[@]}"; do
  for publisher_file in "${PUBLISHER_YAML[@]}"; do
    # Apply bootstrap
    kubectl --kubeconfig $KUBECONFIG apply -f bootstrap.yaml
    kubectl --kubeconfig $KUBECONFIG rollout status --watch --timeout=30000s statefulset/bootstrap -n $NAMESPACE

    # Apply nodes configuration
    kubectl --kubeconfig $KUBECONFIG apply -f $nodes_file
    kubectl --kubeconfig $KUBECONFIG rollout status --watch --timeout=30000s statefulset/nodes-0 -n $NAMESPACE

    ## Apply publisher configuration
    kubectl --kubeconfig $KUBECONFIG apply -f $publisher_file
    sleep 20
    kubectl --kubeconfig $KUBECONFIG wait --for=condition=ready=False pod/publisher -n $NAMESPACE --timeout=-1s
    sleep 20

    kubectl --kubeconfig $KUBECONFIG delete --all statefulset -n $NAMESPACE
    kubectl --kubeconfig $KUBECONFIG delete pod -n $NAMESPACE publisher
    sleep 600
  done
done
