# QMem V4.0 架构：三 MCP 正交拆分（Y 方案落地）

> **日期**：2026-07-20（初版）/ 2026-07-21（核实勘误与残留表清理）
> **文档性质**：架构演进记录。记录从 V3.3（单进程混合系统）→ V4.0（三 MCP 正交分工）的落地。
> **关联文档**：概念总纲见 `QMem-两种记忆方式-项目记忆与领域知识图谱.md`，Y 方案论证见 `QMem-架构演进说明-QMem瘦身与领域知识图谱.md`，V3.3 治理见 `QMem-V3.3-Architecture.md`。
>
> **2026-07-21 核实修订**：本文档最初按"改造前的单目录布局"撰写，文中部分文件名（`mcp_server.py`/`cbm_wrapper.py`/`.mcp.json`/`restart_mcp.ps1` 等）与当前实际三目录布局不符；同时核对实际代码与数据库后，修正了若干数据声称、补全了 codebase-memory 配置、清理了 `core_memory.db` 残留表。修订点见各节"⚠️ 核实修订"标注与文末"七、核实修订日志"。

---

## 一、为什么拆（V3.3 的问题）

V3.3 的 QMem 是一个"职责混合的复杂系统"——单个 MCP 进程里塞了三类完全正交的知识：

| 知识类型 | V3.3 承载 | 问题 |
|---|---|---|
| 项目工程状态 | tier=q4 | 正确归位 |
| 跨项目技术陷阱 | tier=consensus（java-cloud-common 等） | 与全局 CLAUDE.md 硬编码重叠，冗余 |
| 业务领域知识 | tier=consensus（power-grid-domain） | 塞进项目记忆系统是"位置错放"，需求分析阶段被动捎带，注意力分散 |

Y 方案的核心判断：**这三类知识沿三个正交维度分工，应各自独立成系统**。

---

## 二、V4.0 终态架构（三 MCP 正交三维）

```
┌─────────────────────────────────────────────────────────────────┐
│                      宿主 AI（Claude Code / zcode）              │
│   会话中按需调用三类 MCP server（各自独立进程/库/工具空间）      │
└──────────┬───────────────────────┬─────────────────────┬────────┘
           ▼                       ▼                     ▼
  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
  │  QMem（瘦身）    │  │ DomainKG MCP     │  │ codebase-memory  │
  │  纯项目记忆      │  │ 业务概念图谱     │  │ 代码事实图谱     │
  │  11 工具         │  │ 10 工具          │  │ 独立 exe         │
  │                  │  │                  │  │                  │
  │ · 架构/端口      │  │ · 发电计划       │  │ · 函数/类/方法   │
  │ · 任务进度       │  │ · D5000表结构    │  │ · 调用关系       │
  │ · 踩坑根因       │  │ · 负荷电量       │  │ · 表字段         │
  │ · 架构决策       │  │ · 新能源出力     │  │ · 架构社区检测   │
  │                  │  │ · 台账/断面      │  │                  │
  │ core_memory.db   │  │ domain_          │  │ （独立索引库     │
  │ memory_facts     │  │  knowledge.db    │  │   per-project）  │
  │                  │  │ kg_concepts      │  │                  │
  │ mcp/qmem/        │  │ mcp/domain-kg/   │  │ mcp/codebase-    │
  │ server.py        │  │ server.py        │  │ memory/*.exe     │
  └──────────────────┘  └──────────────────┘  └──────────────────┘
```

> ⚠️ **核实修订（目录布局）**：V4.0 已落地为三目录物理隔离，不再是单目录多文件。
> - `mcp/qmem/`：`server.py`（QMemMCP）+ `core_memory.db` + `schema.sql` + `embedding.py` + `search_rrf.py` + `init_project_context.py` + `gui/` + `start.bat`
> - `mcp/domain-kg/`：`server.py`（DomainMCP）+ `domain_knowledge.db` + `kg_schema.sql` + `embedding.py` + `kg/`（kg_store.py / kg_traversal.py）+ `start.bat`
> - `mcp/codebase-memory/`：`codebase-memory-mcp.exe`（现成产物，version 0.10.0，标准 stdin/stdout JSON-RPC）
> - `mcp/tools/`：`migrate_yplan.py`（已归档）+ `check_db.py` + `test_call_log.py`
> - `mcp/WINDOWS_SETUP_GUIDE.md`：三 server 客户端注册方法（Cursor / Claude Desktop JSON）+ 排障 + 目录结构

### 三个系统的职责边界

| 系统 | 维度 | 回答的问题 | 召回方式 | 触发时机 |
|---|---|---|---|---|
| **QMem** | 时间（项目演进） | "这个项目现在做到哪了？架构是什么？" | 按项目隔离，拉模型 | 编码开场 + 收尾 |
| **DomainKG** | 认知（业务理解） | "这个业务概念是什么？AI 别理解错" | 跨项目共享，拉模型 | 需求分析 / 语义理解 |
| **codebase-memory** | 结构（代码实体） | "这个函数被谁调用？表字段是什么？" | 代码图谱，拉模型 | 编码查代码事实 |

---

## 三、具体改动

### 3.1 QMem 瘦身（17 → 11 工具）

> ⚠️ **核实修订**：代码位于 `mcp/qmem/server.py`（原文档误作 `mcp_server.py`）。核实结果——`tools/list` 实际返回 **11 工具**，无 consensus/kg/CBM 残留，与设计一致。

**删除的 6 个 consensus 工具**：`memory_promote` / `memory_demote` / `consensus_recall` / `consensus_health_check` / `add_consensus_ref` / `list_consensus_projects`

**删除的 10 个领域图谱工具**（迁到 DomainKG）：`concept_save` / `concept_update` / `concept_delete` / `concept_get` / `concept_list` / `edge_save` / `edge_delete` / `list_relations` / `concept_recall` / `concept_neighbors`

**删除的 CBM 转发**：原 `cbm_wrapper.py` 在三目录拆分后已不存在（不再有转发层），`_dispatch_tool` 仅分发本地 11 工具，未命中工具报错并指引 DomainKG / codebase-memory。

**保留的 11 个工具**：`mem_save` / `mem_recall` / `mem_search` / `mem_update` / `mem_context` / `mem_get_full` / `mem_delete` / `mem_list_projects` / `init_project_context` / `cross_project_health_check` / `mem_consolidate_project`

**方法瘦身**：`_save`（删共识域守卫）、`_update`（删 confirm_consensus/脐带）、`_delete`（删越权检查/空域清理）、`_recall`（删三步法配额→单 tier RRF）、`_context`（删共识加载）、`_get_full`/`_search`/`_list_projects`（去 tier 过滤）。

**调用日志**：QMem 另开 `call_log.db`（独立文件，WAL 模式，90 天自动清理）记录每次工具调用的审计（tool_name/duration/success/arg_summary/resp_size）。DomainKG 不写调用日志。

**version**：3.3 → 4.0

### 3.2 schema.sql 改动

> ⚠️ **核实修订（重要）**：代码位于 `mcp/qmem/schema.sql`。`CREATE TABLE IF NOT EXISTS` **不会删除已存在的表**，而原 `migrate_yplan.py` 的 step_C 只对 `project_refs` 做 `DELETE`（清数据）而非 `DROP`，导致 `core_memory.db` 物理上长期残留一整套 kg_* 表（含 FTS/向量影子表）+ 空的 project_refs 表。这是设计上的"防迁移灾难"（保留列）副作用——schema 只读不写 tier/origin，但表从未被真正清理。
>
> **2026-07-21 已处理**：见第七节"残留表清理"。清理后 `core_memory.db` 仅保留 `memory_facts` + `memory_vectors` + `memory_facts_fts`（+影子表）+ `sqlite_sequence`，体积 7.1MB → 2.8MB。

schema.sql 本身改动（DDL 层面）：
- 删 `project_refs` 表定义（无跨项目共识引用机制）
- 删 `idx_facts_tier` / `idx_facts_origin` 索引
- **保留** `tier` / `origin_project` 列（历史数据兼容，防迁移灾难；代码不再读写）

### 3.3 DomainKG MCP 独立（`mcp/domain-kg/server.py`）

> ⚠️ **核实修订**：代码位于 `mcp/domain-kg/server.py`（`DomainMCP` 类），原文档误作 `domain_mcp_server.py`。launcher 为 `mcp/domain-kg/start.bat`（原文档误作 `start_domain_mcp.bat`）。核实结果——`tools/list` 实际返回 **10 工具**，schema + dispatch 从原 QMem 原样搬迁，与设计一致。

- `DomainMCP` 类，10 个 concept_*/edge_* 工具
- 独立 `domain_knowledge.db`（kg_* 表前缀），与 core_memory.db 物理隔离
- 复用 `embedding.py`（BGE-small-zh 512维）+ `kg/` 包（KGStore/KGTraversal 零改动）
- `mcp/domain-kg/start.bat` launcher

### 3.4 codebase-memory 独立注册

> ⚠️ **核实修订**：`codebase-memory-mcp.exe` 零代码改动（本就是标准 MCP server，已验证 initialize 返回 version 0.10.0）。三个 server 的客户端注册方法（Cursor / Claude Desktop JSON 两种）统一记录在 `mcp/WINDOWS_SETUP_GUIDE.md` 第 2 节，不再单设示例配置文件。
>
> 历史遗留：原 `mcp/mcp_config_example.json` 只注册了 QMem + DomainKG，漏了 codebase-memory；2026-07-21 复核时发现该示例文件冗余（信息已在 SETUP_GUIDE 完整覆盖），已整体删除，配置说明以 SETUP_GUIDE 为准。

### 3.5 数据迁移（`tools/migrate_yplan.py`，一次性，已归档）

> ⚠️ **核实修订**：脚本位于 `mcp/tools/migrate_yplan.py`，已在文件头部标注"★ 已归档（2026-07-20）★"——V4.0 目录拆分后 db 路径已变（`core_memory.db` → `mcp/qmem/`，`domain_knowledge.db` → `mcp/domain-kg/`），脚本路径失效，保留仅作审计记录。

consensus 9 条数据分三处归位：

| 数据 | 处置 | 理由 |
|---|---|---|
| power-grid-domain 7 条业务概念 | → DomainKG 的 `kg_concepts`（格式转换：title 提取概念名，content→definition，misconception 留空） | Y 方案核心：业务概念横向共享，所有电力项目可用 |
| java-cloud-common 1 条 | → 软删 | CLAUDE.md 已硬编码 IS_DELETE/CLOB 同类内容 |
| weakpwd 1 条 | → 软删 | CLAUDE.md 已硬编码弱口令改造内容 |

kg_* 种子数据（3 概念 + 2 边）从 core_memory.db 搬到 domain_knowledge.db（测试垃圾过滤）。

迁移后（2026-07-21 核实实际数据库）：
- `core_memory.db`：纯 q4，**67 条存活**（常州 44 + 其余项目 23，consensus 存活 0）；含 9 条软删历史行
- `domain_knowledge.db`：**10 条存活概念 + 2 条边**（原文档误记为 9 概念，实际为 10：7 条 power-grid-domain 迁入业务概念 + 可调能力/断面/发电计划 3 条种子）；另有 10 条软删历史行（迁移试写/熔断验证产物）；**全部 verified=0 待人工核实**

### 3.6 清单改动

> ⚠️ **核实修订（文件名）**：三 server 的客户端注册方法记录在 `mcp/WINDOWS_SETUP_GUIDE.md` 第 2 节（原文档误作 `.mcp.json`）。仓库内不存在 `.zcode-plugin/plugin.json` 与 `restart_mcp.ps1`（这些是 zcode 插件包/部署脚本的产物，不在本 mcp 目录）；原 `mcp/mcp_config_example.json` 已于 2026-07-21 删除（信息冗余，以 SETUP_GUIDE 为准）。

- MCP 客户端配置：1 server（QMem）→ **3 server**（QMem + DomainKG + codebase-memory），注册片段见 `WINDOWS_SETUP_GUIDE.md` 第 2 节
- 原 `cbm_wrapper.py`：三目录拆分后已不存在

### 3.7 GUI 双库

> ⚠️ **核实修订**：代码位于 `mcp/qmem/gui/server.py`（原文档误作 `gui/server.py`）。核实结果——双库拆分已落地。

`gui/server.py` 的 `DB_PATH` 拆成 `MEM_DB_PATH`（`mcp/qmem/core_memory.db`）+ `KG_DB_PATH`（`mcp/domain-kg/domain_knowledge.db`）：
- memory 端点（memories/stats/graph）用 `query()`（MEM_DB，只读 `mode=ro`）
- kg 端点（kg-graph/kg-neighbor/concepts）用 `query_kg()`（KG_DB，只读）

### 3.8 skill 文档

`skills/qmem-memory/SKILL.md` 重写 v4.0：
- 删 consensus 全部内容（promote/demote/越权/共识域导航）
- 工具速查从 17 → 11（QMem）+ 10（DomainKG）+ 代码事实说明
- 卫生规则新增三条"各归各位"（业务概念/代码事实/技术规范都不进 QMem）
- 开场召回说明：需求分析阶段改用 concept_recall

> ⚠️ **核实备注**：`skills/qmem-memory/SKILL.md` 不在 `mcp/` 目录内，本目录树未直接核实其内容，需在 skill 所属目录单独核对。

---

## 四、验证记录

### 4.1 2026-07-20 初版验证

- **QMem**：`tools/list` 返回 11 工具，无 consensus/kg/CBM 残留；`mem_context(changzhou)` 返回 44 条无 consensus 字段；禁用工具调用报错并指引 DomainKG
- **DomainKG**：`tools/list` 返回 10 工具；`concept_recall("发电")` 召回可调能力（带 misconception）；`concept_neighbors("发电计划")` 返回 3 节点 2 边；stdin/stdout JSON-RPC 协议正常
- **codebase-memory**：exe 独立运行返回 MCP initialize 响应（version 0.10.0）
- **GUI**：kg 端点从 domain_knowledge.db 读，memory 端点从 core_memory.db 读

### 4.2 2026-07-21 核实复查（直接查库 + 读码）

- **QMem `server.py`**：确认 11 工具，无 consensus/kg/CBM 残留；写入门禁（force 绕过）、软删（deleted_at）、`_enrich_results` 去重、review_queue（progress 30 天复审）逻辑齐备
- **DomainKG `server.py` + `kg/kg_store.py`**：确认 10 工具；**写入护栏实际是双层熔断**（原文档只说"0.75 熔断"，低估了实现）：
  - 第 1 层 **FTS 别名精确命中**：新概念 name 字面命中已有概念的 name/aliases → 拦同义多表述（如"出力计划"vs"发电计划"，BGE-small-zh 向量相似度仅 0.572 拦不住，靠 FTS 兜底）
  - 第 2 层 **name 向量熔断**（阈值 0.75）：拦字面重复/包含（如"发电计划"vs"发电机组出力计划"）
  - 双向量设计：`kg_name_vectors`（仅 name，熔断用）+ `kg_vectors`（name+aliases+definition+misconception，检索用），避免长文本稀释概念名相似度
- **`core_memory.db`**：存活 67（q4 67 / consensus 0），向量 76 行 = memory_facts 76 行（含软删），一一对应 ✅
- **`domain_knowledge.db`**：存活 10 概念 + 2 边（`发电计划 --depends_on--> 可调能力`、`断面 --constrains--> 可调能力`）；**10 条 verified 全为 0（待人工核实）**
- **MCP 客户端配置**：原 `mcp_config_example.json` 仅 QMem + DomainKG、缺 codebase-memory；该示例文件冗余已删，三 server 注册方法统一收口到 `WINDOWS_SETUP_GUIDE.md` 第 2 节
- **`core_memory.db` 残留表**：物理残留 17 张 kg_* 表 + project_refs 表（schema IF NOT EXISTS 不删表所致，**已清理**，见第七节）

---

## 五、回滚

> ⚠️ **核实修订（路径已校正）**：原文档回滚命令引用的文件名（`mcp_server.py`/`cbm_wrapper.py`/`domain_mcp_server.py`/`.mcp.json`/`.zcode-plugin/plugin.json`）在当前布局下均不存在，无法执行。下方为校正后的实际路径版本。

回滚分两层：

**层 1：数据回滚**（core_memory.db 有冷备）
```bash
# mcp/qmem/ 下保留的冷备（任选其一）
cp mcp/qmem/core_memory.db.bak_yplan_20260720   mcp/qmem/core_memory.db   # 迁移前原始
# 或 2026-07-21 残留表清理前的冷备（含 kg_* 残留表 + 67 条 q4）
cp mcp/qmem/core_memory.db.bak_cleanup_20260721 mcp/qmem/core_memory.db
```

**层 2：代码回滚**（git，需在 `mcp/` 仓库根执行；目录布局拆分本身是结构性改动，建议整体 `git checkout` 到拆分前 commit）
```bash
# 删除三目录拆分新增物
rm -rf mcp/domain-kg mcp/codebase-memory
rm mcp/qmem/core_memory.db.bak_cleanup_20260721
# 恢复拆分前的单目录布局（依赖 git 历史，需先确认拆分 commit）
git checkout <拆分前commit> -- mcp/
```

> 注：DomainKG 独立 db（`domain_knowledge.db`）已含迁移后的业务概念，代码回滚后若要恢复单进程混合系统，需把 domain_knowledge.db 的 kg_* 表导回 core_memory.db——此路径不在原迁移脚本的逆操作范围内，建议仅作数据回滚（层 1），保留三 MCP 代码结构。

---

## 六、Y 方案论证对照

本文档是 `QMem-架构演进说明-QMem瘦身与领域知识图谱.md`（Y 方案）的落地。Y 方案当时列的 6 个对比维度，V4.0 实际效果：

| 维度 | Y 方案预期 | V4.0 实际 |
|---|---|---|
| 系统复杂度 | 两个简单系统 | ✅ QMem 11 工具（原 17）+ DomainKG 10 工具，各职责单一 |
| AI 语义理解获取 | 主动调用 | ✅ concept_recall 显式调用 |
| 检索纯净度 | 物理隔离 | ✅ 业务概念在独立 db，不混项目草稿 |
| 跨项目技术陷阱承载 | 存多份+CLAUDE.md 兜底 | ✅ consensus 全软删，靠 CLAUDE.md（⚠️ 见第八节容量边界） |
| 扩展性 | 物理隔离 | ✅ DomainKG 独立扩展不影响 QMem |
| 初始成本 | 一次性 | ✅ 已付出（本次改造） |

Y 方案论证文档第六节"待评判者重点回应的问题"均已落地验证。

---

## 七、核实修订日志（2026-07-21）

### 7.1 残留表清理（core_memory.db）

**问题**：`schema.sql` 用 `CREATE TABLE IF NOT EXISTS`，不会删表；`migrate_yplan.py` step_C 对 `project_refs` 只 `DELETE` 数据不 `DROP` 表。导致 `core_memory.db` 长期残留 18 张死表（17 张 kg_* + project_refs），其中 kg_* 含 FTS5/vec0 虚表及其影子表。功能无影响（代码不读写），但是死重 + 文档声称"删 project_refs 表"未兑现。

**清理操作**（已执行，冷备 `core_memory.db.bak_cleanup_20260721`）：
1. 备份 `core_memory.db` → `core_memory.db.bak_cleanup_20260721`
2. 安全校验：core 残留的 3 条存活概念（发电计划/可调能力/断面）**全部已在 domain_knowledge.db 存在**（差集为空），DROP 不丢业务数据
3. 加载 `sqlite_vec` 扩展后，**按正确顺序 DROP**：先 DROP 3 张虚表本体（`kg_vectors`/`kg_name_vectors`/`kg_concepts_fts`，影子表随 xDestroy 自动级联），再 DROP 3 张普通表（`kg_concepts`/`kg_edges`/`project_refs`），最后清 `sqlite_sequence` 残留项 + `VACUUM`
   - ⚠️ 踩坑：**不可先删影子表再删主虚表**——会让主虚表变"僵尸"（影子丢失导致 xDestroy 报错 `vtable constructor failed` / `no such module: vec0`），无法析构。必须先 DROP 虚表本体。
4. 结果：12 张表 → 最终仅 `memory_facts` + `memory_vectors` + `memory_facts_fts`（+4 影子表）+ `sqlite_sequence`；体积 7.1MB → 2.8MB；memory_facts 67 条 + memory_vectors 76 行（一一对应）完好

### 7.2 MCP 客户端配置收口 + 删除冗余示例文件

原 `mcp/mcp_config_example.json` 只注册了 QMem + DomainKG，遗漏 codebase-memory（"三 MCP"第三条腿没接上）。复核发现该示例文件与 `WINDOWS_SETUP_GUIDE.md` 第 2 节的配置说明完全重叠（SETUP_GUIDE 还多带 `env.PYTHONUTF8` 等字段，更完整），属冗余。处置：

- 删除 `mcp/mcp_config_example.json`
- 三 server 客户端注册方法（Cursor / Claude Desktop JSON 两种）统一以 `mcp/WINDOWS_SETUP_GUIDE.md` 第 2 节为准，其中 codebase-memory 条目指向 `mcp/codebase-memory/codebase-memory-mcp.exe`（已验证 exe 为标准 stdin/stdout JSON-RPC，version 0.10.0）
- 同步修正 SETUP_GUIDE：目录树删去 example 行；原"插件根目录 `.mcp.json` 已配好"表述失实（mcp/ 下并无 `.mcp.json`），改为指明按客户端自行写配置

### 7.3 kg_schema.sql 注释修正

`mcp/domain-kg/kg_schema.sql` 头部注释原写"共用同一个 core_memory.db 文件"（V4.0 拆分前措辞），已改为"独立 domain_knowledge.db，与 QMem 物理隔离"。

### 7.4 文档勘误汇总

| 原文（单目录布局） | 实际（三目录布局） |
|---|---|
| `mcp_server.py` | `mcp/qmem/server.py` |
| `domain_mcp_server.py` | `mcp/domain-kg/server.py` |
| `cbm_wrapper.py` | 三目录拆分后已不存在 |
| `start_domain_mcp.bat` | `mcp/domain-kg/start.bat` |
| `.mcp.json` | 无预制配置文件；三 server 注册见 `WINDOWS_SETUP_GUIDE.md` 第 2 节（原 `mcp_config_example.json` 已删） |
| `.zcode-plugin/plugin.json` | 不在本 mcp 目录（zcode 插件包产物） |
| `restart_mcp.ps1` | 不在本 mcp 目录（部署脚本） |
| `gui/server.py` | `mcp/qmem/gui/server.py` |
| `core_memory.db` 9 概念 | domain_knowledge.db **10 存活概念**（总数 20，软删 10） |
| 单层 0.75 熔断 | **双层熔断**（FTS 别名 + name 向量 0.75） |

---

## 八、已知边界与待办（未关闭）

核实中发现的设计边界，当前数据规模下不致命，但需显式记录：

1. **DomainKG 全部 verified=0**：10 条存活概念无一进入"已核实"状态。迁移后的人工核实流程（GUI 查看 → concept_update(verified=1)）尚未走完。DomainKG 当前是"未审核数据"状态，建议尽快逐条核实。
2. **CLAUDE.md 兜底的容量边界**：跨项目技术陷阱（java-cloud-common/weakpwd）consensus 软删后交给全局 CLAUDE.md 硬编码。当前仅 2 条，可持续；但 CLAUDE.md 每会话注入、定位是"短而权威"，若技术陷阱积累到几十上百条会膨胀失控。**无自动化容量上限或演化预案**，需人工监控。
3. **三 MCP 路由靠 AI 软判断**：一次需求分析可能要串行调 concept_recall（DomainKG）→ mem_context（QMem）→ search_graph（codebase-memory），工具选择依赖 AI 读 SKILL.md 自行判断，是软约束非硬约束。AI 选错 MCP（如该查业务概念却 mem_recall）时，三 MCP 拆分反而增加认知负担。建议在 skill 文档补"工具选择决策树"。
4. **`concept_neighbors` 规模未压测**：递归 CTE 图遍历在当前 2 边规模下无压力，但概念数到几百、边到上千时的性能未验证。
5. **embedding 双进程加载**：QMem 与 DomainKG 各自独立进程，BGE-small-zh ONNX 模型各加载一份（内存翻倍），未做共享。
6. **`migrate_yplan.py` 不可复用**：归位逻辑（title→概念名格式转换）写死且 db 路径已失效，仅作审计。若未来有第二批 consensus 待迁，需新写脚本。
