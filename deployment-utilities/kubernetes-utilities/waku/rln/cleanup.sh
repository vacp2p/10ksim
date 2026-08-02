KUBECONFIG_PATH="<your_kubeconfig>"
kubectl --kubeconfig $KUBECONFIG_PATH delete -f anvil-deployment.yaml
kubectl --kubeconfig $KUBECONFIG_PATH delete -f rln-bootstrap.yaml
kubectl --kubeconfig $KUBECONFIG_PATH delete -f waku-rln-statefulset.yaml
kubectl --kubeconfig $KUBECONFIG_PATH delete -f nwaku-bootstrap.yaml
kubectl --kubeconfig $KUBECONFIG_PATH delete -f publisher.yaml