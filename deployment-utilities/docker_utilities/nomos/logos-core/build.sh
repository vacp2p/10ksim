#!/usr/bin/env bash
set -euo pipefail

IMAGE="${IMAGE:-soutullostatus/logos-core-blockchain:v0.2.1}"

if [ "${LOCAL:-0}" = "1" ]; then
  case "$(uname -m)" in
    arm64|aarch64) PLATFORM="${PLATFORM:-linux/arm64}" ;;
    x86_64|amd64) PLATFORM="${PLATFORM:-linux/amd64}" ;;
    *) echo "Unsupported local architecture: $(uname -m)" >&2; exit 1 ;;
  esac
  OUTPUT="${OUTPUT:---load}"
else
  PLATFORM="${PLATFORM:-linux/amd64}"
  OUTPUT="${OUTPUT:---push}"
fi

if [ "${SKIP_PREFLIGHT:-0}" != "1" ] && printf '%s' "${PLATFORM}" | grep -q 'linux/amd64'; then
  if ! docker run --rm --platform linux/amd64 ubuntu:24.04 uname -m >/dev/null 2>&1; then
    cat >&2 <<'EOF'
Cannot run linux/amd64 containers from this Docker setup.

linux/amd64 builds from an ARM laptop still require Docker to support linux/amd64
container execution because this Dockerfile runs target-platform commands.

Install/refresh emulation, then retry:

  docker run --privileged --rm tonistiigi/binfmt --install amd64

If that is not allowed on this machine, build the amd64 image on an amd64 host or
use the cluster kaniko builder for the amd64 publish.
EOF
    exit 1
  fi
fi

docker buildx build \
  --platform "${PLATFORM}" \
  -t "${IMAGE}" \
  "${OUTPUT}" \
  .
