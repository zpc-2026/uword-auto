# uword-auto

外研U词（微信小程序 / H5 共用后端 `word.fltrp.com`）自动化：**背新词 → 单词检验 → 学完复习**。
零第三方依赖，一条命令跑完；也提供 agent 可直接 import 的 JSON 接口。

```
$ uword status
词书：大学英语四级核心词   已学 675/3250   积分 1308   复习待办 0

$ uword learn 20
  5/20 词  正确 5 错误 0
  …
{"ok": true, "learned": 20, "right": 20, "wrong": 0, "minutes_added": 8}
```

## 别人拿到后照这个走（三条命令）

```bash
git clone https://github.com/zpc-2026/uword-auto.git && cd uword-auto

python -m uword mock          # ① 自检：起本地假接口跑完整流程，不需要账号、不需要密码
                              #    预期最后一行：自检通过

python -m uword login --user 自己的手机号 --password '自己的密码'
                              # ② 登录一次，会话缓存到 ~/.uword/token.json（权限 600）

python -m uword status        # ③ 应看到自己的词书、已学词数、积分、复习待办
```

需要 Python ≥ 3.9，零第三方依赖（`pip install -e .` 可选，只是装出 `uword` 命令）。
账号是微信登录、没设过密码的，用 `python -m uword login --sms --phone 手机号` 走短信设密码。

没登录直接跑会明确报错，不会静默失败：

```
[错误] PermissionError: 没有可用会话：先 uword login，或设置 UWORD_TOKEN
```

## 为什么要自己做

小程序/网页用的都是同一套 HTTP 接口，反编译前端拿到完整契约后，自动化只剩三个动作：

```
SSO 登录 → 绑定外研U词账号 → 换会话串（Authorization）
拿计划/词表 → 逐词取题（每题自带正确释义 des）→ 上报 → studyend 结算
复习队列 → 逐条上报 type=2 → 结算
```

接口细节全部写在 [docs/API.md](docs/API.md)，包括请求体、字段名、错误码。

## 安装

```bash
git clone <this-repo> && cd uword-auto
pip install -e .            # 也可以不装，直接用 python -m uword
python -m uword mock        # 离线自检，不碰真实账号
```

要求 Python ≥ 3.9，无第三方依赖。

## 登录

```bash
# 有密码（推荐）
uword login --user 181xxxxxxxx --password '你的密码'

# 账号是微信登录、没有密码 → 短信验证码设一个
uword login --sms --phone 181xxxxxxxx
# 会在当前目录生成 captcha.jpg，看图输入，然后收短信、设新密码、自动登录
```

会话缓存在 `~/.uword/token.json`（权限 600），之后所有命令都不再需要密码。
也可以直接给会话串：`export UWORD_TOKEN=FP3DE8BE29…`。

## 日常使用

```bash
uword status                      # 词书 / 进度 / 积分 / 复习队列
uword learn 40                    # 背 40 个新词（默认每词停留 25 秒）
uword learn 100 --word-seconds 0  # 只要词数，不耗学习时长
uword review --limit 500          # 清复习队列
uword auto --learn 40 --review 500
uword plan --pstudy 1             # 每词 3 题（选义 + 拼写 + 例句），原地更新不动进度
uword plan --pstudy 0 --pdaycount 40
uword --json status               # 一行 JSON，给脚本/agent 用
```

## 给 agent 用

```python
from uword.agent import api

api.status()                       # {"plan": {…}, "review_queue": 0, …}
api.learn(20, word_seconds=25)     # {"ok": True, "learned": 20, "after": {…}}
api.review(200)
api.auto(learn_count=20, review_limit=200)
```

详见 [docs/AGENT.md](docs/AGENT.md)（环境变量、返回字段、失败模式、并发注意）。

## 它是怎么做题的

每道题都自带 `des`（正确释义），所以不需要题库也不需要模型：

| 题型 | 内容 | 做法 |
|---|---|---|
| 1 看单词选释义 | `content` = `[["a.","美学的，审美的"],…]` | 选项文本与 `des` 归一化比对（去标点/①②，双向包含） |
| 2 看例句选释义 | 同上，另附 `sentence` | 同上 |
| 3 组合拼写 | `content` = `["hamm","er","eh"]` | 按 `word` 贪心吃掉词块，剩余为空即拼对 |

判题其实**在客户端**完成，`yyuserscore/add.htm` 只负责记分；真正让进度前进的是
`yyuserplan/studyend.htm` 的 `sthaswords + len(studyendwords)`。这也意味着：
每日额度（`pdaycount`）在接口层拦不住，想学多少学多少。

## 学习时长

`--word-seconds` 控制每个词之间真实 sleep 的时长（默认 25 秒）：

- `25` → 100 词约 42 分钟，`stminutes` 真实增长 40+ 分钟
- `0` → 100 词约 3 分钟，`stminutes` 只增加几分钟

`stminutes` 是客户端上报值，工具按实际耗时向上取整写入，不虚报。

## 目录结构

```
uword/
├─ fltrp/              真实后端（主路径）
│  ├─ client.py        端点封装、重试、限速、错误归一
│  ├─ auth.py          SSO 登录 / 短信设密码 / 绑定 / 会话缓存
│  ├─ solver.py        三类题的确定性求解
│  └─ ops.py           status / learn / review / set_plan
├─ agent/api.py        给其他 agent 的高层接口
├─ cli.py              命令行
├─ config.py net.py store.py engine.py humanize.py solver.py   （旧：离线自检引擎）
└─ cli_legacy.py       mock 自检的装配代码
tools/                 抓包/侦察/调试脚本（见下）
docs/API.md            接口契约
docs/AGENT.md          agent 接入
```

## tools/ 里的侦察脚本（换接口时用得上）

完整索引见 [tools/README.md](tools/README.md)，日常使用完全用不到这些。

| 脚本 | 作用 |
|---|---|
| `fetch_uword_chunks.py` | 下载 H5 各页面 chunk，抽取全部后端端点 |
| `login_page.py` | 本地登录页（127.0.0.1），账号密码 / 短信设密码 |
| `decrypt_wxapkg.ps1` + `unpack_wxapkg.py` | 解密并解包 PC 微信小程序（V1MMWX） |
| `cdp.py` | 用 CDP 操作 Edge：读 localStorage / cookie、开标签、执行 JS |
| `mitm.py` + `proc_mem_scan.py` | HTTPS 中间人、进程内存字符串扫描（取证用） |
| `mock_server.py` | 离线假接口，供 `uword mock` 自检 |
| `check_solver.py` / `check_account.py` | 抽查判题正确率、只读核对账号数据 |

## 常见问题

| 现象 | 原因 | 解决 |
|---|---|---|
| `没有可用会话：先 uword login` | 没登录 / 缓存被清 | `python -m uword login ...` |
| `用户登录超时`（接口 code 50000） | 会话过期 | 重登；或设 `UWORD_USER`/`UWORD_PASS` 让 agent 接口自动重登 |
| `登录失败 [2012]` | 密码错 | 换密码，或 `--sms` 重新设密码 |
| `账号和选择的角色不一致` | `usercode` 与该账号角色不符 | 学生用默认 `"1"` |
| `发短信失败 [1302]` | 走错成邮箱分支 | 用 `login --sms`，它走 `sms_code_captcha`（要图片验证码） |
| `没有待学新词了` | 词书已学完 | 换词书，或只跑 `review` |
| `plan 被重建了` | 直接调 add.htm 没带 id | 用 `uword plan`，它整体回写原计划对象 |

退出码：`0` 成功 / `1` 业务未成功 / `2` 参数或自检失败 / `3` 会话失效 / `4` 接口错误 / `130` 手动中断。

多机 / 容器 / CI 里不想存密码，直接传会话串：

```bash
export UWORD_TOKEN=FP3DE8BE29…          # 从已登录机器的 ~/.uword/token.json 里取
python -m uword status --json
```

## 边界与已知问题

- **服务端缺陷**：`wxlogin.htm?openid=H5` 不带凭据就返回某个真实账号的会话（H5 把 openid 写死成
  `"H5"`）。本工具不碰这条路径，只用自己 SSO 身份换出来的 openid。
- 判分与时长都是客户端断言，服务端不做校验；本工具按真实计算结果上报，不伪造。
- 单账号别并发跑：`studyend` 会互相覆盖 `sthaswords`。
- 验证码（图形码）只在「短信设密码」时出现，需要人工看一次图；登录后不再需要。

MIT License。
