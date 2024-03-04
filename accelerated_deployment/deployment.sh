kubectl apply -f bootstrap.yaml
kubectl rollout status --watch --timeout=30000s statefulset/bootstrap -n zerotesting
kubectl apply -f midstrap.yaml
kubectl rollout status --watch --timeout=30000s statefulset/midstrap -n zerotesting
kubectl apply -f nodes.yaml
kubectl rollout status --watch --timeout=30000s statefulset/nodes -n zerotesting
