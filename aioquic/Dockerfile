FROM python:3.12-slim

# Install just enough for tc/netem + basic net tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    iproute2 \
    iputils-ping \
    net-tools \
    build-essential \
    libssl-dev \
    nano \
    procps \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY . /workspace

# For aioquic
RUN pip install dnslib jinja2 starlette wsproto

# For qtb
RUN pip install -e .

RUN pip install pandas numpy matplotlib nbformat pyyaml jupyterlab

EXPOSE 8888

CMD ["/bin/bash"]
