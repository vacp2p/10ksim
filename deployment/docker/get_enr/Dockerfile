FROM alpine:latest

# Update the package repository and install bind-tools and wget
RUN apk update && \
    apk add bind-tools bash curl && \
    # Create /app directory
    mkdir /app

ADD getenr.sh /app/getenr.sh

RUN chmod +x /app/getenr.sh

ENTRYPOINT ["/app/getenr.sh"]
