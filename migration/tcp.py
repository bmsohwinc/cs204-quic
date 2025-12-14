# tcp.py
import asyncio
import json
import ssl
import time
from typing import Optional

SERVER_COUNTER = 20  # keep same constant for now (matches your earlier code)


async def run_tcp_server(host: str, port: int, cert: str, key: str, interval_s: float = 0.1):
    """
    TLS TCP server: sends newline-delimited JSON:
      {"counter": N, "timestamp": <server_ts>}
    """
    ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_context.load_cert_chain(cert, key)

    counter = 0

    async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        nonlocal counter
        try:
            while counter < SERVER_COUNTER:
                msg = {
                    "counter": counter,
                    "timestamp": time.time(),  # server_ts
                }
                writer.write((json.dumps(msg) + "\n").encode())
                await writer.drain()
                counter += 1
                await asyncio.sleep(interval_s)
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(handle_client, host, port, ssl=ssl_context)
    print(f"[TCP Server] Listening on {host}:{port}")
    async with server:
        await server.serve_forever()


async def run_tcp_client(
    host: str,
    port: int,
    out_path: str,
    disconnect_at_counter: int = 5,
):
    """
    TLS TCP client: reads newline-delimited JSON, logs JSONL to out_path.
    Adds client_ts (receive timestamp).
    Performs reconnection at disconnect_at_counter (TCP semantics).
    """
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    async def open_conn():
        return await asyncio.open_connection(host, port, ssl=ssl_context)

    reader, writer = await open_conn()
    print("[TCP Client] Connected")

    buffer = ""

    with open(out_path, "w", buffering=1) as f:
        while True:
            chunk = await reader.read(4096)
            if not chunk:
                break

            buffer += chunk.decode()

            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                if not line:
                    continue

                server_msg = json.loads(line)
                client_ts = time.time()

                # ✅ log line: counter, server_ts, client_ts
                log_msg = {
                    "counter": server_msg.get("counter"),
                    "server_ts": server_msg.get("timestamp"),
                    "client_ts": client_ts,
                }
                f.write(json.dumps(log_msg) + "\n")

                c = server_msg.get("counter")

                # Trigger disconnection + reconnection (TCP behavior)
                if c == disconnect_at_counter:
                    print(f"[TCP Client] Disconnecting at counter {disconnect_at_counter}")
                    writer.close()
                    await writer.wait_closed()

                    await asyncio.sleep(0.1)

                    print("[TCP Client] Reconnecting...")
                    reader, writer = await open_conn()
                    print("[TCP Client] Reconnected")
                    buffer = ""  # reset parse buffer after reconnect

                # Stop after last counter
                if c is not None and c >= (SERVER_COUNTER - 1):
                    writer.close()
                    await writer.wait_closed()
                    return
