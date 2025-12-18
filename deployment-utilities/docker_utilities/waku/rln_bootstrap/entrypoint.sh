#!/bin/bash
set -euo pipefail

RPC_URL="${RPC_URL:-http://anvil-rpc.rln-test.svc.cluster.local:8545}"
MNEMONIC="${MNEMONIC:-test test test test test test test test test test test junk}"
NUM_PODS="${NUM_PODS:-3}"

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
  --mnemonic-index 0 | awk '{print $NF}')

DEPLOYER=$(cast wallet address \
  --mnemonic "$MNEMONIC" \
  --mnemonic-index 0 | awk '{print $NF}')
echo "   Deployer: $DEPLOYER"

cd /rln

# Utility function to extract the last deployed address from broadcast JSONs
get_last_deployed_address() {
  local script_dir="$1"   # e.g. "TestToken.sol" or "Deploy.s.sol"
  local file="broadcast/${script_dir}/${CHAIN_ID}/run-latest.json"
  jq -r '
    .transactions[]
    | select(.transactionType == "CREATE")
    | .contractAddress
  ' "$file" | tail -n1
}

##############################################
# 1. Deploy basic TestToken
##############################################
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

##############################################
# 2. Deploy PriceCalculator
##############################################
echo "[2] Deploying LinearPriceCalculator..."
TOKEN_ADDRESS="$TOKEN_ADDRESS" forge script script/Deploy.s.sol:DeployPriceCalculator \
  --broadcast \
  --rpc-url "$RPC_URL" \
  --private-key "$PRIVKEY"

PRICE_CALCULATOR_ADDRESS=$(get_last_deployed_address "Deploy.s.sol")
echo "   LinearPriceCalculator at: $PRICE_CALCULATOR_ADDRESS"

##############################################
# 3. Deploy TestStableToken (with proxy)
##############################################
echo "[3] Deploying TestStableToken (with proxy)..."
forge script script/DeployTokenWithProxy.s.sol:DeployTokenWithProxy \
  --broadcast \
  --rpc-url "$RPC_URL" \
  --mnemonics "$MNEMONIC"

TOKEN_PROXY_ADDRESS=$(jq -r '
  .transactions[]
  | select(.transactionType == "CREATE")
  | .contractAddress
' "broadcast/DeployTokenWithProxy.s.sol/${CHAIN_ID}/run-latest.json" | tail -n1)

if [[ -z "$TOKEN_PROXY_ADDRESS" || "$TOKEN_PROXY_ADDRESS" == "null" ]]; then
  echo "   Could not extract TestStableToken proxy address from broadcast folder."
  find broadcast -type f -name "run-latest.json" | xargs ls -lt | head -n 3
  exit 1
fi

echo "   Deployed TestStableToken Proxy at: $TOKEN_PROXY_ADDRESS"

##############################################
# 4. Deploy RLN contracts (using broadcast files)
##############################################
get_last_deployed_address() {
  local folder="$1"
  local file="/rln/broadcast/${folder}/${CHAIN_ID}/run-latest.json"
  if [[ -f "$file" ]]; then
    jq -r '.transactions[] | select(.transactionType=="CREATE") | .contractAddress' "$file" | tail -n1
  fi
}

echo "[4.1] Deploying LinearPriceCalculator..."
TOKEN_ADDRESS="$TOKEN_PROXY_ADDRESS" \
forge script script/Deploy.s.sol:DeployPriceCalculator \
  --broadcast \
  --rpc-url "$RPC_URL" \
  --private-key "$PRIVKEY" > /tmp/pricecalc-deploy.log 2>&1 || {
    echo "   Failed to deploy LinearPriceCalculator:"
    tail -n 40 /tmp/pricecalc-deploy.log
    exit 1
  }

PRICE_CALCULATOR_ADDRESS=$(get_last_deployed_address "Deploy.s.sol")
if [[ -z "$PRICE_CALCULATOR_ADDRESS" ]]; then
  PRICE_CALCULATOR_ADDRESS=$(grep -m1 -o "0x[a-fA-F0-9]\{40\}" /tmp/pricecalc-deploy.log || true)
fi
if [[ -z "$PRICE_CALCULATOR_ADDRESS" ]]; then
  echo "   Could not extract LinearPriceCalculator address."
  tail -n 40 /tmp/pricecalc-deploy.log
  exit 1
fi
echo "      LinearPriceCalculator deployed at: $PRICE_CALCULATOR_ADDRESS"


echo "[4.2] Deploying Waku RLNv2 implementation..."
forge script script/Deploy.s.sol:DeployWakuRlnV2 \
  --broadcast \
  --rpc-url "$RPC_URL" \
  --private-key "$PRIVKEY" > /tmp/rlnv2-deploy.log 2>&1 || {
    echo "   Failed to deploy Waku RLNv2:"
    tail -n 40 /tmp/rlnv2-deploy.log
    exit 1
  }

RLN_IMPLEMENTATION_ADDRESS=$(get_last_deployed_address "Deploy.s.sol")
if [[ -z "$RLN_IMPLEMENTATION_ADDRESS" ]]; then
  RLN_IMPLEMENTATION_ADDRESS=$(grep -m1 -o "0x[a-fA-F0-9]\{40\}" /tmp/rlnv2-deploy.log || true)
fi
if [[ -z "$RLN_IMPLEMENTATION_ADDRESS" ]]; then
  echo "   Could not extract RLN implementation address."
  tail -n 40 /tmp/rlnv2-deploy.log
  exit 1
fi
echo "      RLN implementation deployed at: $RLN_IMPLEMENTATION_ADDRESS"


echo "[4.3] Deploying RLN Proxy..."
forge script script/Deploy.s.sol:DeployProxy \
  --broadcast \
  --rpc-url "$RPC_URL" \
  --private-key "$PRIVKEY" > /tmp/rlnproxy-deploy.log 2>&1 || {
    echo "   Failed to deploy RLN proxy:"
    tail -n 40 /tmp/rlnproxy-deploy.log
    exit 1
  }

RLN_CONTRACT_ADDRESS=$(get_last_deployed_address "Deploy.s.sol")
if [[ -z "$RLN_CONTRACT_ADDRESS" ]]; then
  RLN_CONTRACT_ADDRESS=$(grep -m1 -o "0x[a-fA-F0-9]\{40\}" /tmp/rlnproxy-deploy.log || true)
fi
if [[ -z "$RLN_CONTRACT_ADDRESS" ]]; then
  echo "   Could not extract RLN proxy address."
  tail -n 40 /tmp/rlnproxy-deploy.log
  exit 1
fi
echo "      RLN proxy deployed at: $RLN_CONTRACT_ADDRESS"


##############################################
# 5. Grant minter privileges to deployer
##############################################
echo "[5] Granting deployer minter privileges..."
cast send "$TOKEN_PROXY_ADDRESS" \
  "addMinter(address)" "$DEPLOYER" \
  --rpc-url "$RPC_URL" \
  --private-key "$PRIVKEY"

##############################################
# 6. Mint tokens to deployer
##############################################
echo "[6] Minting tokens to deployer..."
cast send "$TOKEN_PROXY_ADDRESS" \
  "mint(address,uint256)" "$DEPLOYER" 1000000000000000000000 \
  --rpc-url "$RPC_URL" \
  --private-key "$PRIVKEY"

##############################################
# 7. Approve RLN contract to spend tokens
##############################################
echo "[7] Approving RLN contract to spend tokens..."
cast send "$TOKEN_PROXY_ADDRESS" \
  "approve(address,uint256)" "$RLN_CONTRACT_ADDRESS" 1000000000000000000000 \
  --rpc-url "$RPC_URL" \
  --private-key "$PRIVKEY"


##############################################
# 8. Minting and approving tokens for derived Waku pod keys
##############################################
echo "[8] Minting and approving tokens for derived Waku pod keys..."

MNEMONIC_FILE=/tmp/mnemonic.txt
echo "$MNEMONIC" > "$MNEMONIC_FILE"

for i in $(seq 1 "$NUM_PODS"); do
  DERIVED_PK=$(cast wallet private-key --mnemonic-path "$MNEMONIC_FILE" --mnemonic-index "$i" | tail -n1 | awk '{print $NF}')
  DERIVED_ADDR=$(cast wallet address --mnemonic-path "$MNEMONIC_FILE" --mnemonic-index "$i" | tail -n1 | awk '{print $NF}')
  echo "   Funding Waku key $i: $DERIVED_ADDR"

  # 8.1 Send a small amount of ETH for gas (~1 ETH)
  cast send "$DERIVED_ADDR" \
    --value 1000000000000000000 \
    --rpc-url "$RPC_URL" \
    --private-key "$PRIVKEY"

  # 8.2 Mint tokens to this derived address
  cast send "$TOKEN_PROXY_ADDRESS" \
    "mint(address,uint256)" "$DERIVED_ADDR" 1000000000000000000000 \
    --rpc-url "$RPC_URL" \
    --private-key "$PRIVKEY"

  # 8.3 Approve RLN contract to spend tokens
  cast send "$TOKEN_PROXY_ADDRESS" \
    "approve(address,uint256)" "$RLN_CONTRACT_ADDRESS" 1000000000000000000000000000000 \
    --rpc-url "$RPC_URL" \
    --private-key "$DERIVED_PK"

  # 8.4 (Optional) check token + allowance
  BALANCE=$(cast call "$TOKEN_PROXY_ADDRESS" "balanceOf(address)" "$DERIVED_ADDR" --rpc-url "$RPC_URL")
  ALLOWANCE=$(cast call "$TOKEN_PROXY_ADDRESS" "allowance(address,address)" "$DERIVED_ADDR" "$RLN_CONTRACT_ADDRESS" --rpc-url "$RPC_URL")
  echo "      Balance: $BALANCE"
  echo "      Allowance: $ALLOWANCE"
done



##############################################
# 9. Final output
##############################################
echo ""
echo "========== FINAL OUTPUT =========="
echo "RLN_RELAY_ETH_CLIENT_ADDRESS=$RPC_URL"
echo "RLN_CONTRACT_ADDRESS=$RLN_CONTRACT_ADDRESS"
echo "TOKEN_CONTRACT_ADDRESS=$TOKEN_PROXY_ADDRESS"
echo "RLN_RELAY_CRED_PASSWORD=changeme"
echo "ETH_TESTNET_KEY=$PRIVKEY"
echo "RLN_RELAY_CHAIN_ID=$CHAIN_ID"
echo "=================================="
