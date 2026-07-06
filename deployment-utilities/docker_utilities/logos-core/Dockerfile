# syntax=docker/dockerfile:1

FROM debian:bookworm-slim AS builder

ARG NIX_USER=nixuser
ARG LOGOS_PACKAGE_MANAGER_BRANCH=tutorial-v1
ARG NIX_BUNDLE_LGX_BRANCH=tutorial-v1
ARG DELIVERY_MODULE_BRANCH=v0.1.3
ARG LOGOSCORE_CLI_BRANCH=tutorial-v1

ENV DEBIAN_FRONTEND=noninteractive
ENV PATH=/usr/local/bin:/home/${NIX_USER}/.nix-profile/bin:/home/${NIX_USER}/bin:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    git \
    build-essential \
    gcc-multilib \
    g++-multilib \
    libc6-dev-i386 \
    ssh \
    cmake \
    xz-utils \
    libssl3 \
    && rm -rf /var/lib/apt/lists/*

RUN git config --global http.sslVerify false

RUN useradd -m ${NIX_USER} \
    && mkdir -p /nix /home/${NIX_USER}/bin /etc/nix \
    && chown -R ${NIX_USER}:${NIX_USER} /nix /home/${NIX_USER}

RUN cat > /etc/nix/nix.conf << 'EOF'
experimental-features = nix-command flakes
accept-flake-config = true
trusted-substituters = https://nix-cache.status.im/ https://cache.nixos.org/
trusted-public-keys = nix-cache.status.im-1:x/93lOfLU+duPplwMSBR+OlY4+mo+dCN7n0mr4oPwgY= cache.nixos.org-1:6NCHdD59X431o0gWypbMrAURkbJ16ZPMQFGspcDShjY=
trusted-users = root nixuser
filter-syscalls = false
EOF

USER ${NIX_USER}
WORKDIR /home/${NIX_USER}
ENV HOME=/home/${NIX_USER}
ENV USER=${NIX_USER}
ENV NIX_USER_PROFILE_DIR=/nix/var/nix/profiles/per-user/$USER

RUN curl -L https://nixos.org/nix/install | sh -s -- --no-daemon

RUN git clone https://github.com/logos-co/logos-package-manager.git \
    && cd logos-package-manager \
    && git checkout ${LOGOS_PACKAGE_MANAGER_BRANCH} \
    && nix build \
    && ln -s $(realpath ./result)/bin/lgpm $HOME/bin/lgpm

RUN git clone https://github.com/logos-co/nix-bundle-lgx.git \
    && cd nix-bundle-lgx \
    && git checkout ${NIX_BUNDLE_LGX_BRANCH}

RUN git clone https://github.com/logos-co/logos-delivery-module.git \
    && cd logos-delivery-module \
    && git checkout ${DELIVERY_MODULE_BRANCH} \
    && nix bundle --bundler $HOME/nix-bundle-lgx#dual . \
    && lgpm install --file logos-delivery_module-module-lgx-*/logos-delivery_module-module.lgx --modules-dir "$HOME/.logos/modules"

RUN git clone https://github.com/logos-co/logos-logoscore-cli.git \
    && cd logos-logoscore-cli \
    && git checkout ${LOGOSCORE_CLI_BRANCH} \
    && nix build \
    && mkdir -p /tmp/runtime-root/bin /tmp/runtime-root/nix/store \
    && cp -L $(realpath ./result)/bin/logoscore /tmp/runtime-root/bin/logoscore \
    && nix-store --query --requisites $(realpath ./result)/bin/logoscore | \
       xargs -r cp -at /tmp/runtime-root/nix/store

FROM debian:bookworm-slim AS runtime

ARG NIX_USER=nixuser
ENV DEBIAN_FRONTEND=noninteractive
ENV PATH=/usr/local/bin:/home/${NIX_USER}/bin:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    python3 \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m ${NIX_USER} \
    && mkdir -p /home/${NIX_USER}/.logos/modules /home/${NIX_USER}/bin /nix \
    && chown -R ${NIX_USER}:${NIX_USER} /home/${NIX_USER} /nix

COPY --from=builder /home/${NIX_USER}/.logos/modules /home/${NIX_USER}/.logos/modules
COPY --from=builder /tmp/runtime-root/bin/logoscore /home/${NIX_USER}/bin/logoscore
COPY --from=builder /tmp/runtime-root/nix/store /nix/store
COPY entrypoint.sh /home/${NIX_USER}/entrypoint.sh
COPY main.py /home/${NIX_USER}/main.py

RUN chmod +x /home/${NIX_USER}/entrypoint.sh \
    && chown -R ${NIX_USER}:${NIX_USER} /home/${NIX_USER} /nix

USER ${NIX_USER}
WORKDIR /home/${NIX_USER}
ENTRYPOINT ["/bin/sh", "-c", "./entrypoint.sh"]