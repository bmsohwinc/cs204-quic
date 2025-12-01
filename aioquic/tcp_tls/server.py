import asyncio
import ssl
from pathlib import Path

HOST = "127.0.0.1"
PORT = 8443

HTML_BODY = Path("page.html").read_bytes()

async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    ssl_obj = writer.get_extra_info("ssl_object")
    if ssl_obj is None:
        print("⚠ Connection is NOT using TLS")
    else:
        print("✅ TLS in use")
        print("  TLS version:", ssl_obj.version())
        print("  Cipher:", ssl_obj.cipher())
        
    # Read and ignore the request content (simple demo)
    await reader.read(1024)

    response = (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: text/html; charset=utf-8\r\n"
        b"Content-Length: " + str(len(HTML_BODY)).encode() + b"\r\n"
        b"Connection: close\r\n"
        b"\r\n" +
        HTML_BODY
    )

    writer.write(response)
    await writer.drain()
    writer.close()
    await writer.wait_closed()

async def main():
    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_ctx.load_cert_chain("cert.pem", "key.pem")

    server = await asyncio.start_server(
        handle_client, HOST, PORT, ssl=ssl_ctx
    )

    print(f"Serving on https://{HOST}:{PORT}")
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())
