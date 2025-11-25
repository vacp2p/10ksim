kubectl --kubeconfig <KUBECONFIG> delete -f anvil-deployment.yaml
kubectl --kubeconfig <KUBECONFIG> delete -f rln-bootstrap.yaml
kubectl --kubeconfig <KUBECONFIG> delete -f waku-rln-statefulset.yaml
kubectl --kubeconfig <KUBECONFIG> delete -f publisher.yaml