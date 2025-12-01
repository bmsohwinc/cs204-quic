#!/usr/bin/env python3
from __future__ import annotations

import shlex
import subprocess
import time

from pathlib import Path
from typing import Any, Dict

from .utils import (
    RUNS_DIR,
    load_yaml,
    load_hosts,
    load_impl,
    update_status,
)

def get_latest_qlog_file(qlog_dir: Path) -> Path | None:
    """Return the newest .qlog file in qlog_dir, or None if none exist."""
    qlogs = list(qlog_dir.glob("*.qlog"))
    if not qlogs:
        return None
    return max(qlogs, key=lambda p: p.stat().st_mtime)

# ---------- tc / netem helpers ----------

def _run_tc(cmd: list[str]) -> None:
    """Run a tc command and print it for debugging."""
    print("[tc]", " ".join(cmd))
    subprocess.run(cmd, check=True)


def apply_netem(
    iface: str,
    rtt_ms: float,
    loss_pct: float,
    bw_mbit: float,
    delay_ms: float,
) -> None:
    """
    Configure tc/netem on `iface`.

    - We approximate the link via a simple HTB + netem stack:
      * HTB for bandwidth (if bw_mbit is set)
      * netem for delay + loss
    - `rtt_ms` is logged/kept for semantics but we currently use `delay_ms`
      as the one-way delay, matching the earlier shell setup (e.g., delay 5ms
      ⇒ ~10ms RTT).
    """
    # Always try to clear any prior qdisc; ignore errors.
    subprocess.run(["tc", "qdisc", "del", "dev", iface, "root"], check=False)

    # Optional bandwidth shaping via HTB
    if bw_mbit:
        _run_tc(
            [
                "tc", "qdisc", "add", "dev", iface,
                "root", "handle", "1:", "htb", "default", "1",
            ]
        )
        _run_tc(
            [
                "tc", "class", "add", "dev", iface,
                "parent", "1:", "classid", "1:1",
                "htb", "rate", f"{bw_mbit}mbit",
            ]
        )
        netem_cmd = [
            "tc", "qdisc", "add", "dev", iface,
            "parent", "1:1", "handle", "10:", "netem",
        ]
    else:
        # No bandwidth shaping – netem directly on root
        netem_cmd = [
            "tc", "qdisc", "add", "dev", iface,
            "root", "netem",
        ]

    if delay_ms:
        netem_cmd += ["delay", f"{delay_ms}ms"]
    if loss_pct:
        netem_cmd += ["loss", f"{loss_pct}%"]

    _run_tc(netem_cmd)


def reset_netem(iface: str) -> None:
    """Reset tc/netem on `iface` (best-effort)."""
    print("[tc] reset", iface)
    subprocess.run(["tc", "qdisc", "del", "dev", iface, "root"], check=False)


# ---------- TCP/TLS baseline helper ----------

def run_tcp_baseline(
    suite_name: str,
    exp_name: str,
    load_rps: int,
    load_duration: int,
    log_dir: Path,
    client_qlog_dir: Path,
) -> bool:
    """
    Run a simple TCP/TLS server+client under the *same* tc/netem config.

    For now, we assume:
      - `python3 server.py`
      - `python3 client.py --load-rps N --load-duration S`
    and that IPs / certs are hardcoded inside those scripts.
    """
    tcp_log_dir = log_dir / "tcp"
    tcp_log_dir.mkdir(parents=True, exist_ok=True)

    # Derive TCP metrics filename from latest QUIC qlog
    latest_qlog = get_latest_qlog_file(client_qlog_dir)
    filename_arg = ""
    if latest_qlog is not None:
        tcp_out = latest_qlog.with_name(latest_qlog.stem + "_tcp.json")
        filename_arg = f" --filename {tcp_out}"
        print(f"[{suite_name}/{exp_name}] TCP/TLS metrics file: {tcp_out}")
    else:
        print(f"[{suite_name}/{exp_name}] WARNING: no .qlog file found in {client_qlog_dir}; "
              "not passing --filename to TCP client")

    server_cmd = "python3 server.py"
    client_cmd = (
        f"python3 client.py "
        f"--load-rps {int(load_rps)} "
        f"--load-duration {int(load_duration)}"
        f"{filename_arg}"
    )

    print(f"[{suite_name}/{exp_name}] Comparing TCP/TLS baseline")
    print(f"  TCP server: {server_cmd}")
    print(f"  TCP client: {client_cmd}")

    server_args = shlex.split(server_cmd)
    client_args = shlex.split(client_cmd)

    server_proc = subprocess.Popen(server_args)
    try:
        time.sleep(2)
        client_rc = subprocess.call(client_args)
    finally:
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_proc.kill()
            server_proc.wait()

    if client_rc != 0:
        print(f"[{suite_name}/{exp_name}] TCP/TLS run failed with exit code {client_rc}")
        return False

    return True

# ---------- single experiment runner ----------

def run_single_experiment(
    suite: Dict[str, Any],
    exp_name: str,
    params: Dict[str, Any],
    hosts_cfg: Dict[str, Any],
) -> None:
    suite_name = suite["name"]
    impl_name = suite["implementation"]
    impl = load_impl(impl_name)
    hosts = hosts_cfg["hosts"]
    links = hosts_cfg["links"]

    src = hosts.get(suite["src"])
    dest = hosts.get(suite["dest"])
    link = links.get(suite["link"])

    if not src or not dest or not link:
        raise SystemExit("Invalid src/dest/link in suite; check hosts.yml")

    log_dir = RUNS_DIR / suite_name / exp_name
    log_dir.mkdir(parents=True, exist_ok=True)

    update_status(suite_name, exp_name, "running", log_dir)

    iface = link.get("iface")
    link_type = link.get("type")

    # tc/netem configuration
    rtt_ms = params["rtt_ms"]
    loss_pct = params["loss_pct"]
    bw_mbit = params["bw_mbit"]
    delay_ms = params["delay_ms"]

    print(f"[{suite_name}/{exp_name}] Netem config on {iface}:")
    print(
        f"  rtt={rtt_ms}ms "
        f"loss={loss_pct}% "
        f"bw={bw_mbit}Mbit "
        f"delay={delay_ms}ms"
    )

    netem_applied = False
    if link_type == "local_iface" and iface:
        try:
            apply_netem(
                iface=iface,
                rtt_ms=rtt_ms,
                loss_pct=loss_pct,
                bw_mbit=bw_mbit,
                delay_ms=delay_ms,
            )
            netem_applied = True
        except subprocess.CalledProcessError as exc:
            print(f"[{suite_name}/{exp_name}] Failed to configure tc/netem: {exc}")
            update_status(suite_name, exp_name, "failed", log_dir)
            return
    else:
        print(f"[{suite_name}/{exp_name}] Skipping tc/netem (link type={link_type!r})")

    # Load parameters for the client from CONFIG, not CLI.
    # Per-experiment overrides suite-level.
    load_rps = params.get("load_rps", suite.get("load_rps", 100))
    load_duration = params.get("duration", suite.get("duration", 30))

    # Build commands from implementation template
    port = impl.get("default_port", 4433)
    server_ip = src["ip"]
    client_ip = dest["ip"]

    server_qlog_dir = log_dir / "server"
    client_qlog_dir = log_dir / "client"

    server_qlog_dir.mkdir(parents=True, exist_ok=True)
    client_qlog_dir.mkdir(parents=True, exist_ok=True)

    server_qlog_dir_path = str(server_qlog_dir)
    client_qlog_dir_path = str(client_qlog_dir)

    server_cmd_tpl = impl["server_cmd"]
    client_cmd_tpl = impl["client_cmd"]

    server_cmd = server_cmd_tpl.format(
        server_ip=server_ip,
        client_ip=client_ip,
        port=port,
        qlog_dir=server_qlog_dir_path,
        exp_name=exp_name,
    )
    client_cmd = client_cmd_tpl.format(
        server_ip=server_ip,
        client_ip=client_ip,
        port=port,
        qlog_dir=client_qlog_dir_path,
        exp_name=exp_name,
        rps=int(load_rps),
        duration=int(load_duration),
    )

    impl_type = impl.get("type", "local")

    print(f"[{suite_name}/{exp_name}] Running implementation '{impl_name}' ({impl_type})")
    print(f"  Server: {server_cmd}")
    print(f"  Client: {client_cmd}")

    overall_ok = True

    try:
        # For now, we only support 'local' execution as a placeholder.
        if impl_type == "local":
            # Turn "python3 examples/http3_server.py --foo bar" into a list
            server_args = shlex.split(server_cmd)
            client_args = shlex.split(client_cmd)

            server_proc = subprocess.Popen(server_args)
            try:
                time.sleep(2)  # allow server to start
                client_rc = subprocess.call(client_args)
            finally:
                # Try graceful shutdown first
                server_proc.terminate()
                try:
                    server_proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # If it ignores SIGTERM, force kill
                    server_proc.kill()
                    server_proc.wait()

            overall_ok = (client_rc == 0)

            # Optional TCP/TLS baseline under the same netem config
            if suite.get("compare_tcp"):
                tcp_ok = run_tcp_baseline(
                    suite_name=suite_name,
                    exp_name=exp_name,
                    load_rps=int(load_rps),
                    load_duration=int(load_duration),
                    log_dir=log_dir,
                    client_qlog_dir=client_qlog_dir,
                )
                overall_ok = overall_ok and tcp_ok

        else:
            print("NOTE: Non-local implementations are not yet implemented.")
            overall_ok = False

        if overall_ok:
            update_status(suite_name, exp_name, "done", log_dir)
        else:
            update_status(suite_name, exp_name, "failed", log_dir)

    finally:
        # Always reset tc/netem at the end of the experiment.
        if netem_applied and iface:
            reset_netem(iface)

# ---------- suite runner ----------

def run_suite(exp_path: Path) -> None:
    cfg = load_yaml(exp_path)
    if "suite" not in cfg or "experiments" not in cfg:
        raise SystemExit(f"{exp_path} does not look like a qtb experiments file")

    suite = cfg["suite"]
    suite_name = suite["name"]
    hosts_cfg = load_hosts()

    print(f"Running suite '{suite_name}' from {exp_path}")
    for exp_name, params in cfg["experiments"].items():
        run_single_experiment(suite, exp_name, params, hosts_cfg)


# ---------- show ----------

def show_suite_status(exp_path: Path) -> None:
    cfg = load_yaml(exp_path)
    if "suite" not in cfg:
        raise SystemExit(f"{exp_path} does not look like a qtb experiments file")

    suite = cfg["suite"]
    suite_name = suite["name"]
    status_file = RUNS_DIR / suite_name / "status.yml"
    st = load_yaml(status_file)
    exps_status = st.get("experiments", {})

    print(f"Suite: {suite_name}")
    print(f"Status file: {status_file}")
    print()
    print(f"{'Experiment':<12} {'Status':<10} {'Log directory'}")
    print("-" * 60)
    for exp_name in cfg.get("experiments", {}).keys():
        info = exps_status.get(exp_name, {})
        status = info.get("status", "pending")
        log_dir = info.get("log_dir", "-")
        print(f"{exp_name:<12} {status:<10} {log_dir}")


# ---------- analyze (placeholder) ----------

def create_analysis_placeholder(exp_path: Path) -> None:
    cfg = load_yaml(exp_path)
    if "suite" not in cfg:
        raise SystemExit(f"{exp_path} does not look like a qtb experiments file")
    suite_name = cfg["suite"]["name"]
    suite_dir = RUNS_DIR / suite_name
    suite_dir.mkdir(parents=True, exist_ok=True)

    analysis_path = suite_dir / "analysis_placeholder.txt"
    analysis_text = (
        "Analysis placeholder. In the next phase, qtb will generate a Jupyter "
        "notebook here that loads qlogs from subdirectories.\n"
    )
    analysis_path.write_text(analysis_text)
    print(f"Created analysis placeholder at {analysis_path}")
