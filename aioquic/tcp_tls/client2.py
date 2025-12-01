import asyncio
import ssl
import time
import argparse
import json
import subprocess
import re

HOST = "127.0.0.1"
PORT = 8443

class MetricsCollector:
    def __init__(self):
        self.metrics = []
        self.bytes_sent = 0
        self.bytes_received = 0
        self.start_time = time.time()
        self.last_sample_time = self.start_time
        self.last_bytes_sent = 0
        self.last_bytes_received = 0
    
    def record_request(self, sent_bytes, received_bytes):
        """Record bytes for a completed request"""
        self.bytes_sent += sent_bytes
        self.bytes_received += received_bytes
    
    def sample(self, cwnd=None, rtt=None):
        """Take a throughput sample"""
        now = time.time()
        elapsed = now - self.last_sample_time
        
        if elapsed > 0:
            # Bytes per second
            tx_throughput = (self.bytes_sent - self.last_bytes_sent) / elapsed
            rx_throughput = (self.bytes_received - self.last_bytes_received) / elapsed
            
            self.metrics.append({
                'timestamp': now - self.start_time,
                'tx_throughput_bps': tx_throughput,
                'rx_throughput_bps': rx_throughput,
                'total_bytes_sent': self.bytes_sent,
                'total_bytes_received': self.bytes_received,
                'cwnd': cwnd,
                'rtt_ms': rtt  # RTT in milliseconds
            })
            
            self.last_sample_time = now
            self.last_bytes_sent = self.bytes_sent
            self.last_bytes_received = self.bytes_received
    
    def save(self, filename):
        """Save metrics to JSON file"""
        with open(filename, 'w') as f:
            json.dump(self.metrics, f, indent=2)
        print(f"\n✓ Metrics saved to {filename}")
        print(f"  Total samples: {len(self.metrics)}")
        print(f"  Total bytes sent: {self.bytes_sent:,}")
        print(f"  Total bytes received: {self.bytes_received:,}")
        
        # Show cwnd stats
        cwnd_values = [m['cwnd'] for m in self.metrics if m['cwnd'] is not None]
        if cwnd_values:
            print(f"  CWND samples captured: {len(cwnd_values)}/{len(self.metrics)}")
            print(f"  CWND range: {min(cwnd_values)} - {max(cwnd_values)}")
        else:
            print(f"  CWND samples captured: 0 (connection may be too fast)")

async def get_local_port(writer):
    """Get the local port of the TCP connection"""
    sock = writer.get_extra_info('socket')
    if sock:
        return sock.getsockname()[1]
    return None

async def monitor_cwnd(local_port_container, collector, duration):
    """
    Background task that monitors TCP cwnd using 'ss -ti'
    Samples every 0.1 seconds for better capture rate
    """
    cwnd_pattern = re.compile(r'cwnd:(\d+)')
    rtt_pattern = re.compile(r'rtt:([\d.]+)')
    end_time = time.time() + duration
    
    while time.time() < end_time:
        try:
            local_port = local_port_container.get('port')
            
            if local_port:
                # Monitor the specific connection by local port
                result = subprocess.run(
                    ['ss', '-ti', f'sport = :{local_port}'],
                    capture_output=True,
                    text=True,
                    timeout=0.5
                )
                
                # Parse cwnd and rtt from output
                cwnd = None
                rtt = None
                
                cwnd_match = cwnd_pattern.search(result.stdout)
                if cwnd_match:
                    cwnd = int(cwnd_match.group(1))
                
                rtt_match = rtt_pattern.search(result.stdout)
                if rtt_match:
                    rtt = float(rtt_match.group(1))
                
                collector.sample(cwnd=cwnd, rtt=rtt)
            else:
                # No connection yet
                collector.sample(cwnd=None, rtt=None)
            
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            collector.sample(cwnd=None, rtt=None)
        
        await asyncio.sleep(0.1)  # Sample more frequently for better resolution

async def read_http_response(reader):
    """
    Read a complete HTTP/1.1 response
    Handles Content-Length properly
    """
    # Read headers
    headers_data = b''
    while b'\r\n\r\n' not in headers_data:
        chunk = await reader.read(1024)
        if not chunk:
            break
        headers_data += chunk
    
    # Split headers and any body data already read
    headers_part, _, body_start = headers_data.partition(b'\r\n\r\n')
    
    # Parse Content-Length
    content_length = 0
    for line in headers_part.split(b'\r\n'):
        if line.lower().startswith(b'content-length:'):
            content_length = int(line.split(b':')[1].strip())
            break
    
    # Read remaining body
    body_data = body_start
    while len(body_data) < content_length:
        chunk = await reader.read(content_length - len(body_data))
        if not chunk:
            break
        body_data += chunk
    
    return headers_data

async def send_request(reader, writer, collector, request_num):
    """Send a single HTTP request on persistent connection"""
    try:
        request = (
            "GET / HTTP/1.1\r\n"
            "Host: localhost\r\n"
            "Connection: keep-alive\r\n"  # KEEP CONNECTION ALIVE
            "\r\n"
        )
        request_bytes = request.encode("ascii")
        
        writer.write(request_bytes)
        await writer.drain()
        
        # Read complete response
        response = await read_http_response(reader)
        
        # Record actual bytes
        collector.record_request(len(request_bytes), len(response))
        
        return True
        
    except Exception as e:
        print(f"Request {request_num} failed: {e}")
        return False

async def load_generator(duration, load_rps, collector, local_port_container):
    """
    Generate load at specified RPS using a PERSISTENT connection
    """
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    
    interval = 1.0 / load_rps
    end_time = time.time() + duration
    
    request_count = 0
    success_count = 0
    
    print(f"Starting load generation: {load_rps} RPS for {duration}s")
    print(f"Request interval: {interval:.3f}s")
    print(f"Using PERSISTENT connection (HTTP/1.1 keep-alive)")
    
    # Establish ONE persistent connection
    try:
        reader, writer = await asyncio.open_connection(
            HOST, PORT, ssl=ssl_ctx, server_hostname="localhost"
        )
        
        # Get local port for monitoring
        local_port = await get_local_port(writer)
        if local_port:
            local_port_container['port'] = local_port
            print(f"Connected on local port: {local_port}")
        
        ssl_obj = writer.get_extra_info("ssl_object")
        print(f"TLS: {ssl_obj.version()}, Cipher: {ssl_obj.cipher()[0]}")
        print()
        
        # Send requests on the same connection
        while time.time() < end_time:
            request_start = time.time()
            
            success = await send_request(reader, writer, collector, request_count + 1)
            if success:
                success_count += 1
            request_count += 1
            
            # Maintain target RPS
            elapsed = time.time() - request_start
            sleep_time = max(0, interval - elapsed)
            
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
            
            # Progress indicator
            if request_count % 10 == 0:
                print(f"  Sent {request_count} requests ({success_count} successful)")
        
        # Close connection gracefully
        writer.close()
        await writer.wait_closed()
        
    except Exception as e:
        print(f"Connection error: {e}")
    
    print(f"\nLoad generation complete:")
    print(f"  Total requests: {request_count}")
    print(f"  Successful: {success_count}")
    print(f"  Failed: {request_count - success_count}")

async def main():
    parser = argparse.ArgumentParser(description='TCP/TLS Load Generator with Metrics')
    parser.add_argument('--duration', type=int, required=True,
                       help='Test duration in seconds')
    parser.add_argument('--load-rps', type=float, required=True,
                       help='Target requests per second')
    parser.add_argument('--filename', type=str, required=True,
                       help='Output filename for metrics (JSON)')
    
    args = parser.parse_args()
    
    print(f"Configuration:")
    print(f"  Duration: {args.duration}s")
    print(f"  Target RPS: {args.load_rps}")
    print(f"  Output file: {args.filename}")
    print()
    
    collector = MetricsCollector()
    local_port_container = {}  # Shared dict to communicate port
    
    # Run both tasks concurrently
    await asyncio.gather(
        load_generator(args.duration, args.load_rps, collector, local_port_container),
        monitor_cwnd(local_port_container, collector, args.duration)
    )
    
    # Take final sample and save
    collector.sample()
    collector.save(args.filename)

if __name__ == "__main__":
    asyncio.run(main())