#!/bin/bash

# Automated TCP/TLS Load Test Runner
# Usage: ./run_load_test.sh <duration> <rps> <output_file>

set -e  # Exit on error

DURATION=${1:-10}
RPS=${2:-5}
OUTPUT=${3:-metrics.json}

echo "=========================================="
echo "TCP/TLS Load Test"
echo "=========================================="
echo "Duration: ${DURATION}s"
echo "Target RPS: ${RPS}"
echo "Output: ${OUTPUT}"
echo ""

# Check if certificates exist
if [ ! -f cert.pem ] || [ ! -f key.pem ]; then
    echo "Generating self-signed certificate..."
    openssl req -x509 -newkey rsa:2048 -nodes \
        -keyout key.pem -out cert.pem -days 365 \
        -subj '/CN=localhost' 2>/dev/null
    echo "✓ Certificate generated"
    echo ""
fi

# Start server in background
echo "Starting TLS server..."
python3 server-2.py &
SERVER_PID=$!

# Give server time to start
sleep 2

# Trap to ensure cleanup
cleanup() {
    echo ""
    echo "Cleaning up..."
    kill $SERVER_PID 2>/dev/null || true
    wait $SERVER_PID 2>/dev/null || true
    echo "✓ Server stopped"
}
trap cleanup EXIT

# Check if server started
if ! kill -0 $SERVER_PID 2>/dev/null; then
    echo "ERROR: Server failed to start"
    exit 1
fi
echo "✓ Server running (PID: $SERVER_PID)"
echo ""

# Run load test
echo "Running load test..."
echo ""
python3 client-2.py --duration $DURATION --load-rps $RPS --filename $OUTPUT

echo ""
echo "=========================================="
echo "Test complete! Check ${OUTPUT} for results"
echo "=========================================="
