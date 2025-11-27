FROM python:3.12-slim

# Install just enough for tc/netem + basic net tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    iproute2 \
    iputils-ping \
    net-tools \
    build-essential \
    libssl-dev \
    nano \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

