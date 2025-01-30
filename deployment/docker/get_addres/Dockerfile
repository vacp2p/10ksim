FROM alpine:latest

# Update the package repository and install bind-tools and wget
RUN apk update && \
    apk add bind-tools bash curl && \
    # Create /app directory
    mkdir /app

ADD getaddress.sh /app/getaddress.sh

RUN chmod +x /app/getaddress.sh

ENTRYPOINT ["/app/getaddress.sh"]
