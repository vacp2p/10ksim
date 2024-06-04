kubectl apply -f bootstrap.yaml
kubectl rollout status --watch --timeout=30000s statefulset/bootstrap -n zerotesting
kubectl apply -f midstrap.yaml
kubectl rollout status --watch --timeout=30000s statefulset/midstrap -n zerotesting
kubectl apply -f nodes.yaml
echo "We have deployed all nodes, please watch Prometheus or Grafana to see when they have reached a healthy state."
echo "Please note you cannot (yet) rely on the Ready state as it does not actually indicate an unhealthy peer, just one that is not ready for bootstrapping from."
#kubectl rollout status --watch --timeout=30000s statefulset/nodes -n zerotesting
