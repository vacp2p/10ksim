#!/bin/bash

# Kubeconfig and namespace
KUBECONFIG="<kubeconfig>"
NAMESPACE="zerotesting"

STORES_YAML="nodes_store.yaml"
NODES_YAML="nodes_relay-filter.yaml"
LPS_YAML="nodes_relay-lightpush.yaml"
FILTER_YAML="nodes_filter.yaml"
LPC_YAML="nodes_lightpush.yaml"
PUBLISHER_YAML="publisher.yaml"

# Apply bootstrap
kubectl --kubeconfig $KUBECONFIG apply -f bootstrap.yaml
kubectl --kubeconfig $KUBECONFIG rollout status --watch --timeout=30000s statefulset/bootstrap -n $NAMESPACE

# Apply nodes configuration
kubectl --kubeconfig $KUBECONFIG apply -f $NODES_YAML
kubectl --kubeconfig $KUBECONFIG rollout status --watch --timeout=30000s statefulset/fserver-0 -n $NAMESPACE
kubectl --kubeconfig $KUBECONFIG apply -f $LPS_YAML
kubectl --kubeconfig $KUBECONFIG rollout status --watch --timeout=30000s statefulset/lpserver-0 -n $NAMESPACE
kubectl --kubeconfig $KUBECONFIG apply -f $STORES_YAML
kubectl --kubeconfig $KUBECONFIG rollout status --watch --timeout=30000s statefulset/store-0 -n $NAMESPACE
kubectl --kubeconfig $KUBECONFIG apply -f $FILTER_YAML
kubectl --kubeconfig $KUBECONFIG rollout status --watch --timeout=30000s statefulset/fclient-0 -n $NAMESPACE
kubectl --kubeconfig $KUBECONFIG apply -f $LPC_YAML
kubectl --kubeconfig $KUBECONFIG rollout status --watch --timeout=30000s statefulset/lpclient-0 -n $NAMESPACE
sleep 40
## Apply publisher configuration
kubectl --kubeconfig $KUBECONFIG apply -f $PUBLISHER_YAML
sleep 20
kubectl --kubeconfig $KUBECONFIG wait --for=condition=ready=False pod/publisher -n $NAMESPACE --timeout=-1s
sleep 10
kubectl --kubeconfig $KUBECONFIG apply -f get_filter_messages.yaml
kubectl --kubeconfig $KUBECONFIG apply -f get_store_messages.yaml
sleep 20
kubectl --kubeconfig $KUBECONFIG wait --for=condition=ready=False pod/get-filter-messages -n $NAMESPACE --timeout=-1s
sleep 20
kubectl --kubeconfig $KUBECONFIG delete pod -n $NAMESPACE publisher
kubectl --kubeconfig $KUBECONFIG delete pod -n $NAMESPACE get-filter-messages
kubectl --kubeconfig $KUBECONFIG delete --all statefulset -n $NAMESPACE
