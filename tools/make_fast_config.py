"""生成快速节奏配置（联调/自检用，不真的等 6~14 秒/词）。"""
import json
import pathlib

tpl = json.loads(pathlib.Path("config.example.json").read_text(encoding="utf-8-sig"))
tpl["timing"] = {"word_seconds": [0.05, 0.15], "heartbeat_every": [0.2, 0.4],
                 "rest_every_words": [900, 1000], "rest_seconds": [0, 0]}
tpl["pacing"] = {"min_gap": 0.01, "max_gap": 0.03, "burst": 50}
tpl["storage"] = "fast.db"
tpl["log_file"] = "fast.log"
pathlib.Path("config.fast.json").write_text(
    json.dumps(tpl, ensure_ascii=False, indent=2), encoding="utf-8")
print("config.fast.json written")
