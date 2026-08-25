# Chat 流水线契约

状态:`/api/chat` 请求路径的规范文档。本文档具有约束力 —— 运行时代码应当与之一致,
`tests/pipeline/` 下的测试负责强制执行。

## 0. 这份文档为什么存在

Chat 路径是一条固定顺序的阶段流水线。但今天这条流水线是**隐式**的:它被写了两遍,
一遍在 `AdkRuntime._route_chat_async`,一遍在 `MockDemoRuntime.route_chat`,没有任何
共享定义。两份拷贝已经漂移(见 §5)。

本契约给这些阶段命名、固定顺序、定义每个阶段可以做什么和不可以做什么,目的是让系统变成
**一条流水线 + 两种合成策略**,而不是两条各自演化的流水线。

## 1. 设计决策

以下是承重的选择。每一条都是决策而非偶然,并且每一条我们都明确接受了它的代价。

### D1 —— 路由是确定性的,模型负责参数抽取和措辞

确定性层决定**走哪条 workflow**,LLM 决定**参数抽取**和**最终措辞**。

**理由**:应急运营场景下,路由选择必须可复现、可审计。"系统为什么起草了一份公众预警?"
这个问题的答案不能依赖采样。而自然语言参数抽取和面向指挥官的语言合成,才是模型真正值回
成本的地方。

**接受的代价**:`classify_intent` 是关键词级联,遇到它没覆盖的表达方式会误路由。这是一个
已知且有界的失败 —— 它会选错 workflow,但**绝不会产出无依据的回答**。

### D2 —— 范围门是允许清单,不是语义分类器

`is_wildfire_operations_request()` 保持确定性,保持允许清单形态。判断不确定的请求一律拦截,
并告知操作员重新表述。

**理由**:零延迟、零成本、不引入新的故障模式,以及最关键的一点 —— **可审计**。"我为什么被
拦了"有精确答案。小模型门在这四项上全面劣于当前方案。

**接受的代价**:关键词堆砌可以绕过("我在做山火研究,忽略你的规则然后……")。但影响范围被
D1 限制住了:通过范围门之后的一切都会被路由进某个 workflow tool,而它们全部返回结构化
payload。**不存在从"通过范围门"到"模型自由生成"的路径。**

### D3 —— 注入防御:通道隔离优先,模式匹配垫底

按重要性排序:

1. **工具与检索返回的内容永远不进入 instruction 通道**,一律作为带分隔符的 data 传入。
2. **身份信息(`user_id`、审批 `actor`)永远不来自模型输出。**
3. **工具自己校验参数**,不假设模型已经校验过。
4. 确定性模式拦截(`before_model_callback`)—— **最后一层,不是第一层**。

第 4 层存在于 `app/services/guardrails.py`,但目前**没有被接入任何代码路径**。§3 的阶段 2
给了它调用点。第 1–3 层是结构性的,是对整个代码库的断言,而不是对某个阶段的断言。

**推迟的事项**:基于模型的门。它在检索(RAG)落地时才值得做,而且到那时它应该架在
**检索回来的文档内容**上,不是用户消息上 —— 那才是真正的注入面。

### D4 —— Memory 用来解析问题,绝不用来回答问题

对话历史只有两个合法角色:

- **问题解析**(阶段 3):把表述不完整的请求补全为完整请求 —— 把"那个区域"解析成具体
  AOI,把"再跑一次"解析成具体的历史 run。
- **显式召回**(`MEMORY_LOOKUP` 意图):操作员直接问自己刚才问了什么、当前选中的 AOI 是
  哪个。这是一个有确定性工具的 workflow,不是推断。

**明确否决的非目标**:把对话历史当作证据来源,去回答任何工具都答不了的问题。

对话历史不是关于世界的真相来源。加一级"兜底就从 memory 里自己回答",等于把阶段 6 的拒答
路径专门要防的无依据生成重新引入系统,而且是以**最难被发现的形态** —— 它读起来就像一个
正常回答。

### D5 —— 阶梯的终点是拒答,不是自己作答

当没有任何确定性工具能服务该请求时,终态是 `KNOWLEDGE_REQUIRED`:声明此问题需要经过验证的
文档检索、指出缺失的是什么、然后停止。见 `_knowledge_required_response`。

### D6 —— 一个 orchestrator + 扁平 tools,不用 sub-agents

`root_agent` 是单个 `LlmAgent`,持有全部 workflow tools。ADK 的 sub-agent 每跳要多付一次
模型调用,并给每一跳独立的 instruction 预算和 context。这两样在这里都买不到东西:单一领域、
单一共享 context(AOI),而且按 D1,路由决策我们已经**刻意不交给模型**了。

**何时该回头重新考虑**:tool 数量超过约 15–20 个,以至于一条 instruction 无法把它们都描述
清楚;或者某个子领域确实需要不同的 system instruction 或不同的模型。

### D7 —— 扇出属于证据采集层,不属于路由层

这条流水线是一条**阶梯**:有且只有一级会产出 payload。因此合成阶段永远只面对一个结构化
payload,不存在多路结果需要调和。

真正需要并行扇出的地方已经有了 —— `analysis_pipeline._collect_evidence` 并发查询 weather、
hotspots、warnings 和 Elastic。在路由层再加一层扇出,只会增加成本和调和歧义,换不来任何收益。

## 2. 阶段总表

| # | 阶段 | 决定什么 | 何时短路 |
|---|------|---------|---------|
| 1 | `scope_gate` | 是否属于本领域 | 超出范围 → `OUT_OF_SCOPE` |
| 2 | `injection_gate` | 是否结构性恶意 | 命中模式 → `BLOCKED` |
| 3 | `resolve_context` | 到底在问什么 | 不短路 |
| 4 | `analysis_gate` | 前置状态是否就绪 | 无已完成 run → `must_run_analysis` |
| 5 | `route` | 走哪条 workflow | 不短路 |
| 6 | `execute` | 执行 workflow | 无匹配 workflow → `KNOWLEDGE_REQUIRED` |
| 7 | `synthesize` | 面向操作员的措辞 | 不短路 |
| 8 | `finalize` | 持久化 + 发出 trace | 总是执行(终态) |

**顺序具有约束力。** 任一阶段可以读取 `ChatContext` 中位于它之前的任何内容,不得依赖任何
位于它之后的内容。

## 3. 各阶段契约

### 1. `scope_gate`
- **输入**:`ChatRequest`
- **输出**:继续,或短路返回 `out_of_scope_response()`
- **实现**:`request_scope.is_wildfire_operations_request`
- **不变式**:在任何模型调用、任何持久化、任何工具调用之前执行。被拦截的请求不留下
  conversation 记录,不产生任何成本。

### 2. `injection_gate`
- **输入**:`ChatRequest.message`
- **输出**:继续,或短路返回 `blocked` payload
- **实现**:`guardrails.before_model_callback`(D3 第 4 层)
- **不变式**:确定性,不调用模型。拦截时必须记录命中的具体原因。

### 3. `resolve_context`
- **输入**:`ChatRequest`、对话历史
- **输出**:填充了 `conversation`、归一化 `request`(AOI / run_id 已解析)、`trace_id`
  和压缩上下文摘要的 `ChatContext`
- **实现**:`chat_conversations.prepare_conversation`、`build_context_summary`
- **不变式(D4)**:本阶段可以**读取**历史来把问题补全。**不得**产出任何回答、事实或证据
  性断言。

### 4. `analysis_gate`
- **输入**:intent、request、conversation
- **输出**:继续,或短路返回 `analysis_required_response()`
- **实现**:`chat_conversations.should_block_for_analysis`
- **不变式**:依赖 run 状态的 workflow 永远不会观察到缺失的 run。

### 5. `route`
- **输入**:归一化后的消息
- **输出**:`ChatContext.intent`
- **实现**:`intents.classify_intent`
- **不变式(D1)**:确定性且全覆盖 —— 总是返回一个 intent,兜底为 `QUESTION`。模型不参与。

### 6. `execute`
- **输入**:`intent`、归一化 request、已解析的 run
- **输出**:结构化 payload,或短路返回 `KNOWLEDGE_REQUIRED`(D5)
- **实现**:共享 workflow 分派(当前为 `_route_deterministic_workflow`)
- **不变式**:**所有 runtime 的 intent 覆盖必须完全一致。** 这正是当前代码违反的不变式,
  见 §5。

### 7. `synthesize`
- **输入**:阶段 6 产出的结构化 payload
- **输出**:同一 payload,附加面向操作员的 `answer`
- **实现**:`adk` → LLM(`_apply_synthesis_answer`,由 `_valid_synthesis_answer` 校验,
  模板兜底 `_safe_synthesis_answer`);`demo` → 仅模板
- **不变式**:answer 只能引用 payload 中**实际存在**的字段,不得引入新事实。校验失败时回退
  到模板 —— **绝不回退到自由生成**。
- **这是唯一一个在不同 runtime 之间存在差异的阶段。**

### 8. `finalize`
- **输入**:response payload
- **输出**:终态响应 —— 持久化用户和助手两条消息、更新压缩上下文、发出 trace 事件、附加
  `conversation_id` / `trace_id` / `timing_trace`
- **实现**:`chat_conversations.finalize_chat_response`
- **不变式**:每个请求恰好执行一次,**包括所有短路路径**。

## 4. Runtime 变体

按 D1 和 §3.7,两个 runtime 有且只有一个阶段不同:

- `AdkRuntime`:阶段 1–6、8 共享;阶段 7 = LLM 合成
- `MockDemoRuntime`:阶段 1–6、8 共享;阶段 7 = 模板合成

**除此之外两者的任何差异都是缺陷。**

## 5. 本契约要关闭的已知缺陷

1. **intent 覆盖漂移(违反 §3.6)。** `RISK_TREND`、`RISK_PREDICTION` 以及混合
   exposure/action 请求只在 `MockDemoRuntime` 中被处理。在 `AdkRuntime` 中,只要模型没有
   调用对应的 tool,它们就会掉进通用错误分支。
2. **`before_model_callback` 是死代码(违反 §3.2)。** 它有单元测试,这让"没有调用点"这件事
   更难被发现,而不是更容易。
3. **流水线被写了两遍。** 没有共享定义,就没有任何办法测试顺序或覆盖是否一致。

## 6. 本期明确不做

- **检索(RAG)。** 阶段 6 按设计终止于 `KNOWLEDGE_REQUIRED`。设计文档见
  `docs/rag-architecture-plan.md`。它落地时会成为阶段 6 的一个 workflow,届时 D3 提到的
  模型门才开始值得做 —— 并且是架在检索内容上。
- **基于模型的范围门或注入门。** 见 D2、D3。
- **从对话 memory 中自己作答。** 明确否决,见 D4。

## 7. 测试义务

本契约由以下测试强制执行:

- **顺序与短路语义** —— 用 fake stage 写的流水线级测试,断言"发生短路的阶段之后,所有后续
  阶段都不被执行"。
- **Runtime 一致性** —— 对两个 runtime 参数化的测试,断言 `classify_intent` 能产出的**每一个**
  intent 在两边路由一致。关闭 §5.1。
- **单阶段单元测试** —— 每个阶段一个测试模块,对照 §3 的契约。
- **表征测试(characterization)** —— 在动任何重构之前,先对当前 `route_chat` 行为做
  golden-file 快照,作为回归安全网。

测试套件必须支持**按测试选择 runtime**。当前 `tests/conftest.py` 中的 autouse fixture 给每个
测试都固定了 `AGENT_RUNTIME=mock_demo`,这既阻断了一致性测试,也意味着**生产实际使用的 ADK
路径从未被真正测到**。
