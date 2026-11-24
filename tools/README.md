# tools/ 脚本索引

这些是**侦察与调试**脚本，用来在接口变更时重新摸清契约。日常使用只需要 `uword` 包本身。

## 逆向 / 抓包

| 脚本 | 作用 |
|---|---|
| `grab_web.py <url>` | 抓页面 → 下载 js/css → 扫 `https://`、`baseURL`、`/api` 路径 |
| `fetch_uword_chunks.py` | 按 webpack 运行时表下载 H5 全部页面 chunk，抽取后端 `.htm` 端点 |
| `js_grep.py <正则> [glob]` | 在打包后的 JS 里做正则搜索并打印上下文 |
| `extract_endpoints.py <js>` | 提取接口路径、`url:` 赋值、关键字段名 |
| `har2config.py --har x.har` | HAR → 配置（识别域名、认证头、端点路径） |
| `make_sample_har.py` | 造一份示例 HAR 供 har2config 自测 |
| `proxy_sniff.py` | 只记录 CONNECT/URL 的嗅探代理（盲转发，不劫持） |
| `mitm.py` | HTTPS 中间人，打印请求头（含 Authorization）与响应片段 |
| `decrypt_wxapkg.ps1` + `unpack_wxapkg.py` | 解密 PC 微信 `V1MMWX` 包并解包 |
| `proc_mem_scan.py --pid N --pattern X` | 只读扫描进程内存里的字符串（找 token / 域名） |
| `dump_applet_db.py` | 检查小程序 `applet.db` 结构与关键字 |
| `inspect_applet.py` | 扫小程序缓存目录里的 URL / 关键词 |
| `scan_urls.py <目录>` | 汇总目录内所有 URL 的唯一域名 |
| `dns_scan.py` | 子域枚举（unipus / fltrp 系） |
| `probe_hosts.py` / `probe_api.py` | 探测域名与接口的存活、鉴权要求、错误码格式 |

## 桌面 / 浏览器自动化

| 脚本 | 作用 |
|---|---|
| `cdp.py` | CDP 客户端：列标签、开新标签、页面里执行 JS、导出 cookie |
| `cdp_probe_mint.py` | 清空站点存储后抓首次请求，判断会话是本地残留还是服务端下发 |
| `pc.py` | 截图（Pillow）、鼠标点击、按键、列窗口 |
| `win_probe.py` | 列出/移动/前置窗口（含最小化窗口的还原尝试） |
| `login_page.py` | 本地登录页（127.0.0.1）：账号密码 + 短信验证码设密码 |

## 数据核对 / 调试

| 脚本 | 作用 |
|---|---|
| `check_account.py` | 只读核对词书、进度、积分、复习队列 |
| `check_solver.py` | 抽查若干词的题目，打印求解结果与理由 |
| `change_plan.py` | 改 `pstudy` / `pdaycount`，带 no-op 原值回写校验（原地更新 vs 新建） |
| `uword_fltrp.py` | 单接口调试：`plan` / `words` / `questions` / `raw` |
| `uword_auto.py` | 早期一体化脚本（学习 + 复习），现在等价于 `uword auto` |
| `uword_login.py` | 早期 SSO 登录探测（含失败码诊断） |
| `uword_learn_once.py` / `uword_session.py` | 单次学习 / 单日批次的最小可运行样例 |
| `mock_server.py` | 离线假接口，供 `uword mock` 自检 |
| `make_fast_config.py` | 生成快速节奏配置（联调时不真的等 6~14 秒/词） |

## 注意

- `mitm.py` 需要 `certs/leaf.crt|key`（脚本不附带私钥，自行用 openssl 生成并安装 CA 到用户根存储）。
- `pc.py` / `win_probe.py` / `cdp.py` 会操作本机窗口和浏览器，按需使用。
- 这些脚本默认只用标准库；`pc.py` 需要 Pillow，`cdp.py` 需要 websocket-client。
