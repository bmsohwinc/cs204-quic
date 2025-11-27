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

    # tc/netem configuration (still a stub)
    print(f"[{suite_name}/{exp_name}] Would apply netem on {link['iface']} with:")
    print(
        f"  rtt={params['rtt_ms']}ms "
        f"loss={params['loss_pct']}% "
        f"bw={params['bw_mbit']}Mbit "
        f"delay={params['delay_ms']}ms"
    )

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

        if client_rc == 0:
            update_status(suite_name, exp_name, "done", log_dir)
        else:
            update_status(suite_name, exp_name, "failed", log_dir)
    else:
        print("NOTE: Non-local implementations are not yet implemented.")
        update_status(suite_name, exp_name, "skipped", log_dir)


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
