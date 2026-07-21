"""
领域知识图谱 - 概念卡 CRUD + 强熔断 + 边管理

设计原则：
1. 与 QMem 的 memory_facts 完全隔离（表前缀 kg_，独立 rowid 空间）
2. 强熔断：写新概念前在 kg_vectors 找近邻，sim>0.85 拦截（与 QMem _save 同款机制）
3. definition（联网填）+ misconception（用户补）双字段，是图谱的灵魂
4. 6 种关系类型校验由应用层做（schema 用 UNIQUE(src,dst,type) 防重复边）
"""

import os
import sys
import json
import uuid
import hashlib
import sqlite3
import numpy as np

# 确保能 import 兄弟模块 embedding（domain-kg/server.py 启动时本目录已在 sys.path；
# kg/ 子包内独立运行时，dirname(dirname(__file__)) = domain-kg/，含 embedding.py）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from embedding import BGEEmbedding

# 6 种合法关系类型（与 update/领域知识图谱MCP-自建方案.md 一致）
VALID_RELATIONS = {
    "derives_from",   # 派生自：A 由 B 派生（如"日前发电计划" derives_from "发电计划"）
    "constrains",     # 约束：A 约束 B（如"断面限额" constrains "可调能力"）
    "aggregates",     # 聚合：A 聚合 B（如"虚拟电厂" aggregates "储能"）
    "depends_on",     # 依赖：A 依赖 B（如"发电计划整合" depends_on "发电计划"）
    "synonym_of",     # 同义：A 与 B 同义（如"出力计划" synonym_of "发电计划"）
    "contradicts",    # 矛盾：A 与 B 矛盾（纠错用，如"台账CRUD" contradicts "台账实例化"）
}

# 强熔断阈值（基于 name 向量空间）
# BGE-small-zh 是小模型，对字面不同的同义词（"发电计划"vs"出力计划"=0.572）几乎识别不了，
# 但对字面重叠/包含的（"发电计划"vs"发电机组出力计划"=0.784，"台账"vs"台账数据"=0.834）能区分。
# 故向量熔断的真实价值是【防字面重复/包含】，不是【防同义多表述】。
# 同义多表述（出力计划/计划曲线）改由 FTS 别名熔断（_check_alias_collision）兜底——
# 联网建概念时本就会把别名填进 aliases，FTS 能精准命中。
FUSE_THRESHOLD = 0.75


class KGStore:
    def __init__(self, db_path, embedder: BGEEmbedding = None):
        self.db_path = db_path
        self.embedder = embedder or BGEEmbedding()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.enable_load_extension(True)
        import sqlite_vec
        sqlite_vec.load(conn)
        conn.row_factory = sqlite3.Row
        return conn

    # ==================== 概念卡写入（含强熔断）====================

    def save_concept(self, name, definition="", misconception="", aliases="",
                     source="", force=False):
        """
        写入/更新概念卡。
        - name 是唯一业务标识，已存在则按 name upsert（更新 definition/misconception 等）
        - 新增时强熔断：在 kg_vectors 找近邻，sim>0.85 拦截，返回候选让用户决策
        - force=true 绕过熔断（用户确认确实是新概念时）

        返回:
          {"obs_id", "action": "created|updated", "id"}
          或熔断时 {"warning", "candidates", "hint"}
        """
        if not name:
            return {"error": "name is required"}

        conn = self._get_conn()
        try:
            existing = conn.execute(
                "SELECT id, obs_uuid FROM kg_concepts WHERE name=? AND deleted_at IS NULL",
                (name,)
            ).fetchone()

            content_hash = hashlib.sha256(
                (name + definition + misconception + aliases).encode("utf-8")
            ).hexdigest()[:16]

            # 双向量：
            #   name 向量 = 仅 name（熔断用，纯字面，防"发电计划/发电机组出力计划"这类字面重复）
            #   全文向量 = name+aliases+definition+misconception（检索用，召回优先）
            name_vec = self.embedder.embed(name)
            full_text = " ".join([x for x in [name, aliases, definition, misconception] if x])
            full_vec = self.embedder.embed(full_text)
            name_vec_bytes = np.array(name_vec, dtype=np.float32).tobytes()
            full_vec_bytes = np.array(full_vec, dtype=np.float32).tobytes()

            # ===== upsert：name 已存在则更新 =====
            if existing:
                fid = existing["id"]
                oid = existing["obs_uuid"]
                conn.execute(
                    "UPDATE kg_concepts SET name=?, aliases=?, definition=?, misconception=?, "
                    "source=?, content_hash=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (name, aliases, definition, misconception, source, content_hash, fid)
                )
                conn.execute("DELETE FROM kg_vectors WHERE rowid=?", (fid,))
                conn.execute("DELETE FROM kg_name_vectors WHERE rowid=?", (fid,))
                conn.execute("INSERT INTO kg_vectors(rowid, embedding) VALUES (?, ?)", (fid, full_vec_bytes))
                conn.execute("INSERT INTO kg_name_vectors(rowid, embedding) VALUES (?, ?)", (fid, name_vec_bytes))
                conn.commit()
                return {"obs_id": oid, "action": "updated", "id": fid, "via": "name_upsert"}

            # ===== 新增路径：双层熔断 =====
            # 第 1 层 FTS 别名熔断：新概念 name 字面命中已有概念的 name/aliases → 同义多表述，拦
            # 第 2 层 向量熔断：name 向量相似度>0.75 → 字面重复/包含，拦
            if not force:
                alias_hit = self._check_alias_collision(conn, name)
                if alias_hit:
                    cands = [
                        {"obs_id": d["obs_uuid"], "name": d["name"],
                         "aliases": d["aliases"],
                         "match": d["match"],
                         "definition_preview": (d["definition"] or "")[:80]}
                        for d in alias_hit
                    ]
                    return {
                        "warning": (
                            "概念熔断（别名命中）：新概念名已是某已有概念的名称或别名。"
                            "电力调度领域很多词有多个表述（如'发电计划'的别名'出力计划'），"
                            "这极可能是同一概念的不同叫法。"
                        ),
                        "candidates": cands,
                        "hint": (
                            "请决策：① 是同一概念 → 不要新建，改用 concept_update(obs_id=候选, ...) "
                            "补充该概念的 definition/misconception；"
                            "② 确实是不同概念（碰巧同名/同别名）→ 重新调用 concept_save 并传 force=true 放行。"
                        ),
                    }
                dup = self._nearest_concept_by_name(conn, name_vec, threshold=FUSE_THRESHOLD, limit=3)
                if dup:
                    cands = [
                        {"obs_id": d["obs_uuid"], "name": d["name"],
                         "aliases": d["aliases"],
                         "definition_preview": (d["definition"] or "")[:80],
                         "similarity": round(d["sim"], 3)}
                        for d in dup
                    ]
                    return {
                        "warning": (
                            "概念熔断（字面相似）：已存在概念名向量高度相似的概念（可能是字面重复/包含关系，"
                            "如'发电计划'与'发电机组出力计划'）。"
                        ),
                        "candidates": cands,
                        "hint": (
                            "请决策：① 是同一概念 → 用 concept_update(obs_id=候选, ...) 更新，"
                            "或补 aliases；② 确实是新概念 → 重新调用 concept_save 并传 force=true 放行。"
                        ),
                    }

            oid = uuid.uuid4().hex[:12]
            conn.execute(
                "INSERT INTO kg_concepts(obs_uuid, name, aliases, definition, misconception, source, content_hash) "
                "VALUES(?,?,?,?,?,?,?)",
                (oid, name, aliases, definition, misconception, source, content_hash)
            )
            fid = conn.execute("SELECT id FROM kg_concepts WHERE obs_uuid=?", (oid,)).fetchone()[0]
            conn.execute("INSERT INTO kg_vectors(rowid, embedding) VALUES (?, ?)", (fid, full_vec_bytes))
            conn.execute("INSERT INTO kg_name_vectors(rowid, embedding) VALUES (?, ?)", (fid, name_vec_bytes))
            conn.commit()
            return {"obs_id": oid, "action": "created", "id": fid}
        finally:
            conn.close()

    def _check_alias_collision(self, conn, new_name, limit=5):
        """FTS 别名熔断：检查 new_name 是否已是某概念的 name 或别名（字面精确命中）。
        拦截场景：'发电计划'已有 aliases='出力计划'，现要新建'出力计划' → 字面命中，拦。
        这是向量熔断拦不住的（BGE-small-zh 测'发电计划'vs'出力计划'仅 0.572），
        但 FTS 字面匹配能精准命中。
        返回命中概念列表，每项含 match 字段说明命中类型（name_match/alias_match）。"""
        if not new_name:
            return []
        safe = new_name.replace('"', '""')
        fts_query = f'"{safe}"'
        try:
            rows = conn.execute(
                "SELECT kc.obs_uuid, kc.name, kc.aliases, kc.definition "
                "FROM kg_concepts_fts JOIN kg_concepts kc ON kc.id = kg_concepts_fts.rowid "
                "WHERE kg_concepts_fts MATCH ? AND kc.deleted_at IS NULL "
                "AND (kc.name = ? OR ',' || kc.aliases || ',' LIKE '%,' || ? || ',%') "
                "LIMIT ?",
                (fts_query, new_name, new_name, limit)
            ).fetchall()
        except Exception as e:
            print(f"[kg_alias_collision] query failed: {e}", file=sys.stderr)
            return []

        results = []
        for r in rows:
            # 区分命中类型
            if r["name"] == new_name:
                match = "name_match（名称完全相同）"
            else:
                match = "alias_match（已是该概念的别名）"
            results.append({
                "obs_uuid": r["obs_uuid"], "name": r["name"],
                "aliases": r["aliases"], "definition": r["definition"], "match": match,
            })
        return results

    def _nearest_concept_by_name(self, conn, query_name_vec, threshold=FUSE_THRESHOLD, limit=3):
        """在 kg_name_vectors 找 query_name_vec 的近邻概念（强熔断专用）。
        只比对概念名向量（name+aliases），不受 definition 长文本稀释，
        同义概念名（"发电计划"vs"出力计划"）相似度可达 0.85+，熔断精准。
        返回 sim > threshold 的存活概念列表，按 sim 降序，最多 limit 条。"""
        try:
            v = json.dumps(list(query_name_vec)) if isinstance(query_name_vec, (list, tuple)) else query_name_vec
            rows = conn.execute(
                "SELECT kc.obs_uuid, kc.name, kc.aliases, kc.definition, "
                "vec_distance_cosine(knv.embedding, ?) as distance "
                "FROM kg_name_vectors knv JOIN kg_concepts kc ON knv.rowid = kc.id "
                "WHERE kc.deleted_at IS NULL "
                "ORDER BY distance LIMIT ?",
                (v, max(limit * 3, 10))
            ).fetchall()
        except Exception as e:
            print(f"[kg_nearest_by_name] query failed, fuse disabled: {e}", file=sys.stderr)
            return []

        results = []
        for r in rows:
            sim = 1.0 - float(r["distance"])
            if sim <= threshold:
                continue
            results.append({
                "obs_uuid": r["obs_uuid"], "name": r["name"],
                "aliases": r["aliases"], "definition": r["definition"], "sim": sim,
            })
        results.sort(key=lambda x: x["sim"], reverse=True)
        return results[:limit]

    # ==================== 概念卡更新/删除/查询 ====================

    def update_concept(self, obs_id, **fields):
        """局部更新概念卡。支持 name/definition/misconception/aliases/source/verified。
        改了 name/aliases/definition/misconception 任一 → 重算向量。"""
        if not obs_id:
            return {"error": "obs_id is required"}
        allowed = {"name", "definition", "misconception", "aliases", "source", "verified"}
        sets, params = [], []
        for col in allowed:
            if col in fields and fields[col] is not None:
                sets.append(f"{col}=?")
                params.append(fields[col])
        if not sets:
            return {"error": "nothing to update"}

        conn = self._get_conn()
        try:
            row = conn.execute("SELECT id FROM kg_concepts WHERE obs_uuid=?", (obs_id,)).fetchone()
            if not row:
                return {"error": "not found"}
            fid = row["id"]

            sets.append("updated_at=CURRENT_TIMESTAMP")
            params.append(fid)
            conn.execute(f"UPDATE kg_concepts SET {', '.join(sets)} WHERE id=?", params)

            # 重算向量与 hash（若文本字段变了）
            text_cols = {"name", "aliases", "definition", "misconception"}
            changed = text_cols & set(fields.keys())
            if changed:
                row = conn.execute(
                    "SELECT name, aliases, definition, misconception FROM kg_concepts WHERE id=?",
                    (fid,)
                ).fetchone()
                name, aliases, definition, misconception = (
                    row["name"], row["aliases"], row["definition"], row["misconception"]
                )
                content_hash = hashlib.sha256(
                    (name + definition + misconception + aliases).encode("utf-8")
                ).hexdigest()[:16]
                conn.execute("UPDATE kg_concepts SET content_hash=? WHERE id=?", (content_hash, fid))
                # 全文向量（任意文本字段变了都要重算）
                full_text = " ".join([x for x in [name, aliases, definition, misconception] if x])
                full_vec = self.embedder.embed(full_text)
                conn.execute("DELETE FROM kg_vectors WHERE rowid=?", (fid,))
                conn.execute(
                    "INSERT INTO kg_vectors(rowid, embedding) VALUES (?, ?)",
                    (fid, np.array(full_vec, dtype=np.float32).tobytes())
                )
                # name 向量（仅 name 变了才需要重算，但为简单起见，文本字段变了都重算）
                name_vec = self.embedder.embed(name)
                conn.execute("DELETE FROM kg_name_vectors WHERE rowid=?", (fid,))
                conn.execute(
                    "INSERT INTO kg_name_vectors(rowid, embedding) VALUES (?, ?)",
                    (fid, np.array(name_vec, dtype=np.float32).tobytes())
                )
            conn.commit()
            return {"obs_id": obs_id, "action": "updated"}
        finally:
            conn.close()

    def delete_concept(self, obs_id, hard=False):
        """删除概念卡。默认软删除（deleted_at 标记，可恢复）；hard=true 物理删除。
        物理删除会级联清理 kg_edges 中引用该概念名的边（概念名是边的标识）。"""
        if not obs_id:
            return {"error": "obs_id is required"}
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT id, name FROM kg_concepts WHERE obs_uuid=?", (obs_id,)
            ).fetchone()
            if not row:
                return {"error": "not found"}
            fid, cname = row["id"], row["name"]

            if hard:
                # 先收边名，再删概念（触发器清向量），最后清引用此名的边
                conn.execute("DELETE FROM kg_concepts WHERE obs_uuid=?", (obs_id,))
                conn.execute(
                    "DELETE FROM kg_edges WHERE src_concept=? OR dst_concept=?",
                    (cname, cname)
                )
            else:
                conn.execute(
                    "UPDATE kg_concepts SET deleted_at=CURRENT_TIMESTAMP WHERE obs_uuid=?",
                    (obs_id,)
                )
            conn.commit()
            return {"obs_id": obs_id, "action": "hard_deleted" if hard else "soft_deleted",
                    "concept_name": cname}
        finally:
            conn.close()

    def get_concept(self, obs_id=None, name=None):
        """按 obs_id 或 name 取单张概念卡完整内容。"""
        if not obs_id and not name:
            return {"error": "obs_id or name is required"}
        conn = self._get_conn()
        try:
            if obs_id:
                row = conn.execute(
                    "SELECT obs_uuid, name, aliases, definition, misconception, source, "
                    "verified, created_at, updated_at FROM kg_concepts "
                    "WHERE obs_uuid=? AND deleted_at IS NULL",
                    (obs_id,)
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT obs_uuid, name, aliases, definition, misconception, source, "
                    "verified, created_at, updated_at FROM kg_concepts "
                    "WHERE name=? AND deleted_at IS NULL",
                    (name,)
                ).fetchone()
            if not row:
                return {"error": "not found"}
            return dict(row)
        finally:
            conn.close()

    def list_concepts(self, verified=None, limit=200):
        """列出概念卡（摘要）。verified=None 全部，0=待核实，1=已核实。"""
        conn = self._get_conn()
        try:
            sql = ("SELECT obs_uuid, name, aliases, "
                   "substr(definition,1,100) as definition_preview, "
                   "substr(misconception,1,100) as misconception_preview, "
                   "verified, source, updated_at "
                   "FROM kg_concepts WHERE deleted_at IS NULL")
            params = []
            if verified is not None:
                sql += " AND verified=?"
                params.append(1 if verified else 0)
            sql += " ORDER BY updated_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ==================== 边（关系）管理 ====================

    def save_edge(self, src_concept, dst_concept, relation_type, weight=1.0, note=""):
        """建立概念间的关系边。校验：两端概念存在 + 关系类型合法。
        UNIQUE(src,dst,type) 约束防重复边；同对概念可有多条不同类型边。"""
        if not src_concept or not dst_concept:
            return {"error": "src_concept and dst_concept are required"}
        if relation_type not in VALID_RELATIONS:
            return {"error": f"invalid relation_type: {relation_type}",
                    "valid_types": sorted(VALID_RELATIONS)}
        if src_concept == dst_concept:
            return {"error": "src_concept and dst_concept must differ"}

        conn = self._get_conn()
        try:
            # 校验两端概念存在
            for c in (src_concept, dst_concept):
                exists = conn.execute(
                    "SELECT 1 FROM kg_concepts WHERE name=? AND deleted_at IS NULL", (c,)
                ).fetchone()
                if not exists:
                    return {"error": f"concept not found: {c}"}

            try:
                cur = conn.execute(
                    "INSERT INTO kg_edges(src_concept, dst_concept, relation_type, weight, note) "
                    "VALUES(?,?,?,?,?)",
                    (src_concept, dst_concept, relation_type, weight, note)
                )
                conn.commit()
                return {"edge_id": cur.lastrowid, "action": "created",
                        "src": src_concept, "dst": dst_concept, "relation_type": relation_type}
            except sqlite3.IntegrityError:
                # UNIQUE(src,dst,type) 冲突 → 已存在同款边，幂等返回
                conn.rollback()
                return {"action": "exists", "src": src_concept, "dst": dst_concept,
                        "relation_type": relation_type,
                        "hint": "该关系已存在（同方向同类型唯一）。如需改 weight/note 请用 edge_delete 后重建。"}
        finally:
            conn.close()

    def delete_edge(self, edge_id=None, src_concept=None, dst_concept=None, relation_type=None):
        """删除边。按 edge_id，或按 (src,dst,type) 三元组定位。"""
        conn = self._get_conn()
        try:
            if edge_id:
                cur = conn.execute("DELETE FROM kg_edges WHERE id=?", (edge_id,))
            else:
                if not (src_concept and dst_concept and relation_type):
                    return {"error": "provide edge_id, or (src_concept+dst_concept+relation_type)"}
                cur = conn.execute(
                    "DELETE FROM kg_edges WHERE src_concept=? AND dst_concept=? AND relation_type=?",
                    (src_concept, dst_concept, relation_type)
                )
            conn.commit()
            return {"action": "deleted", "affected": cur.rowcount}
        finally:
            conn.close()

    def list_relations(self):
        """列出 6 种关系类型及说明，供用户建边时参考。"""
        return {
            "derives_from": "派生自：A 由 B 派生（如'日前发电计划'派生自'发电计划'）",
            "constrains": "约束：A 约束 B（如'断面限额'约束'可调能力'）",
            "aggregates": "聚合：A 聚合 B（如'虚拟电厂'聚合'储能'）",
            "depends_on": "依赖：A 依赖 B（如'发电计划整合'依赖'发电计划'）",
            "synonym_of": "同义：A 与 B 同义（如'出力计划'同义'发电计划'）",
            "contradicts": "矛盾：A 与 B 矛盾（纠错用，如'台账CRUD'矛盾'台账实例化'）",
        }
