"""
QUIC Connection Migration vs TCP/TLS Reconnection Test

Requirements:
pip install aioquic
"""

import asyncio
import time
import json
import ssl
import socket
from typing import List, Tuple
from dataclasses import dataclass
from statistics import mean, stdev

from aioquic.asyncio import QuicConnectionProtocol, serve
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import StreamDataReceived
    
# ============================================================================
# CONSTANTS
# ============================================================================
SERVER_COUNTER = 20


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class CounterData:
    counter: int
    timestamp: float

@dataclass
class TestResult:
    protocol: str
    run_number: int
    disconnect_time: float
    reconnect_time: float
    latency_ms: float
    missed_counters: int

# ============================================================================
# TCP/TLS SERVER
# ============================================================================

class TCPServer:
    def __init__(self, host='127.0.0.1', port=4433):
        self.host = host
        self.port = port
        self.counter = 0
        self.running = False
        
    async def handle_client(self, reader, writer):
        """Handle a single client connection"""
        print(f"[TCP Server] Client connected")
        # self.counter = 0
        self.running = True
        
        try:
            while self.running and self.counter < SERVER_COUNTER:
                # Send counter and timestamp
                data = json.dumps({
                    'counter': self.counter,
                    'timestamp': time.time()
                }) + '\n'
                
                writer.write(data.encode())
                await writer.drain()
                
                self.counter += 1
                await asyncio.sleep(0.1)  # 100ms intervals
                
        except (ConnectionResetError, BrokenPipeError):
            print(f"[TCP Server] Client disconnected at counter {self.counter}")
        finally:
            self.running = False
            writer.close()
            await writer.wait_closed()
    
    async def start(self):
        """Start TCP server with TLS"""
        # Create self-signed cert context for testing
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain('cert.pem', 'key.pem')
        
        # For production, load actual certificates:
        # ssl_context.load_cert_chain('cert.pem', 'key.pem')
        
        server = await asyncio.start_server(
            self.handle_client,
            self.host,
            self.port,
            ssl=ssl_context
        )
        
        print(f"[TCP Server] Listening on {self.host}:{self.port}")
        async with server:
            await server.serve_forever()

# ============================================================================
# TCP/TLS CLIENT
# ============================================================================

class TCPClient:
    def __init__(self, host='127.0.0.1', port=4433):
        self.host = host
        self.port = port
        self.data_log: List[CounterData] = []
        
    async def run_test(self, disconnect_at_counter=5) -> TestResult:
        """Run a single test with automated disconnection"""
        self.data_log = []
        disconnect_time = None
        reconnect_time = None
        
        # Create SSL context
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        # First connection
        reader, writer = await asyncio.open_connection(
            self.host, self.port, ssl=ssl_context
        )
        
        print("[TCP Client] Connected")
        
        try:
            buffer = ""
            while True:
                chunk = await reader.read(1024)
                if not chunk:
                    break
                    
                buffer += chunk.decode()
                
                # Process complete lines
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    data = json.loads(line)
                    
                    counter_data = CounterData(
                        counter=data['counter'],
                        timestamp=data['timestamp']
                    )
                    self.data_log.append(counter_data)
                    print(f"[TCP Client] Received counter {counter_data.counter} at {counter_data.timestamp}")
                    
                    # Trigger disconnection
                    if counter_data.counter == disconnect_at_counter and disconnect_time is None:
                        disconnect_time = time.time()
                        print(f"[TCP Client] Disconnecting at counter {disconnect_at_counter}")
                        writer.close()
                        await writer.wait_closed()
                        
                        # Wait a bit to ensure server detects disconnection
                        await asyncio.sleep(0.1)
                        
                        # Reconnect
                        print("[TCP Client] Reconnecting...")
                        reader, writer = await asyncio.open_connection(
                            self.host, self.port, ssl=ssl_context
                        )
                        reconnect_time = time.time()
                        print("[TCP Client] Reconnected")
                        buffer = ""  # Reset buffer
                        
                    if counter_data.counter >= (SERVER_COUNTER - 1):
                        writer.close()
                        await writer.wait_closed()
                        break
                        
        except Exception as e:
            print(f"[TCP Client] Error: {e}")
        
        # Calculate metrics
        latency_ms = (reconnect_time - disconnect_time) * 1000 if disconnect_time and reconnect_time else 0
        
        # Find missed counters
        counters = [d.counter for d in self.data_log]
        missed = 0
        for i in range(len(counters) - 1):
            gap = counters[i + 1] - counters[i] - 1
            if gap > 0:
                missed += gap
        
        return TestResult(
            protocol='TCP/TLS',
            run_number=0,
            disconnect_time=disconnect_time,
            reconnect_time=reconnect_time,
            latency_ms=latency_ms,
            missed_counters=missed
        )

# ============================================================================
# TEST ORCHESTRATION
# ============================================================================

async def run_tcp_tests(num_runs=20):
    """Run multiple TCP/TLS tests"""
    results = []
    
    for run in range(num_runs):
        print(f"\n{'='*60}\nTCP/TLS Test Run {run + 1}/{num_runs}\n{'='*60}")
        
        # Start server in background
        server = TCPServer()
        server_task = asyncio.create_task(server.start())
        
        await asyncio.sleep(0.5)  # Let server start
        
        # Run client test
        client = TCPClient()
        result = await client.run_test(disconnect_at_counter=5)
        result.run_number = run + 1
        results.append(result)
        
        print(f"Latency: {result.latency_ms:.2f}ms, Missed counters: {result.missed_counters}")
        
        # Stop server
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass
        
        await asyncio.sleep(0.5)  # Cooldown between runs
    
    return results

def print_summary(results: List[TestResult]):
    """Print summary statistics"""
    latencies = [r.latency_ms for r in results]
    
    print(f"\n{'='*60}")
    print(f"SUMMARY - {results[0].protocol}")
    print(f"{'='*60}")
    print(f"Total runs: {len(results)}")
    print(f"Average latency: {mean(latencies):.2f}ms")
    print(f"Std deviation: {stdev(latencies):.2f}ms" if len(latencies) > 1 else "N/A")
    print(f"Min latency: {min(latencies):.2f}ms")
    print(f"Max latency: {max(latencies):.2f}ms")
    print(f"Average missed counters: {mean([r.missed_counters for r in results]):.2f}")

# ============================================================================
# MAIN
# ============================================================================

async def main():
    """Run comparison tests"""
    print("QUIC Connection Migration vs TCP/TLS Reconnection Test")
    print("="*60)
    
    # Run TCP/TLS tests
    tcp_results = await run_tcp_tests(num_runs=5)  # Start with 5 for testing
    print_summary(tcp_results)
    
    # QUIC tests would go here when fully implemented
    print("\n[INFO] QUIC tests require full aioquic client implementation")

if __name__ == '__main__':
    asyncio.run(main())
