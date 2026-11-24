"""登录与会话管理。

两条入口：
  ① 账号密码（推荐）：SSO 4.0/sso/login → ssoreg 绑定 → wxlogin 取会话
  ② 短信验证码设密码：image_captcha → sms_code_captcha → update_password_phone_code → ①

会话缓存在 $UWORD_HOME/token.json（默认 ~/.uword/token.json），失效后调用 login() 重取。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .client import Client, code_of, payload


def sso(path: str, **fields) -> dict:
    """统一走 fltrp/openapi/sso.htm 这个网关，path 决定具体动作。"""
    c = Client(pacing=(0.0, 0.0))
    body = {"path": path}
    body.update({k: v for k, v in fields.items() if v is not None})
    return c.request("fltrp/openapi/sso.htm", params=body, auth=False)


def sso_login(username: str, password: str, captcha: str | None = None,
              encode_captha: str | None = None) -> dict:
    body = {"service": "https://word.fltrp.com/", "username": username, "password": password}
    if captcha:
        body["captchaCode"] = captcha
        body["encodeCaptha"] = encode_captha or ""
    r = sso("4.0/sso/login", **body)
    code = code_of(r)
    if code not in ("0", "20000", ""):
        msg = payload(r).get("msg") or r.get("error") or ""
        raise PermissionError(f"登录失败 [{code}] {msg}")
    rs = payload(r).get("rs") or r.get("rs") or {}
    if not rs.get("openid"):
        raise PermissionError(f"登录返回里没有 openid: {json.dumps(r, ensure_ascii=False)[:200]}")
    return rs


def sms_captcha() -> dict:
    r = sso("4.0/sso/image_captcha")
    rs = payload(r).get("rs") or r.get("rs") or {}
    if not rs.get("image"):
        raise RuntimeError(f"取验证码失败: {json.dumps(r, ensure_ascii=False)[:200]}")
    return {"image": rs["image"].replace("\r", "").replace("\n", ""),
            "type": rs.get("type", "image/jpeg"),
            "encode_captha": rs.get("encodeCaptha", "")}


def sms_send(phone: str, captcha_code: str, encode_captha: str) -> None:
    r = sso("4.0/sso/sms_code_captcha", linkType=0, phone=phone,
            captchaCode=captcha_code, encodeCaptha=encode_captha)
    code = code_of(r)
    if code not in ("0", ""):
        raise PermissionError(f"发短信失败 [{code}] {payload(r).get('msg') or ''}")


def sms_set_password(phone: str, code: str, new_password: str) -> None:
    r = sso("1.0/sso/update_password_phone_code", linkType=2, phone=phone,
            code=code, newPassword=new_password)
    c = code_of(r)
    if c not in ("0", ""):
        raise PermissionError(f"设密码失败 [{c}] {payload(r).get('msg') or ''}")


def sso_to_word(rs: dict, tel: str | None = None, email: str | None = None,
                usercode: str = "1") -> dict:
    """把 SSO 身份绑到外研U词账号并换回带会话串的用户对象。

    usercode: "1" = 学生（前端身份选择），"0" 会报"账号和选择的角色不一致"。
    """
    c = Client(pacing=(0.0, 0.0))
    openid = rs["openid"]
    c.ssoreg(tel=tel, email=email, openid=openid, suid=openid, usercode=usercode)
    user = c.wxlogin(openid)
    if not user.get("s"):
        raise PermissionError(
            "绑定成功但没拿到会话，检查 usercode 是否与账号角色一致"
            f"：{json.dumps(user, ensure_ascii=False)[:200]}")
    return user


class TokenStore:
    """会话缓存。位置优先级：UWORD_HOME/token.json → ~/.uword/token.json → ./.uword/token.json"""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else self._default()

    @staticmethod
    def _default() -> Path:
        env = os.environ.get("UWORD_HOME")
        cands = [Path(env)] if env else []
        cands += [Path.home() / ".uword", Path.cwd() / ".uword"]
        for base in cands:
            try:
                base.mkdir(parents=True, exist_ok=True)
                probe = base / ".w"
                probe.write_text("1", encoding="utf-8")
                probe.unlink()
                return base / "token.json"
            except OSError:
                continue
        return Path.cwd() / ".uword" / "token.json"

    def load(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return {}

    def save(self, user: dict) -> dict:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"token": user["s"], "user": {k: user.get(k) for k in
                ("id", "name", "company", "tel2", "openid", "usercode", "s")},
                "at": time.strftime("%F %T")}
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            self.path.chmod(0o600)
        except OSError:
            pass
        return data

    def clear(self) -> None:
        try:
            self.path.unlink()
        except OSError:
            pass


def login(username: str, password: str, usercode: str = "1",
          store: TokenStore | None = None) -> dict:
    """账号密码 → 会话；成功则写缓存。"""
    rs = sso_login(username, password)
    user = sso_to_word(rs, tel=username if "@" not in username else None,
                       email=username if "@" in username else None, usercode=usercode)
    (store or TokenStore()).save(user)
    return user


def login_with_sms(phone: str, new_password: str, captcha_code: str = "",
                   encode_captha: str = "", sms_code: str = "") -> dict:
    """两段式：先发短信（要图片验证码），再设密码并登录。"""
    if not sms_code:
        cap = sms_captcha()
        sms_send(phone, captcha_code, encode_captha or cap["encode_captha"])
        return {"need_sms_code": True, "captcha": cap}
    sms_set_password(phone, sms_code, new_password)
    return login(phone, new_password)


def current_token(refresh: bool = False) -> str:
    """取会话串：优先环境变量，其次缓存文件。"""
    env = os.environ.get("UWORD_TOKEN")
    if env and not refresh:
        return env
    data = TokenStore().load()
    if data.get("token") and not refresh:
        return data["token"]
    raise PermissionError("没有可用会话：先 uword login，或设置 UWORD_TOKEN")
