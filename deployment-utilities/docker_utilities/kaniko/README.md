## Fast native amd64 image builds (kaniko on the lab cluster)

Build any `linux/amd64` image **natively on an amd64 lab node** instead of cross-compiling
under QEMU on the Apple-Silicon Macs. QEMU builds are slow and have stalled on machine
sleep and Docker-Desktop cache eviction; kaniko-on-cluster is native, runs unattended, and
uses a durable registry-backed cache. Generalised from the Shadow base-image build so it
works for any repo/Dockerfile, not just the test nodes.

### Usage

```
deployment-utilities/docker_utilities/kaniko/build-image.sh \
  <repo> <git-ref> <context-subpath> <dockerfile> <destination> [cache-repo]
```

- `repo`            – GitHub `org/name` (e.g. `vacp2p/dst-libp2p-test-node`)
- `git-ref`         – full ref: `refs/heads/<branch>`, `refs/tags/<tag>`, or a commit SHA
- `context-subpath` – build-context dir within the repo
- `dockerfile`      – Dockerfile name (relative to the subpath)
- `destination`     – `repo/image:tag` to push
- `cache-repo`      – optional; defaults to `<dest-without-tag>-cache`

Example — a nim test node from a fix branch:
```
.../kaniko/build-image.sh vacp2p/dst-libp2p-test-node refs/heads/alan/regression-2678 \
  nim-test-node/regression Dockerfile_amd64 \
  radiken/dst-test-node-regression:v2.1.0-2678
```

The script applies a kaniko Job, streams its logs, and waits for completion. Env overrides:
`KC` (kubeconfig, defaults to `$KUBECONFIG` or `~/.kube/config`), `BUILD_NS`, `EXCLUDE_NODE`.

### Builds from git, not your working tree

The context is cloned from `<git-ref>` — **uncommitted local edits are not included.** Commit
and push first. This is also a feature: each build is a reproducible named ref, so concurrent
runs (e.g. two people pinning different nim-libp2p commits) don't stomp each other's files the
way local builds do.

### Parallel builds

Each call is an independent Job named `build-<dest-tag>`, scheduled across the workers (each
~128 cores; a build requests 8). Distinct destination tags run in parallel; re-running the same
tag replaces its job. Just background several invocations.

### One-time setup (per cluster)

```bash
kubectl create namespace zerotesting-build
DCJ=$(kubectl -n <ns-with-creds> get secret dockerhub-creds -o jsonpath='{.data.\.dockerconfigjson}' | base64 -d)
echo "$DCJ" > /tmp/dcj.json
kubectl -n zerotesting-build create secret generic dockerhub-creds \
  --type=kubernetes.io/dockerconfigjson --from-file=.dockerconfigjson=/tmp/dcj.json
rm /tmp/dcj.json
```

### Verifying the right thing got built

A registry cache can serve a stale layer, so for compiled nodes confirm the binary really
contains the intended commit before trusting a run — pull it and grep for a symbol unique to
that commit:
```bash
docker create --name t <image>; docker cp t:/node/main /tmp/main; docker rm t
strings /tmp/main | grep -c <symbol-unique-to-the-commit>
```
