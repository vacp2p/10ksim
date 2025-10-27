#!/bin/bash
set -euo pipefail

RPC_URL="${RPC_URL:-http://anvil-rpc.rln-test.svc.cluster.local:8545}"
MNEMONIC="${MNEMONIC:-test test test test test test test test test test test junk}"

echo "[0] Waiting for Anvil RPC ($RPC_URL) to be ready..."
until curl -sf -X POST \
  -H "Content-Type: application/json" \
  --data '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' \
  "$RPC_URL" | jq -e '.result' >/dev/null 2>&1; do
  echo "  Anvil not ready yet, retrying in 2s..."
  sleep 2
done
echo "Anvil RPC is responsive."

CHAIN_ID=$(cast chain-id --rpc-url "$RPC_URL")
echo "[0.1] Chain ID is $CHAIN_ID"

echo "[0.2] Deriving deployer key/address from mnemonic index 0..."
PRIVKEY=$(cast wallet private-key \
  --mnemonic "$MNEMONIC" \
  --mnemonic-index 0 \
  | awk '{print $NF}')

DEPLOYER=$(cast wallet address \
  --mnemonic "$MNEMONIC" \
  --mnemonic-index 0 \
  | awk '{print $NF}')
echo "   Deployer: $DEPLOYER"

cd /rln

get_last_deployed_address () {
  local script_dir="$1"   # e.g. "TestToken.sol" or "Deploy.s.sol"
  local file="broadcast/${script_dir}/${CHAIN_ID}/run-latest.json"
  jq -r '
    .transactions[]
    | select(.transactionType == "CREATE")
    | .contractAddress
  ' "$file" | tail -n1
}

echo "[1] Deploying TestToken to Anvil..."
forge script test/TestToken.sol \
  --broadcast \
  --rpc-url "$RPC_URL" \
  --tc TestTokenFactory \
  --private-key "$PRIVKEY"

TOKEN_ADDRESS=$(get_last_deployed_address "TestToken.sol")
echo "   TestToken deployed at: $TOKEN_ADDRESS"

echo "[1.1] Minting tokens to $DEPLOYER..."
cast send "$TOKEN_ADDRESS" \
  "mint(address,uint256)" \
  "$DEPLOYER" \
  "1000000000000000000000000" \
  --private-key "$PRIVKEY" \
  --rpc-url "$RPC_URL"

echo "[2] Deploying LinearPriceCalculator..."
TOKEN_ADDRESS="$TOKEN_ADDRESS" forge script script/Deploy.s.sol \
  --broadcast \
  --rpc-url "$RPC_URL" \
  --tc DeployPriceCalculator \
  --private-key "$PRIVKEY"

PRICE_CALCULATOR_ADDRESS=$(get_last_deployed_address "Deploy.s.sol")
echo "   LinearPriceCalculator at: $PRICE_CALCULATOR_ADDRESS"

echo "[3] Deploying WakuRlnV2 implementation..."
forge script script/Deploy.s.sol \
  --broadcast \
  --rpc-url "$RPC_URL" \
  --tc DeployWakuRlnV2 \
  --private-key "$PRIVKEY"

WAKURLNV2_IMPL_ADDRESS=$(get_last_deployed_address "Deploy.s.sol")
echo "   WakuRlnV2 impl at: $WAKURLNV2_IMPL_ADDRESS"

echo "[4] Deploying ERC1967Proxy wired to WakuRlnV2..."
PRICE_CALCULATOR_ADDRESS="$PRICE_CALCULATOR_ADDRESS" \
WAKURLNV2_ADDRESS="$WAKURLNV2_IMPL_ADDRESS" \
forge script script/Deploy.s.sol \
  --broadcast \
  --rpc-url "$RPC_URL" \
  --tc DeployProxy \
  --private-key "$PRIVKEY"

RLN_PROXY_ADDRESS=$(get_last_deployed_address "Deploy.s.sol")
echo "   RLN proxy at: $RLN_PROXY_ADDRESS"

echo ""
echo "========== FINAL OUTPUT =========="
echo "RLN_RELAY_ETH_CLIENT_ADDRESS=$RPC_URL"
echo "RLN_CONTRACT_ADDRESS=$RLN_PROXY_ADDRESS"
echo "TOKEN_CONTRACT_ADDRESS=$TOKEN_ADDRESS"
echo "RLN_RELAY_CRED_PASSWORD=changeme"
echo "ETH_TESTNET_KEY=$PRIVKEY"
echo "RLN_RELAY_CHAIN_ID=$CHAIN_ID"
echo "=================================="
echo ""
