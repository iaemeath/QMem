# CLAUDE.md（项目根工作区）

> `D:\code\` 是**所有项目的根工作区**，包含不同地区（镇江/常州/泰州/靖江）、不同系统（电力调度/排班/弱口令改造/框架父工程）的多个项目。
> **全局指令**（内网环境、通用编码约束、AI 编码自查、记忆体系）见 `~/.claude/CLAUDE.md`，每次会话自动注入，本文件不重复。
> **各项目专属规范**（技术栈细节、数据源、端口、业务约定）见各项目子目录的 `CLAUDE.md`。

## 通用提醒

- 本工作区项目多为"前端独立项目 + 后端独立项目"分仓，改代码前务必确认正确的项目（详见 intranet-dev/skills/gitea-ops 的"确认正确的项目"段）。
- 各项目的详细架构、数据源、模块结构见对应子目录下的 CLAUDE.md（部分项目暂无，见下方索引标注）。

## 项目索引

> **所有项目已建 CLAUDE.md + CM 索引（persistence 落盘）**。改代码前先读项目 CLAUDE.md，查代码结构用 QMem CBM 转发工具（project 名 = `D-code-<文件夹名>`），查踩坑/进度用 QMem（project 名 = 文件夹名，C+ 结构：`-kb` 稳定知识 + `-status` 易过期进度）。召回方法见文末「QMem 召回备忘」。

### 镇江电力调度（主线）

| 子项目 | 路径 | 端口 | QMem project |
|---|---|---|---|
| 保供管控后端 | `bfo_zj_yxyd/` | 8111 /yxyd | bfo_zj_yxyd（kb+status） |
| 保供管控前端 | `guaranteedSupplyControlPlatform/zhenjiang/` | 7001 | （CM 仅 zhenjiang 子目录，无独立 QMem 记忆） |
| 调度APP后端 | `dispatch-app-zj/` | 5000 | dispatch-app-zj（kb） |
| 调度APP前端 | `dispatch-all-new/` | — | dispatch-all-new（kb） |
| 事件管控后端 | `dispatch-event-zj/` | 8087 /event | dispatch-event-zj（kb+status） |
| 事件管控前端 | `zj-sjhgk/` | 8081 | zj-sjhgk（kb） |

### 常州（智能预案，微服务+微前端）

| 子项目 | 路径 | QMem project | 说明 |
|---|---|---|---|
| 常州智能预案 | `changzhou-balance-plan/` | changzhou-balance-plan（kb+status） | 前后端混合仓库，CM 与 AGENTS.md 需同步；模块1.1验收状态见 QMem |

### 排班（独立系统，本地未入 git）

| 子项目 | 路径 | 端口 | QMem project |
|---|---|---|---|
| 排班系统 | `schedule-shifts/` | 后端 8080 / 前端 5173（JDK17 + DM8） | schedule-shifts（kb） |

### 弱口令改造系列（多地区，已完成或推进中）

| 子项目 | 路径 | 端口 | QMem project | 说明 |
|---|---|---|---|---|
| 储能校核后端 | `bfo_cndz/` | 8001 /bfo_cndz | bfo_cndz（kb+status） | 已推送 master d3bad99 |
| 储能校核前端 | `EnergyStorageVerification/` | 9929 | （仅 CM，无独立 QMem 记忆） | 已推送 main 4d7c3e8 |
| 泰州数智化后端 | `binfo-tz-message-manage/` | 8111 /tzMessageManage | binfo-tz-message-manage（kb+status） | 已推送 main（弱口令+导出），单体 |
| 泰州数智化后端 Cloud 版 | `binfo-tz-cloud-message-manage/` | — | （仅 CM 存档，无 QMem 记忆） | 微服务版，弱口令未涉及，仅存档 |
| 泰州数智化前端 | `taiZhou-digital-platform/` | 9010 | taizhou-digital-platform（kb+status） | 已推送 new 0964f221，协作分支 |
| 泰州调度日报 | `bfo_tz_dispatch_report/` | 8112 /tzrb | bfo_tz_dispatch_report（kb+status） | 已推送 origin/master，前端静态页在后端内 |
| 靖江早会后端 | `meeting_jj/` | 9001 /meeting | （仅 CM，无独立 QMem 记忆） | 本地提交未推送 |
| 泰州早会后端 | `meeting_tz/` | 9003 /meeting | （仅 CM，无独立 QMem 记忆） | 后端完成，前端未改 |
| 早会前端（13城市容器） | `front-end-old-metting/` | — | （仅 CM，无独立 QMem 记忆） | 弱口令涉及 taizhou_county_meeting/靖江 |

> 弱口令任务总览（6系统横向对比）见 QMem `_weakpwd` project。

### 框架父工程（被业务项目依赖，改这里影响所有依赖方）

| 父工程 | 路径 | 说明 | QMem project |
|---|---|---|---|
| cloud-frame-parent | `cloud-frame-parent/` | 最底层框架（15 模块：jdbc/feign/gateway/shiro/redis 等） | cloud-frame-parent（kb，改它影响所有依赖方） |
| cloud-balance-parent | `cloud-balance-parent/` | 平衡表领域框架（18 个 frame-balance-* 模块） | cloud-balance-parent（kb） |
| cloud-msg-parent | `cloud-msg-parent/` | 消息领域框架（sendMessage/msg-task） | cloud-msg-parent（kb） |

### 其他

| 目录 | 说明 | QMem project |
|---|---|---|
| `platform-simple-web/` | Vue2 + Ant Design Vue 简化平台前端壳 | （仅 CM） |
| `docs/` | 全局文档区（详见下方"文档目录"） | — |

## 文档目录

> 2026-07-01 核对实际文件。docs/ 根下只有 4 个 .md，其余文档都在项目子目录下。

| 文档 | 说明 |
|------|------|
| `docs/AI记忆体系方案.md` | **寄生谱系方案**（本工作区 AI 记忆体系权威说明：三载体/四象限/寄生哲学/短板评审） |
| `docs/npm依赖与前端技术栈.md` | Vue2/Vue3两套前端技术栈与依赖清单 |
| `docs/数据库表结构索引.md` | 数据库表索引（4 Schema，630+ 表） |
| `docs/数据库连接与SQL覆盖情况.md` | 数据库连接与 SQL 覆盖情况 |
| `docs/内网Gitea仓库索引.md` | Gitea 2292个仓库索引 + 镇江项目组织摘要 |
| `docs/保供管控/` | 保供管控文档（含 `镇江项目/` 01~08 系列、`业务/`、项目概述） |
| `docs/调度小助手后端/` | 调度小助手后端文档（含 `SQL/` 直流出清/调度技术库建表） |
| `docs/调度小助手前端/` | 调度小助手前端文档 |
| `docs/事件管控后端/` | 事件管控后端文档（`业务/` 系统架构/断面模型/状态机/SVG图元等） |
| `docs/事件管控前端/` | 事件管控前端文档 |
| `docs/常州智能预案/` | 常州智能预案文档（业务梳理/项目概览/架构设计/验收测试/需求全集/原始素材） |
| `docs/弱口令校验/` | 弱口令改造文档 |
| `docs/.scripts-archive/` | 归档的脚本/截图中间产物（非文档，周报模板解压XML/页面截图） |

> ⚠️ 旧版登记的 `docs/Skill市场清单.md`、`docs/Maven依赖与配置.md`、`docs/开发规范.md`、`docs/达梦数据库操作指南.md`、`docs/内部服务地址与项目端口.md`、`docs/工作留痕/` 实际不存在，引用前先 `ls docs/` 核对。

## 常用命令

### 事件管控后端 (dispatch-event-zj)
```bash
cd dispatch-event-zj && mvn clean package -DskipTests
# WAR -> Tomcat, port 8087, /event
```

### 事件管控前端 (zj-sjhgk)
```bash
cd zj-sjhgk && npm run dev  # port 8081
```

### 调度APP后端 (dispatch-app-zj)
```bash
cd dispatch-app-zj && mvn clean package -DskipTests
# WAR -> Tomcat, port 5000, /DispatchApp
```

### 调度APP前端 (dispatch-all-new)
```bash
cd dispatch-all-new && npm run dev  # BASE_URL="/module"
```

### 保供管控后端 (bfo_zj_yxyd)
```bash
cd bfo_zj_yxyd && mvn clean install -DskipTests
# port 8111, /yxyd
```

### 保供管控前端 (guaranteedSupplyControlPlatform/zhenjiang)
```bash
cd guaranteedSupplyControlPlatform/zhenjiang && npm run dev  # port 7001
```

### 常州智能预案后端 (changzhou-balance-plan)
```bash
cd changzhou-balance-plan/backend/cloud-cz-balance-parent && mvn clean package -DskipTests
```

### 常州智能预案前端 (changzhou-balance-plan)
```bash
cd changzhou-balance-plan/frontend/cz-main-web && npm run dev  # base 3100
cd changzhou-balance-plan/frontend/cz-resource-web && npm run dev  # 3201
# other sub-apps 3202~3207
```

## QMem 召回备忘

> QMem（`C:\QMem\python\mcp_server.py`）于 2026-07-09 替代了 Engram + mem_search_vector + codebase-memory 三套系统。QMem 是跨会话记忆**唯一来源**，本节是新会话开场的召回指引。

### QMem 工具速查

> v3.0（方案 10 RFC）：单表 + tier 字段区分动态记忆(q4)/共识(consensus) + project_refs 引用图谱。共识和动态记忆同表共存，promote 只改 tier+project（一行 UPDATE），不搬数据不重算向量。

| 工具 | 用途 | 关键参数 |
|---|---|---|
| `mem_context(project=)` | **开场召回**：项目自身动态记忆 + 引用的共识（防爆 top-N） | project, limit=10, consensus_limit=5 |
| `mem_recall(query=)` | **RRF 混合检索**：搜项目动态记忆 + 引用的共识域（单次同源 RRF + 三步法配额）| query, current_project, min_similarity=0.5, limit=10 |
| `consensus_recall(query=)` | **专搜共识库**：查阅通用经验/架构陷阱/踩坑根因 | query, min_similarity, limit |
| `mem_search(query=)` | **精确/过滤查找**：FTS5 MATCH + project/type/scope 过滤（仅 tier=q4） | query, project, type, scope, limit |
| `mem_save(project_id=, content=)` | **写入动态记忆**：topic_key 命中自动 upsert（仅 tier=q4 范围） | project_id, content, title, type, topic_key, scope |
| `mem_update(obs_id=)` | 更新记忆。改 consensus 需 `confirm_consensus=true`；改 consensus content 需声明 `origin_project` 去留 | obs_id, content, title, type, confirm_consensus, origin_project |
| `mem_delete(obs_id=)` | 硬删除。删 consensus 需 `confirm_consensus=true`；自动清理空域 refs | obs_id, confirm_consensus |
| `memory_promote(obs_id=, consensus_domain=)` | **提取为共识**：UPDATE tier+project+origin_project + 建 ref。不挪数据 | obs_id, consensus_domain（必填，如 `_java-cloud-common`） |
| `memory_demote(obs_id=)` | 降级回动态。origin_project 为空（已融合多源）则拒绝降级 | obs_id |
| `consensus_health_check()` | 检查共识域是否有高度相似记录（embedding>0.85），提示精炼 | consensus_domain（可选） |
| `add_consensus_ref(project=, consensus_project=)` | 手动建立项目→共识域引用 | project, consensus_project |
| `list_consensus_projects()` | 列出共识域（供 promote 选择目标） | — |
| `mem_list_projects()` | 列出动态记忆的 project 及记忆数 | — |
| `init_project_context(directory=)` | 探测目录身份（git remote/pom/package.json）| directory |
| **CBM 转发工具** | 代码查询（search_graph/trace_path/get_architecture 等）| 通过 QMem 自动转发到 codebase-memory-mcp |

### 新会话开场必做

```
mem_context(project="<文件夹名>")   # 拉项目动态记忆 + 引用的共识（自动）
```

> v3.0：`mem_context` 自动通过 `project_refs` 加载项目引用的共识域，无需手动补拉 `_` 前缀 project。
> QMem 无 ambiguous_project 问题（不靠 cwd 推断 project，直接传参）。在 `D:\code` 根目录也能用。

### 检索技巧

- **中文查询**（保供/达梦/弱口令/断面）：用 `mem_recall`（向量路覆盖中文双字词，旧 Engram FTS5 的中文盲区已解决）
- **英文标识符**（ResponseMsg/IS_DELETE/FeignClient）：用 `mem_recall` 或 `mem_search`（FTS5 精确匹配）
- **阈值策略**：`min_similarity` 默认 0.5；结果为空降到 0.4；噪声多升到 0.6

### 已迁移的 17 个 project（C+ 结构，从 Engram 迁移）

| project | topic_key | project | topic_key |
|---|---|---|---|
| bfo_zj_yxyd | kb+status | bfo_cndz | kb+status |
| dispatch-event-zj | kb+status | bfo_tz_dispatch_report | kb+status |
| dispatch-app-zj | kb | binfo-tz-message-manage | kb+status |
| dispatch-all-new | kb | taizhou-digital-platform | kb+status |
| zj-sjhgk | kb | changzhou-balance-plan | kb×2+status×2 |
| schedule-shifts | kb | cloud-frame-parent | kb（实体锚点，物理继承） |
| cloud-balance-parent | kb（实体锚点） | cloud-msg-parent | kb（实体锚点） |
| memory-hygiene | 元规则+进度（scope=personal） | | |

> 未建记忆的项目（binfo-tz-cloud-message-manage、meeting_jj/meeting_tz/front-end-old-metting、EnergyStorageVerification、platform-simple-web、guaranteedSupplyControlPlatform）：若后续有跨会话需求用 `mem_save` 补 `-kb`。

### 虚拟 project（第二象限：跨项目部分共识）★

> v3.0 架构变更：`_` 前缀 project 现在存储为 `tier='consensus'` 的共识记忆。项目通过 `project_refs` 表引用共识域，`mem_context` 自动加载引用的共识。
> 不再需要"栈声明触发"手动补拉——用 `add_consensus_ref(project=, consensus_project=)` 建立引用后，开场 `mem_context` 自动带上。

| 共识域 | 类型 | 共识范围 | 应建立引用的项目 |
|---|---|---|---|
| `_weakpwd` | 任务级 | 弱口令改造 6 系统总览+跨系统教训+完成进度 | bfo_cndz / bfo_tz_dispatch_report / binfo-tz-message-manage / taizhou-digital-platform / dispatch-app-zj / meeting_jj / meeting_tz / front-end-old-metting |
| `_vue2-common` | 技术栈级 | Vue2+ElementUI+webpack 共性陷阱（待沉淀） | dispatch-all-new / zj-sjhgk / front-end-old-metting / meeting_jj 前端 |
| `_java-cloud-common` | 技术栈级 | SpringBoot+cloud-frame+MyBatis 共性（IS_DELETE中文值/CLOB/@Transactional）| bfo_zj_yxyd / dispatch-event-zj / dispatch-app-zj / changzhou-balance-plan / 3 父工程 |
| `_dameng-common` | 技术栈级 | 达梦 SQL/disql/DM6DM7 驱动差异（待沉淀） | 所有 Java 后端项目 |

**建立引用**：`add_consensus_ref(project='<真实项目>', consensus_project='<共识域>')`，建立后该项目的 `mem_context` 自动加载引用的共识。
**提取共识**：`memory_promote(obs_id=, consensus_domain='<共识域>')`，将动态记忆提取为共识并自动建立来源项目的引用。
**内容沉淀原则**：共识域只存**跨 ≥2 项目验证过的硬共识**，踩坑时发现跨项目用 `memory_promote` 提取；单项目特有留本项目 tier=q4。

### 写入规则

- project 名 = 子项目文件夹名（任务级总览用任务名，如 `weakpwd`）
- 遵守 `memory-hygiene` project 的卫生规则（详见全局 `~/.zcode/AGENTS.md`）
- `mem_save(project_id="<名>", content="<内容>", title="<标题>", type="<类型>", topic_key="<键>")` — 写入 tier=q4 动态记忆
- 跨项目共识用 `memory_promote(obs_id=, consensus_domain='_xxx')` 提取，不要直接 `mem_save` 到 `_` 前缀 project（upsert 有 tier=q4 守卫，会另建一行）

