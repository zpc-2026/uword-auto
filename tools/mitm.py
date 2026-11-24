"""本地 HTTPS 中间人代理：抓小程序请求头里的 Authorization。

前提：certs/ca.cer 已装进当前用户根存储（certutil -addstore -user Root certs\\ca.cer）。

    python tools/mitm.py --port 8888
    # 然后把系统代理指到 127.0.0.1:8888，打开外研U词小程序
"""
from __future__ import annotations

import argparse
import json
import socket
import socketserver
import ssl
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CERT = ROOT / "certs" / "leaf.crt"
KEY = ROOT / "certs" / "leaf.key"
CAP = ROOT / "tmp" / "capture"
TOKEN_OUT = ROOT / "tmp" / "token_applet.json"
LOG = ROOT / "tmp" / "mitm.log"

MITM_SUFFIX = ("fltrp.com", "fltrp.cn", "unipus.cn")
LOCK = threading.Lock()
FOUND: dict[str, str] = {}


def log(line: str) -> None:
    ts = time.strftime("%H:%M:%S")
    text = f"[{ts}] {line}"
    print(text, flush=True)
    LOG.parent.mkdir(exist_ok=True)
    with LOCK:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(text + "\n")


def want_mitm(host: str) -> bool:
    return any(host.endswith(s) for s in MITM_SUFFIX)


def read_until(sock: socket.socket, marker: bytes, limit: int = 1 << 20) -> bytes:
    buf = b""
    while marker not in buf:
        chunk = sock.recv(8192)
        if not chunk:
            break
        buf += chunk
        if len(buf) > limit:
            break
    return buf


def parse_headers(raw: bytes):
    head, _, rest = raw.partition(b"\r\n\r\n")
    lines = head.split(b"\r\n")
    start = lines[0].decode("latin-1", "ignore")
    headers = []
    for ln in lines[1:]:
        if b":" in ln:
            k, v = ln.split(b":", 1)
            headers.append((k.decode("latin-1").strip(), v.decode("latin-1").strip()))
    return start, headers, rest


def body_len(headers) -> int:
    for k, v in headers:
        if k.lower() == "content-length":
            try:
                return int(v)
            except ValueError:
                return 0
    return 0


def chunked(headers) -> bool:
    return any(k.lower() == "transfer-encoding" and "chunked" in v.lower() for k, v in headers)


def read_chunked(sock: socket.socket, buf: bytes) -> bytes:
    data = buf
    while b"\r\n0\r\n\r\n" not in data and not data.endswith(b"0\r\n\r\n"):
        chunk = sock.recv(8192)
        if not chunk:
            break
        data += chunk
        if len(data) > 4 << 20:
            break
    return data


class Handler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        cli: socket.socket = self.request
        cli.settimeout(30)
        try:
            head = read_until(cli, b"\r\n\r\n")
            if not head:
                return
            start, headers, _ = parse_headers(head)
            if not start.upper().startswith("CONNECT"):
                cli.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")
                return
            host, _, port = start.split()[1].partition(":")
            port = int(port or 443)
            cli.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            if not want_mitm(host):
                self._tunnel(cli, host, port)
                return
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(str(CERT), str(KEY))
            tls = ctx.wrap_socket(cli, server_side=True)
            self._pump(tls, host, port)
        except Exception as e:  # noqa: BLE001
            log(f"! {self.client_address} {type(e).__name__}: {e}")
        finally:
            try:
                cli.close()
            except OSError:
                pass

    def _tunnel(self, cli, host, port):
        up = socket.create_connection((host, port), timeout=15)
        def relay(a, b):
            try:
                while True:
                    d = a.recv(65536)
                    if not d:
                        break
                    b.sendall(d)
            except OSError:
                pass
            finally:
                for s in (a, b):
                    try:
                        s.close()
                    except OSError:
                        pass
        threading.Thread(target=relay, args=(cli, up), daemon=True).start()
        relay(up, cli)

    def _pump(self, tls: ssl.SSLSocket, host: str, port: int):
        upctx = ssl.create_default_context()
        upctx.check_hostname = False
        upctx.verify_mode = ssl.CERT_NONE
        while True:
            raw = read_until(tls, b"\r\n\r\n")
            if not raw:
                return
            start, headers, rest = parse_headers(raw)
            n = body_len(headers)
            body = rest
            while len(body) < n:
                chunk = tls.recv(8192)
                if not chunk:
                    break
                body += chunk
            body = body[:n] if n else body
            auth = next((v for k, v in headers if k.lower() == "authorization"), None)
            log(f"→ {host} {start}" + (f"  [Authorization: {auth[:12]}…]" if auth else ""))
            CAP.mkdir(exist_ok=True)
            with (CAP / "requests.log").open("a", encoding="utf-8") as f:
                f.write(json.dumps({"host": host, "start": start,
                                    "headers": headers,
                                    "body": body.decode("utf-8", "replace")[:2000]},
                                   ensure_ascii=False) + "\n")
            if auth:
                with LOCK:
                    FOUND.setdefault(host, auth)
                TOKEN_OUT.parent.mkdir(exist_ok=True)
                TOKEN_OUT.write_text(json.dumps({"token": auth, "host": host,
                                                 "at": time.strftime("%F %T")},
                                                ensure_ascii=False), encoding="utf-8")
                log(f"★ 抓到 Authorization → {TOKEN_OUT}")

            up = upctx.wrap_socket(socket.create_connection((host, port), timeout=20),
                                   server_hostname=host)
            up.sendall(raw)
            resp_head = read_until(up, b"\r\n\r\n")
            rstart, rheaders, rrest = parse_headers(resp_head)
            rn = body_len(rheaders)
            rbody = rrest
            if chunked(rheaders):
                rbody = read_chunked(up, rrest)
            else:
                while len(rbody) < rn:
                    chunk = up.recv(8192)
                    if not chunk:
                        break
                    rbody += chunk
                rbody = rbody[:rn] if rn else rbody
            up.close()
            tls.sendall(resp_head + rbody if not resp_head.endswith(b"\r\n\r\n") else resp_head + rbody)
            log(f"← {host} {rstart}  {rbody[:120]!r}")
            if "close" in dict((k.lower(), v.lower()) for k, v in headers).get("connection", ""):
                return


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8888)
    args = ap.parse_args()
    if not CERT.exists():
        print("缺证书，先跑证书生成那步")
        return 1
    LOG.parent.mkdir(exist_ok=True)
    log(f"MITM 代理启动 127.0.0.1:{args.port}  目标={MITM_SUFFIX}")
    Server(("127.0.0.1", args.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
