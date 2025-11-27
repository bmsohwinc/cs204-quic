#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import yaml

# Base directories for configs and state.
# You can override configs via QTB_CONFIG_DIR if you want.
REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = Path(os.environ.get("QTB_CONFIG_DIR", REPO_ROOT / "configs"))
HOSTS_FILE = CONFIG_DIR / "hosts.yml"
IMPL_FILE = CONFIG_DIR / "implementations.yml"
EXPERIMENTS_DIR = CONFIG_DIR / "experiments"
RUNS_DIR = REPO_ROOT / "runs"


# ---------- basic YAML helpers ----------

def load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open() as f:
        return yaml.safe_load(f) or {}


def save_yaml(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        yaml.safe_dump(data, f, sort_keys=False)


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
