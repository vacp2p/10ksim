#!/bin/bash

# Kubeconfig and namespace
KUBECONFIG="<kubeconfig>"
NAMESPACE="zerotesting"

NODES_RELAY_0="nodes_relay_0.yaml"
NODES_RELAY_1="nodes_relay_1.yaml"
STORES_YAML="nodes_store.yaml"
PUBLISHER_YAML="publisher.yaml"

# Apply bootstrap
kubectl --kubeconfig $KUBECONFIG apply -f bootstrap.yaml
kubectl --kubeconfig $KUBECONFIG rollout status --watch --timeout=30000s statefulset/bootstrap -n $NAMESPACE

# Apply nodes configuration
kubectl --kubeconfig $KUBECONFIG apply -f $NODES_RELAY_0
kubectl --kubeconfig $KUBECONFIG rollout status --watch --timeout=30000s statefulset/relaya-0 -n $NAMESPACE
kubectl --kubeconfig $KUBECONFIG apply -f $STORES_YAML
kubectl --kubeconfig $KUBECONFIG rollout status --watch --timeout=30000s statefulset/store-0 -n $NAMESPACE
# Apply publisher configuration
kubectl --kubeconfig $KUBECONFIG apply -f $PUBLISHER_YAML

for i in {1..10}; do
  sleep 30
  kubectl --kubeconfig $KUBECONFIG apply -f $NODES_RELAY_1
  sleep 30
  kubectl --kubeconfig $KUBECONFIG delete statefulset relayb-0 -n $NAMESPACE
done

kubectl --kubeconfig $KUBECONFIG wait --for=condition=ready=False pod/publisher -n $NAMESPACE --timeout=-1s
sleep 10
kubectl --kubeconfig $KUBECONFIG apply -f get_store_messages.yaml
sleep 20

kubectl --kubeconfig $KUBECONFIG delete pod -n $NAMESPACE publisher
kubectl --kubeconfig $KUBECONFIG delete --all statefulset -n $NAMESPACE
