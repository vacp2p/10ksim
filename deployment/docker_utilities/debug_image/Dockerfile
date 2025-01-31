FROM debian:bookworm-slim

RUN apt update && \
    apt install -y python3 && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir /app
ADD dns_loop.py /app/dns_loop.py
RUN chmod +x /app/dns_loop.py

ENTRYPOINT ["/app/dns_loop.py"]

