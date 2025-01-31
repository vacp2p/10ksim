#!/bin/bash

STORES_YAML="store_nodes.yaml"
STORE_GETTER_YAML="get_store_messages.yaml"

# Kubeconfig and namespace
KUBECONFIG="<kubeconfig>"
NAMESPACE="zerotesting"

NODES_YAML=("nodes_1k.yaml" "nodes_2k.yaml" "nodes_3k.yaml")
PUBLISHER_YAML=("publisher_msg1s.yaml" "publisher_msg5s.yaml" "publisher_msg10s.yaml")

for nodes_file in "${NODES_YAML[@]}"; do
  for publisher_file in "${PUBLISHER_YAML[@]}"; do
    # Apply bootstrap
    kubectl --kubeconfig $KUBECONFIG apply -f ../bootstrap.yaml
    kubectl --kubeconfig $KUBECONFIG rollout status --watch --timeout=30000s statefulset/bootstrap -n $NAMESPACE

    # Apply nodes configuration
    kubectl --kubeconfig $KUBECONFIG apply -f $STORES_YAML
    kubectl --kubeconfig $KUBECONFIG rollout status --watch --timeout=30000s statefulset/store -n $NAMESPACE
    sleep 30
    kubectl --kubeconfig $KUBECONFIG apply -f $nodes_file
    kubectl --kubeconfig $KUBECONFIG rollout status --watch --timeout=30000s statefulset/nodes -n $NAMESPACE

    ## Apply publisher configuration
    kubectl --kubeconfig $KUBECONFIG apply -f $publisher_file
    sleep 20
    kubectl --kubeconfig $KUBECONFIG wait --for=condition=ready=False pod/publisher -n $NAMESPACE --timeout=-1s

    kubectl --kubeconfig $KUBECONFIG delete pod -n $NAMESPACE publisher
    sleep 30
    kubectl --kubeconfig $KUBECONFIG apply -f $STORE_GETTER_YAML
    sleep 70
    kubectl --kubeconfig $KUBECONFIG wait --for=condition=ready=False pod/get-store-messages -n $NAMESPACE --timeout=-1s

    kubectl --kubeconfig $KUBECONFIG delete pod -n $NAMESPACE get-store-messages
    kubectl --kubeconfig $KUBECONFIG delete --all statefulset -n $NAMESPACE
    sleep 600
  done
done
