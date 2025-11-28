# cs204-quic
QUIC testbed

Course: [CS 204 - Advanced Computer Networks](https://cs.ucr.edu/~ztan/courses/CS204/F25/index.html)
Instructor: [Prof. Zhaowei Tan](https://cs.ucr.edu/~ztan/)

# Task
- Setup a QUIC testbed to study packet metrics

# Setup
- Clone [aioquic](https://github.com/aiortc/aioquic)
- Run below installs once inside the virtual env:
```sh
brew install openssl

export CFLAGS=-I$(brew --prefix openssl)/include
export LDFLAGS=-L$(brew --prefix openssl)/lib

pip install . dnslib jinja2 starlette wsproto
```


# Test
## Basic
- Ensure you are inside the `aioquic/` directory
- Start server:
```sh
python examples/http3_server.py --certificate tests/ssl_cert.pem --private-key tests/ssl_key.pem
```
- Start client:
```sh
python examples/http3_client.py --ca-certs tests/pycacert.pem https://localhost:4433/
```
## Advanced
- Start server as before
- Run below bash script to vary network conditions using tc/netem
    - ensure you modify experiment parameters before running
```sh
./evaluate.sh
```

## Connection migration tests
- Check the `quiche/` directory
- Coming soon...

## QTB
```sh
# Terminal 1
docker built -t qtb .

docker run -it -p 8888:8888 -v $(pwd):/workspace qtb

jupyter lab --ip=0.0.0.0 --port=8888 --no-browser --allow-root

# Terminal 2
# connect to same container as above
docker exec -it <container_id> bash

python -m qtb.cli create-exps baseline --no-edit

python -m qtb.cli run configs/experiments/baseline.yml

python -m qtb.cli analyze client --log-dir runs/baseline/e0/client/d8ea3f73306782cf.qlog

```
