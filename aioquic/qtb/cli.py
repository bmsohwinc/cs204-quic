#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

from .utils import (
    HOSTS_FILE,
    EXPERIMENTS_DIR,
    load_yaml,
    save_yaml,
)
from .runs import run_suite, show_suite_status, create_analysis_placeholder


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

    # Starter template – edit this as needed.
    template = {
        "suite": {
            "name": args.name,
            "implementation": "aioquic",
            "src": "h1",
            "dest": "h2",
            "link": "lo",
            "duration": 30,       # default load duration (seconds)
            "load_rps": 100,      # default load RPS
            "compare_tcp": True,
            "metrics": ["cwnd", "goodput"],
        },
        "experiments": {
            "e0": {
                "rtt_ms": 10,
                "loss_pct": 0.0,
                "bw_mbit": 20,
                "delay_ms": 5,
                # optional overrides:
                # "duration": 30,
                # "load_rps": 100,
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


# ---------- run / show / analyze wrappers ----------

def cmd_run(args: argparse.Namespace) -> None:
    exp_path = Path(args.experiments).resolve()
    run_suite(exp_path)


def cmd_show(args: argparse.Namespace) -> None:
    exp_path = Path(args.experiments).resolve()
    show_suite_status(exp_path)


def cmd_analyze(args: argparse.Namespace) -> None:
    exp_path = Path(args.experiments).resolve()
    create_analysis_placeholder(exp_path)


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
