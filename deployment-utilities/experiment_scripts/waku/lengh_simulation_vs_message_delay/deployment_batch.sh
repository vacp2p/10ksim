#!/bin/bash

NODES_YAML=("nodes.yaml")
PUBLISHER_YAML=("publisher_msg1s-150.yaml" "publisher_msg1s-300.yaml" "publisher_msg1s-600.yaml")

KUBECONFIG="<kubeconfig>"
NAMESPACE="zerotesting"

for nodes_file in "${NODES_YAML[@]}"; do
  for publisher_file in "${PUBLISHER_YAML[@]}"; do
    kubectl --kubeconfig $KUBECONFIG apply -f bootstrap.yaml
    kubectl --kubeconfig $KUBECONFIG rollout status --watch --timeout=30000s statefulset/bootstrap -n $NAMESPACE

    kubectl --kubeconfig $KUBECONFIG apply -f "$nodes_file"
    kubectl --kubeconfig $KUBECONFIG rollout status --watch --timeout=30000s statefulset/nodes-0 -n $NAMESPACE

    kubectl --kubeconfig $KUBECONFIG apply -f "$publisher_file"
    sleep 10
    kubectl --kubeconfig $KUBECONFIG wait --for=condition=ready=False pod/publisher -n $NAMESPACE --timeout=-1s
    sleep 20

    kubectl --kubeconfig $KUBECONFIG delete --all statefulset -n $NAMESPACE
    kubectl --kubeconfig $KUBECONFIG delete pod -n $NAMESPACE publisher
    sleep 200
  done
done
