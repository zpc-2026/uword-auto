"""命令行入口：真实后端（外研U词）+ 离线自检。"""
from __future__ import annotations

import argparse
import json
import sys
import time

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

from .fltrp import auth, ops, solver  # noqa: E402
from .fltrp.client import ApiError, AuthExpired, Client  # noqa: E402


def out(data, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, ensure_ascii=False))
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))


def _client(args) -> Client:
    token = getattr(args, "token", None) or None
    return Client(token=token or auth.current_token(),
                  pacing=(getattr(args, "gap_min", 0.15), getattr(args, "gap_max", 0.35)))


def bar(i: int, n: int, right: int, wrong: int) -> None:
    if i % 5 == 0 or i == n:
        print(f"  {i}/{n} 词  正确 {right} 错误 {wrong}", flush=True)


def cmd_login(args):
    if args.sms:
        cap = auth.sms_captcha()
        p = "captcha.jpg"
        import base64
        open(p, "wb").write(base64.b64decode(cap["image"]))
        print(f"图片验证码已存到 {p}，打开看一眼。", flush=True)
        code = input("图片验证码: ").strip()
        auth.sms_send(args.phone, code, cap["encode_captha"])
        print("短信已发送。", flush=True)
        sms = input("短信验证码: ").strip()
        newpwd = args.password or input("新密码（字母+数字，≥8位）: ").strip()
        auth.sms_set_password(args.phone, sms, newpwd)
        user = auth.login(args.phone, newpwd)
    else:
        user, pwd = args.user, args.password
        if not (user and pwd):
            print("需要 --user 和 --password（或 --sms 走短信设密码）", file=sys.stderr)
            return 2
        user_obj = auth.login(user, pwd, usercode=args.usercode)
        user = user_obj
    data = {"ok": True, "user": {k: user.get(k) for k in ("id", "name", "company", "tel2", "openid", "usercode")},
            "token_file": str(auth.TokenStore().path)}
    out(data, args.json)
    return 0


def cmd_status(args):
    out(ops.status(_client(args)), args.json)
    return 0


def cmd_learn(args):
    r = ops.learn(_client(args), count=args.count,
                  questions_per_word=args.questions or None,
                  word_seconds=args.word_seconds,
                  progress=None if args.json else bar)
    out(r, args.json)
    return 0 if r.get("ok") else 1


def cmd_review(args):
    p = (lambda i, n: print(f"  {i}/{n}", flush=True)) if not args.json else None
    out(ops.review(_client(args), limit=args.limit, progress=p), args.json)
    return 0


def cmd_auto(args):
    rep = {"learn": None, "review": None}
    if args.learn:
        rep["learn"] = ops.learn(_client(args), count=args.learn,
                                 word_seconds=args.word_seconds,
                                 progress=None if args.json else bar)
    if args.review:
        rep["review"] = ops.review(_client(args), limit=args.review)
    rep["status"] = ops.status(_client(args))
    out(rep, args.json)
    return 0


def cmd_plan(args):
    out(ops.set_plan(_client(args), pstudy=args.pstudy, pdaycount=args.pdaycount), args.json)
    return 0


def cmd_questions(args):
    """调试：看某个词下发的题目与求解结果。"""
    c = _client(args)
    qs = c.questions(args.word, args.count)
    rows = []
    for q in qs:
        ok, ans, why = solver.solve(q)
        rows.append({"type": q.get("type"), "word": q.get("word"), "des": q.get("des"),
                     "solved": ok, "answer": ans, "why": why})
    out({"word": args.word, "questions": rows}, True)
    return 0


def cmd_mock(args):
    """离线自检：起本地假接口跑完整流水线（不碰真实账号）。"""
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    srv = root / "tools" / "mock_server.py"
    if not srv.exists():
        print("找不到 tools/mock_server.py", file=sys.stderr)
        return 2
    proc = subprocess.Popen([sys.executable, str(srv), "--port", str(args.port)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    time.sleep(1.2)
    try:
        # 每次自检都用干净的库，避免上一轮的进度导致"学到 0 个也算通过"
        work = root / ".uword"
        work.mkdir(parents=True, exist_ok=True)
        base = json.loads((root / "config.example.json").read_text(encoding="utf-8-sig"))
        base["storage"] = str(work / "mock.db")
        base["log_file"] = str(work / "mock.log")
        cfg_path = work / "mock_config.json"
        cfg_path.write_text(json.dumps(base, ensure_ascii=False), encoding="utf-8")
        for stale in (work / "mock.db",):
            try:
                stale.unlink()
            except OSError:
                pass

        ns = argparse.Namespace(config=str(cfg_path),
                                base_url=f"http://127.0.0.1:{args.port}",
                                book="mock-book", limit=args.limit, rounds=3,
                                minutes=args.minutes, once=False, log=True, quiet=False)
        cfg, client, store, sv, engine, log = _legacy_build(ns)
        cfg.data["timing"] = {"word_seconds": [0.05, 0.2], "heartbeat_every": [0.2, 0.4],
                              "rest_every_words": [900, 1000], "rest_seconds": [0, 0]}
        client.pacer.min_gap, client.pacer.max_gap = 0.01, 0.03
        rep = engine.auto("mock-book", args.minutes)
        out(rep, True)
        ok = (rep["words_learned"] == rep["words_total"] == 24
              and rep["quiz"] > 0 and rep["errors"] == 0)
        print("自检通过" if ok else "自检有问题", file=sys.stderr)
        return 0 if ok else 2
    finally:
        proc.terminate()


def _legacy_build(ns):
    from .cli_legacy import build
    return build(ns)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="uword", description="外研U词 自动化（真实接口 / 离线自检）")
    p.add_argument("-c", "--config", default=None, help="兼容旧版配置（mock 用）")
    p.add_argument("--base-url", default=None, help="兼容旧版（mock 用）")
    p.add_argument("--token", default=None, help="临时指定会话串，默认读 ~/.uword/token.json")
    p.add_argument("--json", action="store_true", help="只输出一行 JSON（给 agent 用）")
    p.add_argument("--gap-min", type=float, default=0.15)
    p.add_argument("--gap-max", type=float, default=0.35)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    common.add_argument("--token", default=argparse.SUPPRESS)
    common.add_argument("--gap-min", type=float, default=argparse.SUPPRESS)
    common.add_argument("--gap-max", type=float, default=argparse.SUPPRESS)
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("login", help="登录并缓存会话", parents=[common])
    sp.add_argument("--user", default=None)
    sp.add_argument("--password", default=None)
    sp.add_argument("--usercode", default="1", choices=["0", "1"], help="1=学生（默认）")
    sp.add_argument("--sms", action="store_true", help="短信验证码设密码后登录")
    sp.add_argument("--phone", default=None)
    sp.set_defaults(func=cmd_login)

    sp = sub.add_parser("status", help="词书 / 进度 / 复习队列", parents=[common])
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("learn", help="背新词", parents=[common])
    sp.add_argument("count", type=int, nargs="?", default=20)
    sp.add_argument("--questions", type=int, default=0, help="每词题量，默认按计划 pstudy")
    sp.add_argument("--word-seconds", type=float, default=25.0, help="每词停留秒数（让学习时长真实增长）")
    sp.set_defaults(func=cmd_learn)

    sp = sub.add_parser("review", help="清复习队列", parents=[common])
    sp.add_argument("--limit", type=int, default=200)
    sp.set_defaults(func=cmd_review)

    sp = sub.add_parser("auto", help="学习 + 复习一把梭", parents=[common])
    sp.add_argument("--learn", type=int, default=20)
    sp.add_argument("--review", type=int, default=200)
    sp.add_argument("--word-seconds", type=float, default=25.0)
    sp.set_defaults(func=cmd_auto)

    sp = sub.add_parser("plan", help="改计划（每词题量 / 每日额度），原地更新不动进度", parents=[common])
    sp.add_argument("--pstudy", type=int, default=None, choices=[0, 1])
    sp.add_argument("--pdaycount", type=int, default=None)
    sp.set_defaults(func=cmd_plan)

    sp = sub.add_parser("questions", help="调试：看某词的题目与自动求解结果", parents=[common])
    sp.add_argument("word")
    sp.add_argument("--count", type=int, default=3)
    sp.set_defaults(func=cmd_questions)

    sp = sub.add_parser("mock", help="离线自检（无需账号）", parents=[common])
    sp.add_argument("--port", type=int, default=8898)
    sp.add_argument("--limit", type=int, default=12)
    sp.add_argument("--minutes", type=float, default=2)
    sp.set_defaults(func=cmd_mock)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args) or 0
    except AuthExpired as e:
        print(f"[会话失效] {e}\n→ 跑 `uword login` 重新登录", file=sys.stderr)
        return 3
    except (ApiError, PermissionError, RuntimeError) as e:
        print(f"[错误] {type(e).__name__}: {e}", file=sys.stderr)
        return 4
    except KeyboardInterrupt:
        print("\n[中断] 进度按批次结算，重跑会从已学位置继续", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
