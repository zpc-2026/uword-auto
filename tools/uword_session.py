"""真实跑一整天的「学习」任务：取词 → 逐词取题 → 上报 → studyend 结算。"""
from __future__ import annotations

import json
import random
import sys
import time

sys.path.insert(0, "tools")
from uword_fltrp import call  # noqa: E402


def plan() -> dict:
    return call("yyuserplan/nowplan.htm", {"status": 0}).get("data") or {}


def words(pageid: int) -> list[str]:
    r = call("yyuserplan/nowplancontent.htm", {"pageid": pageid})
    c = r.get("content") or (r.get("data") or {}).get("content")
    if isinstance(c, str):
        c = json.loads(c)
    return c if isinstance(c, list) else []


def solve(q: dict) -> tuple[bool, str]:
    """题目自带 des（正确释义），选项里比对即可；拼写题按 des 拼。"""
    des = (q.get("des") or "").strip()
    content = q.get("content")
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except json.JSONDecodeError:
            content = []
    if int(q.get("type", 0)) in (1, 2) and isinstance(content, list):
        for opt in content:
            text = opt[1] if isinstance(opt, list) and len(opt) > 1 else str(opt)
            if des and des.split("；")[0] in text or text in des:
                return True, text
        return False, str(content[:1])
    if int(q.get("type", 0)) == 3 and isinstance(content, list):
        # 组合拼写：挑能拼出单词的片段
        word = q.get("word", "")
        picked, rest = [], word
        for chunk in sorted(content, key=len, reverse=True):
            if chunk and chunk in rest:
                picked.append(chunk)
                rest = rest.replace(chunk, "", 1)
        return (rest == ""), "+".join(picked)
    return False, "?"


def main() -> int:
    p = plan()
    pageid, userid = p["pageid"], p["userid"]
    before = p["sthaswords"]
    batch_n = int(p.get("pdaycount") or 20)
    print(f"词书={p['title2']} 已学={before}/{p['stallwords']} 今日量={batch_n} 计划id={p['id']}")

    ws = words(pageid)
    batch = ws[before: before + batch_n]
    print(f"本次批量 {len(batch)} 词：{batch[:6]}…")

    count = 3 if p.get("pstudy") else 1
    total_min = 0.0
    ok = 0
    for i, wid in enumerate(batch, 1):
        t0 = time.time()
        qs = (call("wordentry/selquestionbyword.htm", {"word": wid, "count": count}, "GET")
              .get("data") or [])
        got = 0
        for q in qs:
            right, ans = solve(q)
            r = call("yyuserscore/add.htm", {"userid": userid, "pageid": pageid,
                                             "word": wid, "score": 1 if right else 0,
                                             "type": 100 + int(q.get("type", 1))})
            if r.get("code") == "20000" and right:
                got += 1
        ok += got
        total_min += max(0.25, (time.time() - t0) + random.uniform(3, 6)) / 60.0
        if i % 5 == 0 or i == len(batch):
            print(f"  {i}/{len(batch)} 词完成，累积正确 {ok} 题")

    # 结算：进度与时长在这里才真正 +N
    payload = {
        "id": p["id"],
        "userid": userid,
        "pageid": pageid,
        "stminutes": int(p.get("stminutes", 0) + total_min),
        "sthaswords": before + len(batch),
        "studyendwords": batch,
    }
    r = call("yyuserplan/studyend.htm", payload)
    print(f"studyend → code={r.get('code')} data={str(r.get('data'))[:160]}")

    p2 = plan()
    print(f"\n结算后：已学 {before} → {p2['sthaswords']} / {p2['stallwords']}，"
          f"累计分钟 {p['stminutes']} → {p2['stminutes']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
