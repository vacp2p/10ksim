#!/bin/bash

PUBLISHER_YAML="publisher_testing.yaml"

# Kubeconfig and namespace
KUBECONFIG="<kubeconfig>"
NAMESPACE="zerotesting"

# Apply bootstrap
kubectl --kubeconfig $KUBECONFIG apply -f bootstrap.yaml
kubectl --kubeconfig $KUBECONFIG rollout status --watch --timeout=30000s statefulset/bootstrap -n $NAMESPACE

# Apply nodes configuration
kubectl --kubeconfig $KUBECONFIG apply -f nodes_nim.yaml
kubectl --kubeconfig $KUBECONFIG apply -f nodes_go.yaml
kubectl --kubeconfig $KUBECONFIG rollout status --watch --timeout=30000s statefulset/nodes-nim -n $NAMESPACE
kubectl --kubeconfig $KUBECONFIG rollout status --watch --timeout=30000s statefulset/nodes-go -n $NAMESPACE

## Apply publisher configuration
kubectl --kubeconfig $KUBECONFIG apply -f "$PUBLISHER_YAML"
sleep 10
kubectl --kubeconfig $KUBECONFIG wait --for=condition=ready=False pod/publisher -n $NAMESPACE --timeout=-1s
sleep 20

kubectl --kubeconfig $KUBECONFIG delete --all statefulset -n $NAMESPACE
kubectl --kubeconfig $KUBECONFIG delete pod -n $NAMESPACE publisher
