"""只读核对账号：词书/进度/积分/复习队列。"""
import json
import sys

sys.path.insert(0, "tools")
from uword_fltrp import call  # noqa: E402

p = call("yyuserplan/nowplan.htm", {"status": 0})["data"]
r = call("yyuserscore/todayre.htm", {"userid": p["userid"], "pageid": p["pageid"],
                                     "recount": p.get("prestudycount"),
                                     "type": p.get("prestudy")})
q = r.get("data") or []
print(json.dumps({
    "词书": p["title2"],
    "已学": "{}/{}".format(p["sthaswords"], p["stallwords"]),
    "积分": p.get("rankscore"),
    "累计分钟": p.get("stminutes"),
    "学习天数": p.get("stdays"),
    "复习剩余": len(q) if isinstance(q, list) else q,
    "今日额度": p.get("pdaycount"),
}, ensure_ascii=False, indent=2))
