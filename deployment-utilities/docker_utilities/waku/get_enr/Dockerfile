FROM alpine:latest

RUN apk update && \
    apk add bind-tools bash curl && \
    mkdir /app

ADD getenr.sh /app/getenr.sh

RUN chmod +x /app/getenr.sh

ENTRYPOINT ["/app/getenr.sh"]
