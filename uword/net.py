"""纯标准库 HTTP 客户端：cookie 复用、重试、错误码归一、响应字段拣选。"""
from __future__ import annotations

import http.cookiejar
import json
import random
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request


class AuthExpired(Exception):
    """登录态失效，需要重新抓 token。"""


class ApiError(Exception):
    """业务错误码。"""


def _safe_format(template, ctx: dict):
    """把 {key} 替换成 ctx 里的值，未知占位符原样保留（方便逐层排查）。"""
    if isinstance(template, dict):
        return {k: _safe_format(v, ctx) for k, v in template.items()}
    if isinstance(template, list):
        return [_safe_format(v, ctx) for v in template]
    if not isinstance(template, str):
        return template

    def repl(m):
        key = m.group(1)
        if key in ctx and ctx[key] is not None:
            return str(ctx[key])
        return m.group(0)

    return re.sub(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", repl, template)


class HttpClient:
    def __init__(self, cfg, pacer=None, logger=None):
        self.cfg = cfg
        self.base = cfg.get("base_url", "").rstrip("/")
        self.headers = {k: v for k, v in (cfg.get("headers") or {}).items() if v}
        self.timeout = float(cfg.get("timeout", 15))
        self.retry = int(cfg.get("retry", 3))
        self.pacer = pacer
        self.log = logger or (lambda *a, **k: None)
        self.jar = http.cookiejar.CookieJar()
        ctx = ssl.create_default_context()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar),
            urllib.request.HTTPSHandler(context=ctx),
        )
        self.request_count = 0
        self.error_count = 0

    # ---------- 底层 ----------
    def request(self, method: str, path: str, params=None, body=None, headers=None) -> dict:
        if path.startswith("http"):
            url = path
        else:
            if not path.startswith("/"):
                path = "/" + path
            url = self.base + path
        if params:
            clean = {k: v for k, v in params.items() if v is not None}
            if clean:
                sep = "&" if "?" in url else "?"
                url = url + sep + urllib.parse.urlencode(clean, doseq=True)

        data = None
        hdrs = dict(self.headers)
        hdrs.setdefault("Accept-Encoding", "identity")
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            hdrs.setdefault("Content-Type", "application/json;charset=UTF-8")
        if headers:
            hdrs.update(headers)

        last_err = None
        for attempt in range(1, self.retry + 1):
            if self.pacer:
                self.pacer.wait()
            req = urllib.request.Request(url, data=data, headers=hdrs, method=method.upper())
            try:
                self.request_count += 1
                with self.opener.open(req, timeout=self.timeout) as resp:
                    raw = resp.read().decode("utf-8", "replace")
                return self._parse(raw, url)
            except urllib.error.HTTPError as e:
                self.error_count += 1
                text = ""
                try:
                    text = e.read().decode("utf-8", "replace")[:500]
                except Exception:
                    pass
                if e.code in (401, 403):
                    raise AuthExpired(f"{e.code} {url} :: {text}") from e
                last_err = f"HTTP {e.code} {text}"
            except urllib.error.URLError as e:
                self.error_count += 1
                last_err = f"URLError {e.reason}"
            except json.JSONDecodeError as e:
                self.error_count += 1
                last_err = f"JSONDecode {e}"
            except Exception as e:  # noqa: BLE001
                self.error_count += 1
                last_err = f"{type(e).__name__} {e}"
            if attempt < self.retry:
                backoff = min(20.0, (2 ** attempt) + random.uniform(0, 1.5))
                self.log(f"  ! 请求失败({attempt}/{self.retry}) {last_err} → {backoff:.1f}s 后重试")
                time.sleep(backoff)
        raise ApiError(f"请求彻底失败: {url} :: {last_err}")

    def _parse(self, raw: str, url: str) -> dict:
        raw = raw.strip()
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            raise ApiError(f"非 JSON 响应 {url} :: {raw[:200]}")

    # ---------- 端点调用 ----------
    def has(self, name: str) -> bool:
        return self.cfg.has(name)

    def call(self, name: str, ctx: dict | None = None) -> dict:
        ep = self.cfg.endpoint(name)
        if not ep:
            raise ApiError(f"配置里没有端点 {name}")
        ctx = ctx or {}
        params = _safe_format(ep.get("params") or {}, ctx)
        body = _safe_format(ep.get("json") or ep.get("body") or {}, ctx) if (
            ep.get("json") or ep.get("body")) else None
        resp = self.request(ep.get("method", "GET"), ep["path"], params=params, body=body)
        self.check_code(resp, name)
        return resp

    def check_code(self, resp: dict, name: str = "?") -> None:
        if not isinstance(resp, dict):
            return
        code_keys = self.cfg.get("map.code", ["code"])
        for ck in code_keys:
            if ck in resp:
                code = resp[ck]
                ok = self.cfg.get("map.ok", [0])
                if code in ok:
                    return
                if code in self.cfg.get("map.auth_fail", []):
                    raise AuthExpired(f"[{name}] 登录态失效 code={code} msg={self.msg(resp)}")
                raise ApiError(f"[{name}] code={code} msg={self.msg(resp)}")
        return

    def msg(self, resp: dict) -> str:
        for k in self.cfg.get("map.msg", []):
            if isinstance(resp, dict) and k in resp:
                return str(resp[k])
        return ""

    def data(self, resp: dict):
        if not isinstance(resp, dict):
            return resp
        for k in self.cfg.get("map.data", ["data"]):
            if k in resp:
                return resp[k]
        return resp

    # ---------- 字段拣选 ----------
    def pick(self, obj: dict, field: str, default=None):
        """按 fields.<field> 的候选键顺序取第一个存在的值。"""
        if not isinstance(obj, dict):
            return default
        for key in self.cfg.get(f"fields.{field}", [field]):
            if key in obj and obj[key] not in (None, ""):
                return obj[key]
        return default

    def list_of(self, payload) -> list:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in self.cfg.get("fields.list", ["list"]):
                v = payload.get(key)
                if isinstance(v, list):
                    return v
        return []

    def total_of(self, payload) -> int:
        if isinstance(payload, dict):
            for key in self.cfg.get("fields.total", ["total"]):
                if key in payload:
                    try:
                        return int(payload[key])
                    except (TypeError, ValueError):
                        return 0
        return 0
