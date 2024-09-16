# Spawn bootstrap nodes
kubectl apply -f bootstrap.yaml
# Wait to see that they're healthy
kubectl rollout status --watch --timeout=30000s statefulset/bootstrap -n zerotesting
# Spawn all the nodes
kubectl apply -f nodes-nwaku.yaml
kubectl apply -f nodes-gowaku.yaml
echo "We have deployed all nodes, please watch Prometheus or Grafana to see when they have reached a healthy state."
kubectl rollout status --watch --timeout=30000s statefulset/nodes -n zerotesting
kubectl apply -f publisher.yaml