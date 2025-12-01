import asyncio
import ssl

HOST = "127.0.0.1"
PORT = 8443

async def main():
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE  # ok for local testing

    reader, writer = await asyncio.open_connection(
        HOST, PORT, ssl=ssl_ctx, server_hostname="localhost"
    )

    ssl_obj = writer.get_extra_info("ssl_object")
    print("TLS version:", ssl_obj.version())
    print("Cipher:", ssl_obj.cipher())

    request = (
        "GET / HTTP/1.1\r\n"
        "Host: localhost\r\n"
        "Connection: close\r\n"
        "\r\n"
    )
    writer.write(request.encode("ascii"))
    await writer.drain()

    response = await reader.read(-1)
    writer.close()
    await writer.wait_closed()

    # Split headers and body
    headers, _, body = response.partition(b"\r\n\r\n")
    print("Body length (bytes):", len(body))

if __name__ == "__main__":
    asyncio.run(main())