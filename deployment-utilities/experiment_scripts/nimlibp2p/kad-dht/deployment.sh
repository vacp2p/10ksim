#!/bin/bash
NAMESPACE="nimlibp2p"
KUBECONFIG=~/.kube/config
kubectl --kubeconfig $KUBECONFIG --namespace $NAMESPACE apply -f service.yaml
kubectl --kubeconfig $KUBECONFIG --namespace $NAMESPACE apply -f bootstrap.yaml
kubectl --kubeconfig $KUBECONFIG --namespace $NAMESPACE rollout status --watch --timeout=600s statefulset/bootstrap -n $NAMESPACE
kubectl --kubeconfig $KUBECONFIG --namespace $NAMESPACE apply -f nodes.yaml
kubectl --kubeconfig $KUBECONFIG --namespace $NAMESPACE rollout status --watch --timeout=600s statefulset/nodes -n $NAMESPACE
kubectl --kubeconfig $KUBECONFIG --namespace $NAMESPACE apply -f probe.yaml
kubectl --kubeconfig $KUBECONFIG --namespace $NAMESPACE rollout status --watch --timeout=600s statefulset/nodes -n $NAMESPACE
sleep 60
./cleanup.sh