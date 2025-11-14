# cs204-quic
QUIC testbed

Course: [CS 204 - Advanced Computer Networks](https://cs.ucr.edu/~ztan/courses/CS204/F25/index.html)
Instructor: [Prof. Zhaowei Tan](https://cs.ucr.edu/~ztan/)

# Task
- Setup a QUIC testbed to study packet metrics

# Setup
- [aioquic](https://github.com/aiortc/aioquic)

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
```sh

```