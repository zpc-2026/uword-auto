"""本地嗅探代理：只记录目标域名/URL + TLS SNI，不劫持内容（盲转发）。

用途：把系统/小程序代理指到 127.0.0.1:8888，就能看到它到底在请求哪个域名。

    python tools/proxy_sniff.py --port 8888
    # 然后设置 HKCU 代理：
    #   reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings" /v ProxyEnable /t REG_DWORD /d 1 /f
    #   reg add "HKCU\\...\\Internet Settings" /v ProxyServer /t REG_SZ /d 127.0.0.1:8888 /f
"""
from __future__ import annotations

import argparse
import socket
import socketserver
import struct
import sys
import threading
import time
from pathlib import Path

LOG_LOCK = threading.Lock()
LOG_PATH = Path("proxy.log")


def log(line: str) -> None:
    ts = time.strftime("%H:%M:%S")
    text = f"[{ts}] {line}"
    print(text, flush=True)
    with LOG_LOCK:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(text + "\n")


def parse_sni(data: bytes) -> str | None:
    """从 TLS ClientHello 里抠 SNI。"""
    try:
        if len(data) < 45 or data[0] != 0x16:
            return None
        pos = 5 + 4  # record header + handshake header
        pos += 2 + 32  # version + random
        sid_len = data[pos]
        pos += 1 + sid_len
        cs_len = struct.unpack(">H", data[pos:pos + 2])[0]
        pos += 2 + cs_len
        cm_len = data[pos]
        pos += 1 + cm_len
        ext_total = struct.unpack(">H", data[pos:pos + 2])[0]
        pos += 2
        end = pos + ext_total
        while pos + 4 <= end:
            etype, elen = struct.unpack(">HH", data[pos:pos + 4])
            pos += 4
            if etype == 0x00:  # server_name
                p = pos + 2
                ntype = data[p]
                nlen = struct.unpack(">H", data[p + 1:p + 3])[0]
                if ntype == 0:
                    return data[p + 3:p + 3 + nlen].decode("ascii", "ignore")
            pos += elen
    except Exception:  # noqa: BLE001
        return None
    return None


def relay(a: socket.socket, b: socket.socket) -> None:
    try:
        while True:
            chunk = a.recv(65536)
            if not chunk:
                break
            b.sendall(chunk)
    except OSError:
        pass
    finally:
        for s in (a, b):
            try:
                s.close()
            except OSError:
                pass


class Handler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        client = self.request
        client.settimeout(20)
        try:
            head = client.recv(65536)
        except OSError:
            return
        if not head:
            return
        first_line = head.split(b"\r\n", 1)[0].decode("latin-1", "ignore")
        if first_line.upper().startswith("CONNECT"):
            target = first_line.split()[1]
            host, _, port = target.partition(":")
            port = int(port or 443)
            log(f"CONNECT {host}:{port}")
            try:
                upstream = socket.create_connection((host, port), timeout=15)
            except OSError as e:
                client.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
                log(f"  ! 连接失败 {host}:{port} {e}")
                client.close()
                return
            client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            try:
                client.settimeout(5)
                peek = client.recv(4096, socket.MSG_PEEK)
                sni = parse_sni(peek)
                if sni:
                    log(f"  SNI  {sni}  (→ {host})")
            except OSError:
                pass
            client.settimeout(None)
            t = threading.Thread(target=relay, args=(client, upstream), daemon=True)
            t.start()
            relay(upstream, client)
        else:
            # 明文 HTTP
            try:
                line = first_line
                log(f"HTTP  {line[:200]}")
                hostport = "127.0.0.1:80"
                for h in head.split(b"\r\n")[1:]:
                    if h.lower().startswith(b"host:"):
                        hostport = h.split(b":", 1)[1].strip().decode("latin-1")
                        break
                host, _, port = hostport.partition(":")
                upstream = socket.create_connection((host, int(port or 80)), timeout=15)
                upstream.sendall(head)
                t = threading.Thread(target=relay, args=(client, upstream), daemon=True)
                t.start()
                relay(upstream, client)
            except Exception as e:  # noqa: BLE001
                log(f"  ! 明文转发失败 {e}")
                client.close()


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8888)
    ap.add_argument("--bind", default="127.0.0.1")
    args = ap.parse_args()
    srv = Server((args.bind, args.port), Handler)
    log(f"proxy sniffing on {args.bind}:{args.port} → {LOG_PATH.resolve()}")
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
