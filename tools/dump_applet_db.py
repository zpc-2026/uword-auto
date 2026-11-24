"""只读检查 applet.db：列出表结构，并搜索与接口/token 相关的行。"""
from __future__ import annotations

import sqlite3
import sys


def main(path: str) -> int:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    cur = con.cursor()
    tabs = [r[0] for r in cur.execute(
        "select name from sqlite_master where type in ('table','view')")]
    print("TABLES:", tabs)
    for t in tabs:
        try:
            n = cur.execute(f'select count(*) from "{t}"').fetchone()[0]
            cols = [c[1] for c in cur.execute(f'PRAGMA table_info("{t}")')]
            print(f"-- {t}: rows={n} cols={cols}")
        except Exception as e:  # noqa: BLE001
            print(f"-- {t}: ERR {e}")

    print("\n=== 关键字命中 ===")
    keys = ("unipus", "uword", "tok", "http", "cookie", "book", "wx90b85")
    for t in tabs:
        cols = [c[1] for c in cur.execute(f'PRAGMA table_info("{t}")')]
        text_cols = [c for c in cols]
        where = " OR ".join(f'CAST("{c}" AS TEXT) LIKE ?' for c in text_cols)
        params = [f"%{k}%" for _ in text_cols]
        for k in keys:
            try:
                sql = f'select * from "{t}" where ' + " OR ".join(
                    f'CAST("{c}" AS TEXT) LIKE ?' for c in text_cols) + " limit 3"
                rows = cur.execute(sql, [f"%{k}%"] * len(text_cols)).fetchall()
            except Exception:  # noqa: BLE001
                continue
            for r in rows:
                s = str(r)
                print(f"[{t}/{k}] {s[:600]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "tmp/applet.db"))
