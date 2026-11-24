"""给其他 agent / 其他设备调用的高层接口。

所有函数只吃简单类型、只吐可 json 化的 dict，不依赖当前工作目录。

    from uword.agent import api
    api.login("181xxxxxxxx", "密码")      # 一次即可，会话会缓存
    print(api.status())
    api.learn(20)
    api.review(200)

环境变量：
    UWORD_HOME    会话缓存目录（默认 ~/.uword）
    UWORD_TOKEN   直接给会话串，跳过登录
    UWORD_USER / UWORD_PASS   会话过期时自动重登
"""
from __future__ import annotations

import os

from ..fltrp import auth, ops
from ..fltrp.client import ApiError, AuthExpired, Client

DEFAULT_QUESTIONS = {"pstudy0": 1, "pstudy1": 3}


def make_client(token: str | None = None) -> Client:
    return Client(token=token or auth.current_token())


def _with_retry(fn, *a, **kw):
    """会话过期且环境里配了账号密码时，自动重登一次。"""
    try:
        return fn(*a, **kw)
    except AuthExpired:
        user, pwd = os.environ.get("UWORD_USER"), os.environ.get("UWORD_PASS")
        if not (user and pwd):
            raise
        auth.login(user, pwd)
        return fn(*a, **kw)


def login(username: str | None = None, password: str | None = None,
          usercode: str = "1") -> dict:
    user, pwd = username or os.environ.get("UWORD_USER"), password or os.environ.get("UWORD_PASS")
    if not (user and pwd):
        return {"ok": False, "message": "缺账号密码（参数或 UWORD_USER/UWORD_PASS）"}
    u = auth.login(user, pwd, usercode=usercode)
    return {"ok": True, "user": {k: u.get(k) for k in
                                 ("id", "name", "company", "tel2", "openid", "usercode")},
            "token_saved": str(auth.TokenStore().path)}


def status() -> dict:
    client = make_client()
    return _with_retry(ops.status, client)


def learn(count: int = 20, questions_per_word: int | None = None,
          word_seconds: float = 0.0) -> dict:
    client = make_client()
    return _with_retry(ops.learn, client, count=count,
                       questions_per_word=questions_per_word, word_seconds=word_seconds)


def review(limit: int = 200) -> dict:
    client = make_client()
    return _with_retry(ops.review, client, limit=limit)


def auto(learn_count: int = 20, review_limit: int = 200,
         word_seconds: float = 0.0) -> dict:
    out = {"learn": None, "review": None}
    try:
        out["learn"] = learn(learn_count, word_seconds=word_seconds) if learn_count else None
        out["review"] = review(review_limit) if review_limit else None
        out["status"] = status()
        out["ok"] = True
    except (AuthExpired, ApiError, PermissionError, RuntimeError) as e:
        out["ok"] = False
        out["message"] = f"{type(e).__name__}: {e}"
    return out


def set_plan(pstudy: int | None = None, pdaycount: int | None = None) -> dict:
    client = make_client()
    return _with_retry(ops.set_plan, client, pstudy=pstudy, pdaycount=pdaycount)
