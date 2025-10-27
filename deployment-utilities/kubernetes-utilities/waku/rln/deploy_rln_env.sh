#!/usr/bin/env bash
set -euo pipefail

########################################
# CONFIGURATION
########################################
NAMESPACE="rln-test"
ANVIL_DEPLOY_FILE="anvil-deployment.yaml"
BOOTSTRAP_JOB_FILE="rln-bootstrap.yaml"
KUBECONFIG_PATH="/Users/alberto/Downloads/local.yaml"
TMP_LOG="/tmp/rln-bootstrap.log"
CLEANUP_ON_FAIL=true

########################################
# ARGUMENT PARSING (optional)
########################################
if [[ "${1:-}" == "--no-cleanup" ]]; then
  CLEANUP_ON_FAIL=false
  echo "[INFO] Cleanup disabled for debugging."
fi

########################################
# kubectl wrapper
########################################
k() {
  kubectl --kubeconfig "$KUBECONFIG_PATH" "$@"
}

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
    k delete configmap rln-env -n "$NAMESPACE" --ignore-not-found=true || true
    k delete secret rln-keys -n "$NAMESPACE" --ignore-not-found=true || true
    echo "[CLEANUP] Done."
  fi
}

# Trap any failure
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

echo "[2.2] Checking Anvil pod readiness..."
# We require that the pod is Ready (1/1) AND that the service has endpoints.
# This prevents the bootstrap job from hanging on RPC_URL.
until k get pods -n "$NAMESPACE" -l app=anvil -o jsonpath='{range .items[*]}{.status.containerStatuses[0].ready}{"\n"}{end}' \
     | grep -q "^true$"; do
  echo "  Waiting for anvil pod to be Ready..."
  sleep 2
done

echo "[2.3] Checking anvil-rpc endpoints..."
until k get endpoints anvil-rpc -n "$NAMESPACE" -o jsonpath='{.subsets[0].addresses[0].ip}:{.subsets[0].ports[0].port}' 2>/dev/null \
     | grep -E ':[0-9]+' >/dev/null; do
  echo "  Waiting for anvil-rpc service endpoints..."
  sleep 2
done
echo "Anvil service has endpoints."

########################################
# 3. Run bootstrap job
########################################
echo "[3] Applying RLN bootstrap job..."
# ensure old job is gone or we won't get fresh logs
k delete job rln-bootstrap -n "$NAMESPACE" --ignore-not-found=true
k apply -f "$BOOTSTRAP_JOB_FILE"

echo "[3.1] Waiting for job pod to be created..."
until k get pods -n "$NAMESPACE" -l job-name=rln-bootstrap 2>/dev/null | grep -q 'rln-bootstrap'; do
  echo "  Waiting for job pod to show up..."
  sleep 2
done

echo "[3.2] Waiting for job completion..."
# we'll poll manually instead of plain 'kubectl wait', so we can detect failures too
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
# 4. Capture final output from bootstrap job
########################################
echo "[4] Fetching bootstrap job logs..."
k logs job/rln-bootstrap -n "$NAMESPACE" | tee "$TMP_LOG"

########################################
# 5. Parse addresses / secrets from logs
########################################
echo "[5] Parsing deployment output..."
RLN_RELAY_ETH_CLIENT_ADDRESS=$(grep "^RLN_RELAY_ETH_CLIENT_ADDRESS=" "$TMP_LOG" | cut -d= -f2)
RLN_CONTRACT_ADDRESS=$(grep "^RLN_CONTRACT_ADDRESS=" "$TMP_LOG" | cut -d= -f2)
TOKEN_CONTRACT_ADDRESS=$(grep "^TOKEN_CONTRACT_ADDRESS=" "$TMP_LOG" | cut -d= -f2)
RLN_RELAY_CRED_PASSWORD=$(grep "^RLN_RELAY_CRED_PASSWORD=" "$TMP_LOG" | cut -d= -f2)
RLN_RELAY_CHAIN_ID=$(grep "^RLN_RELAY_CHAIN_ID=" "$TMP_LOG" | cut -d= -f2)
ETH_TESTNET_KEY=$(grep "^ETH_TESTNET_KEY=" "$TMP_LOG" | cut -d= -f2)

if [[ -z "$RLN_CONTRACT_ADDRESS" || -z "$ETH_TESTNET_KEY" ]]; then
  echo "Could not parse addresses/keys from logs."
  cat "$TMP_LOG"
  exit 1
fi

########################################
# 6. Create/update ConfigMap + Secret
########################################
echo "[6] Creating/Updating ConfigMap and Secret for Waku pods..."

k delete configmap rln-env -n "$NAMESPACE" --ignore-not-found=true
k create configmap rln-env -n "$NAMESPACE" \
  --from-literal=RLN_RELAY_ETH_CLIENT_ADDRESS="$RLN_RELAY_ETH_CLIENT_ADDRESS" \
  --from-literal=RLN_CONTRACT_ADDRESS="$RLN_CONTRACT_ADDRESS" \
  --from-literal=RLN_RELAY_CHAIN_ID="$RLN_RELAY_CHAIN_ID" \
  --from-literal=RLN_RELAY_CRED_PASSWORD="$RLN_RELAY_CRED_PASSWORD" \
  --from-literal=TOKEN_CONTRACT_ADDRESS="$TOKEN_CONTRACT_ADDRESS"

k delete secret rln-keys -n "$NAMESPACE" --ignore-not-found=true
k create secret generic rln-keys -n "$NAMESPACE" \
  --from-literal=ETH_TESTNET_KEY="$ETH_TESTNET_KEY"

########################################
# DONE
########################################
trap - ERR INT  # don't auto-cleanup after success
echo
echo "   RLN environment deployed successfully."
echo "   RLN contract:          $RLN_CONTRACT_ADDRESS"
echo "   Token contract:        $TOKEN_CONTRACT_ADDRESS"
echo "   RPC URL:               $RLN_RELAY_ETH_CLIENT_ADDRESS"
echo "   Deployer private key:  $ETH_TESTNET_KEY"
echo
echo "Now you can run Waku/nwaku pods in this namespace with:"
echo
echo "  envFrom:"
echo "    - configMapRef:"
echo "        name: rln-env"
echo "    - secretRef:"
echo "        name: rln-keys"
echo
echo "and each pod will know:"
echo "  * where Anvil RPC is"
echo "  * which RLN contract to talk to"
echo "  * the chain id"
echo "  * the funded private key for approvals/registrations"
echo
