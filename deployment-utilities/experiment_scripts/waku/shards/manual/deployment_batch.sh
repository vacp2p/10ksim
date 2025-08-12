#!/bin/bash

PUBLISHER_YAML="publisher_testing.yaml"

# Kubeconfig and namespace
KUBECONFIG="/home/alberto/.kube/rubi3.yaml"
NAMESPACE="zerotesting"


# Apply bootstrap and midstrap configurations
kubectl --kubeconfig $KUBECONFIG apply -f bootstrap.yaml
kubectl --kubeconfig $KUBECONFIG rollout status --watch --timeout=30000s statefulset/bootstrap -n $NAMESPACE

# Apply nodes configuration
kubectl --kubeconfig $KUBECONFIG apply -f nodes_1k_0.yaml
kubectl --kubeconfig $KUBECONFIG apply -f nodes_1k_1.yaml
kubectl --kubeconfig $KUBECONFIG apply -f nodes_1k_2.yaml
kubectl --kubeconfig $KUBECONFIG apply -f nodes_1k_3.yaml
kubectl --kubeconfig $KUBECONFIG apply -f nodes_1k_4.yaml
kubectl --kubeconfig $KUBECONFIG apply -f nodes_1k_5.yaml
kubectl --kubeconfig $KUBECONFIG apply -f nodes_1k_6.yaml
kubectl --kubeconfig $KUBECONFIG apply -f nodes_1k_7.yaml
kubectl --kubeconfig $KUBECONFIG rollout status --watch --timeout=30000s statefulset/nodes-0 -n $NAMESPACE
kubectl --kubeconfig $KUBECONFIG rollout status --watch --timeout=30000s statefulset/nodes-1 -n $NAMESPACE
kubectl --kubeconfig $KUBECONFIG rollout status --watch --timeout=30000s statefulset/nodes-2 -n $NAMESPACE
kubectl --kubeconfig $KUBECONFIG rollout status --watch --timeout=30000s statefulset/nodes-3 -n $NAMESPACE
kubectl --kubeconfig $KUBECONFIG rollout status --watch --timeout=30000s statefulset/nodes-4 -n $NAMESPACE
kubectl --kubeconfig $KUBECONFIG rollout status --watch --timeout=30000s statefulset/nodes-5 -n $NAMESPACE
kubectl --kubeconfig $KUBECONFIG rollout status --watch --timeout=30000s statefulset/nodes-6 -n $NAMESPACE
kubectl --kubeconfig $KUBECONFIG rollout status --watch --timeout=30000s statefulset/nodes-7 -n $NAMESPACE

sleep 30
## Apply publisher configuration
kubectl --kubeconfig $KUBECONFIG apply -f $PUBLISHER_YAML
sleep 10
kubectl --kubeconfig $KUBECONFIG wait --for=condition=ready=False pod/publisher -n $NAMESPACE --timeout=-1s
sleep 20

kubectl --kubeconfig $KUBECONFIG delete --all statefulset -n $NAMESPACE
kubectl --kubeconfig $KUBECONFIG delete pod -n $NAMESPACE publisher
