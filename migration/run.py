import argparse
import asyncio

from quic import run_quic_client, run_quic_server

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--proto", choices=["tcp", "quic"], required=True)
    p.add_argument("--mode", choices=["server", "client"], required=True)

    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=4434)

    # QUIC-only
    p.add_argument("--cert", default="cert.pem")
    p.add_argument("--key", default="key.pem")
    p.add_argument("--interval", type=float, default=0.1)
    p.add_argument("--out", default="client.log")
    p.add_argument("--migrate-at", type=int, default=5)
    p.add_argument("--migrate-local-port", type=int, default=5555)
    return p.parse_args()

async def entry():
    args = parse_args()

    if args.proto == "tcp":
        # ✅ DO NOT TOUCH YOUR TCP IMPLEMENTATION.
        # Call into your existing TCP server/client entrypoints here.
        if args.mode == "server":
            # await run_tcp_server(args.host, args.port)   # <-- your existing function
            pass
        else:
            # await run_tcp_client(args.host, args.port)   # <-- your existing function
            pass

    elif args.proto == "quic":
        if args.mode == "server":
            await run_quic_server(args.host, args.port, args.cert, args.key, args.interval)
        else:
            await run_quic_client(
                args.host,
                args.port,
                out_path=args.out,
                migrate_at_counter=args.migrate_at,
                migrate_to_local_port=args.migrate_local_port
            )
    else:
        pass

if __name__ == "__main__":
    asyncio.run(entry())
    