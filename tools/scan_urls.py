"""扫目录里的 URL 字符串，汇总唯一域名（找小程序接口域名用）。"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

URL = re.compile(rb"https?://[A-Za-z0-9\.\-]{3,80}(?::\d+)?[/A-Za-z0-9\._\-~%?=&+#]*")
HOST = re.compile(r"^https?://([A-Za-z0-9\.\-]+)")


def main(root: str, limit_mb: int = 40) -> int:
    r = Path(root)
    hosts: Counter = Counter()
    samples: dict[str, str] = {}
    files = 0
    for p in r.rglob("*"):
        if not p.is_file():
            continue
        try:
            size = p.stat().st_size
        except OSError:
            continue
        if size == 0 or size > limit_mb * 1024 * 1024:
            continue
        files += 1
        try:
            data = p.read_bytes()
        except OSError:
            continue
        for m in URL.finditer(data):
            u = m.group().decode("ascii", "ignore").rstrip('"\')],')
            hm = HOST.match(u)
            if not hm:
                continue
            h = hm.group(1).lower()
            hosts[h] += 1
            samples.setdefault(h, u[:160])
    print(f"扫描 {files} 个文件，命中 {len(hosts)} 个域名\n")
    for h, n in hosts.most_common(60):
        print(f"{n:>5}  {h:<45} {samples[h]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
