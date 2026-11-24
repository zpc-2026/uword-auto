"""主流程引擎：同步词表 → 背词（学习）→ 单词检验（做题）→ 学完复习。"""
from __future__ import annotations

import time

from .humanize import Sleeper, rand_range
from .net import ApiError, AuthExpired
from .solver import Solver, norm

TRUE_STR = {"true", "1", "right", "correct", "yes", "y", "对", "正确"}
FALSE_STR = {"false", "0", "wrong", "no", "n", "错", "错误", "incorrect"}


class Engine:
    def __init__(self, cfg, client, store, solver: Solver, log):
        self.cfg = cfg
        self.client = client
        self.store = store
        self.solver = solver
        self.log = log
        self.sleep = Sleeper(cfg, log)
        self.session_id = None
        self.heartbeat_acc = 0.0
        self.deadline = None
        self.fails = 0
        self.summary = {"learned": 0, "quiz": 0, "quiz_ok": 0, "review": 0,
                        "review_ok": 0, "skipped": 0, "errors": 0}

    # ---------- 基础设施 ----------
    def time_left(self) -> float:
        if not self.deadline:
            return 1e9
        return self.deadline - time.time()

    def should_stop(self) -> bool:
        if self.fails >= int(self.cfg.get("limits.fail_budget", 12)):
            self.log("! 失败次数达到上限，停止（可 --reset-fails 或稍后重跑续传）")
            return True
        return self.time_left() <= 0

    def pages(self, endpoint: str, book_id: str, max_pages: int = 40, **extra) -> list[dict]:
        out, page, size = [], 1, int(self.cfg.get("limits.page_size", 30))
        while page <= max_pages:
            ctx = {"book_id": book_id, "page": page, "size": size}
            ctx.update(extra)
            resp = self.client.call(endpoint, ctx)
            payload = self.client.data(resp)
            rows = self.client.list_of(payload)
            if not rows:
                break
            out.extend(r for r in rows if isinstance(r, dict))
            total = self.client.total_of(payload)
            if total and len(out) >= total:
                break
            if len(rows) < size:
                break
            page += 1
        return out

    # ---------- 词表 ----------
    def books(self) -> list[dict]:
        resp = self.client.call("book_list", {})
        return [r for r in self.client.list_of(self.client.data(resp)) if isinstance(r, dict)]

    def sync_words(self, book_id: str, max_pages: int = 40) -> int:
        rows = self.pages("word_list", book_id, max_pages)
        items = []
        for r in rows:
            wid = self.client.pick(r, "id")
            word = self.client.pick(r, "word")
            if wid is None or not word:
                continue
            items.append({"word_id": wid, "word": str(word),
                          "meaning": str(self.client.pick(r, "meaning", "") or "")})
        n = self.store.upsert_words(book_id, items)
        self.log(f"  · 词表同步 {n} 条（接口返回 {len(rows)} 条）")
        self.solver.build_index(book_id)
        return n

    # ---------- 背单词 ----------
    def _start_session(self, book_id: str) -> None:
        if not self.client.has("learn_start"):
            return
        resp = self.client.call("learn_start", {"book_id": book_id})
        sid = self.client.pick(self.client.data(resp) or {}, "session_id")
        self.session_id = str(sid) if sid else None
        self.log(f"  · 学习会话: {self.session_id or '(无 sessionId，跳过心跳)'}")

    def _beat(self, seconds: float) -> None:
        """把停留时间拆成心跳，模拟持续学习。"""
        left = seconds
        step = rand_range(self.cfg.get("timing.heartbeat_every", [18, 32]), (18, 32))
        while left > 0:
            chunk = min(step, left)
            time.sleep(chunk)
            left -= chunk
            self.heartbeat_acc += chunk
            if self.client.has("heartbeat") and self.session_id and self.heartbeat_acc >= step:
                try:
                    self.client.call("heartbeat", {"session_id": self.session_id,
                                                   "cost": int(self.heartbeat_acc * 1000)})
                    self.heartbeat_acc = 0.0
                except AuthExpired:
                    raise
                except ApiError as e:
                    self.log(f"  ! 心跳失败（继续）: {e}")

    def learn(self, book_id: str, limit: int | None = None) -> dict:
        limit = limit or int(self.cfg.get("limits.words_per_run", 40))
        todo = self.store.pending_words(book_id, limit)
        if not todo:
            self.log("  · 没有待学新词了")
            return {"learned": 0}
        self.log(f"== 背单词：{len(todo)} 个新词 ==")
        self._start_session(book_id)
        done = 0
        for w in todo:
            if self.should_stop():
                break
            t0 = time.time()
            try:
                if self.client.has("learn_word"):
                    self.client.call("learn_word", {"word_id": w["word_id"], "cost": 0, "know": 1})
                self._beat(rand_range(self.cfg.get("timing.word_seconds", [6, 14]), (6, 14)))
                cost = int((time.time() - t0) * 1000)
                if self.client.has("learn_word"):
                    self.client.call("learn_word", {"word_id": w["word_id"], "cost": cost, "know": 1})
                self.store.mark_learned(w["word_id"])
                done += 1
                self.summary["learned"] += 1
                self.log(f"  + {w['word']:<18} {w['meaning'][:26]:<28} {cost/1000:.1f}s")
            except AuthExpired:
                raise
            except ApiError as e:
                self.fails += 1
                self.summary["errors"] += 1
                self.log(f"  ! 学词失败 {w.get('word')}: {e}")
        self.store.set_progress(f"learn:{book_id}", str(done))
        return {"learned": done}

    # ---------- 提交与判分 ----------
    def _submit(self, q, ans) -> tuple[bool | None, str | None]:
        cost = rand_range((1.2, 4.5))
        ctx = {"quiz_id": q.quiz_id, "answer": ans.value, "answer_key": ans.key,
               "cost": int(cost * 1000), "word_id": q.word_id or ""}
        resp = self.client.call("quiz_submit", ctx)
        return self._parse_submit(resp, ans)

    def _parse_submit(self, resp: dict, ans) -> tuple[bool | None, str | None]:
        data = self.client.data(resp)
        if isinstance(data, bool):
            return data, None
        if isinstance(data, str):
            return None, data.strip() or None
        if not isinstance(data, dict):
            data = {}
        right, correct = None, None
        for k in self.cfg.get("fields.result_right", []):
            if k not in data:
                continue
            v = data[k]
            if isinstance(v, bool):
                right = v
                break
            if isinstance(v, (int, float)) and int(v) in (0, 1):
                right = bool(int(v))
                break
            if isinstance(v, str):
                lv = v.strip().lower()
                if lv in TRUE_STR:
                    right = True
                    break
                if lv in FALSE_STR:
                    right = False
                    break
        for k in self.cfg.get("fields.result_answer", []):
            v = data.get(k)
            if isinstance(v, str) and v.strip() and v.strip().lower() not in TRUE_STR | FALSE_STR:
                correct = v.strip()
                break
        if right is None and correct and ans.value:
            right = norm(correct) == norm(ans.value) or (
                ans.key is not None and str(correct) == str(ans.key))
        return right, correct

    def _run_questions(self, rows: list[dict], tag: str) -> tuple[int, int]:
        ok = bad = 0
        for raw in rows:
            if self.should_stop():
                break
            try:
                q = self.solver.normalize(raw)
                ans = self.solver.solve(q)
                if not ans.value:
                    self.summary["skipped"] += 1
                    self.log(f"  ? 无法作答，跳过: {q.describe()}")
                    continue
                right, correct = self._submit(q, ans)
                self.solver.feedback(q, ans, right, correct)
                if right is True:
                    ok += 1
                    self.log(f"  ✓ {tag} [{ans.source}] {q.describe()[:70]}")
                elif right is False:
                    bad += 1
                    self.log(f"  ✗ {tag} [{ans.source}] 提交={ans.value} 正确={correct} | {q.describe()[:60]}")
                else:
                    self.log(f"  · {tag} [{ans.source}] 已提交（接口未回判）= {ans.value}")
                    ok += 1
            except AuthExpired:
                raise
            except ApiError as e:
                self.fails += 1
                self.summary["errors"] += 1
                self.log(f"  ! {tag} 提交失败: {e}")
        return ok, bad

    # ---------- 单词检验 ----------
    def quiz(self, book_id: str, rounds: int | None = None) -> dict:
        rounds = rounds or int(self.cfg.get("limits.quiz_rounds", 3))
        total_ok = total_bad = total_q = 0
        for r in range(1, rounds + 1):
            if self.should_stop():
                break
            rows = self.pages("quiz_list", book_id, max_pages=20)
            if not rows:
                self.log(f"  · 第 {r} 轮：没有待检验题目")
                break
            self.log(f"== 单词检验 第 {r} 轮：{len(rows)} 题 ==")
            ok, bad = self._run_questions(rows, "检验")
            total_ok += ok
            total_bad += bad
            total_q += len(rows)
            self.summary["quiz"] += len(rows)
            self.summary["quiz_ok"] += ok
            self.log(f"  → 本轮 {ok}/{len(rows)} 正确")
            if bad == 0:
                break
        return {"questions": total_q, "ok": total_ok, "bad": total_bad}

    # ---------- 复习 ----------
    def review(self, book_id: str, rounds: int | None = None, until_clean: bool = True) -> dict:
        rounds = rounds or int(self.cfg.get("limits.review_rounds", 8))
        total_ok = total_bad = total_q = 0
        for r in range(1, rounds + 1):
            if self.should_stop():
                break
            rows = self.pages("review_list", book_id, max_pages=20)
            if not rows:
                self.log(f"  · 第 {r} 轮：复习队列已清空")
                total_q += 0
                break
            self.log(f"== 复习 第 {r} 轮：{len(rows)} 题 ==")
            ok, bad = self._run_questions(rows, "复习")
            total_ok += ok
            total_bad += bad
            total_q += len(rows)
            self.summary["review"] += len(rows)
            self.summary["review_ok"] += ok
            self.log(f"  → 本轮 {ok}/{len(rows)} 正确")
            if bad == 0 and until_clean:
                # 再探一次，确认服务端确实没货了
                again = self.pages("review_list", book_id, max_pages=2)
                if not again:
                    self.log("  ✓ 复习全部通过")
                    break
        return {"questions": total_q, "ok": total_ok, "bad": total_bad}

    # ---------- 全自动 ----------
    def auto(self, book_id: str, minutes: float | None = None) -> dict:
        minutes = float(minutes or self.cfg.get("limits.max_minutes", 60))
        self.deadline = time.time() + minutes * 60
        self.log(f"== 自动模式：预算 {minutes:.0f} 分钟，词书 {book_id} ==")
        self.sync_words(book_id)
        cycle = 0
        while not self.should_stop():
            cycle += 1
            self.log(f"-- 循环 {cycle} --")
            pending = len(self.store.pending_words(book_id, 9999))
            if pending:
                self.learn(book_id)
            self.quiz(book_id)
            self.review(book_id)
            n, learned = self.store.counts(book_id)
            self.log(f"  进度：{learned}/{n} 已学")
            if pending == 0:
                left = self.pages("review_list", book_id, max_pages=1)
                again = self.pages("quiz_list", book_id, max_pages=1)
                if not left and not again:
                    self.log("✓ 该词书已全部学完、检验通过、复习清空")
                    break
            time.sleep(rand_range((5, 12)))
        return self.report()

    def report(self) -> dict:
        n, learned = self.store.counts()
        s = self.solver.stats
        return {
            "learned": self.summary["learned"],
            "quiz": self.summary["quiz"], "quiz_ok": self.summary["quiz_ok"],
            "review": self.summary["review"], "review_ok": self.summary["review_ok"],
            "skipped": self.summary["skipped"], "errors": self.summary["errors"],
            "solver": dict(s), "bank": self.store.bank_size(),
            "words_total": n, "words_learned": learned,
            "requests": self.client.request_count, "http_errors": self.client.error_count,
        }
