# cs204-quic
QUIC testbed

Course: [CS 204 - Advanced Computer Networks](https://cs.ucr.edu/~ztan/courses/CS204/F25/index.html)

Instructor: [Prof. Zhaowei Tan](https://cs.ucr.edu/~ztan/)

TA: Yuanhao Chang

# Task
- Setup a QUIC testbed to study packet metrics

# Setup
- Clone this repository https://github.com/bmsohwinc/cs204-quic/tree/quic-migration
- Switch to `quic-migration` branch
```sh
git checkout quic-migration
```
- Enter the `aioquic` directory inside the repo folder
```sh
cd aioquic
```
- Setup Docker on your system

# Execution
- Run below Docker commands
```sh
# Terminal 1
docker build -t qtb .

docker run --cap-add=NET_ADMIN -it -p 8888:8888 -v $(pwd):/workspace qtb

jupyter lab --ip=0.0.0.0 --port=8888 --no-browser --allow-root
```
- Open another terminal, connect to the same Docker container
```sh
# Terminal 2
docker exec -it <container_id> bash

qtb create-exps exp_1 --no-edit

qtb run configs/experiments/exp_1.yml

qtb analyze client --log-dir runs/exp1/e0/client/<LOG_NAME>.qlog

```

# Testing Migration
- Go to `migration` directory under repo
- Create virtual environment
```
python -m venv .venv
```
- install aioquic
```
pip install aioquic
```
- Start server 
```
python run.py --proto quic --mode server --host 10.10.1.1 --port 4433
```
- Start client
```
python run.py --proto quic --mode client --host 10.10.1.1 --port 4433 --out quic_client.log --migrate-at 5
```
- Run both tcp/quic using a single command as above
