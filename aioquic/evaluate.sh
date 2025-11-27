#!/usr/bin/env bash
set -euo pipefail

URL="https://127.0.0.1:4433/"
DURATION=60

# TODO: adjust these to match your client
COMMON_CLIENT_ARGS="--load-rps 100 --load-duration ${DURATION} --insecure"
# If you use RPS-based generator, add e.g. "--load-rps 100" above.

LOG_DIR="pkt_logs/$(date +'%Y-%m-%d_%H-%M-%S')"
mkdir -p "$LOG_DIR"

if command -v sudo >/dev/null 2>&1; then
    SUDO=sudo
else
    SUDO=
fi

reset_qdisc() {
    echo "  [tc] Resetting qdisc on lo"
    $SUDO tc qdisc del dev lo root 2>/dev/null || true
}

run_experiment() {
    local id="$1"
    local label="$2"
    local netem_args="$3"   # e.g. 'delay 25ms loss 0.5%'
    local rate="$4"         # e.g. '20mbit' or empty for baseline

    echo
    echo "=============================="
    echo "Running experiment ${id}: ${label}"
    echo "=============================="

    reset_qdisc

    if [[ -z "${netem_args}" && -z "${rate}" ]]; then
        echo "  [tc] Baseline: no shaping"
    else
        echo "  [tc] Adding netem (${netem_args})"
        $SUDO tc qdisc add dev lo root handle 1: netem ${netem_args}

        if [[ -n "${rate}" ]]; then
            echo "  [tc] Adding TBF rate limit (${rate})"
            $SUDO tc qdisc add dev lo parent 1:1 handle 2: tbf \
                rate "${rate}" burst 32kbit latency 400ms
        fi

        echo "  [tc] Current qdisc:"
        tc qdisc show dev lo
    fi

    ts=$(date +"%Y%m%d-%H%M%S")
    qlog_name="EX_${id}_client_${ts}_log.json"
    qlog_path="${LOG_DIR}/${qlog_name}"

    echo "  [client] Starting client, qlog -> ${qlog_path}"
    python3 examples/http3_client.py \
        "${URL}" \
        ${COMMON_CLIENT_ARGS} \
        --quic-log "/workspace/runs/test/"
        # --qlog-filename "${qlog_path}"

    echo "  [client] Done. qlog stored."

    # reset so next experiment starts clean
    reset_qdisc
}

### Define experiments here ###

# N, Label, netem_args, rate
run_experiment 0 "Baseline: no tc" "" ""

# run_experiment 1 "RTT=10ms, 0% loss, 20Mbit" "delay 5ms" "20mbit"
# run_experiment 2 "RTT=10ms, 0.5% loss, 20Mbit" "delay 5ms" "20mbit"
# run_experiment 3 "RTT=10ms, 2% loss, 20Mbit" "delay 5ms" "20mbit"

# run_experiment 4 "RTT=10ms, 0% loss, 10Mbit" "delay 5ms" "10mbit"
# run_experiment 5 "RTT=10ms, 0.5% loss, 10Mbit" "delay 5ms" "10mbit"
# run_experiment 6 "RTT=10ms, 2% loss, 10Mbit" "delay 5ms" "10mbit"

# run_experiment 7 "RTT=50ms, 0% loss, 20Mbit" "delay 25ms" "20mbit"
# run_experiment 8 "RTT=50ms, 0.5% loss, 20Mbit" "delay 25ms" "20mbit"
# run_experiment 9 "RTT=50ms, 2% loss, 20Mbit" "delay 25ms" "20mbit"

# run_experiment 10 "RTT=50ms, 0% loss, 10Mbit" "delay 25ms" "10mbit"
# run_experiment 11 "RTT=50ms, 0.5% loss, 10Mbit" "delay 25ms" "10mbit"
# run_experiment 12 "RTT=50ms, 2% loss, 10Mbit" "delay 25ms" "10mbit"

# run_experiment 13 "RTT=100ms, 0% loss, 20Mbit" "delay 50ms" "20mbit"
# run_experiment 14 "RTT=100ms, 0.5% loss, 20Mbit" "delay 50ms" "20mbit"
# run_experiment 15 "RTT=100ms, 2% loss, 20Mbit" "delay 50ms" "20mbit"

# run_experiment 16 "RTT=100ms, 0% loss, 10Mbit" "delay 50ms" "10mbit"
# run_experiment 17 "RTT=100ms, 0.5% loss, 10Mbit" "delay 50ms" "10mbit"
# run_experiment 18 "RTT=100ms, 2% loss, 10Mbit" "delay 50ms" "10mbit"


echo
echo "All experiments finished."
reset_qdisc
