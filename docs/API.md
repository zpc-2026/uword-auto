# 外研U词后端接口速查（word.fltrp.com）

全部实测于 2026-11，抓包 + 反编译前端（`word.fltrp.com` 的 uni-app H5）交叉验证。
所有请求 `Content-Type: application/json`，鉴权只有一个头：

```
Authorization: <会话串，形如 FP3DE8BE29…>
```

响应统一包一层：

```json
{"code":"20000","message":"SUCCESS","data":{"code":"0","rs":{...}}}
```
- `code=20000` 表示 HTTP/网关层成功，**业务码在 `data.code`**（`"0"` 成功）
- 业务数据在 `data.rs`（对象）或 `data`（数组，如题目列表）
- 会话失效：`{"code":"50000","error":"用户登录超时"}`

## 登录链

| 步骤 | 接口 | 参数 | 返回 |
|---|---|---|---|
| ① 密码登录 | `POST fltrp/openapi/sso.htm` | `{path:"4.0/sso/login", service:"https://word.fltrp.com/", username, password, captchaCode?, encodeCaptha?}` | `data.rs.openid`（SSO 身份）、`jwt`、TGT、ST |
| ② 绑定外研U词 | `POST yyuser/openapi/ssoreg.htm` | `{tel|email, openid, suid, usercode:"1", type:0, source:"miniappid", isAd:0}` | `data.id / tel2 / openid / usercode` |
| ③ 取会话 | `GET yyuser/openapi/wxlogin.htm` | `{openid, type:0, source:"miniappid"}` | `data.s` ← **就是 Authorization** |

短信设密码（账号没有密码时）：

| 步骤 | 接口 | 参数 |
|---|---|---|
| 图片验证码 | `POST fltrp/openapi/sso.htm` | `{path:"4.0/sso/image_captcha"}` → `data.rs.image`(base64) + `data.rs.encodeCaptha` |
| 发短信 | 同上 | `{path:"4.0/sso/sms_code_captcha", linkType:0, phone, captchaCode, encodeCaptha}` |
| 设密码 | 同上 | `{path:"1.0/sso/update_password_phone_code", linkType:2, phone, code, newPassword}` |

> `usercode` 必须与账号角色一致：学生是 `"1"`，填 `"0"` 会返回
> `{"code":"50001","error":"您登录的账号和选择的角色不一致，请重新选择。"}`

## 业务接口

| 用途 | 接口 | 参数 | 关键返回 |
|---|---|---|---|
| 当前计划 | `POST yyuserplan/nowplan.htm` | `{status:0}` | `id,pageid,userid,title2,sthaswords,stallwords,stminutes,rankscore,pdaycount,pstudy,prestudy,prestudycount,strestudydays` |
| 计划词表 | `POST yyuserplan/nowplancontent.htm` | `{pageid}` | `data.content` = JSON 字符串，解析后是 8 位 hex 词 id 数组（长度 = 词书总词数） |
| 今日状态 | `POST yyuserplan/nowst.htm` | `{status:0}` 或 `{userid}` | `dayscount,rankscore,sthaswords…` |
| 取题 | `GET wordentry/selquestionbyword.htm` | `{word:<词id>, count:1~3}` | 题目数组，每题自带 `des`（正确释义） |
| 上报答题 | `POST yyuserscore/add.htm` | 学习：`{userid,pageid,word,score:0|1,type:100+题型}`；复习：`{id,recount,userid,pageid,word,score:0,type:2}` | 回声 |
| 今日复习队列 | `POST yyuserscore/todayre.htm` | `{userid,pageid,recount:prestudycount,type:prestudy}` | 待复习词数组，每项含 `id,word,recount` |
| 结算学习 | `POST yyuserplan/studyend.htm` | `{id,userid,pageid,stminutes,sthaswords,studyendwords:[词id…]}` | 更新后的计划 |
| 结算复习 | 同上 | 追加 `{strestudydays,streminutes}` | 同上 |
| 改计划 | `POST yyuserplan/add.htm` | 计划对象整体（含 `id`）→ **原地更新**，不带 id 会新建 | `SUCCESS` |

### 题型

```jsonc
// type 1：看单词选释义
{"type":1,"word":"crack","des":"发出爆裂声",
 "content":"[[\"v.\",\"发出爆裂声\"],[\"n.\",\"裂缝\"],…]"}
// type 2：看例句选释义（多 sentence/sentencecn）
{"type":2,"des":"准时","content":"[[\"a.\",\"准时的\"],…]"}
// type 3：组合拼写，content 是可点击的词块
{"type":3,"word":"hammer","des":"锤，榔头","content":"[\"hamm\",\"er\",\"eh\"]"}
```

**判题在客户端完成**，`yyuserscore/add.htm` 只是记录分数；进度真正的增长点在
`yyuserplan/studyend.htm` 的 `sthaswords = 现值 + len(studyendwords)`，所以每日额度
（`pdaycount`）拦不住接口调用。

## 已知服务端缺陷（不是本工具的用法）

`GET yyuser/openapi/wxlogin.htm?openid=H5&type=0&source=miniappid` 不带任何凭据就会返回
某个真实账号的完整资料和可用会话串 —— H5 版本把 `openid` 写死成字符串 `"H5"`，而服务端把这个
openid 绑在了一个真实用户上。任何访问网页版的人都会变成那个账号。

本工具不使用这条路径：它总是用你自己 SSO 身份换出来的 openid 调 ③。
