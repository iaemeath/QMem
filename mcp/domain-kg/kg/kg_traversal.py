"""
领域知识图谱 - 递归 CTE 图遍历 + RRF 混合检索

两个核心能力：
1. concept_recall(query)：RRF 混合检索概念卡（FTS5 词法 + 向量语义），返回匹配概念
2. concept_neighbors(obs_id/name, depth, relation_types)：递归 CTE 遍历 kg_edges，
   返回以某概念为中心的子图（节点 + 边），供 GUI 力导向图渲染

设计依据：update/领域知识图谱MCP-自建方案.md（递归 CTE 图遍历 + 6 种关系）
"""

import os
import sys
import json
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class KGTraversal:
    def __init__(self, db_path, embedder=None):
        self.db_path = db_path
        self.embedder = embedder  # RRF 检索需要，可为 None（仅 FTS 降级）

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.enable_load_extension(True)
        import sqlite_vec
        sqlite_vec.load(conn)
        conn.row_factory = sqlite3.Row
        return conn

    # ==================== RRF 混合检索概念 ====================

    def _lexical_search(self, conn, query, limit=20):
        """FTS5 词法检索概念卡。MATCH 查 name/aliases/definition/misconception 四字段。"""
        safe = query.replace('"', '""')
        fts_query = f'"{safe}"'
        try:
            rows = conn.execute(
                "SELECT kc.obs_uuid, kc.name, kc.aliases, kc.definition, kc.misconception, "
                "kc.verified, bm25(kg_concepts_fts) AS fts_score "
                "FROM kg_concepts_fts JOIN kg_concepts kc ON kc.id = kg_concepts_fts.rowid "
                "WHERE kg_concepts_fts MATCH ? AND kc.deleted_at IS NULL "
                "ORDER BY fts_score LIMIT ?",
                (fts_query, limit)
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            print(f"[kg_lex] FTS5 failed, fallback LIKE: {e}", file=sys.stderr)
            # LIKE 降级
            p = f"%{query}%"
            rows = conn.execute(
                "SELECT obs_uuid, name, aliases, definition, misconception, verified "
                "FROM kg_concepts WHERE deleted_at IS NULL "
                "AND (name LIKE ? OR aliases LIKE ? OR definition LIKE ? OR misconception LIKE ?) "
                "LIMIT ?",
                (p, p, p, p, limit)
            ).fetchall()
            return [dict(r) for r in rows]

    def _semantic_search(self, conn, query_vec, limit=10):
        """向量语义检索概念卡（cosine）。"""
        if not self.embedder:
            return []
        try:
            v = json.dumps(list(query_vec))
            rows = conn.execute(
                "SELECT kc.obs_uuid, kc.name, kc.aliases, kc.definition, kc.misconception, "
                "kc.verified, vec_distance_cosine(kv.embedding, ?) as distance "
                "FROM kg_vectors kv JOIN kg_concepts kc ON kv.rowid = kc.id "
                "WHERE kc.deleted_at IS NULL ORDER BY distance LIMIT ?",
                (v, limit * 3)
            ).fetchall()
            res = []
            for r in rows:
                d = dict(r)
                d["similarity"] = round(1.0 - float(d["distance"]), 4)
                res.append(d)
            return res
        except Exception as e:
            print(f"[kg_sem] error: {e}", file=sys.stderr)
            return []

    def recall(self, query, min_similarity=0.5, limit=10, k=60):
        """RRF 混合检索概念卡。FTS5 + 向量融合排序。
        返回匹配的概念卡列表（含 definition/misconception），按相关性降序。"""
        if not query:
            return {"error": "query is required"}

        conn = self._get_conn()
        try:
            lex = self._lexical_search(conn, query, limit=20)
            sem = []
            if self.embedder:
                qvec = self.embedder.embed(query)
                sem = self._semantic_search(conn, qvec, limit=limit * 3)

            scores = {}
            items = {}
            for rank, item in enumerate(lex):
                iid = item["obs_uuid"]
                items[iid] = item
                scores[iid] = scores.get(iid, 0) + (1.0 / (k + rank + 1))
            for rank, item in enumerate(sem):
                if item.get("similarity", 0) < min_similarity:
                    continue
                iid = item["obs_uuid"]
                if iid in items:
                    items[iid].update({kk: vv for kk, vv in item.items() if kk not in items[iid]})
                else:
                    items[iid] = item
                scores[iid] = scores.get(iid, 0) + (1.0 / (k + rank + 1))

            sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:limit]
            results = []
            for iid, sc in sorted_items:
                it = items[iid]
                results.append({
                    "obs_id": iid,
                    "name": it.get("name", ""),
                    "aliases": it.get("aliases", ""),
                    "definition": it.get("definition", ""),
                    "misconception": it.get("misconception", ""),
                    "verified": it.get("verified", 0),
                    "score": round(sc, 6),
                    "similarity": it.get("similarity"),
                })
            return {
                "query": query,
                "total": len(results),
                "results": results,
            }
        finally:
            conn.close()

    # ==================== 递归 CTE 图遍历 ====================

    def neighbors(self, obs_id=None, name=None, depth=2, relation_types=None):
        """以某概念为中心，递归遍历 kg_edges，返回子图（节点 + 边）。
        - depth: 遍历深度（默认 2，即中心概念的直接邻居 + 邻居的邻居）
        - relation_types: 可选，只走指定关系类型（list），None=全部 6 种

        返回 {"center": name, "depth": depth, "nodes": [...], "edges": [...]}
        nodes 含 name/definition_preview/misconception_preview/verified
        edges 含 src/dst/relation_type/weight/note
        """
        if not obs_id and not name:
            return {"error": "obs_id or name is required"}
        if depth < 1:
            depth = 1
        if depth > 5:
            depth = 5  # 防爆炸，电力调度概念图不会深过 5

        conn = self._get_conn()
        try:
            # 定位中心概念
            if obs_id:
                center = conn.execute(
                    "SELECT name FROM kg_concepts WHERE obs_uuid=? AND deleted_at IS NULL",
                    (obs_id,)
                ).fetchone()
            else:
                center = conn.execute(
                    "SELECT name FROM kg_concepts WHERE name=? AND deleted_at IS NULL",
                    (name,)
                ).fetchone()
            if not center:
                return {"error": "concept not found"}
            center_name = center["name"]

            # 关系类型过滤条件
            rel_filter = ""
            rel_params = []
            if relation_types:
                placeholders = ",".join("?" * len(relation_types))
                rel_filter = f" AND relation_type IN ({placeholders})"
                rel_params = list(relation_types)

            # 递归 CTE：双向遍历（边是无向语义，src→dst 和 dst→src 都要跟）
            # 每跳 depth+1，记录到达的概念名和当前深度
            cte_sql = f"""
            WITH RECURSIVE reach(name, depth) AS (
                -- 起点：中心概念
                SELECT ?, 0
                UNION ALL
                -- 递归：从已到达概念出发，沿边扩展（双向）
                SELECT CASE WHEN e.src_concept = r.name THEN e.dst_concept ELSE e.src_concept END,
                       r.depth + 1
                FROM reach r
                JOIN kg_edges e ON (e.src_concept = r.name OR e.dst_concept = r.name)
                WHERE r.depth < ?{rel_filter}
            )
            SELECT DISTINCT name, MIN(depth) as min_depth FROM reach
            WHERE name != ? OR EXISTS (SELECT 1 FROM reach WHERE name = ? AND depth = 0)
            GROUP BY name
            ORDER BY min_depth
            """
            params = [center_name, depth] + rel_params + [center_name, center_name]
            rows = conn.execute(cte_sql, params).fetchall()
            reached_names = [r["name"] for r in rows]

            if not reached_names:
                reached_names = [center_name]

            # 取节点详情
            ph = ",".join("?" * len(reached_names))
            node_rows = conn.execute(
                f"SELECT obs_uuid, name, aliases, definition, misconception, verified "
                f"FROM kg_concepts WHERE name IN ({ph}) AND deleted_at IS NULL",
                reached_names
            ).fetchall()
            nodes = []
            for r in node_rows:
                d = dict(r)
                nodes.append({
                    "obs_id": d["obs_uuid"], "name": d["name"],
                    "aliases": d["aliases"],
                    "definition_preview": (d["definition"] or "")[:120],
                    "misconception_preview": (d["misconception"] or "")[:120],
                    "verified": d["verified"],
                    "is_center": (d["name"] == center_name),
                })

            # 取这些节点之间的边（两端都在 reached 集合内）
            edge_rows = conn.execute(
                f"SELECT src_concept, dst_concept, relation_type, weight, note "
                f"FROM kg_edges WHERE src_concept IN ({ph}) AND dst_concept IN ({ph})"
                + rel_filter,
                reached_names + reached_names + rel_params
            ).fetchall()
            edges = [dict(r) for r in edge_rows]

            return {
                "center": center_name,
                "depth": depth,
                "node_count": len(nodes),
                "edge_count": len(edges),
                "nodes": nodes,
                "edges": edges,
            }
        finally:
            conn.close()
