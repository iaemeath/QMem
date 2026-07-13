# QMem Windows 内网测试机 MCP 配置指南

> QMem v3.0 — 单表全家桶 + 虚拟外键引用（方案 10 RFC）
>
> 架构：所有记忆（动态草稿 q4 + 跨项目共识 consensus）共享同一张 `memory_facts` 表和同一套向量/FTS 索引。
> 通过 `tier` 字段区分层级，`project_refs` 表记录项目→共识域的多对多引用关系。

## 1. 核心运行文件

测试机的核心入口已经封装为了批处理脚本，该脚本会自动处理环境变量和 Python 路径，确保无乱码和依赖正确：
- **入口路径**: `C:\QMem\python\start_python_mcp.bat`

## 2. MCP 客户端配置方法

### 如果使用 Cursor
打开 Cursor 的设置（Settings） -> Features -> MCP Servers，点击 `+ Add New MCP Server`，填写以下信息：

- **Name**: `QMem-Memory`
- **Type**: `command`
- **Command**: `cmd.exe /c C:\QMem\python\start_python_mcp.bat`

### 如果使用 Claude Desktop (或修改 JSON 配置)
编辑你的 `claude_desktop_config.json`，在 `mcpServers` 节点下增加以下配置：

```json
{
  "mcpServers": {
    "QMem-Windows-Python": {
      "command": "cmd.exe",
      "args": [
        "/c",
        "C:\\QMem\\python\\start_python_mcp.bat"
      ]
    }
  }
}
```

## 3. 工具列表（v3.0，14 个本地工具）

| 工具 | 用途 |
|---|---|
| `mem_save` | 写动态记忆（tier=q4） |
| `mem_recall` | 搜项目动态记忆 + 引用的共识（单次同源 RRF + 三步法配额） |
| `mem_search` | 精确过滤动态记忆 |
| `mem_update` | 更新记忆（consensus 需 confirm_consensus=true） |
| `mem_context` | 开场召回：自身记忆 + 引用的共识（防爆 top-N） |
| `mem_delete` | 硬删除（consensus 需 confirm_consensus=true；自动清理空域 refs） |
| `memory_promote` | 提取为共识（UPDATE tier+project+origin_project + 建 ref） |
| `memory_demote` | 降级回动态（origin_project 为空则拒绝——溯源黑洞防护） |
| `consensus_recall` | 专搜共识库 |
| `consensus_health_check` | 检查共识域是否有高度相似记录，提示 AI 精炼 |
| `add_consensus_ref` | 手动建立项目→共识域引用 |
| `list_consensus_projects` | 列出共识域（供 promote 选择目标） |
| `mem_list_projects` | 列动态记忆的 project |
| `init_project_context` | 目录身份探测 |
| CBM 转发工具 | 代码查询（search_graph/trace_path 等），自动转发到 codebase-memory-mcp |

## 4. 常见问题排查

如果在客户端连接时出现 `JSON-RPC parsing error` 或 `timeout`，可以尝试：
1. 打开 Windows 命令行 (`cmd.exe`)
2. 手动运行 `C:\QMem\python\start_python_mcp.bat`
3. 检查是否有 Python 报错（如找不到模块、找不到 `core_memory.db` 等）
4. 如果输出一直停留在空白等待输入，代表服务启动成功，正在等待 JSON-RPC 握手数据（按 Ctrl+C 可退出）。

## 5. DB 状态检查

```bash
python C:\QMem\check_db.py
```

输出 tier 分布（q4/consensus）、project 分布、project_refs 引用关系、列完整性检查。
