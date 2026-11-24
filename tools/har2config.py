"""把抓包 HAR 转成可用的 config.json。

用法：
    python tools/har2config.py --har capture.har --out config.json
    python tools/har2config.py --har capture.har --host api.xxx.cn --out config.json

做的事：
  1) 统计 HAR 里的 XHR/fetch 域名，选出业务域名当 base_url
  2) 抄出 token / Cookie / UA / Referer 等认证头
  3) 按路径关键词把接口映射到 book_list / word_list / quiz_list / quiz_submit / review_list ...
  4) 输出 config.json 和一份"待人工确认清单"
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "config.example.json"

STATIC_EXT = (".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".woff",
              ".woff2", ".ttf", ".mp3", ".mp4", ".ico", ".map")

# 关键词 → 端点 id（按优先级匹配，先命中先用）
PATH_RULES = [
    ("book_list", ["book/list", "books", "wordbook", "word_book", "textbook", "booklist"]),
    ("word_list", ["word/list", "words", "vocab/list", "wordlist", "unit/word", "new/word"]),
    ("learn_start", ["study/start", "learn/start", "begin", "session/start", "task/start"]),
    ("learn_word", ["study/word", "learn/word", "word/study", "record", "know"]),
    ("heartbeat", ["heartbeat", "duration", "time/upload", "tick", "stay"]),
    ("quiz_list", ["quiz/list", "question/list", "exercise", "test/list", "exam/list", "practice"]),
    ("review_list", ["review/list", "relearn", "wrong", "mistake", "复习"]),
    ("quiz_submit", ["submit", "answer", "check", "commit", "grade"]),
    ("progress", ["progress", "plan", "statistic", "report"]),
]

HEADER_KEEP = re.compile(r"^(user-agent|referer|origin|cookie|token|authorization|"
                         r"x-[\w-]+|sign|uid|openid|session|device)", re.I)


def load_entries(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    log = data.get("log") or {}
    return log.get("entries") or []


def norm_path(url: str) -> str:
    p = urlparse(url)
    return p.path or "/"


def is_xhr(entry: dict) -> bool:
    t = (entry.get("_resourceType") or "").lower()
    if t in ("xhr", "fetch"):
        return True
    mime = ((entry.get("response") or {}).get("content") or {}).get("mimeType") or ""
    return "json" in mime


def host_of(url: str) -> str:
    return urlparse(url).netloc


def pick_host(entries: list[dict], forced: str | None) -> tuple[str, str]:
    if forced:
        for e in entries:
            u = (e.get("request") or {}).get("url") or ""
            if forced in u:
                p = urlparse(u)
                return f"{p.scheme}://{p.netloc}", forced
        return f"https://{forced}", forced

    score: Counter = Counter()
    scheme: dict[str, str] = {}
    for e in entries:
        u = (e.get("request") or {}).get("url") or ""
        if not u.startswith("http"):
            continue
        h = host_of(u)
        if not h or h.endswith(STATIC_EXT):
            continue
        if any(urlparse(u).path.lower().endswith(ext) for ext in STATIC_EXT):
            continue
        w = 2 if is_xhr(e) else 1
        score[h] += w
        scheme[h] = urlparse(u).scheme or "https"
    if not score:
        raise SystemExit("HAR 里没有可用的 HTTP 请求，检查导出是否完整")
    host = score.most_common(1)[0][0]
    return f"{scheme.get(host, 'https')}://{host}", host


def pick_headers(entries: list[dict], host: str) -> dict:
    best = None
    best_score = -1
    for e in entries:
        u = (e.get("request") or {}).get("url") or ""
        if host not in u:
            continue
        hdrs = {h.get("name", ""): h.get("value", "")
                for h in ((e.get("request") or {}).get("headers") or [])}
        score = sum(1 for k in hdrs if HEADER_KEEP.match(k))
        if score > best_score:
            best, best_score = hdrs, score
    out = {}
    for k, v in (best or {}).items():
        if HEADER_KEEP.match(k) and v:
            out[k] = v
    # 归一化大小写不敏感键
    if not any(k.lower() == "user-agent" for k in out):
        out["User-Agent"] = "[MINIPROGRAM_UA]"
    return out


def map_endpoints(entries: list[dict], host: str) -> tuple[dict, list[str]]:
    found: dict[str, dict] = {}
    conflicts: dict[str, list[str]] = defaultdict(list)
    for e in entries:
        req = e.get("request") or {}
        u = req.get("url") or ""
        if host not in u:
            continue
        path = norm_path(u)
        low = path.lower()
        for ep, keys in PATH_RULES:
            if any(k.lower() in low for k in keys):
                method = (req.get("method") or "GET").upper()
                if ep in found and found[ep]["path"] != path:
                    conflicts[ep].append(path)
                    continue
                found[ep] = {"method": method, "path": path}
                break
    notes = []
    for ep, paths in conflicts.items():
        uniq = sorted(set(paths))[:4]
        notes.append(f"{ep}: 多个候选路径，已取第一个，其余待确认 {uniq}")
    return found, notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--har", required=True)
    ap.add_argument("--out", default="config.json")
    ap.add_argument("--host", default=None, help="强制指定业务域名")
    args = ap.parse_args()

    entries = load_entries(Path(args.har))
    if not entries:
        raise SystemExit("HAR 是空的")

    base_url, host = pick_host(entries, args.host)
    headers = pick_headers(entries, host)
    eps, notes = map_endpoints(entries, host)

    tpl = json.loads(TEMPLATE.read_text(encoding="utf-8")) if TEMPLATE.exists() else {}
    tpl["base_url"] = base_url
    tpl["headers"] = {**tpl.get("headers", {}), **headers}
    endpoints = tpl.setdefault("endpoints", {})
    missing = []
    for ep in ("book_list", "word_list", "learn_start", "learn_word", "heartbeat",
               "quiz_list", "review_list", "quiz_submit", "progress"):
        if ep in eps:
            endpoints[ep] = {**endpoints.get(ep, {}), **eps[ep]}
        else:
            missing.append(ep)

    out = Path(args.out)
    out.write_text(json.dumps(tpl, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"✓ 业务域名: {base_url}")
    print(f"✓ 认证头: {', '.join(sorted(headers)) or '(没抓到，需手动补)'}")
    print(f"✓ 命中端点 {len(eps)} 个: {', '.join(sorted(eps)) or '无'}")
    if missing:
        print(f"! 未命中（保留模板占位，去 HAR 里搜路径后手填）: {', '.join(missing)}")
    for n in notes:
        print(f"! {n}")
    print(f"\n已写出 {out.resolve()}")
    print("下一步：核对 POST 请求体字段（config.endpoints.*.json）与响应字段名（fields）后跑：")
    print("  python -m uword books      # 验证登录态")
    print("  python -m uword sync --book BOOK_ID")
    print("  python -m uword auto --book BOOK_ID --minutes 60")


if __name__ == "__main__":
    main()
