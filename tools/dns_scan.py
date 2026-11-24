"""子域枚举：对候选前缀做 DNS 解析，筛出 unipus 系业务域名。"""
from __future__ import annotations

import socket
import sys

PREFIXES = """uword uwords uwd uwcd uwdict vocab vocabulary word words wordbook uw
app api m mc wxa wx mp h5 u uc uclub uwp uwx uwb birdflock ucloud ucontent sso
datasink heep uai ulearning learn study quiz exam heepsso passport login account
static cdn img res file oss ceshi test dev pre prod wmp mpa miniapp miniprogram""".split()
DOMAINS = ["unipus.cn", "unipus.com", "fltrp.com", "fltrp.cn"]


def resolve(host: str) -> str | None:
    try:
        return socket.gethostbyname(host)
    except OSError:
        return None


def main() -> int:
    hits = []
    for d in DOMAINS:
        for p in PREFIXES:
            h = f"{p}.{d}"
            ip = resolve(h)
            if ip:
                hits.append((h, ip))
                print(f"OK   {h:<32} {ip}")
    print(f"\n命中 {len(hits)} 个")
    return 0


if __name__ == "__main__":
    sys.exit(main())
