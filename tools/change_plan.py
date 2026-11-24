"""安全地改计划参数（默认改 pstudy：每词几道题）。

    python tools/change_plan.py --show
    python tools/change_plan.py --noop          # 原值回写，验证是"更新"而不是"新建"
    python tools/change_plan.py --pstudy 1      # 每词 3 问
"""
from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, "tools")
from uword_fltrp import call  # noqa: E402

FIELDS = ["pageid", "id", "psort", "pdaycount", "paudio", "pstudy",
          "prestudy", "prestudycount", "stdays", "stallwords"]


def plan() -> dict:
    return call("yyuserplan/nowplan.htm", {"status": 0}).get("data") or {}


def snapshot(p: dict) -> dict:
    return {k: p.get(k) for k in FIELDS}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--noop", action="store_true")
    ap.add_argument("--pstudy", type=int, default=None, choices=[0, 1])
    ap.add_argument("--pdaycount", type=int, default=None)
    args = ap.parse_args()

    p0 = plan()
    print("当前计划:", json.dumps(snapshot(p0), ensure_ascii=False))

    if args.show or (not args.noop and args.pstudy is None and args.pdaycount is None):
        return 0

    body = {k: p0.get(k) for k in FIELDS}
    if args.pstudy is not None:
        body["pstudy"] = args.pstudy
    if args.pdaycount is not None:
        body["pdaycount"] = args.pdaycount

    print("提交:", json.dumps(body, ensure_ascii=False))
    r = call("yyuserplan/add.htm", body)
    print("返回:", json.dumps(r, ensure_ascii=False)[:300])

    p1 = plan()
    print("改后计划:", json.dumps(snapshot(p1), ensure_ascii=False))
    if p1.get("id") != p0.get("id"):
        print("!! 计划 id 变了（可能新建了计划），进度有丢失风险")
        return 2
    if p1.get("sthaswords") != p0.get("sthaswords"):
        print(f"!! 进度从 {p0.get('sthaswords')} 变成 {p1.get('sthaswords')}")
        return 2
    print("✓ 计划 id 与进度都没变，是原地更新")
    return 0


if __name__ == "__main__":
    sys.exit(main())
