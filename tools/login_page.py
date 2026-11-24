"""本地登录页（只监听 127.0.0.1）：两种方式拿外研U词会话。

  ① 账号密码登录       → fltrp/openapi/sso.htm  4.0/sso/login
  ② 短信验证码设密码   → 1.0/sso/put_code_email + 1.0/sso/update_password_phone_code
                         然后立刻用新密码登录

    python tools/login_page.py --port 8899
"""
from __future__ import annotations

import argparse
import json
import ssl
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE = "https://word.fltrp.com/"
SERVICE = "https://word.fltrp.com/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
OUT = Path("tmp")

HTML = r"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>外研U词 · 本地登录</title><style>
 body{font-family:system-ui,"Microsoft YaHei";background:#0f1720;color:#e6edf3;display:flex;
      align-items:center;justify-content:center;height:100vh;margin:0}
 .card{background:#161b22;padding:26px 26px 22px;border-radius:14px;width:420px;
       box-shadow:0 10px 40px #0007}
 h1{font-size:16px;margin:0 0 4px} p.sub{color:#8b949e;font-size:12px;margin:0 0 16px;line-height:1.5}
 .tabs{display:flex;gap:8px;margin-bottom:14px}
 .tab{flex:1;text-align:center;padding:8px;border-radius:8px;background:#0d1117;
      border:1px solid #30363d;font-size:13px;cursor:pointer;color:#8b949e}
 .tab.on{background:#1f6feb22;border-color:#1f6feb;color:#58a6ff}
 label{display:block;font-size:12px;color:#8b949e;margin:10px 0 5px}
 input{width:100%;box-sizing:border-box;padding:9px 11px;border-radius:8px;border:1px solid #30363d;
       background:#0d1117;color:#e6edf3;font-size:14px;outline:none}
 input:focus{border-color:#2f81f7}
 button{width:100%;margin-top:14px;padding:10px;border:0;border-radius:8px;background:#238636;
        color:#fff;font-size:14px;cursor:pointer}
 button.gray{background:#30363d}
 button:disabled{opacity:.55;cursor:default}
 #msg{margin-top:12px;font-size:12.5px;line-height:1.6;white-space:pre-wrap;word-break:break-all}
 .ok{color:#3fb950} .err{color:#f85149} .hint{color:#8b949e}
 #capbox{display:none} #capimg{border-radius:6px;margin-top:6px;cursor:pointer;display:block}
 .row{display:flex;gap:8px} .row>input{flex:1} .row>button{width:120px;margin-top:0}
</style></head><body><div class="card">
 <h1>登录外研U词</h1>
 <p class="sub">本地页面：只监听 127.0.0.1，密码/验证码直接发往 word.fltrp.com 的官方接口，不写日志、不外传。</p>
 <div class="tabs">
  <div class="tab on" id="t1">账号密码</div>
  <div class="tab" id="t2">短信验证码 → 设密码</div>
 </div>

 <div id="pane1">
  <label>手机号 / 邮箱</label><input id="u" placeholder="11 位手机号" autocomplete="username">
  <label>密码</label><input id="p" type="password" autocomplete="current-password">
  <button id="b1">登录</button>
 </div>

 <div id="pane2" style="display:none">
  <label>手机号（接收短信）</label>
  <div class="row"><input id="phone" placeholder="11 位手机号"><button class="gray" id="bsend">发验证码</button></div>
  <label>短信验证码</label><input id="code" placeholder="6 位数字">
  <label>新密码（字母+数字，≥8 位）</label><input id="np" type="password">
  <button id="bset">设置密码并登录</button>
 </div>

 <div id="capbox"><label>图片验证码</label><input id="cap" placeholder="输入图片里的字符">
  <img id="capimg" title="点击刷新" width="110"></div>

 <div id="msg" class="hint">填好后点按钮。</div>
<script>
let encodeCaptha="", capNeeded=false;
const $=id=>document.getElementById(id);
const msg=(t,c)=>{$('msg').className=c||'hint';$('msg').textContent=t;};
function tab(n){
  $('t1').className='tab'+(n==1?' on':''); $('t2').className='tab'+(n==2?' on':'');
  $('pane1').style.display=n==1?'block':'none'; $('pane2').style.display=n==2?'block':'none';
}
$('t1').onclick=()=>tab(1);
$('t2').onclick=()=>{tab(2); refreshCap();};
function showCap(j){ encodeCaptha=j.encodeCaptha||''; capNeeded=true;
  $('capimg').src='data:'+(j.type||'image/png')+';base64,'+j.image;
  $('capbox').style.display='block'; }
async function refreshCap(){
  const r=await fetch('/api/captcha',{method:'POST'}); const j=await r.json();
  if(j.ok){ encodeCaptha=j.encodeCaptha; $('capimg').src='data:'+j.type+';base64,'+j.image;
    $('capbox').style.display='block'; capNeeded=true; msg('需要图片验证码，点图刷新后填。','hint'); }
  else { msg('取验证码失败：'+(j.msg||''),'err'); }
}
$('capimg').onclick=refreshCap;
$('b1').onclick=async()=>{
  const body={phone:$('u').value.trim(),password:$('p').value};
  if(!body.phone||!body.password) return msg('手机号和密码都要填。','err');
  if($('cap').value.trim()){body.captcha=$('cap').value.trim();body.encodeCaptha=encodeCaptha;}
  const b=$('b1'); b.disabled=true; msg('请求中…','hint');
  try{
    const j=await (await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(body)})).json();
    if(j.ok){ msg('登录成功。返回字段：'+(j.fields||[]).join(', ')+'\n\n回对话里说一声“好了”。','ok');
      b.textContent='已登录'; }
    else{ msg('失败：'+j.msg,'err'); b.disabled=false; if(j.need_captcha) refreshCap(); }
  }catch(e){ msg('本地请求出错：'+e,'err'); b.disabled=false; }
};
$('bsend').onclick=async()=>{
  const phone=$('phone').value.trim();
  if(phone.length<11) return msg('手机号要 11 位。','err');
  const b=$('bsend'); b.disabled=true; msg('发送中…','hint');
  try{
    const body={phone, captcha:$('cap').value.trim(), encodeCaptha};
    const j=await (await fetch('/api/sms',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(body)})).json();
    if(j.ok) msg('短信已发出，60 秒内注意查收。填好验证码和新密码再点下面那个按钮。','ok');
    else {
      msg('发送失败：'+j.msg,'err');
      if(j.image){ showCap(j); msg('先照图片填验证码，再点一次「发验证码」。','hint'); }
      else if(j.need_captcha) refreshCap();
    }
  }catch(e){ msg('本地请求出错：'+e,'err'); }
  setTimeout(()=>{b.disabled=false;},3000);
};
$('bset').onclick=async()=>{
  const body={phone:$('phone').value.trim(),code:$('code').value.trim(),newPassword:$('np').value};
  if(!body.phone||!body.code||!body.newPassword) return msg('手机号、验证码、新密码都要填。','err');
  if($('cap').value.trim()){body.captcha=$('cap').value.trim();body.encodeCaptha=encodeCaptha;}
  const b=$('bset'); b.disabled=true; msg('设置中…','hint');
  try{
    const j=await (await fetch('/api/setpass',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(body)})).json();
    if(j.ok){ msg('密码已设置并登录成功。\n返回字段：'+(j.fields||[]).join(', ')+'\n\n回对话里说一声“好了”。','ok');
      b.textContent='已完成'; }
    else{ msg('失败：'+j.msg,'err'); b.disabled=false; if(j.need_captcha) refreshCap(); }
  }catch(e){ msg('本地请求出错：'+e,'err'); b.disabled=false; }
};
</script></div></body></html>
"""


def post_sso(body: dict) -> dict:
    headers = {"User-Agent": UA, "Content-Type": "application/json;charset=UTF-8",
               "Accept": "application/json, text/plain, */*",
               "Origin": BASE.rstrip("/"), "Referer": BASE}
    req = urllib.request.Request(BASE + "fltrp/openapi/sso.htm",
                                 data=json.dumps(body, ensure_ascii=False).encode(),
                                 headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=25, context=CTX) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return {"code": f"HTTP{e.code}", "error": e.read(200).decode("utf-8", "replace")}
    except Exception as e:  # noqa: BLE001
        return {"code": "NETERR", "error": f"{type(e).__name__}: {e}"}


def payload(r: dict) -> dict:
    """真实返回是 {code:"20000", message:"SUCCESS", data:{...}}，业务码/结果都在 data 里。"""
    d = r.get("data")
    return d if isinstance(d, dict) else {}


def ok_payload(r: dict) -> bool:
    p = payload(r)
    return p.get("code") in (None, "", "0", "20000") and not p.get("msg", "").startswith("失败")


def inner(r: dict) -> tuple[str, str]:
    d = payload(r)
    return str(d.get("code") or ("" if str(r.get("code")) == "20000" else r.get("code") or "")), \
        str(d.get("msg") or r.get("error") or r.get("message") or "")


def need_captcha(code: str, msg: str) -> bool:
    return code in ("1506", "1507", "2019", "1305") or "验证码" in msg


class H(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):
        sys.stderr.write("[login-page] %s\n" % (fmt % a))

    def _send(self, obj, code=200, ctype="application/json; charset=utf-8"):
        body = obj.encode() if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            return self._send(HTML, ctype="text/html; charset=utf-8")
        return self._send({"ok": False, "msg": "not found"}, 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            data = json.loads(self.rfile.read(n).decode("utf-8", "replace") if n else "{}")
        except json.JSONDecodeError:
            return self._send({"ok": False, "msg": "bad json"}, 400)

        if self.path == "/api/captcha":
            r = post_sso({"path": "4.0/sso/image_captcha"})
            rs = payload(r).get("rs") or r.get("rs") or {}
            if rs.get("image"):
                return self._send({"ok": True, "type": rs.get("type", "image/png"),
                                   "image": rs["image"].replace("\r", "").replace("\n", ""),
                                   "encodeCaptha": rs.get("encodeCaptha", "")})
            return self._send({"ok": False, "msg": json.dumps(r, ensure_ascii=False)[:200]})

        if self.path == "/api/sms":
            phone = data.get("phone", "")
            cap = data.get("captcha", "").strip()
            enc = data.get("encodeCaptha", "")
            if not cap:
                r = post_sso({"path": "4.0/sso/image_captcha"})
                rs = payload(r).get("rs") or r.get("rs") or {}
                if rs.get("image"):
                    return self._send({"ok": False, "need_captcha": True,
                                       "type": rs.get("type", "image/png"),
                                       "image": rs["image"].replace("\r", "").replace("\n", ""),
                                       "encodeCaptha": rs.get("encodeCaptha", ""),
                                       "msg": "先填图片验证码，再点发验证码。"})
                return self._send({"ok": False, "msg": json.dumps(r, ensure_ascii=False)[:200]})
            r = post_sso({"path": "4.0/sso/sms_code_captcha", "linkType": 0,
                          "encodeCaptha": enc, "phone": phone, "captchaCode": cap})
            code, m = inner(r)
            if ok_payload(r) and code in ("", "0"):
                return self._send({"ok": True})
            return self._send({"ok": False, "msg": f"[{code}] {m}",
                               "need_captcha": need_captcha(code, m) or code == "1105"})

        if self.path == "/api/setpass":
            phone = data.get("phone", "")
            body = {"path": "1.0/sso/update_password_phone_code", "linkType": 2,
                    "newPassword": data.get("newPassword", ""), "code": data.get("code", ""),
                    "phone": phone}
            if data.get("captcha"):
                body["captchaCode"] = data["captcha"]
                body["encodeCaptha"] = data.get("encodeCaptha", "")
            r = post_sso(body)
            code, m = inner(r)
            if not (ok_payload(r) and code in ("", "0")):
                return self._send({"ok": False, "msg": f"[{code}] {m}",
                                   "need_captcha": need_captcha(code, m)})
            # 设完密码立刻登录
            lr = post_sso({"path": "4.0/sso/login", "service": SERVICE,
                           "username": phone, "password": data.get("newPassword", "")})
            lcode = inner(lr)[0]
            if ok_payload(lr) and lcode in ("", "0"):
                OUT.mkdir(exist_ok=True)
                (OUT / "sso.json").write_text(json.dumps(lr, ensure_ascii=False, indent=2),
                                              encoding="utf-8")
                rs = payload(lr).get("rs") or lr.get("rs") or {}
                return self._send({"ok": True, "fields": sorted(rs) if isinstance(rs, dict) else []})
            ic, im = inner(lr)
            return self._send({"ok": False, "msg": f"密码已设置，但登录失败 [{ic}] {im}"})

        if self.path == "/api/login":
            body = {"path": "4.0/sso/login", "service": SERVICE,
                    "username": data.get("phone", ""), "password": data.get("password", "")}
            if data.get("captcha"):
                body["captchaCode"] = data["captcha"]
                body["encodeCaptha"] = data.get("encodeCaptha", "")
            r = post_sso(body)
            ic0, im0 = inner(r)
            code = ic0 or str(r.get("code"))
            if ok_payload(r) and ic0 in ("", "0"):
                OUT.mkdir(exist_ok=True)
                (OUT / "sso.json").write_text(json.dumps(r, ensure_ascii=False, indent=2),
                                              encoding="utf-8")
                rs = payload(r).get("rs") or r.get("rs") or {}
                return self._send({"ok": True, "fields": sorted(rs) if isinstance(rs, dict) else []})
            return self._send({"ok": False, "msg": f"[{code}] {im0}",
                               "need_captcha": need_captcha(ic or code, im)})

        return self._send({"ok": False, "msg": "not found"}, 404)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8899)
    args = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), H)
    print(f"本地登录页: http://127.0.0.1:{args.port}/", flush=True)
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
