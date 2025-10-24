FROM alpine:latest as base
WORKDIR /app

RUN apk add --no-cache python3 py3-pip
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --upgrade pip && pip install requests pydantic dnspython

ADD get_address.py ./get_address.py

FROM base as debug
WORKDIR /app
RUN apk add --no-cache bash bind-tools curl ethtool iputils jq net-tools tcpdump vim wget ws
RUN apk add --no-cache nodejs npm && npm install -g wscat

ENTRYPOINT ["sleep", "infinity"]

FROM base as production
WORKDIR /app
ENTRYPOINT ["python3 /app/get_address.py"]
