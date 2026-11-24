# 给 agent / 其他设备的接入说明

目标：任意 agent、任意机器，只要 Python ≥3.9，就能 `import` 后直接干活，不依赖本仓库的
工作目录、浏览器或抓包。

## 安装

```bash
pip install -e .          # 或把 uword/ 目录整份拷走
uword --help
```

零第三方依赖（urllib + json）。

## 会话怎么来

优先级：`UWORD_TOKEN` 环境变量 → `UWORD_HOME/token.json`（默认 `~/.uword/token.json`）。

```bash
# 一次性登录（会话会缓存，脚本不用再管密码）
uword login --user 181xxxxxxxx --password '***'

# 或者直接给会话串（从浏览器 localStorage 的 user.s、或上游 agent 传进来）
export UWORD_TOKEN=FP3DE8BE29...
```

> 会话有效期通常几天；失效时接口返回 `50000 用户登录超时`。
> 设置了 `UWORD_USER` + `UWORD_PASS` 时，agent API 会**自动重登一次**再重试。

## Agent 调用（推荐）

```python
from uword.agent import api

print(api.status())          # 词书、进度、复习队列
print(api.learn(20))         # 背 20 个新词（按计划每词 1 或 3 题）
print(api.review(200))       # 清复习队列（最多 200 条）
print(api.auto(learn_count=20, review_limit=200))
print(api.set_plan(pstudy=0, pdaycount=40))
```

返回值都是可直接 `json.dumps` 的 dict，核心字段：

```jsonc
// status()
{"plan": {"title2":"大学英语四级核心词","pageid":1,"userid":123456,"id":1261837,
          "sthaswords":675,"stallwords":3250,"stminutes":31692,"rankscore":1308,
          "pdaycount":40,"pstudy":0},
 "review_queue": 0, "words_total": 3250, "requests": 3}

// learn(n)
{"ok":true,"learned":3,"questions":3,"right":3,"wrong":0,"assumed":0,
 "minutes_added":1,"before":{…},"after":{…},"requests":10}

// review(limit)
{"ok":true,"reviewed":480,"queue_before":480,"queue_after":0,"before":{…},"after":{…}}
```

判断成功的字段：`ok == true`；进度看 `after.sthaswords`。

## CLI（给别的脚本或人用）

```bash
uword status --json                         # 一行 JSON，方便 jq
uword learn 100 --json                      # 背 100 个（默认每词停留 25 秒）
uword learn 100 --word-seconds 0            # 只刷词数，不耗时间
uword review --limit 500 --json
uword auto --learn 40 --review 300 --json
uword plan --pstudy 1                       # 每词 3 题（含拼写、例句）
uword plan --pstudy 0                       # 改回每词 1 题
uword questions 51F31E94                    # 调试：看题目与自动求解结果
uword mock                                  # 离线自检，不碰真实账号
```

## 并发与节奏

- 单账号**不要并发**：`studyend` 是客户端上报进度，两个进程会互相覆盖 `sthaswords`。
- 默认请求间隔 0.15~0.35 秒（`--gap-min/--gap-max`），一轮 100 词约 3 分钟。
- `--word-seconds 25` 会在每词之间真实 sleep，让 `stminutes` 自然增长；设 0 则只刷词数。

## 失败模式

| 现象 | 原因 | 处理 |
|---|---|---|
| `AuthExpired: 用户登录超时` | 会话过期 | `uword login`；或配 `UWORD_USER/UWORD_PASS` 让 api 自动重登 |
| `PermissionError: 登录失败 [2012]` | 密码错 | 换密码；没密码用 `uword login --sms` |
| `PermissionError: 账号和选择的角色不一致` | `usercode` 与该账号角色不符 | 学生用 `"1"` |
| `plan 被重建了` | `save_plan` 没带 `id` | 用 `uword plan`，它会整体回写原计划对象 |
| `learn` 返回 `没有待学新词了` | 词书已学完 | 换词书或 `review` |

## 边界

- 判题由客户端断言（`score` 字段），服务端只记分并累加 `sthaswords`，所以「正确率」是工具自己算的。
- 学习时长 `stminutes` 也是客户端上报的；想让它真实，就给 `--word-seconds`。
- 只支持一个已存在的计划；换词书要改 `pageid`（目前用 `uword plan` 之外的方式建计划）。
