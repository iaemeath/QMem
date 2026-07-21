# 领域知识图谱 MCP：自建方案说明

> **日期**：2026-07-20
> **定位**：在确认开源生态无满足需求的现成项目后，本文档系统阐述"自建领域知识图谱 MCP"的架构设计、与所有候选开源方案的逐项对比、以及对公网分析师可能攻击点的预判回应。
> **用途**：交付公网分析师做对抗式评审，判定自建是否成立、设计是否有硬伤。
> **关联**：QMem 现状体检见 `QMem-FullAnalysis-2026-07-17.md`，两种记忆方式概念总纲见 `QMem-两种记忆方式-项目记忆与领域知识图谱.md`，瘦身方案见 `QMem-架构演进说明-QMem瘦身与领域知识图谱.md`。

---

## 一、需求边界：我们要解决的是什么问题

### 1.1 一句话定义

我们要建一个 **"业务概念纠偏字典 + 轻量因果图"**，挂在 AI 编码会话里，**防止 AI 用互联网通识语义去瞎猜专业业务概念**。

它**不是**：
- ❌ 文档 RAG（"扔资料进去做语义检索"）
- ❌ 完整图数据库（Neo4j 那种多跳路径查询引擎）
- ❌ 百科知识库（面面俱到地收录领域知识）
- ❌ 通用记忆层（Mem0/Zep 那种 agent runtime 记忆）

它**是**：
- ✅ 只收"AI 容易理解错"的概念，每个概念一张纠偏卡
- ✅ 概念之间有少量因果/约束边（不追求完整拓扑）
- ✅ AI 写入新概念时做同义词熔断（防同一个概念分裂成多个条目）
- ✅ 全本地、无后台进程、寄生在 MCP 协议上

### 1.2 三个核心使用场景

**场景 A：需求分析阶段（AI 还没进具体项目）**
用户问"台账数据上报模块怎么设计"，AI 召回 → 返回台账概念卡 → AI 知道"台账数据是模板的实例，不是独立 CRUD"。

**场景 B：编码阶段（AI 已进项目）**
AI 要建表，召回"发电计划"概念 → 返回发电计划概念卡 → AI 知道"发电计划是业务领域核心概念，不能降格成普通属性字段"。

**场景 C：写入熔断（AI 想沉淀新概念）**
AI 想写一条"电力平衡"的概念卡 → 系统查近邻 → 发现已有"电网供需平衡"相似度 0.92 → 拦截，返回现有卡 → AI 改为补充而非新建。

### 1.3 六项硬约束（不可妥协）

| # | 约束 | 原因 |
|---|---|---|
| 1 | **MCP 协议（stdio），非 HTTP 服务** | 必须寄生在宿主 Agent（Claude Code），AI 用工具调用语义访问，不走 HTTP |
| 2 | **无后台进程、全本地触发** | 这是 QMem 一贯原则，记忆系统不该需要常驻服务 |
| 3 | **中文语义检索** | 业务概念是中文（发电计划/台账/负荷），英文嵌入/不分词的方案直接出局 |
| 4 | **写入熔断（防同义词分裂）** | 概念图谱最怕"同一概念多个条目"，必须在写入点检查相似度 |
| 5 | **领域隔离** | 电力调度概念不能和别的领域混（避免召回污染） |
| 6 | **全内网可部署、零外部依赖** | 内网无公网，不能依赖 Ollama/Neo4j/云嵌入 API |

---

## 二、为什么所有开源候选都不达标

### 2.1 候选工具完整对比表

| 候选 | 类型 | 存储 | 中文检索 | 写入熔断 | 因果图 | MCP/寄生 | 出局原因 |
|---|---|---|---|---|---|---|---|
| **shaneholloman/mcp-knowledge-graph**（含 knowledgegraph-mcp） | 子串图 | JSONL | ❌ String.includes | ❌ | 弱（实体关系无属性） | ✅ MCP | 无向量/无中文/无熔断 |
| **官方 @modelcontextprotocol/server-memory** | 子串图 | JSONL | ❌ | ❌ | 弱 | ✅ MCP | 图结构更弱，纯教学样例 |
| **aaronsb/memory-graph** | 带权图 | JSONL | ❌ | ❌ | 中（带权边） | ✅ MCP | 无向量/中文不分词/**已 archived** |
| **knowledge-mcp（PyPI，公网分析师推）** | 文档 RAG | 待定 | ⚠️ 取决 Ollama 模型 | ❌ | ❌ | ❌ HTTP+OpenAI 协议 | 见 2.2 专节 |
| **kb-mcp-server（Geeksfino）** | txtai 封装 | txtai | ❌ BM25 不分词 | ❌ | 死代码（未注册） | ✅ MCP | 图工具是无效代码/中文不分词/需 torch |
| **Mem0** | 记忆层 | 多后端 | ⚠️ | ⚠️ LLM 判断 | ❌ | ❌ 自有协议 | 每次 add 调 LLM/依赖 Neo4j |
| **Zep / Graphiti** | 时序图 | Neo4j | ⚠️ | ⚠️ | ✅ | ❌ | 死绑 Neo4j + LLM，CE 已废弃 |
| **Letta** | Agent 框架 | 自有 | ⚠️ | ⚠️ | ❌ | ❌ | 是 agent runtime，不是知识层 |

### 2.2 专节：knowledge-mcp 为什么出局（公网分析师本轮推荐）

公网分析师推荐的 `knowledge-mcp`，启动方式是：

```bash
pip install knowledge-mcp
export OPENAI_API_BASE="http://内网OllamaIP:11434/v1"   # ← 指向 Ollama
knowledge-mcp --data-dir ./electricity-kb --port 8000
```

三个信号暴露其本质是**文档 RAG 服务，不是知识图谱**：

| 信号 | 含义 |
|---|---|
| `OPENAI_API_BASE` 指向 Ollama | **必须依赖常驻 LLM 服务**（Ollama 跑模型），违背"无后台进程"约束 |
| `--data-dir`（丢 .proto/CIM/10万字资料） | 是**文档摄入 + 切块 + 向量化 + 检索**的 RAG 流程，不是概念图谱 |
| `--port 8000`（HTTP 服务） | 是**长期运行的 HTTP 服务**，不是寄生 MCP（stdio） |

**与硬约束的冲突**：

| 约束 | 冲突 |
|---|---|
| MCP 协议 / 寄生 | ❌ 它是 HTTP+OpenAI 兼容协议，不是 MCP server |
| 无后台进程 | ❌ 要常驻 `--port 8000` HTTP 服务 + Ollama LLM 服务 |
| 全内网零依赖 | ❌ 要先部署 Ollama + 拉 LLM + 拉嵌入模型（内网基础设施清单里没有 Ollama） |
| 写入熔断 | ❌ RAG 是批量摄入，无概念级熔断 |
| 因果图 | ❌ 无图结构，返回的是文档切片 |

**更致命的认知错误**：公网分析师把"文档 RAG"当成了"领域知识图谱"。两者解决不同问题：

| | 文档 RAG（knowledge-mcp 类） | 领域知识图谱（我们要的） |
|---|---|---|
| 回答 | "哪份资料提到过 X？" | "X 这个概念到底是什么？AI 别理解错" |
| 内容 | 文档切片（chunk） | 概念卡 + 因果边 |
| 检索结果 | 一段原始资料文本 | 结构化纠偏声明 |
| AI 拿到后 | 自己读、自己总结（**可能总结错**） | 直接读到结论（**零推理**） |
| 纠偏能力 | 无 | 强 |

**自相矛盾**：公网分析师上一轮自己说"扁平警示事实比 RAG 切片纠偏效果好一个数量级"，这一轮却推了个 RAG 服务——**方向和他自己的论点相反**。

**一句话判决**：knowledge-mcp 这类"丢文档做 RAG"的方案，解决的是"AI 查资料"问题，不是我们要解决的"AI 理解业务概念、别理解错"问题。方向就不对。

### 2.3 结论

8 个候选**无一达标**。失败集中在三类：
1. **轻量 MCP 图谱类**（knowledgegraph-mcp / server-memory / memory-graph）：无向量、无中文分词、无熔断
2. **重型记忆/图平台**（Mem0 / Zep / Letta）：依赖 LLM 服务或 Neo4j，违背寄生原则
3. **文档 RAG 类**（knowledge-mcp / kb-mcp-server）：能力错位，不是概念图谱

**开源生态没有满足需求的项目，自建是唯一出路。**

---

## 三、自建架构设计

### 3.1 设计哲学：扁平纠正事实 > 复杂图拓扑

核心洞察（来自公网分析师上一轮的正确论点）：**对"纠偏"这件事，一张扁平的概念卡片比一套复杂的多跳图查询有效得多**。

AI 不需要通过 `发电计划 -[derives_from]-> 96点出清 -[constrains]-> 负荷预测` 三跳路径推导出"别建成 CRUD"；它只需要直接读到一张卡片上写着"⚠️ 发电计划是核心概念，严禁建成 CRUD"。

所以架构取舍是：
- **概念卡（DCK，Domain Concept Card）是主体**——扁平、结构化、带"⚠️ AI 易误解点"段落
- **因果边是辅助**——只在概念之间有**强物理约束/因果律**时才建边（发电计划→96点出清），不追求图完整性
- **写入熔断是生命线**——没有熔断，概念图谱几周内就会因同义词分裂而崩坏

### 3.2 技术栈（全复用 QMem 已验证的栈）

| 层 | 技术 | 复用自 QMem |
|---|---|---|
| 嵌入 | `bge-small-zh-v1.5` ONNX，512 维，CPU | ✅ 同款 |
| 向量存储 | `sqlite-vec` vec0 虚表，cosine | ✅ 同款 |
| 全文检索 | SQLite FTS5 external-content | ✅ 同款 |
| 数据库 | SQLite 单库 | ✅ 同款 |
| 检索 | RRF 混合检索（BM25 + cosine，k=60） | ✅ 同款 |
| 运行时 | Python 3.13，5 个 pip 包 | ✅ 同款 |

**零新增依赖**。BGE-small-zh 已经在 QMem 跑了一年，中文概念检索质量验证过。这意味着自建的**技术风险为零**——所有零件都是 proven 的。

### 3.3 数据模型（两张表 + 向量 + FTS）

```sql
-- 概念卡主表（DCK：Domain Concept Card）
CREATE TABLE kg_concepts (
    id              INTEGER PRIMARY KEY,
    concept_uuid    TEXT UNIQUE,          -- 12位hex
    domain          TEXT NOT NULL,         -- 领域隔离：power-grid / water / gas...
    concept_name    TEXT NOT NULL,         -- 概念主名（如"发电计划"）
    aliases         TEXT,                  -- 别名（JSON数组，如["发电出力计划","GP"]）
    definition      TEXT,                  -- 概念定义（一段话）
    misconception   TEXT,                  -- ⚠️ AI 易误解点（纠偏声明，核心字段）
    impact_on_dev   TEXT,                  -- 对开发的影响（建表/建模/接口决策）
    created_at      TEXT,
    updated_at      TEXT,
    deleted_at      TEXT
);

-- 因果/约束边（轻量，只在强约束时建）
CREATE TABLE kg_edges (
    id              INTEGER PRIMARY KEY,
    src_concept     TEXT NOT NULL,         -- concept_uuid
    dst_concept     TEXT NOT NULL,
    relation        TEXT NOT NULL,         -- 6种语义关系（见下）
    weight          REAL DEFAULT 1.0,      -- 关系强度（0-1）
    note            TEXT,                  -- 关系说明
    created_at      TEXT
);

-- 向量索引（对 concept_name + definition + misconception 拼接向量化）
CREATE VIRTUAL TABLE kg_vectors USING vec0(
    embedding float[512]
);

-- 全文检索
CREATE VIRTUAL TABLE kg_concepts_fts USING fts5(
    concept_name, aliases, definition, misconception,
    content='kg_concepts', content_rowid='id'
);
```

### 3.4 六种关系类型（借鉴 aaronsb/memory-graph 的语义边枚举）

| 关系 | 含义 | 电力调度例子 |
|---|---|---|
| `derives_from` | 派生自 | 96点出清 ← 发电计划 |
| `constrains` | 约束 | 检修计划 → 发电计划（检修时机约束发电） |
| `aggregates` | 聚合 | 发电计划 ⊃ 风电计划 + 光伏计划 + 火电计划 |
| `depends_on` | 依赖 | 负荷预测 → 发电计划（计划依赖预测） |
| `synonym_of` | 同义 | 台账数据 = 台账实例（熔断后建的边） |
| `contradicts` | 矛盾/对立 | 倒送电 ↔ 用电（语义对立，防混淆） |

**边的使用纪律**：只在前四种强物理/业务约束时建边，`synonym_of` 是熔断后的产物，`contradicts` 是防混淆的特殊边。**绝大多数概念之间不建边**——这是"图状语义但不做图数据库"原则的体现。

### 3.5 写入熔断（强熔断，核心机制）

借鉴公网分析师"强熔断"概念，在**概念写入点**做相似度检查：

```python
def save_concept(concept_name, definition, misconception, ...):
    # 1. 对 concept_name + definition 拼接向量化
    emb = embed(f"{concept_name}。{definition}")
    
    # 2. 查同域近邻
    neighbors = query_vec(emb, domain=domain, limit=5)
    
    # 3. 熔断：相似度 > 0.85 阻止新建
    for n in neighbors:
        if cosine(emb, n.embedding) > 0.85:
            return {
                "blocked": True,
                "reason": "疑似重复概念",
                "existing": n,  # 返回现有概念卡全文
                "hint": "请检查是否是同义词/补充，若是请用 update_concept 或建 synonym_of 边"
            }
    
    # 4. 通过熔断才落库
    insert_concept(...)
```

**与 QMem 现有 `_nearest_neighbor` 的关系**：QMem 的 q4 门禁已实现这套逻辑（`mcp_server.py` 的 `mem_save` 写入门禁），自建领域图谱**直接复用这套成熟实现**，只是阈值和提示文案针对概念场景调整。**这不是新代码，是搬运已验证代码。**

### 3.6 工具集（MCP 工具，约 8 个）

| 工具 | 用途 |
|---|---|
| `concept_recall(query, domain)` | RRF 混合检索概念卡（主入口） |
| `concept_get(name_or_uuid)` | 按名/UUID 精确取卡 |
| `concept_save(name, definition, misconception, ...)` | 写概念卡（带熔断） |
| `concept_update(uuid, ...)` | 更新概念卡（重算向量） |
| `concept_delete(uuid)` | 软删除 |
| `concept_neighbors(uuid, depth=2)` | 递归 CTE 遍历因果边（多跳） |
| `concept_health_check(domain)` | 域内两两相似度检测（防堆积） |
| `concept_fuse(uuid_a, uuid_b, relation)` | 合并重复概念，建 synonym_of 边 |

**`concept_neighbors` 用 SQLite 递归 CTE 实现图遍历**（无需图数据库）：

```sql
WITH RECURSIVE walk(uuid, depth) AS (
    SELECT ?, 0
    UNION
    SELECT dst_concept, walk.depth + 1
    FROM kg_edges JOIN walk ON src_concept = walk.uuid
    WHERE walk.depth < ?  -- 深度上限
)
SELECT c.*, walk.depth FROM kg_concepts c JOIN walk ON c.concept_uuid = walk.uuid;
```

这是"图状语义但不做完整图数据库"的技术落地——2-3 跳的因果链用递归 CTE 足够，不需要 Neo4j。

### 3.7 与 QMem / CBM / 全局 CLAUDE.md 的分工

四个系统各司其职，正交不重叠：

| 系统 | 维度 | 回答的问题 | 内容 |
|---|---|---|---|
| **QMem（瘦身版，仅 q4）** | 时间（纵向） | "这个项目现在到哪了？" | 项目架构、进度、踩坑 |
| **领域知识图谱（本文）** | 认知（横向） | "这个业务概念到底是什么？" | 概念卡 + 因果边 |
| **CBM（codebase-memory）** | 结构 | "这段代码怎么调用的？" | 函数/类/调用图 |
| **全局 CLAUDE.md** | 规范 | "编码该遵守什么硬规矩？" | IS_DELETE/CLOB 等永久约束 |

**跨项目技术陷阱（IS_DELETE/CLOB）的处理**（用户已定预案）：存多份——每个相关项目的 q4 各存一份 + 全局 CLAUDE.md 兜底。鉴于项目切换频率低（主力一个项目），冗余成本可接受。**这类陷阱不进领域图谱**——领域图谱只装业务概念，不装技术陷阱（两者的召回时机、检索方式不同）。

---

## 四、与候选方案的逐项碾压对比

以"是否满足六项硬约束 + 核心能力"为维度，自建方案 vs 最接近的三个候选：

| 维度 | 自建 | knowledgegraph-mcp | knowledge-mcp（RAG） | kb-mcp-server |
|---|---|---|---|---|
| MCP/寄生 | ✅ | ✅ | ❌ HTTP | ✅ |
| 无后台进程 | ✅ | ✅ | ❌ 需 Ollama 常驻 | ✅ |
| 中文语义检索 | ✅ BGE-small-zh | ❌ String.includes | ⚠️ 看 Ollama | ❌ BM25 不分词 |
| 写入熔断 | ✅ 强熔断 | ❌ | ❌ | ❌ |
| 因果图 | ✅ 6 种边 + 递归 CTE | ⚠️ 弱 | ❌ | ❌ 死代码 |
| 领域隔离 | ✅ domain 字段 | ❌ | ⚠️ 目录隔离 | ❌ |
| 纠偏结构 | ✅ misconception 字段 | ❌ | ❌ | ❌ |
| 零外部依赖 | ✅ | ✅ | ❌ 需 Ollama | ⚠️ 需 torch |
| **达标数** | **8/8** | **2/8** | **0/8** | **1/8** |

---

## 五、维护成本对冲（回应"自建就要后续不断维护"）

公网分析师和用户都担心：自建 = 长期维护负担。这个担心成立但可对冲，理由有三：

### 5.1 零新增技术栈 = 零新增维护面

自建**完全复用 QMem 已验证的技术栈**（SQLite + sqlite-vec + BGE-small-zh + FTS5 + RRF）。这套栈已经在 QMem 跑了一年，5 个 pip 包，全内网可装。**维护 QMem 的人（就是你自己）已经在维护这套栈**，新增一个领域图谱 MCP 不增加新的技术学习成本、不增加新的依赖管理负担。维护边界等于 QMem 的维护边界 + 一点点业务逻辑代码。

### 5.2 概念图谱是"写入收敛型"系统，越用越稳定

与 q4 动态记忆（每次编码都写）不同，领域概念是**低频写入、高频读取**：

- 概念沉淀后基本不动（发电计划这个概念不会变）
- 只有发现新概念/新误解点时才增补
- 熔断机制保证条目数收敛（不会无限膨胀）

**收敛型系统的维护成本随时间下降**，不是上升。前 3 个月需要补概念，之后基本只读。

### 5.3 代码量可控（预估 < 800 行 Python）

参考 QMem 的实现规模（mcp_server.py 1123 行涵盖 17 个工具 + 治理层），领域图谱 MCP 只有 8 个工具、2 张表、6 种边、一套熔断，**预估 Python 代码 < 800 行**。这是一个单人可长期维护的规模，不是工程团队级系统。

**对比"自建维护成本"与"强行套用不达标开源的适配成本"**：把 knowledgegraph-mcp 改造成满足六项约束（加向量、加中文分词、加熔断、加领域隔离），改动量 > 60%，且改完它就不是原项目了——等于变相自建，还要背上原项目的代码包袱。**直接自建反而更轻**。

---

## 六、预判公网分析师的攻击点 + 回应

### 6.1 攻击点 A："为什么不直接用 knowledgegraph-mcp 魔改？"

**回应**：见第五节 5.3。knowledgegraph-mcp 缺四项核心能力（向量、中文分词、熔断、领域隔离），魔改它 = 加向量引擎 + 换分词 + 加熔断逻辑 + 加字段 = 改动 > 60%。改完它是另一个东西了，而且背着 JSONL 存储、String.includes 这些不该继承的包袱。**从零写一个针对需求优化的 SQLite 版本，比改造一个基因不对的项目更省事、更可控**。这就像"要不要把一辆自行车改造成电动车"——直接买电动车更合理。

### 6.2 攻击点 B："为什么不用文档 RAG（knowledge-mcp）让 AI 自己读资料？"

**回应**：见第二节 2.2。文档 RAG 解决的是"查资料"，我们要的是"纠偏"。AI 读资料切片**会自己总结错**（这正是 AI 理解业务概念出错的根源），而概念卡是**人/专家确认过的结构化纠偏声明，零推理零偏差**。公网分析师上一轮自己说过"扁平事实比 RAG 切片纠偏效果好一个数量级"，这点他是对的，本方案就是这个论点的落地。另外 RAG 还要常驻 Ollama，违背寄生原则。

### 6.3 攻击点 C："自建要维护，你一个人维护得动吗？"

**回应**：见第五节。三点对冲：① 零新增技术栈（复用 QMem 已验证栈）；② 概念图谱是收敛型系统，越用越稳；③ 代码量 < 800 行，单人规模。而且"维护一个针对自己需求优化的 800 行系统" vs "维护一个自己改过 60% 的别人的项目"，前者更轻。

### 6.4 攻击点 D："为什么要有因果边？扁平卡片不就够了？"

**回应**：对，**绝大部分场景扁平卡片就够**——这是本方案的主体。但**少数概念之间有强物理约束**（如"检修计划"和"发电计划"有时序约束、"发电计划"聚合"风光火电"），这些强约束如果只写在卡片正文里，AI 召回时容易漏（因为它只召回了主概念卡，没召回关联卡）。因果边的唯一作用是：召回主概念时，用递归 CTE 把强约束的关联概念一并带出。**边是"召回增强器"，不是"图查询引擎"**。这条原则也防止了"图拓扑膨胀失控"。

### 6.5 攻击点 E："熔断的 0.85 阈值怎么定的？会不会误杀？"

**回应**：阈值参考 QMem 已验证的写入门禁（同样 0.85，已在 changzhou 真实库测过：复制原文 sim=1.0000 拦截、新颖内容放行）。熔断**不删数据**，只阻止新建并返回现有卡——误杀的代价是 AI 改用 update，不是数据丢失。阈值可配置，0.85 是中文概念场景的经验值（低于 0.8 会漏拦同义词，高于 0.9 会误杀近义但不同的概念）。

### 6.6 攻击点 F："为什么不直接扩展 QMem 加个 tier=domain？复用现成的。"

**回应**：这是最该认真回应的一点。**理论上可以**（QMem 的 tier 字段本就是为此设计的），但有三条理由支持**独立 MCP** 而非"QMem 加 tier"：

1. **召回时机不同**：q4 是"进项目后开场召回"，领域概念是"需求分析阶段（还没进项目）就要召回"。混在一个 MCP 里，AI 容易用错工具（该用 concept_recall 时用了 mem_recall，混入项目草稿污染概念检索）。独立 MCP = 独立工具名 = 强制 AI 分清场景。

2. **熔断强度不同**：q4 的门禁是"建议性"的（相似就提示，AI 可 force 放行）；概念图谱的熔断是"强制性"的（同义词必须合并，不能 force 新建，否则图谱崩坏）。两套强度混在一个系统里容易串。

3. **写入主体不同**：q4 由 AI 编码时实时写；概念卡由**用户/专家确认后**沉淀（AI 写入需人工背书）。混在一起会模糊"谁有权写"的边界。

**但保留复用空间**：如果未来验证下来"场景其实没那么分明"，可以把领域图谱降级为 QMem 的一个 tier——因为底层数据模型（concept 卡本质就是带 misconception 字段的记忆）是兼容的。**独立 MCP 是可逆决策，先独立、需要时合并**。

### 6.7 攻击点 G："concept_name + aliases 做向量，中文短词召回准吗？"

**回应**：BGE-small-zh 对中文短概念（"发电计划""负荷电量"）的召回质量在 QMem 一年的使用中验证过，这类 4-6 字的专业术语恰恰是 BGE-small-zh 的强项（比英文短语强）。对极短词（2 字如"负荷"）有召回漂移风险，对策是：concept 卡的向量输入是 `concept_name + aliases + definition + misconception` 拼接（不是只对概念名），上下文足够，短词漂移问题被 definition 的语义锚定抵消。

---

## 七、实施路线（分阶段，可随时中止）

### Phase 0：概念验证（1 天）
- 复用 QMem 的 embedding.py / search_rrf.py
- 建 2 张表 + 向量 + FTS
- 实现 `concept_save`（带熔断）+ `concept_recall`
- 灌入 2 个测试概念（发电计划、台账数据）验证熔断和召回

### Phase 1：最小可用（2-3 天）
- 补全 8 个工具
- 加 kg_edges + 递归 CTE 遍历
- 接入 MCP server（参考 QMem 的 mcp_server.py 骨架）

### Phase 2：业务沉淀（按需，持续）
- 从常州需求文档、电力调度资料中提取核心概念（发电计划/台账/负荷/新能源/D5000 等）
- 重点是写好每张卡的 `misconception` 字段

### Phase 3：治理（可选）
- concept_health_check 防堆积
- 与 QMem 的协同调用约定（需求分析阶段调 concept_recall，编码阶段调 mem_recall）

**中止点**：Phase 0 结束即可判断技术路线是否成立。如果 Phase 0 验证熔断和召回质量达标，后续是业务沉淀工作（写卡片），不是技术开发工作。

---

## 八、作者倾向（标注：倾向非定论，待评判）

基于前述分析，作者倾向：
1. **自建成立**——开源生态确无达标方案，自建是唯一出路（第二节已证）
2. **自建可控**——零新增技术栈、收敛型系统、< 800 行代码（第五节已证）
3. **架构取舍合理**——扁平卡片为主体 + 少量因果边增强召回 + 强熔断防崩坏（第三节已证）

**待公网分析师评判的核心问题**：
- Q1：自建的六项硬约束是否真的不可妥协？任何一项能否放松以换用现成方案？
- Q2：扁平卡片 + 少量因果边的"轻图"设计，是否比纯扁平卡片或完整图数据库更合理？
- Q3：独立 MCP vs QMem 加 tier=domain（第六节 6.6），哪种长期更优？
- Q4：熔断阈值 0.85 + 返回现有卡的策略，是否足够防崩坏？
- Q5：是否有本文未覆盖的开源方案值得重新评估？

---

> 本文为领域知识图谱 MCP 自建方案说明，2026-07-20 生成，交付公网分析师做对抗式评审。
