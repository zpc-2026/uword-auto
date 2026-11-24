"""真实接口上跑一个词的「学习 + 检验 + 上报」，并对比计划进度。"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, "tools")
from uword_fltrp import call  # noqa: E402


def plan() -> dict:
    r = call("yyuserplan/nowplan.htm", {"status": 0})
    return r.get("data") or {}


def words(pageid: int) -> list[str]:
    r = call("yyuserplan/nowplancontent.htm", {"pageid": pageid})
    content = r.get("content") or (r.get("data") or {}).get("content")
    if isinstance(content, str):
        content = json.loads(content)
    return content if isinstance(content, list) else []


def main() -> int:
    p0 = plan()
    pageid, userid = p0["pageid"], p0["userid"]
    learned0 = p0["sthaswords"]
    print(f"词书: {p0['title2']}  总词量={p0['stallwords']}  已学={learned0}  "
          f"每日量={p0['pdaycount']}  计划id={p0['id']}")

    ws = words(pageid)
    print(f"词表 {len(ws)} 个 id")
    idx = learned0 if learned0 < len(ws) else len(ws) - 1
    wid = ws[idx]
    print(f"下一个待学 index={idx} word={wid}")

    q = call("wordentry/selquestionbyword.htm", {"word": wid, "count": 1}, "GET")
    qs = q.get("data") or []
    print(f"取到题目 {len(qs)} 道，type={[x['type'] for x in qs]}")
    if qs:
        first = qs[0]
        print(f"  单词={first['word']} 词性={first['cat']} 释义={first['des']}")
        opts = json.loads(first["content"]) if isinstance(first["content"], str) else first["content"]
        print(f"  选项={opts}")

    for item in qs:
        r = call("yyuserscore/add.htm", {"userid": userid, "pageid": pageid,
                                         "word": wid, "score": 1,
                                         "type": 100 + int(item["type"])})
        print(f"  上报 type={100 + int(item['type'])} → code={r.get('code')} "
              f"data={str(r.get('data'))[:100]}")

    p1 = plan()
    print(f"\n进度对比: 已学 {learned0} → {p1['sthaswords']}  天数={p1['stdays']}  "
          f"累计分钟={p1['stminutes']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
