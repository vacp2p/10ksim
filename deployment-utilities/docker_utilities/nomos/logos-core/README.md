# Logos Core Nomos Image

This image prebakes the Logos Core prerequisites needed before a Nomos node starts:

- `logoscore`
- `lgpm`
- `lgpd`
- `blockchain_module` installed under `/opt/logos/modules`

The default image includes the `0.2.0` Logos Core CLI tools and the `0.2.1`
`blockchain_module`.

The Dockerfile follows the upstream release flow: download `lgpd`, `lgpm`, and
`logoscore`, download `blockchain_module-0.2.1.lgx`, then install it into
`/opt/logos/modules` with `lgpm`.

The image uses Ubuntu 24.04 because the Logos 0.2.0 AppImages require newer glibc
and libstdc++ symbols than Debian bookworm provides.

## Build AMD64

The default helper builds and pushes `linux/amd64`:

```bash
cd deployment-utilities/docker_utilities/nomos/logos-core

IMAGE=soutullostatus/logos-core-blockchain:v0.2.1 ./build.sh
```

Equivalent explicit command:

```bash
docker buildx build \
  --platform linux/amd64 \
  -t soutullostatus/logos-core-blockchain:v0.2.1 \
  --push \
  .
```

To publish a multi-arch image, override `PLATFORM`:

```bash
PLATFORM=linux/amd64,linux/arm64 IMAGE=soutullostatus/logos-core-blockchain:v0.2.1 ./build.sh
```

If the selected platform includes `linux/amd64`, `build.sh` first checks whether
Docker can run an amd64 Ubuntu container. This matters on ARM laptops because the
Dockerfile runs target-platform commands during the build. If the preflight fails,
install or refresh amd64 emulation and retry:

```bash
docker run --privileged --rm tonistiigi/binfmt --install amd64
```

If the preflight is not appropriate for your Docker setup, set
`SKIP_PREFLIGHT=1`.

## Local Test Build

Docker cannot `--load` a multi-platform image into the local image store. For local
testing, `LOCAL=1` loads only your laptop's native platform. On an ARM64 machine
this selects `linux/arm64`; on an x86_64 machine this selects `linux/amd64`:

```bash
LOCAL=1 IMAGE=soutullostatus/logos-core-blockchain:v0.2.1-arm64 ./build.sh
```

Or explicitly:

```bash
docker buildx build \
  --platform linux/arm64 \
  -t soutullostatus/logos-core-blockchain:v0.2.1-arm64 \
  --load \
  .
```

`build.sh` defaults to `--push` for publish builds and `--load` for `LOCAL=1`
builds. Override that with `OUTPUT` when needed:

```bash
OUTPUT=--load PLATFORM=linux/amd64 IMAGE=soutullostatus/logos-core-blockchain:v0.2.1 ./build.sh
```

## Runtime

The module directory is available as:

```bash
/opt/logos/modules
```

Example startup sequence:

```bash
logoscore -m /opt/logos/modules -D &
logoscore load-module blockchain_module
```
