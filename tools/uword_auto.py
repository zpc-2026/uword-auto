"""外研U词 真实全自动：今日学习批次 + 今日复习队列（直接调 word.fltrp.com）。

    python tools/uword_auto.py --learn 20 --review 80
    python tools/uword_auto.py --review 80 --only-review
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time

sys.path.insert(0, "tools")
from uword_fltrp import call  # noqa: E402


def plan() -> dict:
    return call("yyuserplan/nowplan.htm", {"status": 0}).get("data") or {}


def all_words(pageid: int) -> list[str]:
    r = call("yyuserplan/nowplancontent.htm", {"pageid": pageid})
    c = r.get("content") or (r.get("data") or {}).get("content")
    if isinstance(c, str):
        c = json.loads(c)
    return c if isinstance(c, list) else []


def solve(q: dict) -> bool:
    des = (q.get("des") or "").strip()
    content = q.get("content")
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except json.JSONDecodeError:
            content = []
    t = int(q.get("type", 0) or 0)
    if t in (1, 2) and isinstance(content, list):
        for opt in content:
            text = opt[1] if isinstance(opt, list) and len(opt) > 1 else str(opt)
            if not text:
                continue
            if text in des or des.split("；")[0] in text:
                return True
        return False
    if t == 3 and isinstance(content, list):
        rest = str(q.get("word", ""))
        for chunk in sorted(content, key=len, reverse=True):
            if chunk and chunk in rest:
                rest = rest.replace(chunk, "", 1)
        return rest == ""
    return False


def do_learn(p: dict, n: int) -> tuple[int, float]:
    pageid, userid = p["pageid"], p["userid"]
    start = p["sthaswords"]
    ws = all_words(pageid)
    batch = ws[start:start + n]
    if not batch:
        print("· 已经没有待学新词")
        return 0, 0.0
    count = 3 if p.get("pstudy") else 1
    minutes, done = 0.0, 0
    print(f"== 学习 {len(batch)} 词（每题 {count} 问）==")
    for i, wid in enumerate(batch, 1):
        qs = (call("wordentry/selquestionbyword.htm", {"word": wid, "count": count}, "GET")
              .get("data") or [])
        for q in qs:
            right = solve(q)
            call("yyuserscore/add.htm", {"userid": userid, "pageid": pageid, "word": wid,
                                         "score": 1 if right else 0,
                                         "type": 100 + int(q.get("type", 1))})
            time.sleep(random.uniform(0.15, 0.45))
        minutes += random.uniform(0.15, 0.4)
        done += 1
        if i % 5 == 0 or i == len(batch):
            print(f"  {i}/{len(batch)} 词")
    r = call("yyuserplan/studyend.htm", {
        "id": p["id"], "userid": userid, "pageid": pageid,
        "stminutes": int(p.get("stminutes", 0) + minutes),
        "sthaswords": start + len(batch), "studyendwords": batch})
    print(f"  结算 code={r.get('code')}")
    return done, minutes


def do_review(p: dict, limit: int) -> int:
    pageid, userid = p["pageid"], p["userid"]
    r = call("yyuserscore/todayre.htm", {"userid": userid, "pageid": pageid,
                                         "recount": p.get("prestudycount"),
                                         "type": p.get("prestudy")})
    queue = r.get("data") or []
    if not isinstance(queue, list) or not queue:
        print("· 复习队列为空")
        return 0
    print(f"== 复习队列 {len(queue)} 词，处理前 {min(limit, len(queue))} 个 ==")
    done = 0
    for item in queue[:limit]:
        call("yyuserscore/add.htm", {"id": item.get("id"), "recount": item.get("recount"),
                                     "userid": userid, "pageid": pageid,
                                     "word": item.get("word"), "score": 0, "type": 2})
        done += 1
        if done % 20 == 0:
            print(f"  {done} 个")
        time.sleep(random.uniform(0.12, 0.35))
    r2 = call("yyuserplan/studyend.htm", {
        "id": p["id"], "userid": userid, "pageid": pageid,
        "strestudydays": int(p.get("strestudydays", 0)) + 1,
        "streminutes": int(p.get("streminutes", 0) + done * 0.2),
        "stminutes": int(p.get("stminutes", 0) + done * 0.2)})
    print(f"  复习结算 code={r2.get('code')}")
    return done


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--learn", type=int, default=20)
    ap.add_argument("--review", type=int, default=0)
    ap.add_argument("--only-review", action="store_true")
    args = ap.parse_args()

    p0 = plan()
    print(f"起点: {p0['title2']}  已学 {p0['sthaswords']}/{p0['stallwords']}  "
          f"天数 {p0['stdays']}  复习天数 {p0.get('strestudydays')}")
    if not args.only_review:
        do_learn(p0, args.learn)
        p0 = plan()
    if args.review:
        do_review(p0, args.review)
    p1 = plan()
    print(f"\n结果: 已学 {p1['sthaswords']}/{p1['stallwords']} 天数 {p1['stdays']} "
          f"积分 {p1.get('rankscore')} 累计分钟 {p1['stminutes']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
