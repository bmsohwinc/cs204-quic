import asyncio
import ssl

HOST = "127.0.0.1"
PORT = 8443

async def handle_client(reader, writer):
    """Handle multiple HTTP requests on a persistent connection"""
    addr = writer.get_extra_info('peername')
    print(f"Connection from {addr}")
    
    request_count = 0
    
    try:
        while True:
            # Read one HTTP request
            request_data = b''
            
            # Read until we get the end of headers
            while b'\r\n\r\n' not in request_data:
                chunk = await reader.read(1024)
                if not chunk:
                    # Connection closed by client
                    print(f"  {addr}: Connection closed after {request_count} requests")
                    return
                request_data += chunk
            
            request_count += 1
            
            # Parse request line
            request_line = request_data.split(b'\r\n')[0].decode('ascii')
            
            # Check if client wants to close connection
            # Look for "Connection: close" header (case-insensitive)
            request_lower = request_data.lower()
            connection_close = b'connection: close' in request_lower
            keep_alive = not connection_close  # Keep alive unless explicitly told to close
            
            # Read and serve page.html
            try:
                with open('page.html', 'rb') as f:
                    body = f.read()
                
                response_headers = (
                    "HTTP/1.1 200 OK\r\n"
                    "Content-Type: text/html\r\n"
                    f"Content-Length: {len(body)}\r\n"
                    "Connection: keep-alive\r\n"
                    "\r\n"
                ).encode('ascii')
                
                writer.write(response_headers + body)
                await writer.drain()
                
            except FileNotFoundError:
                # Fallback if page.html doesn't exist
                error_body = b"404 Not Found - page.html missing"
                error_response = (
                    "HTTP/1.1 404 Not Found\r\n"
                    "Content-Type: text/plain\r\n"
                    f"Content-Length: {len(error_body)}\r\n"
                    "Connection: keep-alive\r\n"
                    "\r\n"
                ).encode('ascii')
                
                writer.write(error_response + error_body)
                await writer.drain()
            
            # If client sent Connection: close, exit after this response
            if not keep_alive:
                print(f"  {addr}: Client requested close after {request_count} requests")
                break
                
    except Exception as e:
        print(f"  {addr}: Error after {request_count} requests: {e}")
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except:
            pass

async def main():
    # Create SSL context
    ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    
    try:
        ssl_ctx.load_cert_chain('cert.pem', 'key.pem')
    except FileNotFoundError:
        print("ERROR: cert.pem and key.pem not found!")
        print("\nGenerate them with:")
        print("  openssl req -x509 -newkey rsa:2048 -nodes \\")
        print("    -keyout key.pem -out cert.pem -days 365 \\")
        print("    -subj '/CN=localhost'")
        return
    
    server = await asyncio.start_server(
        handle_client, HOST, PORT, ssl=ssl_ctx
    )
    
    addr = server.sockets[0].getsockname()
    print(f'Serving on {addr}')
    print('Supports HTTP/1.1 persistent connections')
    print('Press Ctrl+C to stop')
    print()
    
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped")
