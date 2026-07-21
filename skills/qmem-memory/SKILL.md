---
name: qmem-memory
description: "Use when 需要保存/检索跨会话项目记忆（QMem 的 mem_save/mem_recall/mem_context）、查业务概念定义（DomainKG 的 concept_recall/concept_get）、查代码事实（codebase-memory 的 search_graph/trace_path）、查阅项目踩坑根因/决策理由/任务进度、新会话开场召回。覆盖 V4.0 三 MCP 架构：QMem=项目时间维度 / DomainKG=业务认知维度 / codebase-memory=代码结构维度。"
version: 4.0
---

# QMem 跨会话项目记忆系统（v4.0 三 MCP 架构）

> **V4.0（2026-07-20）重大架构变更**：拆成 3 个正交 MCP server，各管一个维度。
>
> | MCP server | 维度 | 职责 | 工具前缀 |
> |---|---|---|---|
> | **QMem**（本 skill） | 时间（项目演进） | 项目架构/进度/踩坑/决策 | `mem_*` |
> | **DomainKG** | 认知（业务理解） | 电力调度业务概念（"纠偏字典"） | `concept_*` / `edge_*` |
> | **codebase-memory** | 结构（代码实体） | 函数/类/调用关系/表字段 | `search_graph` / `trace_path` 等 |
>
> QMem 不再承载 consensus 共识域（已删）、不再转发 CBM、不再含领域图谱。
> - 业务概念查询 → DomainKG 的 `concept_recall`
> - 代码事实查询 → codebase-memory 的 `search_graph`/`trace_path`
> - 跨项目技术规范 → 全局 `~/.claude/CLAUDE.md`（已硬编码）

## 开场召回（必做）

```
mem_context(project="<文件夹名>")
```

v4.0：mem_context 返回**摘要索引**（title + content 前100字 + obs_id），只含本项目记忆（不再加载共识域）。AI 全局扫描后用 `mem_get_full(obs_id=)` 拉相关记忆的完整全文。

**需求分析/业务理解阶段**：开场改用 DomainKG 的 `concept_recall(query="发电计划")` 核对业务概念语义，防止"台账建成 CRUD""发电计划当属性"这类理解错误。

## 增量验收闭环（整批改完后必做）

「改完一整批代码 → 比对原始需求文档 vs 代码实现」是核心动作。关键：**等一个方案/计划执行完整批改完后跑一次**，不要每个文件都重建图谱。

```
方案执行完成（整批改完）
  → index_repository(repo_path="<项目绝对路径>", mode="fast")  # codebase-memory 真增量重建图谱
  → detect_changes(project="<文件夹名>")                        # 看本次改动影响范围（只读）
  → qmem:acceptance-check 对照 docs/需求文档出验收报告
```

- **为什么 per-batch 而非 per-write**：index_repository 即便 fast 也要对变更文件跑 LSP 解析（单文件几秒），per-write 会拖垮编码节奏
- **mode="fast"**：最轻量重建（只索引过滤后文件、跳过相似度/语义边）
- **detect_changes 不更新图谱**：它只读现有图谱算影响范围，所以必须先 index_repository 让图谱跟上
- **前置条件**：项目必须是 git 仓库
- 示例：`changzhou-balance-plan` 一轮改完 → `index_repository(repo_path="D:\\code\\changzhou-balance-plan", mode="fast")` → `detect_changes(project="changzhou-balance-plan")` → acceptance-check 对照 `docs/需求分析-x.y-*.md`

## 工具速查（QMem 项目记忆，11 个）

| 工具 | 用途 | 关键参数 |
|---|---|---|
| `mem_context(project=)` | **开场召回**：返回项目记忆摘要索引，不再返回全文 | project |
| `mem_get_full(obs_id=)` | **按需拉全文**：从摘要索引拿到 obs_id 后拉完整 content。支持批量（逗号分隔，上限20） | obs_id |
| `mem_recall(query=)` | **RRF 混合检索**：搜当前项目的记忆（FTS5+向量） | query, current_project, min_similarity=0.5, limit=10 |
| `mem_search(query=)` | **精确/过滤查找**：FTS5 MATCH + project/type 过滤 | query, project, type, limit |
| `mem_save(project_id=, content=)` | **写入项目记忆**：topic_key 命中自动 upsert。★ 写入门禁：相似度>0.85 拦截，force=true 放行 | project_id, content, title, type, topic_key, force |
| `mem_update(obs_id=)` | 局部更新（content/title/type），自动重算向量 | obs_id, content, title, type |
| `mem_delete(obs_id=)` | 默认软删（可恢复）；hard=true 物理删 | obs_id, hard |
| `mem_list_projects()` | 列出所有项目的记忆数 | — |
| `init_project_context(directory=)` | 探测目录身份（git remote/pom/package.json） | directory |
| `cross_project_health_check()` | 检测跨项目记忆的语义重复（判断真重复 vs 同构模板） | threshold=0.85, limit=20 |
| `mem_consolidate_project(project=)` | 单项目内高相似簇检测（消化单项目堆积） | project, threshold=0.85 |

### 领域知识图谱工具（DomainKG MCP，10 个）

业务概念查询**不在 QMem**，在独立的 DomainKG MCP：

| 工具 | 用途 |
|---|---|
| `concept_recall(query=)` | **业务概念 RRF 检索**：需求分析阶段核对业务名词语义（防理解错误） |
| `concept_get(name=)` | 拉取单个概念完整定义 + AI 易误解点（misconception） |
| `concept_save(name=, definition=)` | 写入/更新概念卡（强熔断防"发电计划/出力计划"重复） |
| `concept_update(obs_id=)` / `concept_delete(obs_id=)` / `concept_list()` | 概念卡管理 |
| `edge_save(src_concept=, dst_concept=, relation_type=)` | 建概念关系边（6 种关系） |
| `edge_delete()` / `list_relations()` | 边管理 |
| `concept_neighbors(name=)` | 递归图遍历：以某概念为中心扩展子图 |

### 代码事实工具（codebase-memory MCP）

代码实体查询**不在 QMem**，在独立的 codebase-memory MCP：`search_graph` / `trace_path` / `get_architecture` / `get_code_snippet` / `search_code` / `query_graph` / `index_repository` / `detect_changes` 等。

## 检索技巧

- **项目记忆**（中文：保供/达梦/弱口令/断面）：用 QMem 的 `mem_recall`（向量路覆盖中文双字词）
- **项目记忆**（英文标识符：ResponseMsg/FeignClient）：用 `mem_recall` 或 `mem_search`（FTS5 精确匹配）
- **业务概念**（发电计划/台账/D5000/负荷电量）：用 DomainKG 的 `concept_recall`
- **代码事实**（函数签名/调用关系/表字段）：用 codebase-memory 的 `search_graph`/`trace_path`
- **阈值策略**：`min_similarity` 默认 0.5；结果为空降到 0.4；噪声多升到 0.6

## 记忆生命周期与主题分类

### type 字段（★ 必填，决定生命周期）

每次 `mem_save` **必须标对 type**：

| type 值 | 生命周期 | 含义 | 审查策略 |
|---|---|---|---|
| `reference` | 稳定 | 项目骨架/数据模型/踩坑根因/决策理由 | 代码大改时才更新 |
| `progress` | ★ 易过期 | 当前进度/未推送/待修复/完成度 | 每次推进时 upsert，超 30 天需验证 |
| `decision` | 稳定 | 架构决策带理由 | 决策变更时更新 |
| `bugfix` | 稳定 | 已修复的 bug 根因 | 不需审查 |
| `learning` | 稳定 | 经验教训 | 不需审查 |
| `manual` | 稳定 | 手动记录 | 不需审查 |

### topic_key 字段（可选，仅记忆多时用）

- 一个 project 只有 1-2 条记忆时 → **topic_key 留空**（project + type 已足够 upsert）
- 一个 project 记忆多（>3 条）时 → 用 topic_key 按主题/里程碑区分（如 `arch`、`workflow`、`m1.4`）
- topic_key 不带生命周期后缀，纯按主题命名
- 单项目 topic_key 总数 ≤ 5

### upsert 锚点

`同 project + topic_key` 命中则更新。topic_key 留空时按 `project + 空 topic_key` upsert。

### 易过期审查

mem_context 自动返回 `review_queue`（本项目 type=progress 且超 30 天的记忆）。引用前用 git/代码验证，已推进的 upsert 更新、已作废的软删。

### 卫生规则（★ V4.0 重点——三类知识各归各位）

1. **type 必须标对** — 稳定知识用 `reference`/`decision`/`bugfix`，易过期进度用 `progress`
2. **topic_key 可选** — 记忆少时留空，多时按主题命名
3. **写可复用结论，不写流水账** — 一条记忆一个主题，合并同主题碎片
4. **易过期信息标时间锚点** — 进度类 title 带日期，超 30 天引用前用 git/代码验证
5. **★ 业务概念不进 QMem** — 发电计划/台账/D5000 等业务概念用 DomainKG 的 `concept_save` 存，不要用 `mem_save` 存进项目记忆（会污染项目检索且无法跨项目共享）
6. **★ 代码事实不进 QMem** — 函数签名/调用关系/表字段用 codebase-memory 的 `search_graph`/`trace_path` 查，记忆表只存代码里读不出的决策/背景/踩坑
7. **★ 跨项目技术规范不进 QMem** — IS_DELETE中文值/CLOB 等技术陷阱在全局 `~/.claude/CLAUDE.md`，不要重复存进每个项目记忆

## 扩张管理

- 每项目固定线性增长，30 项目内可控
- project 数到 30+ 时考虑分层命名（zj-/tz-/cz- 前缀）
- 同构模板项目（多地区相同业务）各自存项目记忆，用 `cross_project_health_check` 判断是同构（各自保留）还是真重复（合并）

## 克隆项目身份红线

同构/克隆项目（meeting_jj↔meeting_tz、front-end-old-metting 13 城、guaranteedSupplyControlPlatform 多城）的 CLAUDE.md 必须有「⚠️ 地区身份红线」段：绝对身份+血缘关系+共享资源警告（弱口令验证禁止写非原密码）+文案地区名。
