docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t docker.io/<your_registry>/publisher:v1.1.0 \
  --push \
  --no-cache \
  .