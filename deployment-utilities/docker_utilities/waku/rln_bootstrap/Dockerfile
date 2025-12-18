FROM ghcr.io/foundry-rs/foundry:latest

# We need root to install packages
USER 0

# Install deps:
# - curl/jq/git/gnupg/ca-certificates so we can talk to Anvil and parse JSON
# - Node 18 (via NodeSource) so pnpm works
# - pnpm globally
RUN apt-get update -y \
    && apt-get install -y --no-install-recommends curl jq ca-certificates git gnupg bash \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g pnpm \
    && rm -rf /var/lib/apt/lists/*

# Prepare working dir for the RLN contracts
WORKDIR /rln

# Clone the repo WITH submodules so forge-std and other deps are present
RUN git clone --recursive \
    --branch temp-with-imt-dep \
    https://github.com/logos-messaging/waku-rlnv2-contract.git /rln


# Install JS deps once at build-time, so the runtime job doesn't need network/npm
RUN pnpm install

# Pre-build with forge so solc/artifacts are already warmed
RUN forge build

# Copy runtime bootstrap script (this script does the actual deploy to Anvil)
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Run that script by default
ENTRYPOINT ["/entrypoint.sh"]
