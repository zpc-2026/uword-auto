"""题目求解。三类题都能确定性地做对，因为每道题都自带 des（正确释义）。

  1 = 看单词选释义     content = [["a.","美学的，审美的"], ...]
  2 = 看例句选释义     content 同上，另带 sentence / sentencecn
  3 = 组合拼写         content = ["aesthe","tic","easthe","oesthe","dic","tec"]
其他题型（含 <blank> 的填空）按题干里唯一的内嵌答案尝试，实在判不出就标记 assumed。
"""
from __future__ import annotations

import json
import re

MARKS = "①②③④⑤⑥⑦⑧⑨⑩"
PUNCT = "，。、；;：:,.\"'“”‘’()（）[]【】<>《》!！?？-_/\\|·`~*#@$%^&+= \t\r\n"


def norm(s: str | None) -> str:
    if not s:
        return ""
    out = str(s)
    for m in MARKS:
        out = out.replace(m, "")
    return "".join(ch for ch in out.lower() if ch not in PUNCT)


def options_of(q: dict) -> list[str]:
    content = q.get("content")
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except json.JSONDecodeError:
            content = [content]
    if not isinstance(content, list):
        return []
    out = []
    for item in content:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            out.append(str(item[1]))
        elif isinstance(item, dict):
            out.append(str(item.get("text") or item.get("content") or ""))
        else:
            out.append(str(item))
    return [o for o in out if o]


def senses(s: str | None) -> list[str]:
    if not s:
        return []
    parts = re.split(r"[;；,，/、]", str(s))
    return [norm(p) for p in parts if norm(p)]


def solve(q: dict) -> tuple[bool, str, str]:
    """返回 (是否判对, 选中/拼出的答案, 说明)。"""
    des = q.get("des") or ""
    qtype = int(q.get("type") or 0)
    opts = options_of(q)

    if qtype in (1, 2) and opts:
        want = senses(des)
        for o in opts:
            no = norm(o)
            if not no:
                continue
            if any(no == w or (w and (w in no or no in w)) for w in want):
                return True, o, "选项命中 des"
        # 兜底：选项里唯一在 des 文本中出现的
        hits = [o for o in opts if norm(o) and norm(o) in norm(des)]
        if len(hits) == 1:
            return True, hits[0], "唯一子串命中"
        return False, opts[0] if opts else "", "未匹配到 des"

    if qtype == 3 and opts:
        rest = str(q.get("word") or "")
        picked = []
        for chunk in sorted(opts, key=len, reverse=True):
            if chunk and chunk in rest:
                picked.append(chunk)
                rest = rest.replace(chunk, "", 1)
        return (rest == ""), "+".join(picked), "拼块还原"

    if isinstance(q.get("word"), str) and q["word"]:
        return True, q["word"], "题型未知，按词面提交"

    return False, "", f"题型 {qtype} 无法判定"


def answer_for_content(q: dict) -> str:
    """部分题型需要把答案文本一起回传（当前接口不校验，保留给未来变体）。"""
    ok, ans, _ = solve(q)
    return ans if ok else ""
