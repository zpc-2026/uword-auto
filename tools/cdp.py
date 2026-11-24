"""最小 CDP 客户端：开新标签、等加载、在页面里执行 JS。

    python tools/cdp.py list
    python tools/cdp.py open https://word.fltrp.com/ --eval "JSON.stringify(Object.keys(localStorage))"
"""
from __future__ import annotations

import argparse
import json
import ssl
import sys
import time
import urllib.request

import websocket  # websocket-client

HTTP_CTX = ssl.create_default_context()


def http_json(url: str, method: str = "GET"):
    req = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def browser_ws(port: int) -> str:
    return http_json(f"http://127.0.0.1:{port}/json/version")["webSocketDebuggerUrl"]


class Session:
    def __init__(self, ws_url: str):
        self.ws = websocket.create_connection(ws_url, timeout=30,
                                              suppress_origin=True,
                                              http_proxy_host=None)
        self.seq = 0

    def send(self, method: str, params: dict | None = None, session_id: str | None = None):
        self.seq += 1
        msg = {"id": self.seq, "method": method, "params": params or {}}
        if session_id:
            msg["sessionId"] = session_id
        self.ws.send(json.dumps(msg))
        return self.seq

    def wait_for(self, msg_id: int, timeout: float = 30) -> dict:
        end = time.time() + timeout
        while time.time() < end:
            raw = self.ws.recv()
            data = json.loads(raw)
            if data.get("id") == msg_id:
                return data
        raise TimeoutError(f"等待 id={msg_id} 超时")

    def call(self, method: str, params: dict | None = None, session_id: str | None = None,
             timeout: float = 30) -> dict:
        mid = self.send(method, params, session_id)
        return self.wait_for(mid, timeout)

    def eval(self, expr: str, session_id: str | None = None, await_promise: bool = True) -> str:
        r = self.call("Runtime.evaluate", {
            "expression": expr,
            "returnByValue": True,
            "awaitPromise": await_promise,
            "userGesture": True,
        }, session_id)
        res = r.get("result", {}).get("result", {})
        if "value" in res:
            v = res["value"]
            return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
        return json.dumps(r, ensure_ascii=False)[:600]

    def close(self):
        try:
            self.ws.close()
        except Exception:  # noqa: BLE001
            pass


def open_tab(port: int, url: str, wait: float = 3.0):
    ws = browser_ws(port)
    s = Session(ws)
    r = s.call("Target.createTarget", {"url": url})
    target_id = r["result"]["targetId"]
    att = s.call("Target.attachToTarget", {"targetId": target_id, "flatten": True})
    sid = att["result"]["sessionId"]
    time.sleep(wait)
    return target_id, sid, s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=54670)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list")

    p_open = sub.add_parser("open")
    p_open.add_argument("url")
    p_open.add_argument("--eval", default="document.title")
    p_open.add_argument("--wait", type=float, default=3.5)
    p_open.add_argument("--keep", action="store_true", help="不关闭标签")

    p_eval = sub.add_parser("eval")
    p_eval.add_argument("--url", default=None, help="按 URL 关键字选已有标签")
    p_eval.add_argument("expr")

    p_ck = sub.add_parser("cookies")
    p_ck.add_argument("--filter", default="unipus")

    args = ap.parse_args()
    if args.cmd == "list":
        for t in http_json(f"http://127.0.0.1:{args.port}/json/list"):
            print(f"{t['type']:<8} {t.get('title','')[:40]:<42} {t['url'][:110]}")
        return 0

    if args.cmd == "open":
        target_id, sid, s = open_tab(args.port, args.url, args.wait)
        print("URL:", s.eval("location.href", sid))
        print("TITLE:", s.eval("document.title", sid))
        print("RESULT:", s.eval(args.eval, sid))
        if getattr(args, "close", False):
            s.call("Target.closeTarget", {"targetId": target_id})
        s.close()
        return 0

    if args.cmd == "cookies":
        targets = http_json(f"http://127.0.0.1:{args.port}/json/list")
        page = next(t for t in targets if t["type"] == "page")
        s = Session(page["webSocketDebuggerUrl"])
        r = s.call("Network.getAllCookies", {})
        s.close()
        for c in r.get("result", {}).get("cookies", []):
            if args.filter and args.filter not in c["domain"]:
                continue
            val = c.get("value", "")
            print(f"{c['domain']:<22} {'HttpOnly' if c.get('httpOnly') else '        '} "
                  f"{c['name']:<26} {val[:18]}{'…' if len(val) > 18 else ''}")
        return 0

    if args.cmd == "eval":
        targets = http_json(f"http://127.0.0.1:{args.port}/json/list")
        pick = None
        for t in targets:
            if t["type"] != "page":
                continue
            if args.url and args.url not in t["url"]:
                continue
            pick = t
            break
        if not pick:
            print("没找到匹配的标签页")
            return 1
        s = Session(pick["webSocketDebuggerUrl"])
        print(s.eval(args.expr))
        s.close()
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
