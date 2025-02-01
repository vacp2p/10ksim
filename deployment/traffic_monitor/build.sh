# docker buildx create --name multiarch --use

docker buildx build --platform linux/amd64,linux/arm64 \
  -t zorlin/traffic-monitor:latest \
  --push .