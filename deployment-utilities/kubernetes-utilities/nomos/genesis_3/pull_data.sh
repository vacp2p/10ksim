mkdir -p nomos-downloads

for pod in $(kubectl get pods -n nomos-genesis -o jsonpath='{.items[*].metadata.name}'); do
  ord="${pod##*-}"
  dest="nomos-downloads/$pod"

  echo "Downloading from $pod (ord=$ord)..."
  mkdir -p "$dest/logs"

  # Copy logs without tar: enumerate files and stream them with cat
  kubectl exec -n nomos-genesis "$pod" -- sh -c 'find /state/logs -type f' | while IFS= read -r file; do
    rel="${file#/state/logs/}"
    mkdir -p "$dest/logs/$(dirname "$rel")"
    kubectl exec -n nomos-genesis "$pod" -- cat "$file" > "$dest/logs/$rel"
  done

  # Copy shared settings
  kubectl exec -n nomos-genesis "$pod" -- cat /data/volumes/nomos/deployment-settings.yaml > "$dest/deployment-settings.yaml"

  # Copy ordinal-specific config
  kubectl exec -n nomos-genesis "$pod" -- cat "/data/volumes/nomos/user_config_${ord}.yaml" > "$dest/user_config_${ord}.yaml"
done