#!/bin/bash

NODES_YAML="nodes.yaml"
NODES_PX_YAML="nodes_px.yaml"
NODES_YAML_2="nodes_2.yaml"

# Kubeconfig and namespace
KUBECONFIG="<kubeconfig>"
NAMESPACE="zerotesting"

# Apply bootstrap
kubectl --kubeconfig $KUBECONFIG apply -f bootstrap.yaml
kubectl --kubeconfig $KUBECONFIG rollout status --watch --timeout=30000s statefulset/bootstrap -n $NAMESPACE

# Apply nodes configuration
kubectl --kubeconfig $KUBECONFIG apply -f $NODES_YAML
kubectl --kubeconfig $KUBECONFIG apply -f $NODES_PX_YAML
#kubectl --kubeconfig $KUBECONFIG apply -f $NODES_YAML_2


sleep 600
kubectl --kubeconfig $KUBECONFIG delete --all statefulset -n $NAMESPACE
kubectl --kubeconfig $KUBECONFIG delete pod -n $NAMESPACE publisher