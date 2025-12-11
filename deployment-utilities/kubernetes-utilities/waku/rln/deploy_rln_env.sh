#!/usr/bin/env bash
set -euo pipefail

########################################
# CONFIGURATION
########################################
NAMESPACE="rln-test"
ANVIL_DEPLOY_FILE="anvil-deployment.yaml"
BOOTSTRAP_JOB_FILE="rln-bootstrap.yaml"
WAKU_STATEFULSET_FILE="waku-rln-statefulset.yaml"
WAKU_BOOTSTRAP_FILE="nwaku-bootstrap.yaml"
KUBECONFIG_PATH="/Users/alberto/Downloads/local.yaml"
TMP_LOG="/tmp/rln-bootstrap.log"
CLEANUP_ON_FAIL=true

########################################
# ARGUMENT PARSING
########################################
if [[ "${1:-}" == "--no-cleanup" ]]; then
  CLEANUP_ON_FAIL=false
  echo "[INFO] Cleanup disabled for debugging."
fi

########################################
# kubectl wrapper
########################################
k() { kubectl --kubeconfig "$KUBECONFIG_PATH" "$@"; }

########################################
# cleanup on failure
########################################
cleanup() {
  if [[ "$CLEANUP_ON_FAIL" == true ]]; then
    echo
    echo "[CLEANUP] Cleaning up namespace $NAMESPACE ..."
    k delete job rln-bootstrap -n "$NAMESPACE" --ignore-not-found=true || true
    k delete deploy anvil -n "$NAMESPACE" --ignore-not-found=true || true
    k delete svc anvil-rpc -n "$NAMESPACE" --ignore-not-found=true || true
    k delete statefulset rln-0 -n "$NAMESPACE" --ignore-not-found=true || true
    k delete statefulset rln-bootstrap -n "$NAMESPACE" --ignore-not-found=true || true
    k delete configmap rln-env -n "$NAMESPACE" --ignore-not-found=true || true
    k delete secret rln-keys -n "$NAMESPACE" --ignore-not-found=true || true
    echo "[CLEANUP] Done."
  fi
}
trap 'echo "[ERROR] Deployment failed. Triggering cleanup."; cleanup' ERR INT

########################################
# START DEPLOYMENT
########################################
echo "=========================================="
echo " Deploying RLN local environment to k8s"
echo " Namespace: $NAMESPACE"
echo " Kubeconfig: $KUBECONFIG_PATH"
echo "=========================================="

########################################
# 1. Namespace
########################################
if ! k get ns "$NAMESPACE" >/dev/null 2>&1; then
  echo "[1] Creating namespace $NAMESPACE..."
  k create ns "$NAMESPACE"
else
  echo "[1] Namespace $NAMESPACE already exists."
fi

########################################
# 2. Apply / rollout Anvil
########################################
echo "[2] Applying Anvil Deployment and Service..."
k apply -f "$ANVIL_DEPLOY_FILE"
echo "[2.1] Waiting for Anvil rollout..."
k rollout status deploy/anvil -n "$NAMESPACE" --timeout=90s

echo "[2.2] Checking Anvil readiness..."
until k get pods -n "$NAMESPACE" -l app=anvil -o jsonpath='{range .items[*]}{.status.containerStatuses[0].ready}{"\n"}{end}' | grep -q "^true$"; do
  echo "  Waiting for anvil pod to be Ready..."
  sleep 2
done

until k get endpoints anvil-rpc -n "$NAMESPACE" -o jsonpath='{.subsets[0].addresses[0].ip}:{.subsets[0].ports[0].port}' 2>/dev/null | grep -E ':[0-9]+' >/dev/null; do
  echo "  Waiting for anvil-rpc endpoints..."
  sleep 2
done
echo "Anvil RPC ready."

########################################
# 3. Run bootstrap job
########################################
echo "[3] Applying RLN bootstrap job..."
k delete job rln-bootstrap -n "$NAMESPACE" --ignore-not-found=true
k apply -f "$BOOTSTRAP_JOB_FILE"

echo "[3.1] Waiting for job pod..."
until k get pods -n "$NAMESPACE" -l job-name=rln-bootstrap 2>/dev/null | grep -q 'rln-bootstrap'; do
  echo "  Waiting for bootstrap pod..."
  sleep 2
done

echo "[3.2] Waiting for job completion..."
JOB_TIMEOUT_SECS=400
ELAPSED=0
while true; do
  STATUS=$(k get job rln-bootstrap -n "$NAMESPACE" -o jsonpath='{.status.conditions[?(@.type=="Complete")].status}' 2>/dev/null || true)
  FAILED=$(k get job rln-bootstrap -n "$NAMESPACE" -o jsonpath='{.status.failed}' 2>/dev/null || echo 0)
  if [[ "$STATUS" == "True" ]]; then
    echo "Bootstrap job completed."
    break
  fi
  if [[ "$FAILED" != "0" && "$FAILED" != "" ]]; then
    echo "Bootstrap job failed."
    k logs job/rln-bootstrap -n "$NAMESPACE" || true
    exit 1
  fi
  if (( ELAPSED >= JOB_TIMEOUT_SECS )); then
    echo "Timeout waiting for bootstrap job to complete."
    k logs job/rln-bootstrap -n "$NAMESPACE" || true
    exit 1
  fi
  sleep 5
  ELAPSED=$((ELAPSED+5))
done

########################################
# 4. Parse bootstrap logs
########################################
echo "[4] Fetching bootstrap logs..."
k logs job/rln-bootstrap -n "$NAMESPACE" | tee "$TMP_LOG"

########################################
# 5. Parse addresses / secrets from logs
########################################
echo "[5] Parsing deployment output..."

parse_field() {
  local key="$1"
  grep -m1 "^${key}=" "$TMP_LOG" | cut -d= -f2 | tr -d '\r' || true
}

RLN_RELAY_ETH_CLIENT_ADDRESS=$(parse_field RLN_RELAY_ETH_CLIENT_ADDRESS)
RLN_CONTRACT_ADDRESS=$(parse_field RLN_CONTRACT_ADDRESS)
TOKEN_CONTRACT_ADDRESS=$(parse_field TOKEN_CONTRACT_ADDRESS)
RLN_RELAY_CRED_PASSWORD=$(parse_field RLN_RELAY_CRED_PASSWORD)
RLN_RELAY_CHAIN_ID=$(parse_field RLN_RELAY_CHAIN_ID)
ETH_TESTNET_KEY=$(parse_field ETH_TESTNET_KEY)
DEPLOYER_PRIVATE_KEY=${ETH_TESTNET_KEY}  # fallback – same key in your current setup

# Log what we parsed for easier debugging
echo "  RLN_CONTRACT_ADDRESS=${RLN_CONTRACT_ADDRESS}"
echo "  TOKEN_CONTRACT_ADDRESS=${TOKEN_CONTRACT_ADDRESS}"
echo "  RLN_RELAY_CRED_PASSWORD=${RLN_RELAY_CRED_PASSWORD}"
echo "  RLN_RELAY_ETH_CLIENT_ADDRESS=${RLN_RELAY_ETH_CLIENT_ADDRESS}"
echo "  ETH_TESTNET_KEY=${ETH_TESTNET_KEY}"

if [[ -z "${RLN_CONTRACT_ADDRESS}" || -z "${ETH_TESTNET_KEY}" ]]; then
  echo "   Could not parse addresses/keys from logs."
  echo "--- Dump of /tmp/rln-bootstrap.log ---"
  cat "$TMP_LOG"
  exit 1
fi

########################################
# 6. Create ConfigMap + Secret
########################################
echo "[6] Creating ConfigMap and Secret..."
k delete configmap rln-env -n "$NAMESPACE" --ignore-not-found=true
k create configmap rln-env -n "$NAMESPACE" \
  --from-literal=RLN_RELAY_ETH_CLIENT_ADDRESS="$RLN_RELAY_ETH_CLIENT_ADDRESS" \
  --from-literal=RLN_CONTRACT_ADDRESS="$RLN_CONTRACT_ADDRESS" \
  --from-literal=TOKEN_CONTRACT_ADDRESS="$TOKEN_CONTRACT_ADDRESS" \
  --from-literal=RLN_RELAY_CHAIN_ID="$RLN_RELAY_CHAIN_ID" \
  --from-literal=RLN_RELAY_CRED_PASSWORD="$RLN_RELAY_CRED_PASSWORD"

k delete secret rln-keys -n "$NAMESPACE" --ignore-not-found=true
k create secret generic rln-keys -n "$NAMESPACE" \
  --from-literal=ETH_TESTNET_KEY="$ETH_TESTNET_KEY" \
  --from-literal=DEPLOYER_PRIVATE_KEY="$DEPLOYER_PRIVATE_KEY"

########################################
# 7. Apply or refresh Waku StatefulSet
########################################
echo "[7] Applying or refreshing Waku StatefulSet..."
if k get statefulset rln-0 -n "$NAMESPACE" >/dev/null 2>&1; then
  echo "StatefulSet already exists; forcing restart to reload config."
  k rollout restart statefulset rln-0 -n "$NAMESPACE"
else
  echo "Creating new StatefulSet from $WAKU_STATEFULSET_FILE..."
  k apply -f "$WAKU_BOOTSTRAP_FILE"
  sleep 5
  k rollout status statefulset/rln-bootstrap -n "$NAMESPACE"
  k apply -f "$WAKU_STATEFULSET_FILE"
fi

echo "[7.1] Waiting for all Waku pods to be Ready..."
k rollout status statefulset/rln-0 -n "$NAMESPACE"

k apply -f publisher.yaml

########################################
# DONE
########################################
trap - ERR INT
echo
echo "   RLN environment deployed successfully."
echo "   RLN contract:          $RLN_CONTRACT_ADDRESS"
echo "   RLN cred passw:        $RLN_RELAY_CRED_PASSWORD"
echo "   Token contract:        $TOKEN_CONTRACT_ADDRESS"
echo "   RPC URL:               $RLN_RELAY_ETH_CLIENT_ADDRESS"
echo "   Deployer private key:  $DEPLOYER_PRIVATE_KEY"
echo
echo "   ConfigMap + Secret updated and StatefulSet refreshed."
echo "Pods should now register RLN memberships automatically."
echo
