FROM ubuntu:24.04

ARG LOGOS_TOOLS_VERSION=0.2.0
ARG BLOCKCHAIN_MODULE_VERSION=0.2.1
ARG TARGETARCH

ENV LOGOS_MODULES_DIR=/opt/logos/modules

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl grep jq squashfs-tools tar && \
    rm -rf /var/lib/apt/lists/*

RUN set -eu; \
    case "${TARGETARCH:-amd64}" in \
      amd64) \
        if [ ! -e /lib/ld-linux-x86-64.so.2 ] && [ -e /lib64/ld-linux-x86-64.so.2 ]; then \
          ln -s /lib64/ld-linux-x86-64.so.2 /lib/ld-linux-x86-64.so.2; \
        fi \
        ;; \
      arm64) \
        if [ ! -e /lib/ld-linux-aarch64.so.1 ] && [ -e /lib/aarch64-linux-gnu/ld-linux-aarch64.so.1 ]; then \
          ln -s /lib/aarch64-linux-gnu/ld-linux-aarch64.so.1 /lib/ld-linux-aarch64.so.1; \
        fi \
        ;; \
    esac

RUN set -eu; \
    case "${TARGETARCH:-amd64}" in \
      amd64) logos_arch="x86_64" ;; \
      arm64) logos_arch="aarch64" ;; \
      *) echo "Unsupported TARGETARCH: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    install -d /usr/local/bin /tmp/logos-install; \
    cd /tmp/logos-install; \
    for tool in logoscore lgpm lgpd; do \
      case "$tool" in \
        logoscore) repo="logos-logoscore-cli" ;; \
        lgpm) repo="logos-package-manager" ;; \
        lgpd) repo="logos-package-downloader" ;; \
      esac; \
      curl -fsSLO "https://github.com/logos-co/${repo}/releases/download/${LOGOS_TOOLS_VERSION}/${tool}-${logos_arch}-linux.tar.gz"; \
      tar -xzf "${tool}-${logos_arch}-linux.tar.gz"; \
      appimage="${tool}-${logos_arch}.AppImage"; \
      install -d "/opt/logos/appimages/${tool}"; \
      extracted=false; \
      for offset in $(grep -abo 'hsqs' "$appimage" | cut -d: -f1); do \
        rm -rf "/opt/logos/appimages/${tool}"; \
        install -d "/opt/logos/appimages/${tool}"; \
        if unsquashfs -q -o "$offset" -d "/opt/logos/appimages/${tool}" "$appimage" && \
            [ -x "/opt/logos/appimages/${tool}/usr/bin/.${tool}.elf" ]; then \
          extracted=true; \
          break; \
        fi; \
      done; \
      if [ "$extracted" != "true" ]; then \
        echo "Could not extract $appimage" >&2; \
        exit 1; \
      fi; \
    done; \
    rm -rf /tmp/logos-install

RUN for tool in logoscore lgpm lgpd; do \
      elf=".$tool.elf"; \
      printf '%s\n' \
        '#!/usr/bin/env sh' \
        'set -eu' \
        "appdir=\"/opt/logos/appimages/${tool}\"" \
        'export APPDIR="$appdir"' \
        'export LD_LIBRARY_PATH="$appdir/usr/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"' \
        "exec \"\$appdir/usr/bin/${elf}\" \"\$@\"" \
        > "/usr/local/bin/${tool}"; \
      chmod +x "/usr/local/bin/${tool}"; \
    done

RUN logoscore --version >/dev/null && \
    lgpm --version >/dev/null && \
    lgpd --version >/dev/null

RUN set -eu; \
    install -d /tmp/logos-module "${LOGOS_MODULES_DIR}"; \
    cd /tmp/logos-module; \
    lgpd download blockchain_module --version "${BLOCKCHAIN_MODULE_VERSION}" --output ./; \
    lgpm --modules-dir "${LOGOS_MODULES_DIR}" install --file "blockchain_module-${BLOCKCHAIN_MODULE_VERSION}.lgx"; \
    rm -rf /tmp/logos-module

WORKDIR /

ENTRYPOINT ["logoscore"]
