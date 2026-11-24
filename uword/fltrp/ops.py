"""业务动作：状态 / 学习 / 复习 / 改计划。全部返回可直接 json 化的 dict。"""
from __future__ import annotations

import random
import time

from .client import Client
from .solver import solve

PLAN_FIELDS = ["pageid", "id", "psort", "pdaycount", "paudio", "pstudy",
               "prestudy", "prestudycount", "stdays", "stallwords"]


def _snap(p: dict) -> dict:
    return {k: p.get(k) for k in ("title2", "pageid", "userid", "id", "sthaswords",
                                  "stallwords", "stminutes", "rankscore", "stdays",
                                  "pdaycount", "pstudy", "strestudydays")}


def status(client: Client) -> dict:
    p = client.nowplan()
    if not p:
        raise RuntimeError("nowplan 没有返回数据，会话可能无效")
    queue = client.review_queue(p["userid"], p["pageid"],
                                p.get("prestudycount") or 0, p.get("prestudy") or 0)
    words = client.plan_words(p["pageid"])
    return {"plan": _snap(p), "review_queue": len(queue),
            "words_total": len(words), "requests": client.calls}


def learn(client: Client, count: int = 20, questions_per_word: int | None = None,
          word_seconds: float = 0.0, progress=None) -> dict:
    p = client.nowplan()
    pageid, userid = p["pageid"], p["userid"]
    before = int(p["sthaswords"])
    words = client.plan_words(pageid)
    if not words:
        return {"ok": False, "message": "词表为空"}
    batch = words[before: before + count]
    if not batch:
        return {"ok": False, "message": "没有待学新词了", "before": _snap(p)}

    per_word = questions_per_word if questions_per_word is not None else (3 if p.get("pstudy") else 1)
    right = wrong = asked = 0
    assumed = 0
    spent = 0.0
    for i, wid in enumerate(batch, 1):
        t0 = time.time()
        for q in client.questions(wid, per_word):
            ok, ans, why = solve(q)
            asked += 1
            if ok:
                right += 1
            else:
                wrong += 1
            if "未知" in why:
                assumed += 1
            client.add_score(userid=userid, pageid=pageid, word=wid,
                             score=1 if ok else 0, type=100 + int(q.get("type") or 1))
        if word_seconds > 0:
            time.sleep(random.uniform(word_seconds * 0.7, word_seconds * 1.3))
        spent += max(0.0, time.time() - t0) / 60.0
        if progress:
            progress(i, len(batch), right, wrong)

    minutes = max(1, int(round(spent)))
    client.study_end(id=p["id"], userid=userid, pageid=pageid,
                     stminutes=int(p.get("stminutes") or 0) + minutes,
                     sthaswords=before + len(batch), studyendwords=batch)
    after = client.nowplan()
    return {"ok": True, "learned": len(batch), "questions": asked,
            "right": right, "wrong": wrong, "assumed": assumed,
            "minutes_added": minutes, "before": _snap(p), "after": _snap(after),
            "requests": client.calls}


def review(client: Client, limit: int = 200, progress=None) -> dict:
    p = client.nowplan()
    userid, pageid = p["userid"], p["pageid"]
    queue = client.review_queue(userid, pageid,
                                p.get("prestudycount") or 0, p.get("prestudy") or 0)
    if not queue:
        return {"ok": True, "reviewed": 0, "queue_before": 0, "queue_after": 0,
                "message": "复习队列为空"}

    todo = queue[:limit]
    done = 0
    for item in todo:
        client.add_score(id=item.get("id"), recount=item.get("recount"),
                         userid=userid, pageid=pageid, word=item.get("word"),
                         score=0, type=2)
        done += 1
        if progress:
            progress(done, len(todo))
    client.study_end(id=p["id"], userid=userid, pageid=pageid,
                     strestudydays=int(p.get("strestudydays") or 0) + 1,
                     streminutes=int(p.get("streminutes") or 0) + max(1, done // 5),
                     stminutes=int(p.get("stminutes") or 0) + max(1, done // 5))
    after = client.nowplan()
    left = client.review_queue(userid, pageid,
                               after.get("prestudycount") or 0, after.get("prestudy") or 0)
    return {"ok": True, "reviewed": done, "queue_before": len(queue),
            "queue_after": len(left), "before": _snap(p), "after": _snap(after),
            "requests": client.calls}


def set_plan(client: Client, pstudy: int | None = None,
             pdaycount: int | None = None) -> dict:
    p = client.nowplan()
    body = {k: p.get(k) for k in PLAN_FIELDS}
    if pstudy is not None:
        body["pstudy"] = int(pstudy)
    if pdaycount is not None:
        body["pdaycount"] = int(pdaycount)
    client.save_plan(body)
    q = client.nowplan()
    if q.get("id") != p.get("id") or q.get("sthaswords") != p.get("sthaswords"):
        return {"ok": False, "message": "计划被重建了，进度可能受影响",
                "before": _snap(p), "after": _snap(q)}
    return {"ok": True, "before": _snap(p), "after": _snap(q)}
