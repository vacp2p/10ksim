#!/usr/bin/env bash
# Native amd64 image builds on the lab cluster via kaniko.
#
# Why: building linux/amd64 images on Apple-Silicon Macs cross-compiles under QEMU
# emulation -- slow, and long Nim/Shadow compiles stall on machine sleep / Docker
# cache eviction. Kaniko runs ON an amd64 lab node, so the build is native, runs
# unattended, caches to a registry repo (durable), and several can run in parallel.
#
# Usage:
#   deployment-utilities/docker_utilities/kaniko/build-image.sh \
#     <repo> <git-ref> <context-subpath> <dockerfile> <destination> [cache-repo]
#
# Example (a nim test node from a branch):
#   .../kaniko/build-image.sh vacp2p/dst-libp2p-test-node refs/heads/alan/regression-2678 \
#     nim-test-node/regression Dockerfile_amd64 radiken/dst-test-node-regression:v2.1.0-2678
#
# IMPORTANT: kaniko builds from the GIT ref, NOT your local working tree -- commit and
# push first. <git-ref> is a full ref: refs/heads/<branch>, refs/tags/<tag>, or a SHA.
#
# Prereqs (one-time): namespace $BUILD_NS with a `dockerhub-creds` dockerconfigjson
# secret -- see README.md.
set -euo pipefail

KC="${KC:-${KUBECONFIG:-$HOME/.kube/config}}"
BUILD_NS="${BUILD_NS:-zerotesting-build}"
# Avoid the master/monitoring node (it interferes with workloads).
EXCLUDE_NODE="${EXCLUDE_NODE:-node-01.ih-eu-mda1.misc.vaclab}"

if [ "$#" -lt 5 ]; then
  sed -n '2,18p' "$0"; exit 1
fi
REPO="$1"; GIT_REF="$2"; SUBPATH="$3"; DOCKERFILE="$4"; DESTINATION="$5"
CACHE_REPO="${6:-${DESTINATION%%:*}-cache}"

# k8s-safe Job name derived from the destination image:tag (distinct tags -> distinct
# jobs run in parallel; re-running the same tag replaces its job).
tagpart="$(echo "${DESTINATION##*/}" | tr '[:upper:]' '[:lower:]' | tr ':._/' '----' | sed 's/[^a-z0-9-]//g')"
BUILD_NAME="$(echo "build-${tagpart}" | cut -c1-60)"

echo ">>> building $DESTINATION"
echo "    repo=$REPO ref=$GIT_REF subpath=$SUBPATH dockerfile=$DOCKERFILE"
echo "    job=$BUILD_NAME ns=$BUILD_NS cache=$CACHE_REPO"

render() {
cat <<YAML
apiVersion: batch/v1
kind: Job
metadata:
  name: ${BUILD_NAME}
  namespace: ${BUILD_NS}
  labels: { app: kaniko-build }
spec:
  backoffLimit: 0
  ttlSecondsAfterFinished: 86400
  template:
    metadata:
      labels: { app: kaniko-build, build: ${BUILD_NAME} }
    spec:
      restartPolicy: Never
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
              - matchExpressions:
                  - key: kubernetes.io/hostname
                    operator: NotIn
                    values: [ ${EXCLUDE_NODE} ]
      containers:
        - name: kaniko
          image: gcr.io/kaniko-project/executor:v1.23.2
          args:
            - "--context=git://github.com/${REPO}.git#${GIT_REF}"
            - "--context-sub-path=${SUBPATH}"
            - "--dockerfile=${DOCKERFILE}"
            - "--destination=${DESTINATION}"
            - "--cache=true"
            - "--cache-repo=${CACHE_REPO}"
            - "--snapshot-mode=redo"
            - "--use-new-run"
          volumeMounts:
            - { name: docker-config, mountPath: /kaniko/.docker }
          resources:
            requests: { cpu: "8", memory: "8Gi" }
            limits: { cpu: "32", memory: "16Gi" }
      volumes:
        - name: docker-config
          secret:
            secretName: dockerhub-creds
            items:
              - { key: .dockerconfigjson, path: config.json }
YAML
}

render | kubectl --kubeconfig "$KC" delete -f - --ignore-not-found >/dev/null 2>&1 || true
render | kubectl --kubeconfig "$KC" apply -f -

echo ">>> waiting for build pod, then streaming logs (Ctrl-C detaches; build keeps running)"
kubectl --kubeconfig "$KC" -n "$BUILD_NS" wait --for=condition=Ready pod -l "build=${BUILD_NAME}" --timeout=180s || true
kubectl --kubeconfig "$KC" -n "$BUILD_NS" logs -f -l "build=${BUILD_NAME}" --tail=-1 || true

echo ">>> waiting for job completion"
if kubectl --kubeconfig "$KC" -n "$BUILD_NS" wait --for=condition=complete --timeout=1800s "job/${BUILD_NAME}"; then
  echo "BUILD COMPLETE: $DESTINATION"
else
  echo "BUILD FAILED or TIMED OUT: $DESTINATION"
  kubectl --kubeconfig "$KC" -n "$BUILD_NS" describe "job/${BUILD_NAME}" | tail -25
  exit 1
fi
