"""抽查求解器：拉若干词的题目并打印判题理由（在项目根目录下运行）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from uword.fltrp import Client, current_token  # noqa: E402
from uword.fltrp.solver import solve  # noqa: E402

c = Client(token=current_token(), pacing=(0.05, 0.15))
p = c.nowplan()
words = c.plan_words(p["pageid"])[p["sthaswords"]: p["sthaswords"] + 8]
ok = bad = 0
for wid in words:
    for q in c.questions(wid, 1):
        solved, ans, why = solve(q)
        ok += solved
        bad += (not solved)
        print(f"{'OK ' if solved else 'BAD'} type={q.get('type')} word={q.get('word')} "
              f"des={q.get('des')!r} ans={ans!r} ({why})")
print(f"\n对 {ok} 错 {bad}")
