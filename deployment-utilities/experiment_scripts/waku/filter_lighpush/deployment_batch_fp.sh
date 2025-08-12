#!/bin/bash

# Kubeconfig and namespace
KUBECONFIG="<kubeconfig>"
NAMESPACE="zerotesting"

NODES_YAML=("nodes_testing.yaml")
PUBLISHER_YAML=("publisher_testing.yaml")
FILTER_YAML="filter_testing.yaml"
LPC_YAML="lightpush_client_testing.yaml"
LPS_YAML="lightpush_server_testing.yaml"

for nodes_file in "${NODES_YAML[@]}"; do
  for publisher_file in "${PUBLISHER_YAML[@]}"; do
    # Apply bootstrap
    kubectl --kubeconfig $KUBECONFIG apply -f ../bootstrap.yaml
    kubectl --kubeconfig $KUBECONFIG rollout status --watch --timeout=30000s statefulset/bootstrap -n $NAMESPACE

    # Apply nodes configuration
    kubectl --kubeconfig $KUBECONFIG apply -f $nodes_file
    kubectl --kubeconfig $KUBECONFIG rollout status --watch --timeout=30000s statefulset/nodes -n $NAMESPACE
    sleep 20
    kubectl --kubeconfig $KUBECONFIG apply -f $FILTER_YAML
    kubectl --kubeconfig $KUBECONFIG rollout status --watch --timeout=30000s statefulset/filter -n $NAMESPACE
    kubectl --kubeconfig $KUBECONFIG apply -f $LPS_YAML
    kubectl --kubeconfig $KUBECONFIG rollout status --watch --timeout=30000s statefulset/lightpush-server -n $NAMESPACE
    kubectl --kubeconfig $KUBECONFIG apply -f $LPC_YAML
    kubectl --kubeconfig $KUBECONFIG rollout status --watch --timeout=30000s statefulset/lightpush-client -n $NAMESPACE
    sleep 20
    ## Apply publisher configuration
    kubectl --kubeconfig $KUBECONFIG apply -f $publisher_file
    sleep 20
    kubectl --kubeconfig $KUBECONFIG wait --for=condition=ready=False pod/publisher -n $NAMESPACE --timeout=-1s
    sleep 10
    kubectl --kubeconfig $KUBECONFIG apply -f get_filter_messages.yaml
    sleep 20
    kubectl --kubeconfig $KUBECONFIG wait --for=condition=ready=False pod/get-filter-messages -n $NAMESPACE --timeout=-1s
    sleep 20
    kubectl --kubeconfig $KUBECONFIG delete pod -n $NAMESPACE publisher
    kubectl --kubeconfig $KUBECONFIG delete pod -n $NAMESPACE get-filter-messages
    kubectl --kubeconfig $KUBECONFIG delete --all statefulset -n $NAMESPACE
    sleep 600
  done
done
