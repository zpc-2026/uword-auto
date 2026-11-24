"""外研U词（word.fltrp.com）后端客户端。

所有请求都是 HTTP + JSON，鉴权只有一个头：Authorization: <会话串>。
会话失效时接口返回 {"code":"50000","error":"用户登录超时"}，抛 AuthExpired。
"""
from __future__ import annotations

import json
import random
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://word.fltrp.com/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")
SERVICE = BASE


class AuthExpired(Exception):
    """会话失效，需要重新登录。"""


class ApiError(Exception):
    """业务错误。"""


def payload(resp: dict):
    """真实返回 {code:"20000", message:"SUCCESS", data:{...}|[...]}，业务数据在 data 里。

    注意 data 可能是 dict（计划/用户）也可能是 list（题目、复习队列），两种都要原样放行。
    """
    if not isinstance(resp, dict):
        return {}
    d = resp.get("data")
    return d if isinstance(d, (dict, list)) else {}


def code_of(resp: dict) -> str:
    p = payload(resp)
    if p.get("code") not in (None, ""):
        return str(p.get("code"))
    if isinstance(p.get("rs"), (dict, list)):
        return "0"
    return str(resp.get("code") or "")


class Client:
    def __init__(self, token: str | None = None, timeout: float = 20.0,
                 retries: int = 3, pacing: tuple[float, float] = (0.15, 0.35),
                 logger=None):
        self.token = token
        self.timeout = timeout
        self.retries = retries
        self.pacing = pacing
        self.log = logger or (lambda *a, **k: None)
        self.calls = 0
        self.errors = 0
        self._ctx = ssl.create_default_context()
        self._ctx.check_hostname = False
        self._ctx.verify_mode = ssl.CERT_NONE

    # ---------- 底层 ----------
    def _sleep(self) -> None:
        lo, hi = self.pacing
        if hi > 0:
            time.sleep(random.uniform(lo, hi))

    def request(self, path: str, params: dict | None = None, method: str = "POST",
                auth: bool = True, body: dict | None = None) -> dict:
        url = BASE + path.lstrip("/")
        data = None
        headers = {"User-Agent": UA, "Accept": "application/json, text/plain, */*",
                   "Origin": BASE.rstrip("/"), "Referer": BASE}
        if auth and self.token:
            headers["Authorization"] = self.token
        if method.upper() == "GET":
            if params:
                url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        else:
            data = json.dumps(body if body is not None else (params or {}),
                              ensure_ascii=False).encode()
            headers["Content-Type"] = "application/json;charset=UTF-8"

        last = None
        for attempt in range(1, self.retries + 1):
            self._sleep()
            req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
            try:
                self.calls += 1
                with urllib.request.urlopen(req, timeout=self.timeout, context=self._ctx) as r:
                    raw = r.read().decode("utf-8", "replace")
                return json.loads(raw) if raw.strip() else {}
            except urllib.error.HTTPError as e:
                self.errors += 1
                text = e.read(200).decode("utf-8", "replace")
                last = f"HTTP {e.code} {text}"
                if e.code in (401, 403):
                    raise AuthExpired(last) from e
            except urllib.error.URLError as e:
                self.errors += 1
                last = f"URLError {e.reason}"
            except json.JSONDecodeError as e:
                self.errors += 1
                last = f"非 JSON 响应 {e}"
            if attempt < self.retries:
                time.sleep(min(15.0, 2 ** attempt + random.uniform(0, 1)))
        raise ApiError(f"{path} 请求失败: {last}")

    def _check(self, resp: dict, name: str) -> dict:
        if not isinstance(resp, dict):
            return resp
        c = str(resp.get("code") or "")
        if c == "50000":
            raise AuthExpired(f"[{name}] {resp.get('error') or resp.get('message')}")
        if c and c not in ("20000", "0"):
            raise ApiError(f"[{name}] code={c} {resp.get('error') or resp.get('message')}")
        return resp

    def call(self, path: str, params: dict | None = None, method: str = "POST",
             auth: bool = True) -> dict:
        return self._check(self.request(path, params, method, auth), path)

    # ---------- 账号 ----------
    def wxlogin(self, openid: str, type_: int = 0, source: str = "miniappid") -> dict:
        r = self.call("yyuser/openapi/wxlogin.htm",
                      {"openid": openid, "type": type_, "source": source}, "GET", auth=False)
        return payload(r)

    def ssoreg(self, tel: str | None = None, email: str | None = None, openid: str = "",
               suid: str = "", usercode: str = "1", source: str = "miniappid",
               type_: int = 0) -> dict:
        body = {"openid": openid, "suid": suid, "type": type_, "source": source,
                "usercode": usercode, "isAd": 0}
        if tel:
            body["tel"] = tel
        if email:
            body["email"] = email
        return payload(self.call("yyuser/openapi/ssoreg.htm", body, auth=False))

    # ---------- 计划 ----------
    def nowplan(self, status: int = 0) -> dict:
        return payload(self.call("yyuserplan/nowplan.htm", {"status": status}))

    def nowst(self, userid: int | None = None) -> dict:
        return payload(self.call("yyuserplan/nowst.htm", {"userid": userid} if userid else {"status": 0}))

    def plan_words(self, pageid: int) -> list[str]:
        p = payload(self.call("yyuserplan/nowplancontent.htm", {"pageid": pageid}))
        content = p.get("content")
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                return []
        return content if isinstance(content, list) else []

    def save_plan(self, plan: dict) -> dict:
        return payload(self.call("yyuserplan/add.htm", plan))

    # ---------- 学习 / 检验 ----------
    def questions(self, word_id: str, count: int = 3) -> list[dict]:
        r = self.call("wordentry/selquestionbyword.htm",
                      {"word": word_id, "count": count}, "GET")
        d = payload(r)
        if isinstance(d, list):
            return d
        data = d.get("data") if isinstance(d, dict) else None
        return data if isinstance(data, list) else []

    def add_score(self, **fields) -> dict:
        return payload(self.call("yyuserscore/add.htm", fields))

    def study_end(self, **fields) -> dict:
        return payload(self.call("yyuserplan/studyend.htm", fields))

    # ---------- 复习 ----------
    def review_queue(self, userid: int, pageid: int, recount: int, type_: int) -> list[dict]:
        p = payload(self.call("yyuserscore/todayre.htm",
                              {"userid": userid, "pageid": pageid,
                               "recount": recount, "type": type_}))
        return p if isinstance(p, list) else []
