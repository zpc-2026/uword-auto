"""取证：清空站点存储后重载，看首次请求有没有 Authorization（判断会话是本地残留还是服务端发号）。"""
from __future__ import annotations

import json
import sys
import time

sys.path.insert(0, "tools")
import cdp  # noqa: E402


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9333
    origin = sys.argv[2] if len(sys.argv) > 2 else "https://word.fltrp.com"
    pg = [t for t in cdp.http_json(f"http://127.0.0.1:{port}/json/list") if t["type"] == "page"][0]
    s = cdp.Session(pg["webSocketDebuggerUrl"])
    print("清空全部存储:", s.call("Storage.clearDataForOrigin",
                             {"origin": origin, "storageTypes": "all"}).get("result"))
    s.call("Network.enable", {})
    s.call("Page.enable", {})
    s.call("Page.reload", {"ignoreCache": True})

    rows, bodies = [], []
    start = time.time()
    while time.time() - start < 10:
        try:
            s.ws.settimeout(1.0)
            d = json.loads(s.ws.recv())
        except Exception:  # noqa: BLE001
            continue
        m = d.get("method")
        p = d.get("params", {})
        if m == "Network.requestWillBeSent":
            req = p["request"]
            hdrs = req.get("headers") or {}
            auth = any(k.lower() == "authorization" for k in hdrs)
            rows.append((p["requestId"], req["method"], req["url"][:110], auth))
        elif m == "Network.responseReceived":
            body = None
            if p.get("type") in ("XHR", "Fetch") and len(bodies) < 4:
                body = p
            if body:
                bodies.append(body)

    print(f"\n首次加载请求 {len(rows)} 个：")
    for rid, meth, url, auth in rows[:15]:
        print(f"  {meth:<5} {'AUTH' if auth else '    '}  {url}")

    print("\n前 4 个 XHR 响应：")
    for b in bodies:
        try:
            r = s.call("Network.getResponseBody", {"requestId": b["requestId"]})
            txt = (r.get("result") or {}).get("body", "")[:300]
        except Exception as e:  # noqa: BLE001
            txt = f"<取 body 失败 {e}>"
        print(f"  {b['response']['url'][:100]}\n    {txt}")

    print("\nlocalStorage:", s.eval(
        "JSON.stringify({ls:Object.keys(localStorage),"
        "uid:(()=>{try{return JSON.parse(localStorage.getItem('user')||'null')?.data?.id}"
        "catch(e){return null}})()})"))
    s.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
