"""本地假接口：完全离线跑通 learn → quiz → review 流水线（自检用）。

它按 config.example.json 里的默认路径实现，行为上模拟真实小程序后端：
  · 词书 / 词表分页
  · 学习会话 + 心累计时长
  · 检验题目（选释义、选单词、拼写、选词填空"硬题"）
  · 提交判分，答错进复习队列，答对移除
  · 同一 quizId 答错后重试，靠本地答案库命中即可通过（验证自学习）
"""
from __future__ import annotations

import argparse
import json
import random
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

WORDS = [
    ("acquire", "获得；习得"), ("ambitious", "有雄心的"), ("benefit", "益处；好处"),
    ("campaign", "活动；运动"), ("despite", "尽管"), ("efficient", "高效的"),
    ("feature", "特征；特点"), ("generate", "产生；生成"), ("hypothesis", "假设"),
    ("illustrate", "说明；举例说明"), ("justify", "证明…正当"), ("maintain", "维持；保养"),
    ("negotiate", "谈判；协商"), ("obvious", "明显的"), ("participate", "参与"),
    ("qualify", "使合格；取得资格"), ("relevant", "相关的"), ("significant", "重要的；显著的"),
    ("transform", "转变；改造"), ("ultimate", "最终的"), ("valid", "有效的"),
    ("withdraw", "撤回；取款"), ("abundant", "丰富的；充足的"), ("complex", "复杂的"),
]

BOOK_ID = "mock-book"
STATE = {
    "learned": set(),
    "quiz_pending": {},      # word_id -> set(quiz_id)
    "review_pending": set(),  # word_id
    "session": None,
    "heartbeat_ms": 0,
}

WORD_ROWS = [
    {"id": f"w{i+1:03d}", "word": w, "meaning": m} for i, (w, m) in enumerate(WORDS)
]
BY_ID = {r["id"]: r for r in WORD_ROWS}

_QUIZ: dict[str, dict] = {}


def _mask(word: str) -> str:
    n = len(word)
    hide = 2 if n >= 6 else 1
    idx = sorted(random.sample(range(n), hide))
    chars = list(word)
    for i in idx:
        chars[i] = "_"
    return "".join(chars)


def _distract(field: str, exclude: str, k: int = 3) -> list[str]:
    pool = [r[field] for r in WORD_ROWS if r[field] != exclude]
    random.shuffle(pool)
    return pool[:k]


def build_quizzes() -> None:
    """每个词 3 题，前两个词额外加一道无上下文的"硬题"（考验答案库自学习）。"""
    _QUIZ.clear()
    for i, r in enumerate(WORD_ROWS):
        wid, w, m = r["id"], r["word"], r["meaning"]
        # q1 看英文选中文
        opts = [m] + _distract("meaning", m)
        random.shuffle(opts)
        qid = f"{wid}-q1"
        _QUIZ[qid] = {"word_id": wid, "correct": m, "type": "meaning_choice",
                      "opts": opts}
        # q2 看中文选英文
        opts2 = [w] + _distract("word", w)
        random.shuffle(opts2)
        qid2 = f"{wid}-q2"
        _QUIZ[qid2] = {"word_id": wid, "correct": w, "type": "word_choice"}
        # q3 拼写（掩码固定，保证同一题多次拉取一致）
        qid3 = f"{wid}-q3"
        _QUIZ[qid3] = {"word_id": wid, "correct": w, "type": "spell", "hint": _mask(w)}
        if i < 2:
            qid4 = f"{wid}-q4"
            _QUIZ[qid4] = {"word_id": wid, "correct": w, "type": "cloze"}


def _options_payload(correct: str, others: list[str]) -> list[dict]:
    opts = [correct] + others
    random.shuffle(opts)
    return [{"key": str(i), "text": t} for i, t in enumerate(opts)]


def question_payload(qid: str) -> dict:
    meta = _QUIZ[qid]
    wid = meta["word_id"]
    row = BY_ID[wid]
    t = meta["type"]
    if t == "meaning_choice":
        return {"quizId": qid, "type": t, "wordId": wid, "word": row["word"],
                "stem": row["word"], "options": meta["opts"]}
    if t == "word_choice":
        return {"quizId": qid, "type": t, "wordId": wid, "meaning": row["meaning"],
                "stem": row["meaning"],
                "options": _options_payload(row["word"], _distract("word", row["word"]))}
    if t == "spell":
        return {"quizId": qid, "type": t, "wordId": wid, "meaning": row["meaning"],
                "hint": meta.get("hint"), "stem": meta.get("hint")}
    if t == "cloze":
        return {"quizId": qid, "type": t, "wordId": wid,
                "stem": "The team tried to ____ the whole process within a month.",
                "options": _options_payload(row["word"], _distract("word", row["word"]))}
    return {"quizId": qid, "type": t, "options": []}


def pending_questions(offset: int, limit: int) -> list[dict]:
    ids = []
    for wid, qids in STATE["quiz_pending"].items():
        if wid not in STATE["learned"]:
            continue
        for q in sorted(qids):
            ids.append(q)
    ids.sort()
    return [question_payload(q) for q in ids[offset:offset + limit]]


def review_questions(offset: int, limit: int) -> list[dict]:
    out = []
    for wid in sorted(STATE["review_pending"])[offset:offset + limit]:
        row = BY_ID[wid]
        out.append({"quizId": f"{wid}-r1", "type": "review_choice", "wordId": wid,
                    "meaning": row["meaning"], "stem": row["meaning"],
                    "options": _options_payload(row["word"], _distract("word", row["word"]))})
    return out


def submit(qid: str, answer: str) -> dict:
    meta = _QUIZ.get(qid)
    if not meta and qid.endswith("-r1"):
        wid = qid[:-3]
        meta = {"word_id": wid, "correct": BY_ID[wid]["word"], "type": "review_choice"}
    if not meta:
        return {"code": 404, "msg": "题目不存在"}
    wid = meta["word_id"]
    correct = meta["correct"]
    ok = str(answer).strip().lower() == str(correct).strip().lower()
    if ok:
        STATE["quiz_pending"].get(wid, set()).discard(qid)
        if not STATE["quiz_pending"].get(wid):
            STATE["quiz_pending"].pop(wid, None)
        STATE["review_pending"].discard(wid)
        return {"code": 0, "msg": "ok", "data": {"right": True, "correct": correct}}
    if qid in _QUIZ:
        # 真实产品：检验做错不重做，直接扔进复习队列
        STATE["quiz_pending"].get(wid, set()).discard(qid)
        if not STATE["quiz_pending"].get(wid):
            STATE["quiz_pending"].pop(wid, None)
        STATE["review_pending"].add(wid)
    return {"code": 0, "msg": "ok", "data": {"right": False, "correct": correct}}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # 静默
        pass

    def _send(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        page, size = int(q.get("page", 1)), int(q.get("size", 30))
        if u.path == "/api/v1/book/list":
            return self._send({"code": 0, "data": {"list": [
                {"id": BOOK_ID, "name": "外研U词·模拟词书", "total": len(WORD_ROWS)}]}})
        if u.path == "/api/v1/word/list":
            start = (page - 1) * size
            rows = WORD_ROWS[start:start + size]
            return self._send({"code": 0, "data": {"list": rows, "total": len(WORD_ROWS)}})
        if u.path == "/api/v1/quiz/list":
            off = (page - 1) * size
            return self._send({"code": 0, "data": {
                "list": pending_questions(off, size),
                "total": sum(len(v) for v in STATE["quiz_pending"].values())}})
        if u.path == "/api/v1/review/list":
            off = (page - 1) * size
            return self._send({"code": 0, "data": {
                "list": review_questions(off, size),
                "total": len(STATE["review_pending"])}})
        if u.path == "/api/v1/study/progress":
            return self._send({"code": 0, "data": {"learned": len(STATE["learned"]),
                                                   "total": len(WORD_ROWS)}})
        return self._send({"code": 404, "msg": "no route"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        body = self._body()
        if u.path == "/api/v1/study/start":
            STATE["session"] = "sess-0001"
            return self._send({"code": 0, "data": {"sessionId": STATE["session"]}})
        if u.path == "/api/v1/study/word":
            wid = str(body.get("wordId"))
            if wid not in BY_ID:
                return self._send({"code": 404, "msg": "bad wordId"})
            STATE["learned"].add(wid)
            qids = {q for q in _QUIZ if q.startswith(wid + "-")}
            STATE["quiz_pending"][wid] = qids
            return self._send({"code": 0, "data": {"ok": True}})
        if u.path == "/api/v1/study/heartbeat":
            STATE["heartbeat_ms"] += int(body.get("cost") or 0)
            return self._send({"code": 0, "data": {"total": STATE["heartbeat_ms"]}})
        if u.path == "/api/v1/quiz/submit":
            return self._send(submit(str(body.get("quizId")), str(body.get("answer"))))
        return self._send({"code": 404, "msg": "no route"}, 404)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8899)
    args = ap.parse_args()
    build_quizzes()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"mock server on http://127.0.0.1:{args.port}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
