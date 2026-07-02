#!/usr/bin/env bash
# Verify a freshly-built image's binary contains (and lacks) expected markers,
# before you deploy it -- so a stale or mis-built binary can't silently burn a
# large run (see the June 2026 wasted 1000-node campaign).
#
# Runs an in-cluster Job on an amd64 lab node (same pattern as build-image.sh):
# it greps the image's binary for each required / forbidden marker string. The
# Job succeeds only if every assertion holds; otherwise this script exits non-zero.
# grep -a is used, so no binutils/strings needed in the image.
#
# Usage:
#   deployment-utilities/docker_utilities/kaniko/verify-image.sh <image> \
#     [--binary PATH] [--require SYMS] [--forbid SYMS]
#     --binary PATH   binary to inspect inside the image (default /node/main)
#     --require SYMS   comma-separated markers that MUST be present
#     --forbid  SYMS   comma-separated markers that MUST be absent
#
# Example (a ping-off, quic-enabled test node):
#   .../kaniko/verify-image.sh radiken/dst-test-node-regression:v2.1.0-rerun2 \
#     --require lsquic --forbid pingMeshLoop
set -euo pipefail

KC="${KC:-${KUBECONFIG:-$HOME/.kube/config}}"
BUILD_NS="${BUILD_NS:-zerotesting-build}"
EXCLUDE_NODE="${EXCLUDE_NODE:-node-01.ih-eu-mda1.misc.vaclab}"
DOCKER_SECRET="${DOCKER_SECRET:-dockerhub-creds}"

BINARY="/node/main"; REQUIRE=""; FORBID=""
if [ "$#" -lt 1 ]; then sed -n '2,20p' "$0"; exit 1; fi
IMAGE="$1"; shift
while [ "$#" -gt 0 ]; do
  case "$1" in
    --binary)  BINARY="$2";  shift 2;;
    --require) REQUIRE="$2"; shift 2;;
    --forbid)  FORBID="$2";  shift 2;;
    *) echo "unknown arg: $1" >&2; exit 1;;
  esac
done
if [ -z "$REQUIRE" ] && [ -z "$FORBID" ]; then
  echo "nothing to check: pass --require and/or --forbid" >&2; exit 1
fi

# comma -> space for the in-pod shell loops (markers must be single tokens)
REQ="$(echo "$REQUIRE" | tr ',' ' ')"
FRB="$(echo "$FORBID"  | tr ',' ' ')"

tagpart="$(echo "${IMAGE##*/}" | tr '[:upper:]' '[:lower:]' | tr ':._/' '----' | sed 's/[^a-z0-9-]//g')"
JOB="$(echo "verify-${tagpart}" | cut -c1-60)"

echo ">>> verifying $IMAGE (binary=$BINARY)"
echo "    require=[$REQUIRE] forbid=[$FORBID] job=$JOB ns=$BUILD_NS"

render() {
cat <<YAML
apiVersion: batch/v1
kind: Job
metadata:
  name: ${JOB}
  namespace: ${BUILD_NS}
  labels: { app: image-verify }
spec:
  backoffLimit: 0
  ttlSecondsAfterFinished: 3600
  template:
    metadata:
      labels: { app: image-verify, verify: ${JOB} }
    spec:
      restartPolicy: Never
      imagePullSecrets: [ { name: ${DOCKER_SECRET} } ]
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
              - matchExpressions:
                  - key: kubernetes.io/hostname
                    operator: NotIn
                    values: [ ${EXCLUDE_NODE} ]
      containers:
        - name: verify
          image: ${IMAGE}
          imagePullPolicy: Always
          command: ["/bin/sh", "-c"]
          args:
            - |
              bin="${BINARY}"; rc=0
              if [ ! -f "\$bin" ]; then echo "FAIL: binary \$bin not found in image"; exit 2; fi
              for s in ${REQ}; do
                if grep -aq -- "\$s" "\$bin"; then echo "OK  present: \$s"; else echo "FAIL missing: \$s"; rc=1; fi
              done
              for s in ${FRB}; do
                if grep -aq -- "\$s" "\$bin"; then echo "FAIL present(forbidden): \$s"; rc=1; else echo "OK  absent : \$s"; fi
              done
              echo "---"; [ \$rc -eq 0 ] && echo "VERIFY PASS" || echo "VERIFY FAIL"
              exit \$rc
          resources:
            requests: { cpu: "1", memory: "256Mi" }
            limits:   { cpu: "2", memory: "1Gi" }
YAML
}

render | kubectl --kubeconfig "$KC" delete -f - --ignore-not-found >/dev/null 2>&1 || true
render | kubectl --kubeconfig "$KC" apply -f -

echo ">>> streaming verify output"
kubectl --kubeconfig "$KC" -n "$BUILD_NS" wait --for=condition=Ready pod -l "verify=${JOB}" --timeout=120s >/dev/null 2>&1 || true
kubectl --kubeconfig "$KC" -n "$BUILD_NS" logs -f -l "verify=${JOB}" --tail=-1 2>/dev/null || true

# Determine result from Job status (logs -f returns once the pod exits).
for _ in $(seq 1 15); do
  sc="$(kubectl --kubeconfig "$KC" -n "$BUILD_NS" get "job/${JOB}" -o jsonpath='{.status.succeeded}' 2>/dev/null || true)"
  fc="$(kubectl --kubeconfig "$KC" -n "$BUILD_NS" get "job/${JOB}" -o jsonpath='{.status.failed}'    2>/dev/null || true)"
  [ "$sc" = "1" ] && { echo "VERIFY OK: $IMAGE"; exit 0; }
  if [ -n "$fc" ] && [ "$fc" != "0" ]; then
    echo "VERIFY FAILED: $IMAGE"
    kubectl --kubeconfig "$KC" -n "$BUILD_NS" describe "job/${JOB}" | tail -20
    exit 1
  fi
  sleep 2
done
echo "VERIFY: could not determine result for $IMAGE" >&2; exit 2
