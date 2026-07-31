mkdir -p nomos-downloads

for pod in $(kubectl get pods -n nomos-genesis -o jsonpath='{.items[*].metadata.name}'); do
  ord="${pod##*-}"
  dest="nomos-downloads/$pod"

  echo "Downloading from $pod (ord=$ord)..."
  mkdir -p "$dest/logs"

  # Copy logs
  kubectl exec -n nomos-genesis "$pod" -- tar cf - -C /state/logs . | tar xf - -C "$dest/logs"

  # Copy shared settings
  kubectl exec -n nomos-genesis "$pod" -- cat /data/volumes/nomos/deployment-settings.yaml > "$dest/deployment-settings.yaml"

  # Copy ordinal-specific config
  kubectl exec -n nomos-genesis "$pod" -- cat "/data/volumes/nomos/user_config_${ord}.yaml" > "$dest/user_config_${ord}.yaml"
done