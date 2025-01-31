FROM alpine:latest

RUN apk update && \
    apk add bind-tools bash curl && \
    mkdir /app

ADD getaddress.sh /app/getaddress.sh

RUN chmod +x /app/getaddress.sh

ENTRYPOINT ["/app/getaddress.sh"]
