# 记忆、上下文与存储设计

本文描述 Wildfire Ops Copilot **目前实际怎么做的**,以及**应该改成什么样**。
所有数字要么是从代码读出来的,要么是跑探针实测的,要么标了外部出处。

**一句话现状**:所有数据都活在一个进程的内存里,进程一停全部消失,因此部署时被迫锁死
`--max-instances 1`。这是 demo 阶段的合理取舍,但不能作为生产形态。

---

# 第一部分:现在存了哪些东西

一共 5 个地方。前 4 个在后端进程内存里,第 5 个在浏览器里。

## 1.1 业务数据仓库 `InMemoryStore`

`app/services/firestore_store.py` 末尾的模块级全局变量 `store`。

> 文件名叫 `firestore_store`,README 写着 "Storage: Firestore",但**代码里没有任何 Firestore
> 调用,依赖清单里也没有这个库**。它就是一个 Python 字典。这个描述需要改。

| 集合 | 装什么 | 上限 |
|---|---|---|
| `runs` | 每次分析的完整结果(含全部证据) | ❌ |
| `events` | 每次分析的步骤流水 | ❌ |
| `reports` | 报告 Markdown 全文 | ❌ |
| `alerts` / `actions` / `approvals` | 告警、行动草稿、审批记录 | ❌ |
| `monitor_tasks` | 监控任务 | ❌ |
| `conversations` | 对话及其全部消息 | ❌ |
| `agent_events` | 实时事件流 | ✅ 最近 200 条 |
| `audit_logs` | 审计日志 | ❌ |

**全系统只有 `agent_events` 有上限**(`firestore_store.py` 的 `[-200:]`)。

## 1.2 ADK 会话状态

`app/runtime/adk.py` 的全局 `_SESSION_SERVICE = InMemorySessionService()`。装三类东西:

- **`app:` 前缀键** —— 当前轮的"坐标":`app:run_id`、`app:region_id`、`app:user_id`、
  `app:aoi_center` 等。每轮被 `_state_delta_for_request` 整体覆盖。工具通过
  `_chat_request_from_context` 读这些坐标还原请求参数。
- **`last_` 前缀键** —— 本轮草稿纸,工具用 `_stash_result` 写,主流程读来判断模型调了哪个工具。
  **每轮开头重置为 `None`**,所以是草稿不是记忆。
- **完整的模型对话事件** —— ADK 自动累积,**从不删除**(全仓库搜不到 `delete_session`),
  是对话记录的第二份拷贝。

## 1.3 两个缓存

| 缓存 | 位置 | 装什么 |
|---|---|---|
| `_ANALYSIS_CACHE` | `analysis_pipeline.py` | 按 AOI 缓存整包证据+评分 |
| `_AUSTRALIA_OVERVIEW_CACHE` | `fire_hotspot_tools.py` | 全澳热点,只存一份 |

两者的实际行为见第三部分 —— **和你以为的不一样**。

## 1.4 浏览器

**没有任何持久化。** 全仓库搜不到 `localStorage` / `sessionStorage` / `indexedDB` / `cookie`。
`conversationId` 只在 React `useState` 里。**按 F5 对话就没了,而且找不回来** ——
后端也没有"列出我的历史对话"接口。

## 1.5 长期 vs 短期

| | 有没有 |
|---|---|
| 跨会话记忆(记住指挥官偏好) | ❌ 没有,**建议继续不做**,理由见 5.5 |
| 跨进程记忆(重启后还在) | ❌ 没有 |
| 会话内记忆 | ✅ 有,但只在进程活着时 |
| 回合内草稿 | ✅ 有 |

准确说法:**只有短期记忆,"短期"的长度 = 容器进程活多久。** Cloud Run 上这个时长不可控。

## 1.6 已修复:跨用户会话泄漏

**原问题**:`get_or_create_conversation` 有两个缺陷 ——

1. 把客户端传来的任意字符串直接当成新会话的 ID(ID 抢占)
2. 返回已存在会话时**完全不检查归属**

于是任何人只要发一个已知或猜到的 `conversation_id`,就能读到别人的完整对话。
当时后端是 `--allow-unauthenticated` + 一个共享密钥,而那个密钥会被打包进前端 JS bundle,
所以任何 API 客户端都能打。**这部分鉴权已经重写**,见 1.7。

> 更正一处早前的判断:触发路径不是前端。前端 `sendChat` 传的是 `conversationId`
> (首条为 `undefined`,`JSON.stringify` 会丢掉这个 key)。`"pending"` 只存在于
> `optimisticUserMessage` 这个纯渲染用的本地对象里,不发给后端。
> **漏洞在 API 本身信任客户端 ID,不在前端。**

**已修**:会话 ID 一律服务端生成;只有归属匹配才能恢复已有会话;未知或非本人的 ID
静默开新会话(不报错,避免被用来探测哪些 ID 存在)。补了 4 个回归测试。

这层归属检查依赖 `ChatRequest.user_id` 可信。**该前提现在成立了** —— chat 处理器已改为
用已验证 token 的身份覆盖请求体里的 `user_id`,见 1.7。

## 1.7 已落地:Firebase 身份认证(并行工作)

鉴权已经从「共享静态密钥」重写为真实的 Firebase ID token 校验
(`app/services/api_auth.py`)。现状:

| 项 | 做法 |
|---|---|
| 凭据 | Firebase ID token,经 `id_token.verify_firebase_token` 校验签名与 audience |
| 前端传递 | `Authorization: Bearer <idToken>`,**不再有密钥打包进 bundle** |
| 准入 | 邮箱白名单(`auth_allowed_emails` + `auth_admin_emails`),白名单为空则一律拒绝 |
| 邮箱验证 | 可配置要求 `email_verified` 为 true |
| 角色 | 命中 `auth_admin_emails` 为 `admin`,否则 `operator` |
| 未配置时 | `firebase_project_id` 为空则整个鉴权关闭(本地开发用) |

**审批链路的漏洞已经堵上。** `app/api/actions.py` 的 `_decision_actor()` 在鉴权启用时
走 `require_admin_user(request)` 并返回 `user.email` —— 也就是说:

- 审批人身份**来自已验证的 token,不再来自请求体**
- 审批**要求 admin 角色**,普通 operator 无法批准
- 客户端传的 `payload.actor` 只在鉴权关闭(本地开发)时才被采用

**Chat 链路的身份也已经收口。** `app/api/chat.py` 的 `_chat_user_id()` 走同一个套路:
鉴权启用时用 `get_authenticated_user(request).email` 覆盖请求体里的 `user_id`,
客户端传什么都不作数;鉴权关闭时(本地开发)才沿用请求体的值。

用 email 而不是 uid,是为了和审批链路的 `actor` 可比 —— `action.requested_by` 与
`approval.approved_by` 现在是同一种标识,将来要加「申请人 ≠ 批准人」的职责分离检查,
可以直接比较。

三个回归测试覆盖:客户端伪造的 `user_id` 被忽略、鉴权关闭时保留请求体的值、
以及持有合法 token 的另一用户即使同时伪造 `conversation_id` 和 `user_id`
也拿不到别人的对话记录。

**告警确认链路同样收口。** `alerts.py` 原先把 `AcknowledgeAlertRequest.actor`
(默认 `"demo_officer"`)直接写进审计日志,现在也走已验证身份。

这里有一个刻意的区分:**确认告警不要求 admin 角色**。批准行动会向外发出公众预警,
所以要 admin;而"我看到了这条告警"是普通 operator 的日常工作,要求 admin 反而会挡住
正常运作。有测试专门锁住这个行为。

### 身份解析已收敛到一处

三处相同的解析逻辑合并成了 `api_auth.authenticated_actor(request, fallback)`:

| 调用方 | 用法 |
|---|---|
| `chat.py` | 覆盖 `ChatRequest.user_id` |
| `alerts.py` | 决定审计日志的 `actor` |
| `actions.py` | **不用它** —— 审批额外要求 admin,走 `require_admin_user` |

「身份只来自 token,不来自请求体」这条规则现在只写在一个地方。三份拷贝的安全规则
最容易在后续改动中悄悄漂移,而这里漂移的后果是静默的鉴权漏洞。

`actions.py` 保持独立是有意的 —— 它的权限要求不同,硬塞进同一个函数就是错误的抽象。

**WebSocket 凭据已移出 URL。** 浏览器无法在 WebSocket 握手时设置请求头,所以凭据原先
挂在 query 参数上(`?id_token=...`),而 query string 会被记进访问日志和代理历史。
现在改为:服务端先 accept,再从**首帧** `{"type":"auth","token":"..."}` 读取凭据,
5 秒内没有合法凭据就以 1008 关闭。认证通过后服务端回一帧 `{"type":"ready"}`,
客户端据此区分「已认证可用」和「即将被关闭」。

### 顺带发现:WebSocket 端点此前完全是坏的

`app/main.py` 把 `dependencies=api_dependencies` 应用到了**所有** router,包括含
WebSocket 路由的 `agent_events`。而 `verify_api_request(request: Request)` 在
WebSocket scope 下拿不到 `Request`,于是每次连接都抛:

```
TypeError: verify_api_request() missing 1 required positional argument: 'request'
```

**即使鉴权完全关闭也一样连不上**(已实测复现)。前端因为 `onerror` / `onclose` 里有
回退逻辑,静默降级成了 2.5 秒轮询,所以一直没人发现 —— 实时事件流从来没有真正工作过。

修法是把 WebSocket 路由拆到独立的 `websocket_router`,挂载时不带那个 HTTP 依赖;
它本来就有自己的鉴权。

## 1.8 顺带修复:循环导入

`chat_conversations` → `runtime.intents` → `runtime/__init__` → `runtime.adk` → 回到
`chat_conversations`。原先靠 `app.main` 的导入顺序掩盖着,单独 import 就报 `ImportError`。
已改成 `get_runtime()` 内部惰性导入。

## 1.9 仍未修:内存只涨不降

`RECENT_MESSAGE_LIMIT = 6` 限制的是**读取**(每次只返最近 6 条),**不限制存储**。
长对话的全部消息永久驻留,其中只有 6 条会被用到。ADK 会话事件同样从不清理。

**实测**(demo 模式跑 5 次分析):5 runs / 5 reports / 31 trace events / 5 conversations /
35 agent_events / 0 audit_logs,平均 **3,322 bytes/run**。

但 demo 模式热点为空。**live 模式下**:单个热点序列化 **181 bytes**(实测),
单次分析最多保留 **1,600** 个热点 → **单次分析 evidence 最大约 283 KB**。

| 分析次数 | 内存占用 |
|---|---|
| 100 | ≈ 28 MB |
| 500 | ≈ 138 MB |
| 1000 | ≈ 276 MB |

Cloud Run 配的是 1Gi。而且 `execute_analysis_request` 是**先建 run 再算**,
所以**命中缓存也照样新增一条 run** —— 缓存省的是外部 API 调用,不是内存。

---

# 第二部分:上下文管理

## 2.1 每轮模型看到什么

`_message_with_operational_context` 拼出**一个字符串**,四块:

```
Operator request: {用户这句话}
context_json: {结构化 JSON}
Compressed conversation context: {一段散文}
{固定指令文本}
```

## 2.2 `context_json` —— 结构化当前状态

- **`selected_aoi`**:`region_id` / `region_name` / `run_id` / `conversation_id` / `center` /
  `radius_km` —— **这些是编号和坐标,不是数值结论**。模型把它传给工具,工具拿编号去仓库查真数据。
  **这个设计是对的**:编号能重新查证,数值不能。
- **`latest_run`**:`risk_score` / `risk_level` / `drivers` / `recommendations`
- **`evidence`**:五个数据源的摘要

### ⚠️ 问题:四个数据源的来源标记被丢掉了

```python
"hotspots":          run.evidence["hotspots"]["data"]           # 只取 .data
"weather":           run.evidence["weather"]["data"]            # 只取 .data
"spatial":           run.evidence["spatial"]["data"]            # 只取 .data
"official_warnings": run.evidence["official_warnings"]["data"]  # 只取 .data
"elastic":           {"mode": ..., "evidence": [...][:3]}       # 保留了 mode
```

`mode` / `source` / `cached` / `status` 都挂在 `.data` **外面**。

**结果:模型看不出热点、天气、空间、预警数据是真实的、演示的、还是过期缓存的。**
第三部分说的那个"刷新失败就给旧数据"会打 `cached: True`,**这个标记永远到不了模型**。

只有 `elastic` 保留了 `mode` —— 而这恰恰是最该保留的,因为 Elastic 失败时系统会用一段
写死的假证据顶上(`elastic_mcp_tools.py` 的 `_fallback_payload`)。

## 2.3 `compressed_context` —— 压缩的对话历史

`build_context_summary` 生成的**纯文本**,每轮完全重建(实际每轮写了两次 ——
`finalize_chat_response` 调了两遍 `update_conversation_context`):

```
AOI: {区域名}. Latest analysis: {区域名} {等级} {分数}/100.
Elastic evidence ({mode}): {最多 2 条标题}. Earlier intents: {最近 6 个}.
Recent conversation: {最近 4 条,每条截断 120 字符}.
```

### ⚠️ 问题:压缩把"从哪来的"丢了

同一个风险分数的两种形态:

| | `run.evidence` 里 | `compressed_context` 里 |
|---|---|---|
| 形态 | 结构化字段 | `"Latest analysis: NSW HIGH 78/100."` |
| 真数据还是降级数据 | `mode` 说得清 | ❌ |
| 什么时候取的 | `selected_at` | ❌ |
| 怎么算出来的 | `drivers` 数组 | ❌ |

两种形态**并排放进同一个 prompt**,模型分不清哪个可追溯。系统目前靠一句指令处理:
`"Never answer directly from context_json or model memory."` —— **指令是最弱的约束手段**。

## 2.4 裁剪规则汇总

| 裁在哪 | 规则 |
|---|---|
| 用户单条消息 | 4000 字符 |
| 整个请求体 | 64 KB |
| 返前端的消息 | 最近 6 条 |
| 摘要里的对话 | 最近 4 条 × 120 字符 |
| 摘要里的历史意图 | 最近 6 个 |
| `context_json` 的 Elastic 证据 | 最多 3 条 |
| 单次分析保留热点 | 1600 个 |
| 概览保留热点 | 2400 个 |

**体积控制得不错。问题不在体积,在于截断时把"数据从哪来"一起丢了。**

---

# 第三部分:180 秒到底在做什么(实测)

## 3.1 结论先说

**默认路径上,180 秒缓存根本没生效 —— 每次请求都在重新拉数据。**

## 3.2 实测方法

给 `_fetch_dea_features` 和 `_fetch_australia_hotspot_rows` 打桩计数,其余外部依赖全部
stub 掉,`WILDFIRE_DATA_MODE=live`。

## 3.3 场景 A:默认 `region_id="live_australia"`,数据完全不变,连续 3 次分析

```
第1次: DEA拉取累计=1   分析缓存条目=1
第2次: DEA拉取累计=2   分析缓存条目=1
第3次: DEA拉取累计=3   分析缓存条目=1
```

**3 次分析 = 3 次 DEA 网络拉取。**

原因:`_select_live_hotspot_region()` 直接调 `_fetch_dea_features()`,
**完全绕过了 `_AUSTRALIA_OVERVIEW_CACHE`**。而 `live_australia` 是
`ChatRequest.region_id` 的默认值,也是 `settings.demo_region_id` —— 就是最常走的那条路。

## 3.4 场景 B:热点位置抖动 0.001°(约 100 米)

```
DEA拉取累计=4   分析缓存条目=2

live|live_nsw_97_429|-33.7100|150.3144|40.0|wildfire operational evidence|30d|...
live|live_nsw_97_429|-33.7100|150.3154|40.0|wildfire operational evidence|30d|...
```

经度从 `150.3144` 变成 `150.3154`,**缓存 key 变了,整包重算**。

原因:`_select_live_hotspot_region` 算的 AOI 中心是热点的**加权重心**,
而 `_analysis_cache_key` 把中心点按**小数点后 4 位(约 11 米)**放进 key。
真实热点数据每 10 分钟就变,重心随之漂移 —— **生产环境下这个缓存基本永远不命中。**

## 3.5 场景 C:固定 `region_id="state_nsw"` + 显式 AOI

```
第1次: DEA拉取=0  澳洲行缓存拉取=1  分析缓存条目=1
第2次: DEA拉取=0  澳洲行缓存拉取=1  分析缓存条目=1
第3次: DEA拉取=0  澳洲行缓存拉取=1  分析缓存条目=1
```

**这条路径是对的。** 缓存正常工作,3 次分析只拉 1 次。

## 3.6 三个设计缺陷

**缺陷一:自动选区路径绕过了缓存。**
`_select_live_hotspot_region` 用 `_fetch_dea_features()` 而不是
`_get_or_load_australia_hotspot_rows()`。同一份数据,两条取数路径,只有一条有缓存。

**缺陷二:缓存 key 包含一个持续变化的派生值。**
把"从数据算出来的重心"放进缓存 key,等于让缓存 key 跟着数据一起变。
**缓存 key 只应该包含请求参数,不应该包含数据的函数。**

**缺陷三:五个数据源被塞进同一个 180 秒 TTL。**
`_ANALYSIS_CACHE` 缓存的是整包证据,但这五个源的天然刷新率差了三个数量级。

## 3.7 真实火场需要的刷新频率

先看这个 app 实际调的五个数据源,以及它们**真实的**更新频率:

| 数据源 | 体积(实测) | 真实刷新频率 | 上游缓存头 | 当前 | 评价 |
|---|---|---|---|---|---|
| **DEA Hotspots** | **149 MB** | Himawari 每 10 分钟(144 次/天) | `ETag` + `Last-Modified` | 默认路径**每次都拉** | ❌ 见 3.8 |
| **Open-Meteo 预报** | 数 KB | 底层模式每 6 小时 | — | 180 秒 | ❌ 过度约 100 倍 |
| **NSW RFS 事件** | 69 KB | 事件驱动 | **`max-age=30`** | 180 秒 | ⚠️ 比上游建议值还长 |
| **OSM 道路/城镇** | 中等 | 天/周级 | — | 180 秒 | ❌ 过度约 1000 倍 |
| **NASA FIRMS** | — | NRT 延迟约 3 小时 | — | 180 秒 | ❌ 过度 |

### 关键洞察

**180 秒比 Himawari 的 10 分钟还要短。** 也就是说,即使缓存正常工作,你也在
**同一份数据上重复拉取约 3.3 次**,一点新鲜度都换不来 —— 纯浪费。

**最夸张的是 OSM 空间数据。** 道路和城镇的位置以周为单位变化,却被缓存 180 秒。
而且它恰恰是最慢最贵的那个(Overpass 查询,代码里专门给了 10 秒软超时)。

### 火场人员真正需要的节奏

真实的应急运营是分层的,不是一个统一的刷新率:

| 数据类型 | 应该多久刷新 | 依据 |
|---|---|---|
| **热点位置** | **10 分钟** | 对齐 Himawari 的真实节拍,再快没有新数据 |
| **官方警告/事件** | **1–2 分钟**(或改推送) | 事件驱动,疏散决策直接依赖它,这是唯一值得高频轮询的 |
| **天气实况** | 10 分钟 | BOM 州级观测就是 10 分钟粒度 |
| **天气预报** | 6 小时 | 底层模式的更新周期,拉更勤只是拿到同一份数据 |
| **火险等级 / FBI** | 每天 2 次 | 澳洲火险天气预报查看器就是每天 0800 和 1900 更新 |
| **地理底图(道路/城镇/保护区)** | **7 天** | 地物几乎不动;按 AOI 缓存,可以近乎永久 |

**另外一个更重要的点**:真实的事故管理团队按**operational period**(通常 12 小时一班)
运作,决策节奏是"班次级"的。分钟级刷新服务的是**态势感知**(地图上的点在动),
而不是**决策**(要不要疏散)。这两者需要不同的数据新鲜度保证:

- 态势图可以显示 10 分钟前的热点,只要**明确标注是 10 分钟前的**
- 疏散建议不能基于任何未标注时间的数据

这正好接回第二部分那个问题:**你的 `context_json` 把时间戳和 `mode` 都丢掉了。**

## 3.8 真正的问题:每次请求下载 149 MB 并全量解析

`_fetch_dea_features()` 对一个 **149 MB** 的 JSON 做 `httpx.get()` + `response.json()`,
15 秒超时。实测:

```
GET https://hotspots.dea.ga.gov.au/data/recent-hotspots.json
content-length: 156,537,355      ← 149 MB
features 条数 : 175,286          ← 整个澳洲

解析前 峰值 RSS:  12.9 MB
解析后 峰值 RSS: 679.4 MB        ← Cloud Run 实例上限 1024 MB
```

**单次解析占 679 MB,而部署配置是 `--memory 1Gi --concurrency 4`。
两个请求同时走到这一步就是约 1.36 GB,必然被 OOM kill。**

再叠加 3.3 的实测(默认路径每次分析都拉),这不是"缓存 TTL 设短了",
而是**架构方向反了**:上游拉取被挂在了用户请求的关键路径上。

### 上游已经把答案写在响应头里了

```
DEA: etag: "3fc9a36..."  +  last-modified: ...
     → 带 If-None-Match 重发,实测返回 304,传输 0 字节

RFS: cache-control: max-age=30, must-revalidate
     → 发布方明确说了缓存 30 秒
```

**尊重上游的缓存头,用条件请求,而不是自己发明 TTL。**

## 3.9 真实预警系统的通用模式

核心是一句话:**上游拉取与用户请求彻底解耦。**

| | 现在 | 应该 |
|---|---|---|
| 谁触发上游拉取 | **用户请求** | **后台定时任务** |
| 用户请求做什么 | 拉 149MB → 解析 → 计算 | **只读本地存储** |
| 拉取频率 | 每请求一次 | 固定节拍,对齐数据源 |
| 未变化时的成本 | 149 MB | **304,0 字节** |
| 前端更新方式 | 客户端轮询 | 服务端推送 |

Watch Duty 这类实际投产的野火预警应用就是这个结构:后台持续摄取多源数据入库,
客户端只读 + 接收推送。

## 3.10 建议的缓存策略

**第一步(最重要):把 DEA 摄取移出请求路径。**

后台定时任务每 10 分钟拉一次(对齐 Himawari 节拍),带 `If-None-Match`;
未变化拿 304 就直接返回。拉到新数据后**只保留聚合结果**入库,不保留 175k 原始 feature。
用户请求只读库,永不触发上游拉取。

这一步同时解决:OOM 风险、每请求 149MB 的传输、以及 3.3 的缓存绕过问题。

**第二步:分层 TTL,尊重上游缓存头。**

```
热点(DEA)        : 600 秒 + ETag 条件请求   ← 对齐 Himawari
官方警告(RFS)    : 尊重 max-age=30
天气实况          : 600 秒
天气预报          : 6 小时
地理底图(OSM)    : 7 天,按 AOI 持久化
Elastic 文档证据   : 1 小时
```

**第三步:修 3.6 的三个缺陷。**

1. 让 `_select_live_hotspot_region` 走统一的取数路径(缺陷一)
2. 缓存 key 只放请求参数,不放数据的派生值(缺陷二)
3. 每个数据源独立 TTL 独立过期(缺陷三)
4. 给"过期也给旧数据"加年龄上限,并把实际年龄带到 UI 和模型上下文

### 顺带:两个数据标注问题

```python
active_rows = [row for row in rows if row["detected_at"] >= now - timedelta(hours=24)]
if not active_rows:
    active_rows = rows          # ← 24 小时内没有时,悄悄改用全部历史数据
```

字段名还是 `hotspot_count_24h` / `count_24h`,但数据可能来自更早。

以及 demo 模式下 `selected_at` 的值是字符串 `"demo"` 而不是时间戳。

---

# 第四部分:冷启动 —— dashboard 为什么要等 10 秒

## 4.1 结论:是冷启动,与拉取数据无关

对线上服务实测 `/health`(该接口只返回一个字典,不访问任何数据):

| 请求 | TTFB |
|---|---|
| 第 1 次 | **12.73 秒** |
| 第 2 次 | 0.135 秒 |
| 第 3 次 | 0.139 秒 |

`/health` 不碰 DEA、不碰任何存储,所以这 12.7 秒**全部是 Cloud Run 冷启动**
(镜像拉取 + 容器启动 + Python 导入 + uvicorn 绑定)。

## 4.2 为什么用户感知到的是"整个 dashboard 卡住"

`frontend/app/page.tsx` 的挂载 effect 用 `overviewLoading` **阻塞整个页面渲染**,
等 `GET /api/hotspots/overview` 返回。冷启动期间这个请求一直挂着,
所以用户看到的是白屏,而不是"地图在加载"。

`getHotspotFocus` 是用户操作触发的,不在冷启动关键路径上。

## 4.3 启动路径上的重量(实测)

| | 加载模块数 | 包含的重包 |
|---|---|---|
| 修复循环导入**之前** | **1,643** | matplotlib、numpy、PIL、google.adk、google.genai |
| 修复**之后** | **813** | 无 |

单独 `import app.runtime.adk` 本地实测 **829 ms**(热文件系统 + 本机 CPU),
Cloud Run 冷启动时 CPU 受限,实际更慢。

matplotlib(30 MB)+ numpy(33 MB)+ PIL(14 MB)+ fontTools(19 MB)= **96 MB**
依赖,只被 `risk_trend.py` 和 `hotspot_visualization.py` 用于画图。

> ⚠️ **线上跑的仍是旧代码。** 1.7 节那个循环导入修复顺带把这些重包移出了启动路径,
> 但需要重新部署才能生效。

## 4.4 优化手段,按性价比排序

| # | 手段 | 成本 | 效果 |
|---|---|---|---|
| 1 | **前端不阻塞渲染** —— 先渲染外壳和地图,热点数据异步填充 | **$0** | 感知延迟 12 秒 → 0 秒 |
| 2 | **重新部署**,拿到惰性导入的收益 | **$0** | 启动模块数减半 |
| 3 | **把 matplotlib 导入挪进函数内部**(`risk_trend.py`、`hotspot_visualization.py` 现在是模块级导入) | **$0** | 首次聊天也不必加载 96 MB 依赖 |
| 4 | **`--cpu-boost`** 启动期临时提升 CPU | 仅启动那几秒计费 | 直接压缩冷启动时长 |
| 5 | **Cloud Scheduler 的监控 tick 兼做保活** | **$0**(3 个任务免费) | 每 10 分钟一次请求,实例基本不会被回收 |
| 6 | `--min-instances 1` | **约 $10/月** | 彻底消除冷启动 |

**第 1 项是最大的一笔,而且不花钱。** 冷启动客观上仍然存在,但用户不再盯着白屏 ——
这是感知性能和实际性能的区别。

**第 5 项很划算**:第六部分本来就建议把监控循环改成 Cloud Scheduler 打
`/tasks/monitor-tick`。每 10 分钟一次请求会让实例保持温热,**保活是白送的副作用**。

**第 6 项不建议**:每月 10 美元,而第 1、4、5 项加起来基本能解决问题。
如果面试前想要绝对稳妥的演示效果,可以临时开几天再关掉。

## 4.5 顺带:降低内存配置的前提

现在 `--memory 1Gi` 有很大一部分是被 3.8 那个 679 MB 的 JSON 解析吃掉的。
把 DEA 摄取移出请求路径之后,请求路径的内存占用会大幅下降,
**届时可以考虑降到 512Mi,进一步省钱**。

---

# 第五部分:存到哪里

## 5.1 约束条件

1. **成本优先** —— 个人 GCP 账号自费
2. **必须体现生产级能力** —— 这是作品集项目
3. **现在被迫 `--max-instances 1`**,因为状态在单进程内存里
4. **审批和审计记录必须持久** —— 这是应急系统的核心,丢了整个产品就没有意义

## 5.2 数据的实际访问模式

| 数据 | 访问方式 | 特点 |
|---|---|---|
| `runs` | 按 ID 点读;按 region 查最新一条 | 写一次读多次,体积大 |
| `conversations` + messages | 点读 + 追加 + 取最近 6 条 | 高频小写 |
| `actions` / `approvals` | 点读 + 全量列出 | 量小,**必须持久** |
| `reports` | 点读,Markdown 全文 | 写一次,体积中等 |
| `monitor_tasks` | 扫描到期任务 | 量小 |
| `agent_events` | 最近 200 条,推 WebSocket | 高频写,可丢 |
| `audit_logs` | 只追加,几乎不读 | **必须持久**,适合冷存 |

## 5.3 选项对比

| 方案 | 免费额度 | 空闲成本 | 契合度 |
|---|---|---|---|
| **Firestore(原生模式)** | 1 GiB 存储、5 万读/天、2 万写/天、2 万删/天、10 GiB 出站/月 | **$0** | ✅ 文档模型贴合;**原生 TTL 策略**;实时监听可替代 WebSocket hub |
| **Cloud SQL(Postgres)** | 无免费额度 | **约 $8–10/月起,常驻计费** | ❌ 空闲 99% 的 demo 纯烧钱;还要配连接池 |
| **Memorystore(Redis)** | 无 | **约 $35/月起** | ❌ 直接排除 |
| **BigQuery** | 10 GB 存储、1 TB 查询/月 | $0 | ⚠️ 只适合审计和事件流,不适合点读 |
| **GCS** | 5 GB 标准存储/月 | $0 | ⚠️ 适合大块 blob,配对象生命周期规则 |

## 5.4 推荐:Firestore 为主,配一次数据形态改造

### 为什么是 Firestore

1. **空闲零成本。** Cloud SQL 是常驻计费,对一个大部分时间没人访问的作品集项目,
   每月十块钱换不来任何东西。Firestore 按用量计费,不用就不花钱。
2. **原生 TTL 策略。** 可以直接在时间戳字段上配过期删除,不用自己写清理任务 ——
   这正好补上第一部分那个"除了 `agent_events` 全都没有上限"的洞。
3. **文档模型贴合。** `RunRecord`、`ConversationRecord` 本来就是自包含文档,
   messages 做子集合天然支持"取最近 6 条"。
4. **实时监听。** 可以直接替掉现在那个进程内的 `AgentEventHub`(它在多实例下根本不工作)。
5. README 已经这么写了 —— 补上实现,而不是改文档去迁就代码。

### 关键改造:不要再持久化原始热点数组

这是**比选哪个数据库更重要**的一步。

现在 `run.evidence["hotspots"]["data"]["hotspots"]` 存着最多 1600 个热点点位
(实测 283 KB)。但**分析跑完之后,这些点位没有任何用处**了 ——
地图已经渲染过,后续所有问题("风险为什么高"、"和昨天比怎么变的")用的都是聚合值。

改成只存聚合:点数、重心、包围盒、置信度分布、`mode`、`observed_at`。
需要重放点位时按 `run_id` 重新拉。

效果:

| | 单 run 体积 | 1 GiB 免费额度能存 |
|---|---|---|
| 现在 | ≈ 283 KB | ≈ 3,700 次分析 |
| 改造后 | ≈ 3 KB | **≈ 350,000 次分析** |

**这一步比任何数据库选型都省钱,而且让 Firestore 文档保持在快读、便宜的区间。**

### 写入量核算(验证免费额度够不够)

单次分析的写入:1 run + 1 report + 约 8 条 trace event + 2 条聊天消息 +
1 次 conversation 更新 + 约 7 条 agent event ≈ **20 次写**。

2 万次写/天 ÷ 20 ≈ **每天 1000 次分析** —— 作品集演示绰绰有余。

如果要更省,把 `trace events` 和 `agent_events` **批量合并成 run 文档里的一个数组字段**,
单次分析降到约 5 次写,变成每天 4000 次分析。

### 审计日志:单独放 BigQuery

`audit_logs` 和 `agent_events` 是**只追加、几乎不点读、需要长期保存**的数据 ——
这正是 BigQuery 的形状,而且代码里已经有 `_write_bigquery_event` 的桩子了。

但要修一个问题:现在那段代码**每条事件都新建一个 `bigquery.Client()`**
并且在请求路径上同步插入。应该改成复用客户端 + 批量异步写入。

**理由要说清楚**:审计记录的生命周期必须**长于**运营数据。运营数据配 TTL 自动删,
审计记录不能删 —— 放在同一个库里,这两种策略会互相打架。

## 5.5 取舍

| 选择 | 得到 | 放弃 |
|---|---|---|
| Firestore 而非 Cloud SQL | 空闲零成本;原生 TTL;免运维 | 复杂查询能力;跨文档事务较弱(本项目用不到) |
| 不存原始热点点位 | 存储降低约 100 倍 | 无法按历史 run 重放点位图(可按需重拉) |
| 审计放 BigQuery | 长期留存与运营数据解耦 | 多一个系统;审计查询有延迟(可接受) |
| 保持不做跨会话记忆 | 不引入陈旧偏好、班次隔离、纠错、审计解释这一整套复杂度 | 无法"记住指挥官偏好"(当前需求不需要) |

---

# 第六部分:省钱 + 体现生产能力

这两个目标在大部分点上**不冲突**,因为浪费本身就不是生产级做法。

## 6.1 最大的一笔省钱:监控循环改用 Cloud Scheduler

现在 `start_monitor_loop()` 用 `asyncio.create_task` 在进程内跑死循环。这有两个问题:

1. **不可靠。** Cloud Run 在没有请求时会把 CPU 降到接近零,实例还会被回收。
   要让它可靠就得开 `--no-cpu-throttling`(常驻 CPU 计费),**这是最贵的一档**。
2. **多实例会重复告警。** 每个实例都跑自己的循环。

改成 **Cloud Scheduler 定时打一个 `/tasks/monitor-tick` 接口**:

- Cloud Scheduler **每个结算账号免费 3 个任务**
- Cloud Run 可以保持 `--min-instances 0` + CPU 节流,**只按请求计费**
- 顺便解决了多实例重复告警,也不再依赖"进程一直活着"

**这一条同时是省钱和生产级架构** —— 面试里这是个好例子:
把"进程内定时器"换成"外部调度 + 无状态接口",是有状态服务变无状态的标准做法。

## 6.2 分层 TTL 直接减少出站流量

按第三部分的分层策略,粗算每天的外部拉取次数(假设 100 次分析/天):

| 数据源 | 现在 | 改造后 | 降幅 |
|---|---|---|---|
| DEA Hotspots | 100 次(每次分析都拉) | 144 次/天封顶,实际按需 | 对齐真实节拍 |
| Overpass(OSM) | 100 次 | ≈ 每个 AOI 每周 1 次 | **约 700 倍** |
| Open-Meteo | 100 次 | 每 6 小时 = 4 次 | **25 倍** |

Overpass 那一项收益最大 —— 它既慢又重,而数据几乎不变。

## 6.3 存储成本

按 5.4 的改造,1 GiB 免费额度能存约 35 万次分析。配上 Firestore TTL 策略
(运营数据留 30 天,审计进 BigQuery 长留),**实际上永远不会超出免费额度**。

## 6.4 解锁 `--max-instances > 1`

状态外移之后,`--max-instances 1` 这个限制就没了。但**不要立刻调高** ——
Cloud Run 按实例数计费,作品集项目设 `--max-instances 2` 就够了。

**关键是:限制从"架构上做不到"变成"成本上主动选择"。** 这两件事在面试里
是完全不同的答案。

## 6.5 不要做的省钱动作

- ❌ 不要为了省钱把 TTL 调得更长而不标注数据年龄 —— 应急产品里这是安全问题
- ❌ 不要为了省 Firestore 写入而不落审批/审计记录
- ❌ 不要上 Redis 缓存层 —— 每月 35 美元起,而 Firestore 读本来就够快

---

# 第七部分:改造顺序

按"每一步都留下一个能跑的系统"排:

| # | 动作 | 收益 | 工作量 |
|---|---|---|---|
| 1 | ~~修跨用户会话泄漏~~ | 安全 | ✅ 已完成 |
| 2 | ~~修循环导入~~(顺带把启动模块数减半) | 可测试性 + 冷启动 | ✅ 已完成 |
| 3 | **重新部署**,让第 2 步的冷启动收益生效 | 冷启动 | **10 分钟** |
| 4 | **前端不阻塞渲染** —— 先出外壳,数据异步填充 | 感知延迟 12 秒 → 0 | **半天,零成本** |
| 5 | **DEA 摄取移出请求路径** + ETag 条件请求 | 消除 OOM 风险;每请求 149MB → 0 | 1 天 |
| 6 | 停止持久化原始热点数组,只存聚合 | 存储降约 100 倍 | 半天 |
| 7 | 分层 TTL + 统一取数路径 + 缓存 key 去掉派生值 | 外部拉取大幅下降 | 半天 |
| 8 | matplotlib 导入挪进函数内部 | 首次聊天不加载 96MB 依赖 | 1 小时 |
| 9 | `--cpu-boost` | 压缩冷启动 | 10 分钟 |
| 10 | 把 `mode` / `observed_at` 带到 `context_json` 和 UI | 能看出数据新鲜度 | 半天 |
| 11 | `Store` 抽象 + `FirestoreStore` 实现 | 解锁多实例;数据不再随重启消失 | 1–2 天 |
| 12 | 监控循环改 Cloud Scheduler(兼做保活) | 省钱 + 无状态 + 冷启动 | 半天 |
| 13 | Firestore TTL 策略 + 审计写 BigQuery | 自动清理;审计长留 | 半天 |
| 14 | ~~身份认证:审批 `actor` 从 token 取 + 要求 admin~~ | 审批链路不再可伪造 | ✅ 已完成(见 1.7) |
| 15 | ~~chat 处理器用已验证身份覆盖 `ChatRequest.user_id`~~ | 1.6 的归属检查真正生效 | ✅ 已完成 |
| 16 | ~~`alerts.py` 的 `actor` 同样从 token 取~~ | 审计日志的操作人不再可伪造 | ✅ 已完成 |
| 17 | ~~WebSocket token 移出 query 参数~~(顺带修好了从未工作过的 WS 端点) | 凭据不进访问日志 | ✅ 已完成 |

**第 3、4 步今天就能做完,而且零成本** —— 它们直接解决你感知到的 10 秒卡顿。
**第 5 步优先级最高**:679 MB 的解析峰值配 1Gi 内存和 concurrency 4,现在是随时会 OOM 的状态。
第 11 步是解锁一切的关键。**身份认证部分(第 14–17 步)已经全部完成**:
审批、对话、告警确认三条链路的身份都不再可伪造,WebSocket 凭据也移出了 URL。
剩下的都是性能与存储改造,不再有已知的鉴权缺口。

---

# 第八部分:ADK 会话状态踩坑与记忆最佳实践

本部分是 2026-09-01 接真实 Gemini 跑离线评测时挖出来的。两个 bug 都属于
**代码看起来完全正确、但静默失效**的类型,单靠读代码发现不了。

## 8.1 踩坑一:`get_session()` 返回的是深拷贝,就地修改无效

**症状**:8 条 memory 用例在 mock runtime 下 100% 通过,接真实 ADK 后
`memory_exact_match_accuracy` 直接掉到 **0**。路由对、工具对,查询也执行了,
但一律返回 `not_found`。

**当时的代码**(`app/runtime/adk/session.py`):

```python
session = await session_service.get_session(...)
session.state.update(_state_delta_for_request(request))   # 静默失效
```

**根因**。ADK 源码 `google/adk/sessions/in_memory_session_service.py:202`:

```python
copied_session = _copy_session(session)
...
# Return a copy of the session object with merged state.
return self._merge_state(app_name, user_id, copied_session)
```

`get_session()` 返回**深拷贝**。改拷贝不影响存储。没有异常、没有警告、`update()`
正常返回 —— 写进去的东西直接蒸发。

**断链完整路径**:

```
LLM 调 conversation_memory_lookup_tool
  → 工具只能看 session state,读 conversation_id
  → 拿到 None                                    ← 断点
  → 构造 conversation_id=None 的 ChatRequest
  → store.conversations.get("") 查不到
  → not_found
```

对话内容一直好好躺在 `InMemoryStore` 里。丢的是**指向它的那个键**。

**ADK 只认两条写入路径**:

| 路径 | 用法 |
|---|---|
| 创建时传入 | `create_session(..., state={...})` |
| 事件提交 | `append_event(session, event)`,状态放 `event.actions.state_delta` |

这样设计是为了让状态变更可排序、可重放,换 `DatabaseSessionService` /
`VertexAiSessionService` 后端时同一份代码仍然成立。就地改内存对象换个后端立刻失效。

**已修**:`_ensure_session()` 增加可选 `state` 参数,创建会话时就把
`_state_delta_for_request(request)` 播种进去。

## 8.2 踩坑二:`app:` 前缀是**全应用共享**,不是会话级

ADK 的 state 键前缀有语义,源码 `in_memory_session_service.py:126` 把 `app:` 开头的键
写进 `self.app_state[app_name]`,再由 `_merge_state` 合并进**每一个**会话:

| 前缀 | 作用域 |
|---|---|
| `app:` | 该应用**所有用户、所有会话**共享 |
| `user:` | 该用户跨会话 |
| 无前缀 | 仅当前会话 |
| `temp:` | 不持久化 |

我们把 `conversation_id` / `run_id` / `user_id` / `region_*` / `aoi_*` 全写成了
`app:` 前缀。单用户 demo 看不出问题,**多用户并发时用户 A 的工具会读到用户 B 的坐标**。
这与 1.6 修的会话 ID 归属校验是两个独立问题:1.6 管的是"能不能恢复别人的会话",
这里管的是"当轮工具读到谁的坐标"。

**已修**:全部去掉 `app:` 前缀改为会话级。涉及 3 个文件、8 个键:
`session.py`、`tools/_shared.py`、`tools/scenario_tools.py`。

## 8.3 为什么离线评测没测出来

mock runtime 直接把 `ChatRequest` 对象传给 handler,**完全不经过 ADK session state**。
写入、序列化、工具读取这整条链路在离线评测里一行都没执行过。

50 条用例全绿,测的却是另一条代码路径。

**教训:评测必须走生产路径,否则测得越绿越危险。** 这也是本项目评测框架加
`--runtime {mock_demo,adk}` 开关的原因。

## 8.4 Agent 记忆最佳实践

**四层要分清**:

| 层 | 内容 | 存哪 | 生命周期 |
|---|---|---|---|
| 工作状态 | 当前轮的坐标、指针 | session state | 单次会话 |
| 对话历史 | 消息 transcript | 真正的存储,append-only | 长期 |
| 长期记忆 | 跨会话的用户偏好 | 独立存储 + 显式写入策略 | 永久 |
| 检索知识 | 文档、政策 | 向量库 / 搜索 | 与会话无关 |

**六条原则**:

1. **身份与内容分离。** session state 只放 ID 指针,内容放真正的存储。
   本项目架构本来就是对的 —— 很多实现反过来把整段历史塞进 session state,几轮就爆 context。
2. **精确回忆必须走确定性查询,绝不问模型。** 「我上一个问题是什么」要么从存储精确取出,
   要么明说没有。本项目做对了这点,所以失败时返回 `not_found` 而不是编一个问题 ——
   这也是 `hallucinated_state_rate` 全程为 0 的原因。
3. **单一真相源。** transcript 只有一个 owner。
4. **显式写入路径 + 写后读回验证。** 一行断言就能在第一次运行时炸出 8.1 那个 bug。
5. **边界处校验上下文。** 工具拿到 `conversation_id=None` 应当抛错,而不是安静返回
   `not_found` —— 它把配置 bug 伪装成了"没有记录"。
6. **键要分作用域。** 见 8.2。

**不要修改框架 getter 返回的对象。** 默认假设拷贝语义,除非文档明确说是引用。

## 8.5 修复前后实测

同一套 50 条 golden case,真实 Gemini(`--runtime adk`):

| 指标 | 修复前 | 修复后 |
|---|---|---|
| `success_rate` | 0.60 | **0.74 – 0.76** |
| `memory_exact_match_accuracy` | **0.00** | **1.00** |
| `tool_argument_accuracy` | 0.64 | 0.86 |
| `route_accuracy` | 0.94 | 0.94 – 0.98 |
| `p95_latency_ms` | 10,249 | 8,379 |
| `unsafe_action_execution_rate` | 0.0 | 0.0 |
| `hallucinated_state_rate` | 0.0 | 0.0 |

> 给了区间是因为**同一份代码连跑两次结果会抖**(0.74 / 0.76,route 0.94 / 0.98)。
> LLM 评测本身有运行间方差,单次结果不能当精确指标用。要报数就多跑几次取中位数,
> 或者只报确定性指标(`memory_exact_match`、`unsafe_action`、`hallucinated_state`)。

**离线 mock 的数字不能代表线上**:mock 的 p50 是 0.09 ms,真实 Gemini 是 **5,900 ms** ——
差六万倍。mock 只适合做回归门禁,不能用来谈性能。

---

## 8.6 评测重构:契约断言 vs 能力断言

**问题**:2026-09-01 的评测里,13 条失败中只有 2 条是模型行为问题,其余 11 条是
**我们自己的标签重命名和字段路径分歧**。但它们全部混在一个 `success_rate` 里,
导致这个数字既不能反映 agent 能力,也不能定位代码问题。

最典型的是工具断言的实现:

```python
tool_ok = str(expected.get("tool", "")) in trace_text   # 对人类可读文本做子串匹配
```

重构一次显示标签,评测大面积飘红,而模型什么都没变。8 月 18 号的存档是 100%,
今天同一份 mock 只有 82% —— 差的全是标签,不是能力。

**重构**:把断言分成两类,分别计分。

```python
# 契约:断言响应形状——字段路径、trace 标签。重构会破,与 agent 行为无关。
contract_checks = [tool_ok] + argument_results + memory_result

# 能力:断言 agent 做对了事。
capability_checks = [route_ok, not scope_false_pass, not scope_false_reject,
                     not unsafe_executed, not hallucinated_state] + artifact_results + multi_step
```

**关键规则:契约破损的用例不计入能力分母。** 读不到字段意味着"答案不可读",
不等于"答案错了"。这是三态而非二态:通过 / 失败 / **不可测**。

新增汇总字段:

| 字段 | 含义 |
|---|---|
| `capability_pass_rate` | 契约完好用例上的能力通过率 —— **对外要报的就是这个** |
| `capability_pass_rate_all_cases` | 全部用例上的能力通过率(保守口径) |
| `contract_pass_rate` | 契约通过率 —— **这是我们自己代码的健康度,不是模型的** |
| `contract_broken_case_ids` | 契约破损清单,直接指向要修的地方 |
| `success_rate` | 旧口径(两类混合),保留兼容,**不要用它对外报数** |

全部落地后的真实 ADK 运行:

| 指标 | 起始 | 最终 |
|---|---|---|
| `success_rate` | 0.60 | **0.94** |
| `capability_pass_rate` | — | **0.94** |
| `contract_pass_rate` | 0.78 | **1.00** |
| `tool_selection_accuracy` | 0.80 | **1.00** |
| `tool_argument_accuracy` | 0.64 | **1.00** |
| `memory_exact_match_accuracy` | 0.00 | **1.00** |
| `multi_step_completion_rate` | 1.00 | 1.00 |
| `unsafe_action_execution_rate` | 0.0 | 0.0 |
| `hallucinated_state_rate` | 0.0 | 0.0 |
| p50 / p95 延迟 | 5,961 / 10,249 ms | 6,136 / 10,346 ms |

**契约类失败已全部清零。** 剩下 3 条全是能力问题,且集中在一类:**相近意图的边界混淆**

```
qa_008        QUESTION       → ANALYST_QA
workflow_003  ACTION_COMMAND → EXPOSURE_ACTION
safety_001    ACTION_COMMAND → EXPOSURE_ACTION
```

这才是需要靠提示词和工具描述去解决的部分,也是唯一结果不保证的部分。

### 已完成:`tool_ok` 已升回能力指标

工具选择**本质上是能力问题** —— "agent 有没有挑对工具"显然是行为。
但当前实现断言的是展示标签的子串,所以它测的实际上是字符串,不是决策。

**已落地**:新增 `app/services/tool_registry.py`,把 **稳定 id → 可接受展示标签** 的映射
收敛到一处;golden 的 50 条断言从 `tool` 展示名迁移到 `tool_id`;`_score_case` 改为
解析 id 再比对标签,`tool_ok` 移回 `capability_checks`。

```python
TOOL_IDS = {
    "analyst_qa": ("Analyst Agent", "Gemini Context Answer"),          # 重命名，保留历史别名
    "hotspot_visualization": ("Hotspot Density Tool", "Hotspot Visualization Tool"),  # 被拆分
    ...
}
```

以后重命名展示文案,只改这里一个元组,不用动 50 条 golden。

> ⚠️ **这次重新基线化了 9 条用例,是一个判断,不是纯技术修复。**
> `Gemini Context Answer` 已被 `Analyst Agent` 取代,`Hotspot Visualization Tool` 被拆成
> Density / Contour / AI Map Interpreter 三个。registry 把旧名作为别名接受,等于认定
> **这两次是重构而非行为回归**。如果当初的意图是"真实问题不该走 Analyst Agent",
> 那这 9 条应该改的是运行时,不是 registry。

## 8.7 顺带修正:计算结果的响应形状分歧

`calc_001` / `calc_002` 曾被判失败,断言 `response.result` 为 `null`。实际探测:

| runtime | `response.result` | `response.calculation.result` |
|---|---|---|
| `mock_demo` | 314.1592653589793 | 314.1592653589793 |
| `adk` | **不存在** | 314.1592653589793 |

**计算本身两边完全正确且一致**,分歧只在 mock 额外挂了一个顶层 `result` 冗余副本。
前端全仓搜不到任何对 `response.result` 的读取,所以这不是线上缺陷。

**处理**:golden 的断言路径改为 `response.calculation.result` ——
即两个 runtime 都真实产出的那个形状。**没有给 ADK 补 `response.result`**,
那只会把 mock 的冗余复制过去。mock 顶层的 `result` 建议后续删除。

> 这与 8.1 是同一类问题:**mock 与生产的响应形状分歧**。
> 8.1 是 session state 没写进去,8.7 是字段挂在不同层级。
> 每次这类分歧都会让离线评测给出虚假的绿色。

---

# 附:一张总表

| 存在哪 | 装什么 | 保鲜期 | 上限 | 重启后 |
|---|---|---|---|---|
| `InMemoryStore` 8 个集合 | 业务数据 | ❌ | ❌ | 全丢 |
| `InMemoryStore.agent_events` | 事件流 | ❌ | ✅ 200 条 | 全丢 |
| ADK `InMemorySessionService` | 坐标 + 草稿 + 对话事件 | ❌ | ❌ | 全丢 |
| `_ANALYSIS_CACHE` | 分析结果 | 180 秒(**key 会漂,基本不命中**) | ❌ | 全丢 |
| `_AUSTRALIA_OVERVIEW_CACHE` | 全澳热点 | 180 秒(**默认路径绕过它**) | 单条 | 全丢 |
| 浏览器 React state | conversationId | — | — | **刷新即丢** |

---

## 外部资料出处

- [DEA Hotspots 产品说明](https://knowledge.dea.ga.gov.au/data/product/dea-hotspots/index.html) —— Himawari 每 10 分钟(144 次/天),极轨卫星 2–10 次/天
- [Digital Earth Australia Hotspots 数据集](https://researchdata.edu.au/digital-earth-australia-hotspots-dataset/3431940)
- [NSW RFS 火险天气预报查看器](https://fireweather.aig.apps.rfs.nsw.gov.au/about.html) —— 每天 0800 与 1900 更新
- [AFDRS 官方站](https://afdrs.com.au/) —— 火险等级与 Fire Behaviour Index
- [BOM 预报更新时间](https://www.bom.gov.au/news-and-media/weather-forecast-update-times-align-nationwide) —— 每天 4 次,每 6 小时
- [BOM 气象站数据说明](https://www.bom.gov.au/climate/data/stations/about-weather-station-data.shtml) —— AWS 1 分钟至每小时
- [Firestore 配额与限制](https://firebase.google.com/docs/firestore/quotas) —— 免费额度
- [Cloud Scheduler 定价](https://cloud.google.com/scheduler/pricing) —— 每结算账号 3 个免费任务
- [Cloud Run 启动 CPU 加速](https://cloud.google.com/blog/products/serverless/announcing-startup-cpu-boost-for-cloud-run--cloud-functions) —— `--cpu-boost`
- [Watch Duty 工作原理](https://www.watchduty.org/how-it-works/overview) —— 实际投产的野火预警应用,推送为主
- DEA / RFS feed 的体积与缓存头为本次直接实测,非引用
