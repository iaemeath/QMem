#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
领域知识图谱 MCP server（DomainKG）—— V4.0 Y 方案独立进程

定位：电力调度领域的语义理解服务（"纠偏字典"，非百科全书）。
只收 AI 容易理解错的专业概念。跨所有项目共享（横向认知维度）。

与 QMem / CBM 的正交分工：
  - QMem（mcp/qmem/server.py）：项目记忆（纵向时间维度，按项目隔离）
  - DomainKG（本文件）：业务概念（横向认知维度，跨项目共享）
  - codebase-memory（mcp/codebase-memory/）：代码事实图谱（结构维度，函数/调用/表字段）

数据：独立 domain_knowledge.db（kg_* 表前缀），与 QMem 的 core_memory.db 物理隔离。
技术栈复刻 QMem 三件套：SQLite + sqlite_vec(BGE-small-zh 512维) + FTS5 + RRF。

启动：start.bat（或 python -u server.py）
通信：JSON-RPC over stdin/stdout
"""
import sys
import os
import json

# V4.0 目录独立：DomainKG 全部资源（db/schema/kg包/embedding）与本文件同目录（mcp/domain-kg/）
_DIR = os.path.dirname(os.path.abspath(__file__))
DBPATH = os.path.join(_DIR, "domain_knowledge.db")

from embedding import BGEEmbedding
from kg.kg_store import KGStore, VALID_RELATIONS
from kg.kg_traversal import KGTraversal


class DomainMCP:
    """领域知识图谱 MCP。10 个工具：概念卡 CRUD + 关系边管理 + RRF 检索 + 递归 CTE 图遍历。"""

    def __init__(self):
        self.embedder = BGEEmbedding()
        self.kg_store = KGStore(DBPATH, embedder=self.embedder)
        self.kg_traversal = KGTraversal(DBPATH, embedder=self.embedder)
        self.local_tools = {
            "concept_save", "concept_update", "concept_delete", "concept_get",
            "concept_list", "edge_save", "edge_delete", "list_relations",
            "concept_recall", "concept_neighbors",
        }
        # V4.0 目录独立：DomainKG 不写调用日志（call_log 归 QMem 专属）。time 仅保留 import 备用。

    def _get_conn(self):
        import sqlite3
        conn = sqlite3.connect(DBPATH)
        conn.enable_load_extension(True)
        import sqlite_vec
        sqlite_vec.load(conn)
        conn.row_factory = sqlite3.Row
        return conn

    def handle_request(self, req):
        method = req.get("method")
        params = req.get("params", {})
        rid = req.get("id")
        try:
            if method == "initialize":
                res = self._init()
            elif method == "tools/list":
                res = self._tools_list()
            elif method == "tools/call":
                res = self._tools_call(params)
            else:
                raise ValueError(f"unknown method: {method}")
            return {"jsonrpc": "2.0", "id": rid, "result": res}
        except Exception as e:
            import traceback
            return {"jsonrpc": "2.0", "id": rid,
                    "error": {"code": -32603, "message": str(e),
                              "data": traceback.format_exc()}}

    def _init(self):
        conn = self._get_conn()
        with open(os.path.join(_DIR, "kg_schema.sql"), encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()
        conn.close()
        return {"protocolVersion": "2024-11-05",
                "serverInfo": {"name": "domain-kg-mcp", "version": "4.1"},
                "capabilities": {"tools": {}}}

    def _tools_list(self):
        tools = [
            {"name": "concept_save", "description": "写入/更新领域概念卡（DCK）。name 是唯一标识，已存在则 upsert。★ 强熔断：纯新增时若已有相似度>0.75 的概念，返回 candidates 拦截（电力领域多表述词多，防'发电计划/出力计划'写成两条）；确认是新概念请传 force=true。definition=权威定义，misconception=AI 易误解点（用户补，先留空），aliases=逗号分隔别名，source=定义来源URL/文献。", "inputSchema": {"type": "object", "properties": {"name": {"type": "string", "description": "概念名，唯一业务标识（如'发电计划'）"}, "definition": {"type": "string", "description": "权威定义。电力语境优先"}, "misconception": {"type": "string", "description": "AI 易误解点。先留空，用户在 GUI 查看后补（如'台账数据不是CRUD，是从模板实例化'）"}, "aliases": {"type": "string", "description": "别名，逗号分隔"}, "source": {"type": "string", "description": "定义来源。URL/文献名/【来源待核实】"}, "force": {"type": "boolean", "description": "默认 false。熔断拦截后确认是新概念时传 true 放行"}}, "required": ["name"]}},
            {"name": "concept_update", "description": "按 obs_id 局部更新概念卡（name/definition/misconception/aliases/source/verified）。改文本字段自动重算向量。★ 用户在 GUI 发现错误后用此工具修改；核实无误后传 verified=1 标记已核实。", "inputSchema": {"type": "object", "properties": {"obs_id": {"type": "string"}, "name": {"type": "string"}, "definition": {"type": "string"}, "misconception": {"type": "string"}, "aliases": {"type": "string"}, "source": {"type": "string"}, "verified": {"type": "integer", "description": "0=待核实, 1=已核实"}}, "required": ["obs_id"]}},
            {"name": "concept_delete", "description": "删除概念卡。默认软删除（可恢复）；hard=true 物理删除并级联清理引用该概念名的边。", "inputSchema": {"type": "object", "properties": {"obs_id": {"type": "string"}, "hard": {"type": "boolean", "description": "默认 false 软删除；true 物理删除+清边"}}, "required": ["obs_id"]}},
            {"name": "concept_get", "description": "按 obs_id 或 name 取单张概念卡完整内容（definition+misconception 全文）。", "inputSchema": {"type": "object", "properties": {"obs_id": {"type": "string"}, "name": {"type": "string"}}, "required": []}},
            {"name": "concept_list", "description": "列出概念卡摘要。verified=0 查待核实（需用户看 GUI 确认），=1 查已核实，不传查全部。", "inputSchema": {"type": "object", "properties": {"verified": {"type": "integer", "description": "不传=全部, 0=待核实, 1=已核实"}, "limit": {"type": "integer", "default": 200}}, "required": []}},
            {"name": "edge_save", "description": "建立概念间的关系边。6 种关系：derives_from(派生)/constrains(约束)/aggregates(聚合)/depends_on(依赖)/synonym_of(同义)/contradicts(矛盾,纠错用)。两端按概念 name 引用，必须已存在。同对概念可有多条不同类型边；同方向同类型唯一。建边前可先 list_relations 看关系说明。", "inputSchema": {"type": "object", "properties": {"src_concept": {"type": "string", "description": "源概念 name"}, "dst_concept": {"type": "string", "description": "目标概念 name"}, "relation_type": {"type": "string", "enum": sorted(VALID_RELATIONS), "description": "关系类型"}, "weight": {"type": "number", "default": 1.0, "description": "关系强度[0,1]"}, "note": {"type": "string", "description": "关系说明，如'发电计划约束可调能力上限'"}}, "required": ["src_concept", "dst_concept", "relation_type"]}},
            {"name": "edge_delete", "description": "删除关系边。按 edge_id，或按 (src_concept+dst_concept+relation_type) 三元组定位。", "inputSchema": {"type": "object", "properties": {"edge_id": {"type": "integer"}, "src_concept": {"type": "string"}, "dst_concept": {"type": "string"}, "relation_type": {"type": "string"}}, "required": []}},
            {"name": "list_relations", "description": "列出 6 种关系类型及说明，建边前参考。", "inputSchema": {"type": "object", "properties": {}}, },
            {"name": "concept_recall", "description": "RRF 混合检索概念卡（FTS5+向量）。返回匹配概念的 definition+misconception。★ requirement-analysis 拆需求时用此工具核对业务名词语义，防止'台账建成CRUD''发电计划当属性'这类理解错误。需求分析/业务理解阶段主用此工具（不走 QMem）。", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "min_similarity": {"type": "number", "default": 0.5}, "limit": {"type": "integer", "default": 10}}, "required": ["query"]}},
            {"name": "concept_neighbors", "description": "递归 CTE 图遍历：以某概念为中心，沿 kg_edges 扩展子图（节点+边）。用于理解概念间依赖/约束关系。depth=遍历深度(默认2,最大5)，relation_types=只走指定关系(list)。返回结构供可视化渲染。", "inputSchema": {"type": "object", "properties": {"obs_id": {"type": "string"}, "name": {"type": "string"}, "depth": {"type": "integer", "default": 2}, "relation_types": {"type": "array", "items": {"type": "string"}, "description": "可选，过滤关系类型"}}, "required": []}},
        ]
        return {"tools": tools}

    def _tools_call(self, params):
        name = params.get("name")
        args = params.get("arguments", {})
        if name not in self.local_tools:
            raise ValueError(f"Local tool not found: {name}")
        dispatch = {
            "concept_save": lambda: self.kg_store.save_concept(
                args.get("name", ""), definition=args.get("definition", ""),
                misconception=args.get("misconception", ""), aliases=args.get("aliases", ""),
                source=args.get("source", ""), force=bool(args.get("force"))),
            "concept_update": lambda: self.kg_store.update_concept(
                args.get("obs_id"), name=args.get("name"), definition=args.get("definition"),
                misconception=args.get("misconception"), aliases=args.get("aliases"),
                source=args.get("source"), verified=args.get("verified")),
            "concept_delete": lambda: self.kg_store.delete_concept(
                args.get("obs_id"), hard=bool(args.get("hard"))),
            "concept_get": lambda: self.kg_store.get_concept(
                obs_id=args.get("obs_id"), name=args.get("name")),
            "concept_list": lambda: self.kg_store.list_concepts(
                verified=args.get("verified"), limit=args.get("limit", 200)),
            "edge_save": lambda: self.kg_store.save_edge(
                args.get("src_concept", ""), args.get("dst_concept", ""),
                args.get("relation_type", ""), weight=args.get("weight", 1.0),
                note=args.get("note", "")),
            "edge_delete": lambda: self.kg_store.delete_edge(
                edge_id=args.get("edge_id"), src_concept=args.get("src_concept"),
                dst_concept=args.get("dst_concept"), relation_type=args.get("relation_type")),
            "list_relations": lambda: self.kg_store.list_relations(),
            "concept_recall": lambda: self.kg_traversal.recall(
                args.get("query", ""), min_similarity=args.get("min_similarity", 0.5),
                limit=args.get("limit", 10)),
            "concept_neighbors": lambda: self.kg_traversal.neighbors(
                obs_id=args.get("obs_id"), name=args.get("name"),
                depth=args.get("depth", 2), relation_types=args.get("relation_types")),
        }
        if name not in dispatch:
            raise ValueError(f"Local tool not found: {name}")
        result = dispatch[name]()
        return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}


def serve():
    server = DomainMCP()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            res = server.handle_request(req)
            sys.stdout.write(json.dumps(res, ensure_ascii=False) + "\n")
            sys.stdout.flush()
        except Exception as e:
            import traceback
            sys.stderr.write(f"Error: {e}\n{traceback.format_exc()}\n")


if __name__ == "__main__":
    serve()
