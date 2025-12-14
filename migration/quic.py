
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

# =========================
# QUIC (aioquic) COUNTER STREAM
# =========================

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Optional

from aioquic.asyncio import QuicConnectionProtocol, connect, serve
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import StreamDataReceived


@dataclass
class CounterMsg:
    counter: int
    ts: float  # seconds since epoch


# --------
# QUIC SERVER
# --------
class CounterQuicServer(QuicConnectionProtocol):
    """
    Protocol:
      - client opens a bidi stream and sends: b"START\n"
      - server responds on same stream with newline-delimited JSON:
            {"counter": N, "ts": 1234.56}\n
    """
    def __init__(self, *args, interval_s: float = 0.05, **kwargs):
        super().__init__(*args, **kwargs)
        self._interval_s = interval_s
        self._stream_id: Optional[int] = None
        self._task: Optional[asyncio.Task] = None
        self._counter = 0

    def quic_event_received(self, event):
        if isinstance(event, StreamDataReceived):
            data = event.data
            if self._stream_id is None and b"START" in data:
                self._stream_id = event.stream_id
                if self._task is None:
                    self._task = asyncio.create_task(self._send_loop())

    async def _send_loop(self):
        assert self._stream_id is not None
        sid = self._stream_id
        try:
            while self._counter < SERVER_COUNTER:
                msg = {"counter": self._counter, "ts": time.time()}
                payload = (json.dumps(msg) + "\n").encode("utf-8")
                self._quic.send_stream_data(sid, payload, end_stream=False)
                self.transmit()
                self._counter += 1
                await asyncio.sleep(self._interval_s)

            # end the stream
            self._quic.send_stream_data(sid, b"", end_stream=True)
            self.transmit()
        except asyncio.CancelledError:
            pass


async def run_quic_server(host: str, port: int, cert: str, key: str, interval_s: float):
    cfg = QuicConfiguration(is_client=False)
    cfg.load_cert_chain(certfile=cert, keyfile=key)

    await serve(
        host,
        port,
        configuration=cfg,
        create_protocol=lambda *a, **kw: CounterQuicServer(*a, interval_s=interval_s, **kw),
    )
    # serve() starts listening; keep process alive
    await asyncio.Future()


# --------
# QUIC CLIENT (with migration)
# --------
class CounterQuicClient(QuicConnectionProtocol):
    """
    Reads newline-delimited JSON from one stream and logs it.
    Migration:
      - rebind to a new local UDP port *without* closing the QUIC connection
      - switch to next available connection ID (good hygiene for new path)
    """
    def __init__(self, *args, remote_addr=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._buf = bytearray()
        self._lines = asyncio.Queue()

        self.remote_addr = remote_addr # tuple of the form (host, port)

    def connection_made(self, transport):
        print("[QUIC Client] Connection made called.")
        super().connection_made(transport)
        # stash remote tuple (aioquic transport is "connected" UDP)
        print("[QUIC Client] transport extras: ", transport._extra)
        # peer = transport.get_extra_info("peername")
        # if peer:
        #     self._remote_host, self._remote_port = peer[0], peer[1]

    def quic_event_received(self, event):
        if isinstance(event, StreamDataReceived):
            self._buf.extend(event.data)
            while True:
                i = self._buf.find(b"\n")
                if i < 0:
                    break
                line = bytes(self._buf[:i])
                del self._buf[: i + 1]
                if line:
                    self._lines.put_nowait(line)

    async def migrate(self, new_local_port):
        loop = asyncio.get_running_loop()

        # 1. Close old transport
        self._transport.close()

        # 2. Create new transport (same protocol, IPv6, no remote_addr)
        await loop.create_datagram_endpoint(
            lambda: self,
            local_addr=("::", 0),
        )

        # 3. (optional) Change CID for address mobility
        self.change_connection_id()

        # 4. Generate traffic using protocol API
        await self.ping()

    async def read_line(self) -> bytes:
        return await self._lines.get()


async def run_quic_client(
    host: str,
    port: int,
    out_path: str,
    migrate_at_counter: int,
    migrate_to_local_port: int,
):
    cfg = QuicConfiguration(is_client=True)
    cfg.verify_mode = 0  # CERT_NONE (keep simple for local/self-signed)

    async with connect(
        host,
        port,
        configuration=cfg,
        create_protocol=lambda *a, **kw: CounterQuicClient(
            *a, remote_addr=(host, port), **kw
        ),
        wait_connected=True,
        local_port=0,
    ) as proto:
        client: CounterQuicClient = proto

        # Start stream
        sid = client._quic.get_next_available_stream_id()
        client._quic.send_stream_data(sid, b"START\n", end_stream=False)
        client.transmit()

        with open(out_path, "w", buffering=1) as f:
            while True:
                line = await client.read_line()
                msg = json.loads(line.decode("utf-8"))
                # log whatever your TCP client logs (keep your format consistent)
                f.write(json.dumps(msg) + "\n")

                if msg.get("counter") == migrate_at_counter:
                    await client.migrate(migrate_to_local_port)
                
                if msg.get("counter") >= SERVER_COUNTER - 1:
                    break
        
        client.close()