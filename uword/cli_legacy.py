"""旧版装配（仅用于 `uword mock` 离线自检）。

真实业务走 uword.fltrp；这里的 Config/Net/Engine 是早期对着本地假接口写的通用引擎，
保留它是为了让 mock 自检在没有账号的机器上也能验证调度与判分逻辑。
"""
from __future__ import annotations

import time

from .config import Config
from .engine import Engine
from .humanize import Pacer
from .net import HttpClient
from .solver import Solver
from .store import Store


def make_logger(cfg, quiet: bool = False):
    path = cfg.get("log_file")

    def log(msg: str):
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        if not quiet:
            print(line, flush=True)
        if path:
            try:
                with open(path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except OSError:
                pass

    return log


def build(args, quiet: bool = False):
    cfg = Config.load(getattr(args, "config", None), getattr(args, "base_url", None))
    log = make_logger(cfg, quiet)
    p = cfg.get("pacing") or {}
    pacer = Pacer(p.get("min_gap", 0.9), p.get("max_gap", 2.8), p.get("burst", 3))
    client = HttpClient(cfg, pacer=pacer, logger=log)
    store = Store(cfg.get("storage", "uword.db"))
    solver = Solver(cfg, store, client, log)
    engine = Engine(cfg, client, store, solver, log)
    return cfg, client, store, solver, engine, log
