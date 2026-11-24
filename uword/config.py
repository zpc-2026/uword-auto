"""配置装载与默认端点模板。

真实域名 / 路径 / 字段名都要从抓包（HAR）里替换，这里只给出可直接跑通 mock 的骨架。
"""
from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path

DEFAULTS = {
    "base_url": "https://[API_HOST]",
    "headers": {
        "User-Agent": "[MINIPROGRAM_UA]",
        "Referer": "https://servicewechat.com/[APPID]/[VERSION]/page-frame.html",
        "Accept": "application/json, text/plain, */*",
        "token": "[TOKEN]",
        "Cookie": "[COOKIE]",
        "X-Device-Id": "[DEVICE_ID]",
    },
    "timeout": 15,
    "retry": 3,
    # 拟人节奏：任意两次请求之间的间隔（秒）
    "pacing": {"min_gap": 0.9, "max_gap": 2.8, "burst": 3},
    "limits": {
        "words_per_run": 40,     # 单次最多学多少新词
        "page_size": 30,         # 列表分页大小
        "quiz_rounds": 3,        # 单词检验最多刷几轮
        "review_rounds": 8,      # 复习最多刷几轮
        "max_minutes": 60,       # auto 模式总时长
        "fail_budget": 12,       # 连续/累计失败上限，超了就停
    },
    "timing": {
        "word_seconds": [6, 14],     # 每个新词停留时长（拟人）
        "heartbeat_every": [18, 32],  # 心跳包间隔（累积学习时长）
        "rest_every_words": [12, 18], # 每学 N 个词歇一次
        "rest_seconds": [20, 55],
    },
    "map": {
        "code": ["code", "errcode", "status", "errno"],
        "ok": [0, 200, "0", "200", "success", "ok", True],
        "msg": ["msg", "message", "errmsg", "info"],
        "data": ["data", "result", "payload"],
        "auth_fail": [401, 403, 1001, 1002, "401", "403"],
    },
    "fields": {
        "id": ["id", "wordId", "word_id"],
        "word": ["word", "spell", "en", "name"],
        "meaning": ["meaning", "trans", "translation", "cn", "transCn"],
        "list": ["list", "items", "rows", "records", "questions", "words"],
        "total": ["total", "count", "totalCount", "totalNum"],
        "quiz_id": ["quizId", "quiz_id", "questionId", "id"],
        "qtype": ["type", "quizType", "qtype", "questionType"],
        "stem": ["stem", "sentence", "title", "content", "question", "prompt"],
        "hint": ["hint", "pattern", "letters", "mask", "spell"],
        "word_id": ["wordId", "word_id", "wid"],
        "word_hint": ["word", "spell"],
        "options": ["options", "choices", "optionList", "answers", "items"],
        "option_key": ["key", "id", "value", "optionId"],
        "option_text": ["text", "content", "name", "word", "meaning", "title"],
        "session_id": ["sessionId", "session_id", "sid", "recordId"],
        "result_right": ["right", "correct", "isRight", "isCorrect", "pass", "result"],
        "result_answer": ["correct", "correctAnswer", "rightAnswer", "answerKey", "standard", "answer"],
    },
    "endpoints": {
        "book_list": {"method": "GET", "path": "/api/v1/book/list", "params": {}},
        "word_list": {"method": "GET", "path": "/api/v1/word/list",
                      "params": {"bookId": "{book_id}", "page": "{page}", "size": "{size}"}},
        "learn_start": {"method": "POST", "path": "/api/v1/study/start",
                        "json": {"bookId": "{book_id}"}},
        "learn_word": {"method": "POST", "path": "/api/v1/study/word",
                       "json": {"wordId": "{word_id}", "cost": "{cost}", "know": "{know}"}},
        "heartbeat": {"method": "POST", "path": "/api/v1/study/heartbeat",
                      "json": {"sessionId": "{session_id}", "cost": "{cost}"}},
        "quiz_list": {"method": "GET", "path": "/api/v1/quiz/list",
                      "params": {"bookId": "{book_id}", "page": "{page}", "size": "{size}"}},
        "review_list": {"method": "GET", "path": "/api/v1/review/list",
                        "params": {"bookId": "{book_id}", "page": "{page}", "size": "{size}"}},
        "quiz_submit": {"method": "POST", "path": "/api/v1/quiz/submit",
                        "json": {"quizId": "{quiz_id}", "answer": "{answer}", "cost": "{cost}"}},
        "progress": {"method": "GET", "path": "/api/v1/study/progress",
                     "params": {"bookId": "{book_id}"}},
    },
    # 答题策略链，从左到右尝试
    "answer_chain": ["bank", "index", "echo", "guess"],
    "storage": "uword.db",
    "answer_bank": "answer_bank.json",
    "log_file": "uword.log",
}


def _merge(base, over):
    if isinstance(base, dict) and isinstance(over, dict):
        out = deepcopy(base)
        for k, v in over.items():
            out[k] = _merge(out[k], v) if k in out else deepcopy(v)
        return out
    return deepcopy(over)


class Config:
    def __init__(self, data: dict):
        self.data = data

    @classmethod
    def load(cls, path: str | None = None, base_url: str | None = None) -> "Config":
        data = deepcopy(DEFAULTS)
        if path:
            p = Path(path)
            if not p.exists():
                raise SystemExit(f"配置文件不存在: {p}")
            data = _merge(data, json.loads(p.read_text(encoding="utf-8-sig")))
        token = os.environ.get("UWORD_TOKEN")
        if token:
            data.setdefault("headers", {})["token"] = token
        cookie = os.environ.get("UWORD_COOKIE")
        if cookie:
            data.setdefault("headers", {})["Cookie"] = cookie
        if base_url:
            data["base_url"] = base_url.rstrip("/")
        return cls(data)

    def get(self, path: str, default=None):
        cur = self.data
        for part in path.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

    @property
    def endpoints(self) -> dict:
        return self.data.get("endpoints", {})

    def endpoint(self, name: str) -> dict | None:
        ep = self.endpoints.get(name)
        return ep if isinstance(ep, dict) and ep.get("path") else None

    def has(self, name: str) -> bool:
        return self.endpoint(name) is not None
