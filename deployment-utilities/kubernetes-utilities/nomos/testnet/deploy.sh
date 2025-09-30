NAMESPACE="nomos-testnet" # Do not change, every .yaml uses the same NAMESPACE inside
NOMOS_REPO_PATH="/path/to/nomos/repo"

# Namespace
kubectl create namespace $NAMESPACE
# Prometheus configuration
kubectl -n nomos-testnet create configmap prom-config --from-file="$NOMOS_REPO_PATH/testnet/monitoring/prometheus.yml"
# Grafana configuration
kubectl -n nomos-testnet create configmap grafana-env --from-env-file="$NOMOS_REPO_PATH/testnet/monitoring/grafana/plugins.env"
kubectl -n nomos-testnet create configmap grafana-ini --from-file=grafana.ini="$NOMOS_REPO_PATH/testnet/monitoring/grafana/grafana.ini"
kubectl -n nomos-testnet create configmap grafana-provisioning --from-file=datasources.yaml="$NOMOS_REPO_PATH/testnet/monitoring/grafana/datasources.yaml" --from-file=dashboards.yml="$NOMOS_REPO_PATH/testnet/monitoring/grafana/dashboards.yml"
kubectl -n nomos-testnet create configmap grafana-dashboards --from-file="$NOMOS_REPO_PATH/testnet/monitoring/grafana/dashboards"

# Apply deployments
kubectl apply -f cfgsync.yaml
kubectl rollout status --watch --timeout=30000s deployment/cfgsync -n $NAMESPACE
kubectl apply -f prometheus.yaml
kubectl rollout status --watch --timeout=30000s deployment/prometheus -n $NAMESPACE
kubectl apply -f grafana.yaml
kubectl rollout status --watch --timeout=30000s deployment/grafana -n $NAMESPACE
kubectl apply -f nomos_executor.yaml
kubectl apply -f nomos_node.yaml
