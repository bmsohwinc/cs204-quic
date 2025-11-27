#!/usr/bin/env python3
import argparse
import os
import subprocess
from pathlib import Path
from typing import Any, Dict

import yaml

# Base directory for configs and state.
# You can override by setting QTB_CONFIG_DIR in the environment.
REPO_ROOT = Path(__file__).resolve().parent.parent   # /workspace/aioquic
CONFIG_DIR = REPO_ROOT / "configs"
HOSTS_FILE = CONFIG_DIR / "hosts.yml"
IMPL_FILE = CONFIG_DIR / "implementations.yml"
EXPERIMENTS_DIR = CONFIG_DIR / "experiments"
RUNS_DIR = REPO_ROOT / "runs"


# ---------- Helpers ----------

def load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open() as f:
        return yaml.safe_load(f) or {}


def save_yaml(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        yaml.safe_dump(data, f, sort_keys=False)


# ---------- add-host / add-link ----------

def cmd_add_host(args: argparse.Namespace) -> None:
    cfg = load_yaml(HOSTS_FILE)
    hosts = cfg.get("hosts", {})
    hosts[args.name] = {
        "type": args.type,
        "ip": args.ip,
        "ssh": args.ssh,
    }
    cfg["hosts"] = hosts
    save_yaml(HOSTS_FILE, cfg)
    print(f"Added/updated host '{args.name}' in {HOSTS_FILE}")


def cmd_add_link(args: argparse.Namespace) -> None:
    cfg = load_yaml(HOSTS_FILE)
    links = cfg.get("links", {})
    links[args.name] = {
        "type": args.type,
        "iface": args.iface,
        "description": args.description,
    }
    cfg["links"] = links
    save_yaml(HOSTS_FILE, cfg)
    print(f"Added/updated link '{args.name}' in {HOSTS_FILE}")


# ---------- create-exps ----------

def cmd_create_exps(args: argparse.Namespace) -> None:
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    exp_path = EXPERIMENTS_DIR / f"{args.name}.yml"
    if exp_path.exists() and not args.force:
        print(f"{exp_path} already exists. Use --force to overwrite.")
        return

    # Simple starter template – you’ll edit this after creation.
    template = {
        "suite": {
            "name": args.name,
            "implementation": "aioquic",
            "src": "h1",
            "dest": "h2",
            "link": "lo",
            "duration": 30,
            "compare_tcp": True,
            "metrics": ["cwnd", "goodput"],
        },
        "experiments": {
            "e0": {
                "rtt_ms": 10,
                "loss_pct": 0.0,
                "bw_mbit": 20,
                "delay_ms": 5,
            },
            "e1": {
                "rtt_ms": 50,
                "loss_pct": 2.5,
                "bw_mbit": 10,
                "delay_ms": 5,
            },
        },
    }
    save_yaml(exp_path, template)
    print(f"Created experiment suite template at {exp_path}")

    if not args.no_edit:
        editor = os.environ.get("EDITOR", "vi")
        subprocess.call([editor, str(exp_path)])


# ---------- config loaders ----------

def load_impl(name: str) -> Dict[str, Any]:
    cfg = load_yaml(IMPL_FILE)
    impls = cfg.get("implementations", {})
    if name not in impls:
        raise SystemExit(f"Implementation '{name}' not found in {IMPL_FILE}")
    return impls[name]


def load_hosts() -> Dict[str, Any]:
    cfg = load_yaml(HOSTS_FILE)
    return {
        "hosts": cfg.get("hosts", {}),
        "links": cfg.get("links", {}),
    }


# ---------- status handling ----------

def update_status(suite_name: str, exp_name: str, status: str, log_dir: Path) -> None:
    status_file = RUNS_DIR / suite_name / "status.yml"
    st = load_yaml(status_file)
    exps = st.get("experiments", {})
    exps[exp_name] = {
        "status": status,
        "log_dir": str(log_dir),
    }
    st["experiments"] = exps
    save_yaml(status_file, st)


# ---------- core runner ----------

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
    rps = suite["rps"]
    duration = suite["duration"]

    src = hosts.get(suite["src"])
    dest = hosts.get(suite["dest"])
    link = links.get(suite["link"])

    if not src or not dest or not link:
        raise SystemExit("Invalid src/dest/link in suite; check hosts.yml")

    log_dir = RUNS_DIR / suite_name / exp_name
    log_dir.mkdir(parents=True, exist_ok=True)

    update_status(suite_name, exp_name, "running", log_dir)

    # TODO: apply tc netem based on `link` + `params`
    print(f"[{suite_name}/{exp_name}] Would apply netem on {link['iface']} with:")
    print(
        f"  rtt={params['rtt_ms']}ms loss={params['loss_pct']}% "
        f"bw={params['bw_mbit']}Mbit delay={params['delay_ms']}ms"
    )

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
        rps=rps,
        duration=duration,
    )

    impl_type = impl.get("type", "local")

    print(f"[{suite_name}/{exp_name}] Running implementation '{impl_name}' ({impl_type})")
    print(f"  Server: {server_cmd}")
    print(f"  Client: {client_cmd}")

    # For now, we only support 'local' execution as a placeholder.
    # Real version: branch here for docker/ssh etc.
    if impl_type == "local":
        server_proc = subprocess.Popen(server_cmd, shell=True)
        try:
            client_rc = subprocess.call(client_cmd, shell=True)
        finally:
            server_proc.terminate()
            server_proc.wait()
        if client_rc == 0:
            update_status(suite_name, exp_name, "done", log_dir)
        else:
            update_status(suite_name, exp_name, "failed", log_dir)
    else:
        print("NOTE: Non-local implementations are not yet implemented.")
        update_status(suite_name, exp_name, "skipped", log_dir)


def cmd_run(args: argparse.Namespace) -> None:
    exp_path = Path(args.experiments).resolve()
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

def cmd_show(args: argparse.Namespace) -> None:
    exp_path = Path(args.experiments).resolve()
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

def cmd_analyze(args: argparse.Namespace) -> None:
    exp_path = Path(args.experiments).resolve()
    cfg = load_yaml(exp_path)
    if "suite" not in cfg:
        raise SystemExit(f"{exp_path} does not look like a qtb experiments file")
    suite_name = cfg["suite"]["name"]
    suite_dir = RUNS_DIR / suite_name
    suite_dir.mkdir(parents=True, exist_ok=True)

    # Placeholder: later you’ll generate a Jupyter notebook here.
    analysis_path = suite_dir / "analysis_placeholder.txt"
    analysis_text = (
        "Analysis placeholder. In the next phase, qtb will generate a Jupyter "
        "notebook here that loads qlogs from subdirectories.\n"
    )
    analysis_path.write_text(analysis_text)
    print(f"Created analysis placeholder at {analysis_path}")


# ---------- CLI wiring ----------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="qtb", description="QUIC Testbed Orchestrator (qtb)")
    sub = p.add_subparsers(dest="cmd", required=True)

    # add-host
    ph = sub.add_parser("add-host", help="Add or update a host in hosts.yml")
    ph.add_argument("name", help="Logical host name (e.g., h1)")
    ph.add_argument("ip", help="Host IP address")
    ph.add_argument("--ssh", default=None, help="SSH target (user@host), optional")
    ph.add_argument(
        "--type",
        choices=["local", "docker", "ssh"],
        default="local",
        help="Host type (for future extensions)",
    )
    ph.set_defaults(func=cmd_add_host)

    # add-link
    pl = sub.add_parser("add-link", help="Add or update a link in hosts.yml")
    pl.add_argument("name", help="Link name (e.g., lo)")
    pl.add_argument("--iface", default="lo", help="Interface name, e.g., lo, eth0")
    pl.add_argument(
        "--type",
        choices=["local_iface", "docker_network"],
        default="local_iface",
        help="Link type",
    )
    pl.add_argument(
        "--description",
        default="",
        help="Human-readable description of the link",
    )
    pl.set_defaults(func=cmd_add_link)

    # create-exps
    pc = sub.add_parser("create-exps", help="Create an experiment suite YAML template")
    pc.add_argument("name", help="Suite name (basename of YAML file)")
    pc.add_argument(
        "--force", action="store_true", help="Overwrite existing experiments file"
    )
    pc.add_argument(
        "--no-edit",
        action="store_true",
        help="Do not open the file in $EDITOR after creation",
    )
    pc.set_defaults(func=cmd_create_exps)

    # run
    pr = sub.add_parser("run", help="Run experiments from a suite YAML file")
    pr.add_argument("experiments", help="Path to experiments YAML file")
    pr.set_defaults(func=cmd_run)

    # show
    ps = sub.add_parser("show", help="Show status of experiments in a suite")
    ps.add_argument("experiments", help="Path to experiments YAML file")
    ps.set_defaults(func=cmd_show)

    # analyze
    pa = sub.add_parser(
        "analyze",
        help="Prepare analysis artifacts for a suite (notebook placeholder for now)",
    )
    pa.add_argument("experiments", help="Path to experiments YAML file")
    pa.set_defaults(func=cmd_analyze)

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
    