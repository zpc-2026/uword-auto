"""拟人节奏控制：令牌桶限速 + 随机抖动，避免固定间隔被打点。"""
from __future__ import annotations

import random
import time


def rand_range(pair, default=(1.0, 2.0)) -> float:
    try:
        lo, hi = float(pair[0]), float(pair[1])
    except (TypeError, IndexError, ValueError):
        lo, hi = default
    if hi <= lo:
        return lo
    # 三角分布偏中段，比均匀分布更像人
    return round(random.triangular(lo, hi, (lo + hi) / 2), 2)


class Pacer:
    """burst 次请求可以走得快一点，然后强制拉开间隔。"""

    def __init__(self, min_gap: float = 0.9, max_gap: float = 2.8, burst: int = 3):
        self.min_gap = float(min_gap)
        self.max_gap = float(max_gap)
        self.burst = max(1, int(burst))
        self.count = 0
        self.last = 0.0

    def wait(self) -> float:
        now = time.monotonic()
        gap = 0.0
        if self.count % self.burst == 0:
            gap = random.uniform(self.min_gap, self.max_gap)
        else:
            gap = random.uniform(self.min_gap * 0.35, self.min_gap)
        if self.last:
            elapsed = now - self.last
            remaining = gap - elapsed
            if remaining > 0:
                time.sleep(remaining)
        self.count += 1
        self.last = time.monotonic()
        return gap


class Sleeper:
    def __init__(self, cfg, log=None):
        self.cfg = cfg
        self.log = log or (lambda *a, **k: None)
        self.words_done = 0
        self.rest_every = int(rand_range(cfg.get("timing.rest_every_words", [12, 18]), (12, 18)))

    def word_pause(self) -> float:
        s = rand_range(self.cfg.get("timing.word_seconds", [6, 14]), (6, 14))
        time.sleep(s)
        self.words_done += 1
        if self.words_done % self.rest_every == 0:
            r = rand_range(self.cfg.get("timing.rest_seconds", [20, 55]), (20, 55))
            self.log(f"  · 阶段休息 {r}s（已处理 {self.words_done} 词）")
            time.sleep(r)
            self.rest_every = int(rand_range(self.cfg.get("timing.rest_every_words", [12, 18]), (12, 18)))
        return s
