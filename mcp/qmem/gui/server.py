#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
QMem 记忆可视化 - 只读 HTTP 服务
零依赖（仅 Python 标准库），只读连接 core_memory.db，绝不写库。

启动:  cd <QMem根>/gui && python server.py   （如 D:\\cly-marketplace\\qmem\\mcp\\gui）
访问:  http://localhost:8765
"""

import json
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# ── 配置 ──────────────────────────────────────────────
PORT = 8765
GUI_DIR = os.path.dirname(os.path.abspath(__file__))
# V4.0 目录拆分：QMem 在 mcp/qmem/，DomainKG 在 mcp/domain-kg/。GUI 在 mcp/gui/。
MEM_DB_PATH = os.path.normpath(os.path.join(GUI_DIR, "..", "qmem", "core_memory.db"))
KG_DB_PATH = os.path.normpath(os.path.join(GUI_DIR, "..", "domain-kg", "domain_knowledge.db"))
DB_URI = "file:%s?mode=ro" % MEM_DB_PATH.replace("\\", "/")          # 默认：记忆库（兼容旧引用）
KG_DB_URI = "file:%s?mode=ro" % KG_DB_PATH.replace("\\", "/")
DEFAULT_LIMIT = 200


# ── 数据库只读连接 ────────────────────────────────────
def _query_db(db_uri, sql, params):
    """底层只读查询，自动加载 sqlite_vec 扩展（KG 向量检索需要）。"""
    conn = sqlite3.connect(db_uri, uri=True)
    conn.enable_load_extension(True)
    try:
        import sqlite_vec
        sqlite_vec.load(conn)
    except Exception as e:
        # vec 扩展加载失败时，纯 memory_* 的 SQL 仍可正常工作（KG 相关查询会报错，但不阻塞其它端点）
        print("[query] sqlite_vec load failed (KG endpoints will error): %s" % e)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
        return rows
    finally:
        conn.close()


def query(sql, params=()):
    """执行只读查询（记忆库 core_memory.db），返回 list[dict]。"""
    return _query_db(DB_URI, sql, params)


def query_kg(sql, params=()):
    """执行只读查询（领域库 domain_knowledge.db），返回 list[dict]。KG 端点专用。"""
    return _query_db(KG_DB_URI, sql, params)


def query_one(sql, params=()):
    """执行只读查询（记忆库），返回单个 dict（第一行）或 None。"""
    rows = query(sql, params)
    return rows[0] if rows else None


# ── API 实现 ──────────────────────────────────────────
def api_memories(params):
    """记忆列表，支持 project / type / q 过滤"""
    where = ["deleted_at IS NULL"]
    args = []

    p = params.get("project", [None])[0]
    if p:
        where.append("project = ?")
        args.append(p)

    ty = params.get("type", [None])[0]
    if ty:
        where.append("type = ?")
        args.append(ty)

    q = params.get("q", [None])[0]
    if q:
        where.append("(title LIKE ? OR content LIKE ?)")
        like = "%%%s%%" % q
        args += [like, like]

    where_clause = " AND ".join(where)
    sql = (
        "SELECT obs_uuid, project, topic_key, title, content, type, "
        "       created_at, updated_at "
        "FROM memory_facts "
        "WHERE %s "
        "ORDER BY updated_at DESC LIMIT ?" % where_clause
    )
    args.append(DEFAULT_LIMIT)
    return query(sql, args)


def api_stats(_params):
    """统计汇总：总数 / type 分布 / 各 project 记忆数"""
    stats = {}
    stats["total"] = query(
        "SELECT COUNT(*) AS n FROM memory_facts WHERE deleted_at IS NULL"
    )[0]["n"]

    stats["type"] = query(
        "SELECT type AS k, COUNT(*) AS n FROM memory_facts "
        "WHERE deleted_at IS NULL GROUP BY type ORDER BY n DESC"
    )

    stats["by_project"] = query(
        "SELECT project AS k, COUNT(*) AS n FROM memory_facts "
        "WHERE deleted_at IS NULL GROUP BY project "
        "ORDER BY n DESC"
    )
    return stats


def api_graph(_params):
    """项目记忆分布图：每个 project 一个节点，大小=记忆数，颜色按主 type。
    V4.0：project_refs 表已删（共识机制移除），本图只展示项目记忆体量分布，无边。"""
    # 各项目记忆数 + type 分布
    count_map = {}
    for row in query(
        "SELECT project, type, COUNT(*) AS n FROM memory_facts "
        "WHERE deleted_at IS NULL GROUP BY project, type"
    ):
        c = count_map.setdefault(row["project"], {"total": 0, "types": {}})
        c["total"] += row["n"]
        c["types"][row["type"]] = row["n"]

    nodes = []
    for pid, c in count_map.items():
        # 主 type（记忆数最多的 type）作为节点颜色映射依据
        main_type = max(c["types"].items(), key=lambda kv: kv[1])[0] if c["types"] else ""
        nodes.append({
            "id": pid, "type": "project",
            "count": c["total"], "types": c["types"],
            "main_type": main_type, "degree": 0,
        })
    # 按记忆数降序，方便 graph.html 渲染
    nodes.sort(key=lambda n: n["count"], reverse=True)
    return {"nodes": nodes, "edges": []}


# ── 领域知识图谱 API（只读，供 kg.html 消费）──────────

def api_concepts(params):
    """领域概念卡列表。支持 verified / q 过滤。
    verified: '' 全部 / '0' 待核实 / '1' 已核实
    q: 按 name/aliases/definition/misconception 模糊匹配"""
    where = ["deleted_at IS NULL"]
    args = []

    v = params.get("verified", [None])[0]
    if v in ("0", "1"):
        where.append("verified = ?")
        args.append(int(v))

    q = params.get("q", [None])[0]
    if q:
        where.append("(name LIKE ? OR aliases LIKE ? OR definition LIKE ? OR misconception LIKE ?)")
        like = "%%%s%%" % q
        args += [like, like, like, like]

    where_clause = " AND ".join(where)
    sql = (
        "SELECT obs_uuid, name, aliases, definition, misconception, source, verified, "
        "       created_at, updated_at "
        "FROM kg_concepts WHERE %s "
        "ORDER BY (verified = 0), updated_at DESC LIMIT ?" % where_clause  # 待核实(verified=0)排前面
    )
    args.append(DEFAULT_LIMIT)
    return query_kg(sql, args)


def api_kg_graph(_params):
    """领域知识图谱全局概览：所有概念节点 + 所有关系边。供 kg.html 力导向图渲染。
    节点附带 definition/misconception 预览 + verified 状态 + 度数。
    边含 relation_type（6 种，不同颜色）+ note。"""
    # 节点
    node_rows = query_kg(
        "SELECT obs_uuid, name, aliases, definition, misconception, source, verified, updated_at "
        "FROM kg_concepts WHERE deleted_at IS NULL"
    )
    nodes = []
    for r in node_rows:
        nodes.append({
            "id": r["name"],              # 图谱用概念名做节点 id
            "obs_id": r["obs_uuid"],
            "name": r["name"],
            "aliases": r["aliases"],
            "definition_preview": (r["definition"] or "")[:200],
            "misconception_preview": (r["misconception"] or "")[:200],
            "source": r["source"],
            "verified": r["verified"],
            "updated_at": r["updated_at"],
        })

    # 边（只保留两端概念都存活的边）
    name_set = {n["id"] for n in nodes}
    edge_rows = query_kg(
        "SELECT src_concept, dst_concept, relation_type, weight, note FROM kg_edges"
    )
    edges = []
    for r in edge_rows:
        if r["src_concept"] in name_set and r["dst_concept"] in name_set:
            edges.append({
                "source": r["src_concept"],
                "target": r["dst_concept"],
                "relation_type": r["relation_type"],
                "weight": r["weight"],
                "note": r["note"],
            })

    # 计算每个节点度数（供节点大小映射）
    deg = {}
    for e in edges:
        deg[e["source"]] = deg.get(e["source"], 0) + 1
        deg[e["target"]] = deg.get(e["target"], 0) + 1
    for n in nodes:
        n["degree"] = deg.get(n["id"], 0)

    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "pending_verify": sum(1 for n in nodes if not n["verified"]),
        "nodes": nodes,
        "edges": edges,
        "relation_types": {
            "derives_from": "派生", "constrains": "约束", "aggregates": "聚合",
            "depends_on": "依赖", "synonym_of": "同义", "contradicts": "矛盾",
        },
    }


def api_kg_neighbor(params):
    """单概念邻域子图（递归遍历，深度可调）。供点击节点后聚焦查看。
    参数: name=概念名, depth=深度(默认2, 最大5)"""
    name = params.get("name", [None])[0]
    if not name:
        return {"error": "name is required"}
    depth_str = params.get("depth", ["2"])[0]
    try:
        depth = max(1, min(5, int(depth_str)))
    except ValueError:
        depth = 2

    # SQLite 递归 CTE：双向遍历 kg_edges
    cte = (
        "WITH RECURSIVE reach(nm, d) AS ("
        "  SELECT ?, 0 "
        "  UNION ALL "
        "  SELECT CASE WHEN e.src_concept = r.nm THEN e.dst_concept ELSE e.src_concept END, r.d + 1 "
        "  FROM reach r JOIN kg_edges e ON (e.src_concept = r.nm OR e.dst_concept = r.nm) "
        "  WHERE r.d < ?"
        ") "
        "SELECT nm, MIN(d) AS md FROM reach GROUP BY nm ORDER BY md"
    )
    rows = query_kg(cte, (name, depth))
    reached = [r["nm"] for r in rows] or [name]

    # 节点详情
    ph = ",".join("?" * len(reached))
    node_rows = query_kg(
        "SELECT obs_uuid, name, aliases, definition, misconception, source, verified "
        "FROM kg_concepts WHERE name IN (%s) AND deleted_at IS NULL" % ph,
        reached
    )
    nodes = []
    for r in node_rows:
        nodes.append({
            "id": r["name"], "obs_id": r["obs_uuid"], "name": r["name"],
            "aliases": r["aliases"],
            "definition_preview": (r["definition"] or "")[:200],
            "misconception_preview": (r["misconception"] or "")[:200],
            "source": r["source"], "verified": r["verified"],
            "is_center": (r["name"] == name),
        })

    # 边
    edge_rows = query_kg(
        "SELECT src_concept, dst_concept, relation_type, weight, note "
        "FROM kg_edges WHERE src_concept IN (%s) AND dst_concept IN (%s)" % (ph, ph),
        reached + reached
    )
    edges = [
        {"source": r["src_concept"], "target": r["dst_concept"],
         "relation_type": r["relation_type"], "weight": r["weight"], "note": r["note"]}
        for r in edge_rows
    ]
    return {"center": name, "depth": depth, "nodes": nodes, "edges": edges}


# ── 路由表 ────────────────────────────────────────────
API_ROUTES = {
    "/api/memories": api_memories,
    "/api/stats": api_stats,
    "/api/graph": api_graph,
    "/api/concepts": api_concepts,
    "/api/kg-graph": api_kg_graph,
    "/api/kg-neighbor": api_kg_neighbor,
}


# ── HTTP Handler ──────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        # API 路由
        if path in API_ROUTES:
            try:
                data = API_ROUTES[path](params)
                self._json(data)
            except Exception as e:
                self._json({"error": str(e)}, code=500)
            return

        # 静态文件：友好路由映射
        if path == "/":
            path = "/index.html"
        elif path == "/graph":
            path = "/graph.html"
        elif path == "/kg":
            path = "/kg.html"

        # 安全：禁止目录穿越
        rel = path.lstrip("/")
        abs_path = os.path.normpath(os.path.join(GUI_DIR, rel))
        if not abs_path.startswith(GUI_DIR):
            self._text(403, "Forbidden")
            return

        if os.path.isfile(abs_path):
            self._serve_file(abs_path)
        else:
            self._text(404, "Not Found")

    def _json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _text(self, code, msg):
        body = msg.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, abs_path):
        ext = os.path.splitext(abs_path)[1].lower()
        ctype = {
            ".html": "text/html; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".svg": "image/svg+xml",
        }.get(ext, "application/octet-stream")

        with open(abs_path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        # 简化日志，只打请求行
        print("  %s" % (self.address_string(),))


def main():
    if not os.path.isfile(MEM_DB_PATH):
        print("[ERROR] 记忆库不存在: %s" % MEM_DB_PATH)
        raise SystemExit(1)

    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("=" * 50)
    print("  QMem 记忆可视化 (只读)")
    print("  记忆库: %s" % MEM_DB_PATH)
    print("  领域库: %s" % KG_DB_PATH)
    print("  访问:   http://localhost:%d" % PORT)
    print("=" * 50)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  已停止")
        server.shutdown()


if __name__ == "__main__":
    main()
