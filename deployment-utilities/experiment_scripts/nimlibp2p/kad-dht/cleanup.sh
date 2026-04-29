NAMESPACE="nimlibp2p"
KUBECONFIG=~/.kube/config
kubectl --kubeconfig $KUBECONFIG --namespace $NAMESPACE delete -f bootstrap.yaml
kubectl --kubeconfig $KUBECONFIG --namespace $NAMESPACE delete -f nodes.yaml
kubectl --kubeconfig $KUBECONFIG --namespace $NAMESPACE delete -f probe.yaml