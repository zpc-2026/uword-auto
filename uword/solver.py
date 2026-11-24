"""答题求解器。

策略链（可配置 answer_chain）：
  bank  —— 本地答案库（提交反馈会自动回填，越刷越准）
  index —— 离线词表反查：中义↔英文、字母提示正则匹配（拼写题主力）
  echo  —— 题干/选项自洽（选项里出现目标词、题干唯一包含某选项）
  guess —— 兜底（排除法 + 已错选项降权）
"""
from __future__ import annotations

import random
import re
import string
from dataclasses import dataclass, field

PUNCT = "，。、；;：:,.\"'“”‘’()（）[]【】<>《》!！?？-_/\\|·`~*#@$%^&+= \t\r\n"

SPELL_WORDS = ("spell", "拼写", "组合", "assemble", "letters", "word_form", "spelling")
CHOICE_WORDS = ("choice", "select", "choose", "选择", "单选")


def norm(s: str | None) -> str:
    if not s:
        return ""
    s = str(s).lower()
    return "".join(ch for ch in s if ch not in PUNCT)


def senses(s: str | None) -> set[str]:
    """把 'n. 苹果；宝物' 拆成多个候选义项。"""
    if not s:
        return set()
    out = set()
    for part in re.split(r"[;；,，/、|]", str(s)):
        n = norm(part)
        if n:
            out.add(n)
            out.add(norm(re.sub(r"^[a-z]{1,5}\.\s*", "", part)))
    return out


@dataclass
class Question:
    quiz_id: str
    qtype: str
    stem: str = ""
    word_id: str | None = None
    word: str | None = None
    meaning: str | None = None
    hint: str | None = None
    options: list[dict] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    @property
    def is_spell(self) -> bool:
        t = (self.qtype or "").lower()
        if self.hint and ("_" in self.hint or "*" in self.hint):
            return True
        return any(k in t for k in SPELL_WORDS) or (not self.options and not self.word)

    def describe(self) -> str:
        bits = [f"type={self.qtype}"]
        if self.word:
            bits.append(f"word={self.word}")
        if self.meaning:
            bits.append(f"cn={self.meaning}")
        if self.hint:
            bits.append(f"hint={self.hint}")
        if self.options:
            bits.append(f"opts={len(self.options)}")
        return " ".join(bits)


@dataclass
class Answer:
    value: str | None = None
    key: str | None = None
    source: str = "none"
    confidence: float = 0.0


class Solver:
    def __init__(self, cfg, store, client, log=None):
        self.cfg = cfg
        self.store = store
        self.client = client
        self.log = log or (lambda *a, **k: None)
        self.chain = cfg.get("answer_chain", ["bank", "index", "echo", "guess"])
        self.word2meaning: dict[str, str] = {}
        self.meaning2word: dict[str, str] = {}
        self.used_wrong: dict[str, set] = {}
        self.stats = {"bank": 0, "index": 0, "echo": 0, "guess": 0, "none": 0,
                      "correct": 0, "wrong": 0, "unknown": 0}

    # ---------- 索引 ----------
    def build_index(self, book_id: str | None = None) -> None:
        self.word2meaning.clear()
        self.meaning2word.clear()
        for row in self.store.all_words(book_id):
            w = (row.get("word") or "").strip()
            m = (row.get("meaning") or "").strip()
            if not w:
                continue
            self.word2meaning[norm(w)] = m
            for s in senses(m):
                self.meaning2word.setdefault(s, w.lower())
        self.log(f"  · 离线词表: {len(self.word2meaning)} 词 / {len(self.meaning2word)} 义项")

    # ---------- 归一化题目 ----------
    def normalize(self, raw: dict) -> Question:
        c = self.client
        qid = str(c.pick(raw, "quiz_id", "") or "")
        qtype = str(c.pick(raw, "qtype", "") or "")
        stem = str(c.pick(raw, "stem", "") or "")
        word = c.pick(raw, "word_hint")
        meaning = c.pick(raw, "meaning")
        hint = c.pick(raw, "hint")
        options = []
        raw_opts = c.pick(raw, "options", [])
        if isinstance(raw_opts, list):
            for i, o in enumerate(raw_opts):
                if isinstance(o, dict):
                    key = str(c.pick(o, "option_key", i))
                    text = c.pick(o, "option_text", "")
                    options.append({"key": key, "text": str(text)})
                else:
                    options.append({"key": str(i), "text": str(o)})
        if not stem:
            # 题干缺失时用中义或英文词兜底，方便 fingerprint
            stem = str(meaning or word or "")
        return Question(quiz_id=qid, qtype=qtype, stem=stem, word_id=(
            str(c.pick(raw, "word_id")) if c.pick(raw, "word_id") is not None else None),
            word=str(word) if word else None, meaning=str(meaning) if meaning else None,
            hint=str(hint) if hint else None, options=options, raw=raw)

    def fingerprint(self, q: Question) -> str:
        return f"{q.qtype}|{norm(q.stem)[:80]}|{q.word_id or ''}"

    # ---------- 主入口 ----------
    def solve(self, q: Question) -> Answer:
        for name in self.chain:
            fn = getattr(self, f"_s_{name}", None)
            if not fn:
                continue
            ans = fn(q)
            if ans and ans.value:
                self.stats[name] = self.stats.get(name, 0) + 1
                return ans
        self.stats["none"] += 1
        return Answer(value=None, source="none", confidence=0.0)

    # ---------- 策略实现 ----------
    def _s_bank(self, q: Question) -> Answer | None:
        row = self.store.bank_get(self.fingerprint(q))
        if not row or not row.get("answer"):
            return None
        val = row["answer"]
        opt = self._match_option(q, val)
        if opt and not q.is_spell:
            return Answer(value=opt["text"], key=opt["key"], source="bank", confidence=0.95)
        return Answer(value=val, key=(opt or {}).get("key"), source="bank", confidence=0.9)

    def _s_index(self, q: Question) -> Answer | None:
        if not self.word2meaning:
            return None
        # 1) 拼写题：字母提示 + 中义
        if q.is_spell:
            w = self._solve_spell(q)
            if w:
                return Answer(value=w, source="index", confidence=0.85)
            return None
        # 2) 选择题
        if not q.options:
            return None
        # 2a) 已知英文词，选中文释义
        if q.word and norm(q.word) in self.word2meaning:
            want = self.word2meaning[norm(q.word)]
            opt = self._match_option(q, want, fuzzy=True)
            if opt:
                return Answer(value=opt["text"], key=opt["key"], source="index", confidence=0.8)
        # 2b) 已知中文释义，选英文词
        if q.meaning:
            for s in senses(q.meaning):
                w = self.meaning2word.get(s)
                if w:
                    opt = self._match_option(q, w, fuzzy=True)
                    if opt:
                        return Answer(value=opt["text"], key=opt["key"], source="index", confidence=0.8)
        # 2c) 选项里只有一个能在词表中查到英文，且与题干/中义能对上
        hits = []
        for o in q.options:
            n = norm(o["text"])
            if n in self.word2meaning:
                hits.append(o)
        if len(hits) == 1 and (q.meaning or q.stem):
            return Answer(value=hits[0]["text"], key=hits[0]["key"], source="index", confidence=0.55)
        return None

    def _s_echo(self, q: Question) -> Answer | None:
        # 选项里出现了目标词本身（很多"看中文选英文"会把答案混在选项里）
        if q.word and q.options:
            for o in q.options:
                if norm(o["text"]) == norm(q.word):
                    return Answer(value=o["text"], key=o["key"], source="echo", confidence=0.6)
        # 题干唯一包含某个选项
        if q.stem and q.options:
            st = norm(q.stem)
            inside = [o for o in q.options if norm(o["text"]) and norm(o["text"]) in st]
            if len(inside) == 1:
                return Answer(value=inside[0]["text"], key=inside[0]["key"], source="echo", confidence=0.5)
        return None

    def _s_guess(self, q: Question) -> Answer | None:
        if not q.options:
            return None
        bad = self.used_wrong.get(self.fingerprint(q), set())
        pool = [o for o in q.options if o["key"] not in bad] or list(q.options)
        # 优先长选项（释义类题目正确答案通常更完整）
        pool.sort(key=lambda o: len(o["text"]), reverse=True)
        top = pool[: max(1, len(pool) // 2)]
        pick = random.choice(top)
        return Answer(value=pick["text"], key=pick["key"], source="guess", confidence=0.3)

    # ---------- 工具 ----------
    def _match_option(self, q: Question, value: str, fuzzy: bool = False) -> dict | None:
        nv = norm(value)
        if not nv:
            return None
        for o in q.options:
            if o["key"] == str(value):
                return o
        for o in q.options:
            no = norm(o["text"])
            if no and (no == nv or (fuzzy and (no in nv or nv in no))):
                return o
        if fuzzy:
            for o in q.options:
                if nv and no_sim(norm(o["text"]), nv) >= 0.7:
                    return o
        return None

    def _solve_spell(self, q: Question) -> str | None:
        hint = (q.hint or q.stem or "").strip()
        if not hint:
            return None
        letters = [ch.lower() for ch in hint if ch.isalpha() or ch in "_-*· "]
        pattern = "".join(ch if ch.isalpha() else "." for ch in letters if ch not in " ·")
        if len(pattern) < 2:
            return None
        rx = re.compile("^" + re.escape(pattern).replace(r"\.", ".") + "$")
        cands = [w for w in self.word2meaning if len(w) == len(pattern) and rx.match(w)]
        if q.meaning:
            want = senses(q.meaning)
            scored = []
            for w in cands:
                m = senses(self.word2meaning.get(w, ""))
                overlap = len(want & m)
                scored.append((overlap, -len(w), w))
            scored.sort(reverse=True)
            if scored and scored[0][0] > 0:
                return scored[0][2]
        if len(cands) == 1:
            return cands[0]
        return None

    # ---------- 反馈学习 ----------
    def feedback(self, q: Question, answer: Answer, right: bool | None,
                 correct_value: str | None) -> None:
        if right is True:
            self.stats["correct"] += 1
            if answer.value:
                self.store.bank_put(self.fingerprint(q), q.qtype, q.stem, answer.value, hit=True)
            return
        if right is False:
            self.stats["wrong"] += 1
            self.used_wrong.setdefault(self.fingerprint(q), set()).add(str(answer.key))
            if correct_value:
                self.store.bank_put(self.fingerprint(q), q.qtype, q.stem, correct_value, hit=False)
                self.log(f"    ✗ 记入答案库: {q.describe()} → {correct_value}")
            return
        self.stats["unknown"] += 1
        if correct_value:
            self.store.bank_put(self.fingerprint(q), q.qtype, q.stem, correct_value, hit=False)


def no_sim(a: str, b: str) -> float:
    """极简相似度（含中文场景，按字符集合重叠 + 序列比例）。"""
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    jac = len(sa & sb) / max(1, len(sa | sb))
    ratio = 1 - abs(len(a) - len(b)) / max(len(a), len(b))
    return 0.5 * jac + 0.5 * ratio
