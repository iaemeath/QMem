#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
领域知识图谱 单元测试（unittest，零依赖，内网可用）
覆盖 4 类：概念熔断 / 关系边 / 图遍历检索 / MCP 工具分发

运行:
  cd D:\\cly-marketplace\\qmem\\mcp\\domain-kg
  python -m unittest kg.test_kg -v
或:
  python kg/test_kg.py
"""
import os
import sys
import json
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))        # domain-kg/kg/
_PYDIR = os.path.dirname(_HERE)                            # domain-kg/
sys.path.insert(0, _PYDIR)

import sqlite3
from kg.kg_store import KGStore, VALID_RELATIONS
from kg.kg_traversal import KGTraversal


def _build_db():
    """建一个临时库并执行 kg_schema.sql，返回 (db_path, conn_for_assert)"""
    fd, db_path = tempfile.mkstemp(suffix=".db", prefix="kg_ut_")
    os.close(fd)
    conn = sqlite3.connect(db_path)
    conn.enable_load_extension(True)
    import sqlite_vec
    sqlite_vec.load(conn)
    with open(os.path.join(_PYDIR, "kg_schema.sql"), encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()
    return db_path


class _KgBase(unittest.TestCase):
    """公共 fixture：每个测试一个全新临时库 + 3 个种子概念 + 2 条边"""

    def setUp(self):
        self.db_path = _build_db()
        self.store = KGStore(self.db_path)
        self.traversal = KGTraversal(self.db_path, embedder=self.store.embedder)
        self._seed()

    def tearDown(self):
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    def _seed(self):
        """种子数据：发电计划(含别名出力计划)/可调能力/断面 + 2 边"""
        r = self.store.save_concept(
            name="发电计划",
            definition="发电机组在未来某时段内的出力安排，是电网调度的核心依据。",
            misconception="发电计划不是属性字段，是独立核心业务概念。",
            aliases="出力计划,计划曲线", source="电力调度原理")
        self.plan_id = r["obs_id"]
        self.store.save_concept(
            name="可调能力",
            definition="发电侧或负荷侧在规定时间内可提供的上调/下调容量。",
            aliases="调节能力,备用容量", source="电力市场基础")
        self.store.save_concept(
            name="断面",
            definition="输电断面是一组潮流方向相同、电气距离相近的输电线路集合。",
            aliases="输电断面", source="电力系统分析")
        self.store.save_edge("断面", "可调能力", "constrains", note="断面限额约束可调能力上限")
        self.store.save_edge("发电计划", "可调能力", "depends_on", note="计划编制依赖可调能力")


# ============================================================
# 第一类：概念熔断（双层）
# ============================================================
class TestConceptFuse(_KgBase):

    def test_alias_collision_blocked(self):
        """FTS 别名熔断：写已有概念的别名 → 必须拦"""
        r = self.store.save_concept(name="出力计划", definition="出力安排曲线")
        self.assertIn("warning", r, "出力计划是发电计划的别名，应被 FTS 熔断拦下")
        self.assertEqual(len(r["candidates"]), 1)
        self.assertEqual(r["candidates"][0]["name"], "发电计划")
        self.assertIn("alias", r["candidates"][0]["match"])

    def test_literal_similarity_blocked(self):
        """向量字面熔断：写与已有概念名高度重叠的词（sim>0.75）→ 拦"""
        r = self.store.save_concept(name="发电机组出力计划", definition="机组出力安排")
        self.assertIn("warning", r, "发电机组出力计划与发电计划字面重叠(0.784)，应被向量熔断拦下")
        self.assertGreaterEqual(r["candidates"][0]["similarity"], 0.75)

    def test_different_concept_not_blocked(self):
        """不同概念不误杀：可调能力/断面已存在，再写个完全不相关的应放行"""
        r = self.store.save_concept(name="虚拟电厂", definition="聚合分布式资源参与电网调度的实体。")
        self.assertEqual(r.get("action"), "created", "虚拟电厂与种子概念无关，不应被熔断")

    def test_force_bypasses_fuse(self):
        """force=true 绕过熔断（用户确认确为新概念时）"""
        r = self.store.save_concept(name="出力计划", definition="不同语境下的出力计划", force=True)
        self.assertEqual(r.get("action"), "created", "force=true 应绕过熔断直接创建")

    def test_name_upsert_updates_existing(self):
        """同名概念走 upsert（更新而非新建/熔断）"""
        r = self.store.save_concept(
            name="发电计划",
            definition="更新后的定义。",
            misconception="更新的误解点。", aliases="出力计划")
        self.assertEqual(r.get("action"), "updated")
        self.assertEqual(r.get("via"), "name_upsert")
        # 验证内容确实更新了
        c = self.store.get_concept(obs_id=self.plan_id)
        self.assertIn("更新后", c["definition"])

    def test_empty_name_rejected(self):
        r = self.store.save_concept(name="", definition="x")
        self.assertIn("error", r)


# ============================================================
# 第二类：关系边管理
# ============================================================
class TestEdges(_KgBase):

    def test_valid_edge_created(self):
        """合法关系建边成功"""
        r = self.store.save_edge("发电计划", "断面", "depends_on", note="计划受断面约束")
        self.assertEqual(r.get("action"), "created")

    def test_all_six_relations_accepted(self):
        """6 种关系类型都被接受（在两个概念间建不同类型的边）"""
        # 补充概念供 6 种关系测试。注意：概念名要与种子概念字面差异够大，
        # 否则会被向量熔断拦下（如"日前发电计划"与"发电计划"字面重叠会被拦）。
        # 用 force=True 确保这些语义上确实不同的概念能建起来。
        self.store.save_concept(name="储能装置", definition="储能设备", force=True)
        self.store.save_concept(name="VPP虚拟电厂", definition="聚合分布式资源", force=True)
        self.store.save_concept(name="系统负荷", definition="电网总用电负荷", force=True)
        self.store.save_concept(name="检修计划", definition="设备检修安排", force=True)
        cases = [
            # 每种关系类型一条，src/dst 选字面不重叠的概念对
            ("VPP虚拟电厂", "发电计划", "derives_from"),   # 派生
            ("VPP虚拟电厂", "储能装置", "aggregates"),      # 聚合
            ("发电计划", "可调能力", "depends_on"),         # 依赖（种子已建，幂等 exists 也算通过）
            ("断面", "可调能力", "constrains"),             # 约束（种子已建）
            ("系统负荷", "检修计划", "synonym_of"),         # 同义（此处仅为验证类型可接受）
            ("检修计划", "发电计划", "contradicts"),        # 矛盾
        ]
        for src, dst, rel in cases:
            r = self.store.save_edge(src, dst, rel)
            self.assertIn(r.get("action"), ("created", "exists"),
                          f"{src}-{rel}->{dst} 应成功或幂等，实际: {r}")

    def test_invalid_relation_rejected(self):
        """非法关系类型被拒，且返回合法类型清单"""
        r = self.store.save_edge("发电计划", "可调能力", "is_a")
        self.assertIn("error", r)
        self.assertIn("valid_types", r)
        self.assertEqual(set(r["valid_types"]), VALID_RELATIONS)

    def test_nonexistent_concept_rejected(self):
        """引用不存在的概念建边被拒"""
        r = self.store.save_edge("不存在的概念", "可调能力", "constrains")
        self.assertIn("error", r)

    def test_self_loop_rejected(self):
        """自环边被拒"""
        r = self.store.save_edge("发电计划", "发电计划", "derives_from")
        self.assertIn("error", r)

    def test_duplicate_edge_idempotent(self):
        """同方向同类型重复边：幂等返回 exists（UNIQUE 约束）"""
        r1 = self.store.save_edge("发电计划", "可调能力", "depends_on")
        self.assertEqual(r1.get("action"), "exists", "种子已建过这条边，应幂等")

    def test_delete_edge_by_triple(self):
        """按 (src,dst,type) 三元组删边"""
        r = self.store.delete_edge(src_concept="发电计划", dst_concept="可调能力",
                                    relation_type="depends_on")
        self.assertEqual(r.get("affected"), 1)
        # 再删应 affected=0
        r2 = self.store.delete_edge(src_concept="发电计划", dst_concept="可调能力",
                                     relation_type="depends_on")
        self.assertEqual(r2.get("affected"), 0)

    def test_list_relations_returns_six(self):
        """list_relations 返回 6 种关系说明"""
        r = self.store.list_relations()
        self.assertEqual(len(r), 6)
        for rel in VALID_RELATIONS:
            self.assertIn(rel, r)


# ============================================================
# 第三类：检索 + 图遍历
# ============================================================
class TestTraversal(_KgBase):

    def test_recall_hits_concept(self):
        """RRF 检索命中概念"""
        r = self.traversal.recall("发电", min_similarity=0.3, limit=5)
        self.assertGreaterEqual(r["total"], 1)
        names = [x["name"] for x in r["results"]]
        self.assertIn("发电计划", names)

    def test_recall_returns_definition_and_misconception(self):
        """检索结果含 definition + misconception 双字段"""
        r = self.traversal.recall("发电", min_similarity=0.3, limit=5)
        hit = next(x for x in r["results"] if x["name"] == "发电计划")
        self.assertTrue(hit["definition"])
        self.assertTrue(hit["misconception"])

    def test_recall_empty_query_rejected(self):
        r = self.traversal.recall("")
        self.assertIn("error", r)

    def test_neighbors_returns_subgraph(self):
        """图遍历：以发电计划为中心 depth=2，应返回子图（含邻居+边）"""
        r = self.traversal.neighbors(name="发电计划", depth=2)
        self.assertEqual(r["center"], "发电计划")
        node_names = [n["name"] for n in r["nodes"]]
        self.assertIn("发电计划", node_names)
        self.assertIn("可调能力", node_names)
        # 断面通过可调能力连过来（depth=2 可达）
        self.assertIn("断面", node_names)
        self.assertGreaterEqual(r["edge_count"], 2)

    def test_neighbors_by_obs_id(self):
        """按 obs_id 遍历与按 name 等价"""
        r = self.traversal.neighbors(obs_id=self.plan_id, depth=1)
        self.assertEqual(r["center"], "发电计划")
        # depth=1 只到直接邻居（可调能力），不到断面
        node_names = [n["name"] for n in r["nodes"]]
        self.assertIn("可调能力", node_names)
        self.assertNotIn("断面", node_names)

    def test_neighbors_relation_filter(self):
        """关系类型过滤：只走 constrains 时，发电计划无 constrains 边，应只返回自己"""
        r = self.traversal.neighbors(name="发电计划", depth=2, relation_types=["constrains"])
        node_names = [n["name"] for n in r["nodes"]]
        # 发电计划没有 constrains 关系，过滤后只返回中心自己
        self.assertEqual(node_names, ["发电计划"])

    def test_neighbors_nonexistent_concept(self):
        r = self.traversal.neighbors(name="不存在的概念")
        self.assertIn("error", r)

    def test_neighbors_depth_capped(self):
        """depth>5 被截到 5（防爆炸）"""
        r = self.traversal.neighbors(name="发电计划", depth=99)
        self.assertEqual(r["depth"], 5)


# ============================================================
# 第四类：MCP 工具分发（V4.0：通过 DomainMCP.handle_request 走真实 JSON-RPC 链路）
# ============================================================
class TestMCPDispatch(unittest.TestCase):
    """启动真实 DomainMCP server（领域知识图谱独立进程，V4.0 从 QMem 拆出）。
    initialize 建表到生产 domain_knowledge.db（IF NOT EXISTS 幂等，不破坏已有数据）。
    验证 10 个 concept_*/edge_* 工具能被 tools/list 列出并被 tools/call 正确分发。"""

    @classmethod
    def setUpClass(cls):
        from server import DomainMCP
        cls.srv = DomainMCP()
        # initialize 建表（幂等，不破坏已有数据）
        cls.srv.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})

    def _call(self, name, args):
        """调用 MCP 工具，返回解析后的 dict"""
        r = self.srv.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                      "params": {"name": name, "arguments": args}})
        self.assertNotIn("error", r, f"tools/call {name} 报错: {r}")
        return json.loads(r["result"]["content"][0]["text"])

    def test_all_ten_tools_registered(self):
        """tools/list 包含全部 10 个领域图谱工具"""
        r = self.srv.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = {t["name"] for t in r["result"]["tools"]}
        expected = {"concept_save", "concept_update", "concept_delete", "concept_get",
                    "concept_list", "edge_save", "edge_delete", "list_relations",
                    "concept_recall", "concept_neighbors"}
        missing = expected - names
        self.assertFalse(missing, f"未注册的工具: {missing}")

    def test_concept_save_recall_roundtrip(self):
        """concept_save 写入（带熔断 upsert 语义）→ concept_recall 能召回"""
        # 用一个本轮测试独有的概念名，避免和生产种子冲突；force 绕过与近邻的相似
        cname = "测试概念_MCP分发验证"
        r = self._call("concept_save", {"name": cname, "definition": "MCP分发测试用",
                                         "misconception": "测试误解点", "force": True})
        self.assertEqual(r.get("action", r.get("via", "")) in ("created", "name_upsert"), True)
        # recall 召回
        r2 = self._call("concept_recall", {"query": cname, "limit": 5, "min_similarity": 0.3})
        names = [x["name"] for x in r2["results"]]
        self.assertIn(cname, names)
        # 清理：软删
        self._call("concept_delete", {"obs_id": r["obs_id"]})

    def test_concept_save_fuse_returns_candidates(self):
        """concept_save 熔断时返回 candidates（走 MCP 分发，不止直接调用）"""
        # V4.0：自建一个带别名的概念，再写其别名验证 FTS 熔断（不依赖生产数据状态）
        base = "测试基概念_MCP熔断验证"
        alias = "测试基概念别名"
        # 先建基概念（force 绕过与生产概念相似）
        self._call("concept_save", {"name": base, "definition": "熔断测试基概念",
                                     "aliases": alias, "force": True})
        try:
            # 写别名应被 FTS 熔断拦下
            r = self._call("concept_save", {"name": alias, "definition": "别名熔断MCP测试"})
            self.assertIn("warning", r)
            self.assertTrue(r["candidates"])
        finally:
            # 清理基概念（软删）
            got = self._call("concept_get", {"name": base})
            if "obs_uuid" in got:
                self._call("concept_delete", {"obs_id": got["obs_uuid"]})

    def test_concept_get_returns_full_card(self):
        """concept_get 返回完整 definition+misconception"""
        # V4.0：自建一个带 misconception 的概念，验证 get 返回双字段（不依赖生产数据）
        cname = "测试概念_get验证"
        r = self._call("concept_save", {"name": cname, "definition": "get测试定义全文",
                                         "misconception": "get测试误解点全文", "force": True})
        try:
            got = self._call("concept_get", {"obs_id": r["obs_id"]})
            self.assertEqual(got["name"], cname)
            self.assertTrue(got["definition"])
            self.assertTrue(got["misconception"])
        finally:
            self._call("concept_delete", {"obs_id": r["obs_id"]})

    def test_concept_list_filter_verified(self):
        """concept_list 按 verified 过滤"""
        r_all = self._call("concept_list", {})
        self.assertIsInstance(r_all, list)
        self.assertGreater(len(r_all), 0)
        r_pending = self._call("concept_list", {"verified": 0})
        for c in r_pending:
            self.assertEqual(c["verified"], 0)

    def test_edge_save_and_list_relations(self):
        """edge_save 建边 + list_relations 返回 6 种关系"""
        rels = self._call("list_relations", {})
        self.assertEqual(len(rels), 6)
        # 建一条种子没建过的边（发电计划 constrains 断面）
        r = self._call("edge_save", {"src_concept": "发电计划", "dst_concept": "断面",
                                      "relation_type": "constrains", "note": "MCP测试边"})
        self.assertIn(r.get("action"), ("created", "exists"))
        # 清理这条测试边
        self._call("edge_delete", {"src_concept": "发电计划", "dst_concept": "断面",
                                    "relation_type": "constrains"})

    def test_edge_save_invalid_relation_via_mcp(self):
        """MCP 分发下非法关系类型被拒"""
        r = self._call("edge_save", {"src_concept": "发电计划", "dst_concept": "可调能力",
                                      "relation_type": "is_a"})
        self.assertIn("error", r)

    def test_concept_neighbors_via_mcp(self):
        """concept_neighbors 通过 MCP 分发返回子图"""
        r = self._call("concept_neighbors", {"name": "发电计划", "depth": 2})
        self.assertEqual(r["center"], "发电计划")
        self.assertGreaterEqual(r["node_count"], 1)
        names = [n["name"] for n in r["nodes"]]
        self.assertIn("发电计划", names)

    def test_concept_update_verified_flag(self):
        """concept_update 改 verified 标志"""
        # 找一个待核实的概念，标已核实，再改回来（避免污染生产数据状态）
        c = self._call("concept_get", {"name": "断面"})
        orig = c["verified"]
        try:
            self._call("concept_update", {"obs_id": c["obs_uuid"], "verified": 1})
            c2 = self._call("concept_get", {"obs_id": c["obs_uuid"]})
            self.assertEqual(c2["verified"], 1)
        finally:
            # 还原
            self._call("concept_update", {"obs_id": c["obs_uuid"], "verified": orig})


if __name__ == "__main__":
    unittest.main(verbosity=2)
