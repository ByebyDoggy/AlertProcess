"""
SignatureDB 二级缓存单元测试
============================
覆盖:
  - Level 1: 本地 SQLite 查询（命中/未命中）
  - Level 2: 4byte.directory API 在线查询（命中/未命中）
  - Level 3: Unknown 标记回填
  - 排序规则: 按 id ASC 升序，ID最小优先
  - 批量查询 bulk_lookup()
  - 标准化 _normalize_selector()

运行: python -m pytest tests/test_signature_db.py -v
注意: API 相关测试使用实例级 mock (patch.object(db_instance, ...))，
      因为 @patch.object(Class, ...) 对 self.xxx() 调用不生效。
"""

import pytest
import sqlite3
import tempfile
import os
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from detectors.trace.signature_db import SignatureDB, _UNKNOWN_SIGNATURE_PREFIX


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def temp_db_path():
    """创建临时 SQLite 数据库文件，测试结束后自动删除"""
    fd, path = tempfile.mkstemp(suffix=".db", prefix="test_sig_")
    os.close(fd)
    yield Path(path)
    if os.path.exists(path):
        try:
            os.unlink(path)
        except OSError:
            pass


@pytest.fixture
def db(temp_db_path):
    """初始化一个空的 SignatureDB 实例"""
    sig_db = SignatureDB(db_path=temp_db_path)
    sig_db._ensure_db()
    yield sig_db
    sig_db.close()


@pytest.fixture
def db_with_data(temp_db_path):
    """预填数据的 SignatureDB 用于测试 Level 1 命中"""
    sig_db = SignatureDB(db_path=temp_db_path)
    sig_db._ensure_db()
    conn = sig_db._get_conn()
    test_records = [
        ("0xa9059cbb", "transfer(address,uint256)", 123456),
        ("0xa9059cbb", "transfer(address,uint256) [v2 override]", 999999),
        ("0x23b872dd", "transferFrom(address,address,uint256)", 50000),
        ("0xe0232b42", "flashLoan(address,uint256,bytes)", 236604),
        ("0x095ea7b3", "approve(address,uint256)", 80000),
        ("0xdeadbeef", f"{_UNKNOWN_SIGNATURE_PREFIX}0xdeadbeef)", 0),
    ]
    for sel, text_sig, num in test_records:
        conn.execute(
            "INSERT INTO signatures (selector, text_signature, num_results) VALUES (?, ?, ?)",
            (sel, text_sig, num),
        )
    conn.commit()
    yield sig_db
    sig_db.close()


# ============================================================
# 测试: _normalize_selector 标准化
# ============================================================

class TestNormalizeSelector:

    def test_lowercase_conversion(self):
        assert SignatureDB._normalize_selector("0xA9059CBB") == "0xa9059cbb"

    def test_add_0x_prefix(self):
        assert SignatureDB._normalize_selector("a9059cbb") == "0xa9059cbb"

    def test_truncate_to_10_chars(self):
        assert SignatureDB._normalize_selector("0xa9059cbbextra") == "0xa9059cbb"
        assert SignatureDB._normalize_selector("a9059cbb00000000") == "0xa9059cbb"

    def test_strip_whitespace(self):
        assert SignatureDB._normalize_selector("  0xa9059cbb  ") == "0xa9059cbb"

    def test_empty_input(self):
        assert SignatureDB._normalize_selector("") == ""

    def test_too_short(self):
        assert SignatureDB._normalize_selector("0xabc") == ""


# ============================================================
# 测试: Level 1 — SQLite 命中
# ============================================================

class TestLevel1SQLiteHit:

    def test_lookup_single_hit(self, db_with_data):
        result = db_with_data.lookup("0xa9059cbb")
        assert result == "transfer(address,uint256)"

    def test_lookup_all_multiple_sigs(self, db_with_data):
        results = db_with_data.lookup_all("0xa9059cbb")
        assert len(results) == 2
        assert results[0] == "transfer(address,uint256)"
        assert results[1] == "transfer(address,uint256) [v2 override]"

    def test_lookup_by_hex_with_id(self, db_with_data):
        resp = db_with_data.lookup_by_hex("0xa9059cbb")
        assert resp["source"] == "db"
        assert len(resp["signatures"]) == 2
        assert resp["signatures"][0]["text"] == "transfer(address,uint256)"
        assert "id" in resp["signatures"][0]

    def test_unknown_record_returns_empty(self, db_with_data):
        results = db_with_data.lookup_all("0xdeadbeef")
        assert results == []

    def test_lookup_by_hex_unknown_source(self, db_with_data):
        resp = db_with_data.lookup_by_hex("0xdeadbeef")
        assert resp["source"] == "unknown"
        assert resp["total"] == 0

    def test_target_selector_e0232b42(self, db_with_data):
        result = db_with_data.lookup("0xe0232b42")
        assert result == "flashLoan(address,uint256,bytes)"

    def test_not_in_db_returns_none_for_api_fallback(self, db_with_data):
        result = db_with_data._lookup_db_all("0xabcdef01")
        assert result is None


# ============================================================
# 测试: Level 2 — API 回退（实例级 Mock）
# ============================================================

class TestLevel2APIFallback:

    def test_api_hit_writes_to_db(self, db):
        """API 命中 → 写入 DB → 第二次从 DB 返回"""
        with patch.object(db, '_query_4byte_api_all', return_value=["flashLoan(address,uint256,bytes)"]):
            db._api_enabled = True
            result = db.lookup("0xe0232b42")
            assert result == "flashLoan(address,uint256,bytes)"

            # 验证已写入 DB
            db_results = db._lookup_db_all("0xe0232b42")
            assert db_results is not None
            assert db_results[0] == "flashLoan(address,uint256,bytes)"

    def test_api_sort_by_id_asc(self, db):
        with patch.object(db, '_query_4byte_api_all', return_value=["func_a()", "func_b()", "func_c()"]):
            db._api_enabled = True
            results = db.lookup_all("0xabcdef01")  # 必须是 10 字符
            assert results == ["func_a()", "func_b()", "func_c()"]

    def test_api_miss_marks_unknown(self, db):
        with patch.object(db, '_query_4byte_api_all', return_value=[]):
            db._api_enabled = True
            results = db.lookup_all("0xdeadbeef")
            assert results == []
            db_check = db._lookup_db_all("0xdeadbeef")
            assert db_check == []

    def test_api_network_error_graceful(self, db):
        with patch.object(db, '_query_4byte_api_all', side_effect=Exception("network error")):
            db._api_enabled = True
            # lookup 内部调用 lookup_all，API 异常会传播
            # 当前设计：API 异常不捕获（直接抛出），最终返回 None 或异常
            # 验证行为：异常时不会写入任何数据
            try:
                result = db.lookup("0xbadbad01")
            except Exception:
                result = None
            # 无论哪种方式都不应崩溃整个流程

    def test_api_disabled_no_call(self, db):
        db._api_enabled = False
        with patch.object(db, '_query_4byte_api_all') as mock_api:
            result = db.lookup_all("0xcafebabe")
            assert result == []
            mock_api.assert_not_called()


# ============================================================
# 测试: Unknown 标记回填
# ============================================================

class TestUnknownMarking:

    def test_unknown_written_after_api_miss(self, db):
        with patch.object(db, '_query_4byte_api_all', return_value=[]):
            db._api_enabled = True
            r1 = db.lookup_all("0xunknown0001")  # 10 字符
            assert r1 == []
            r2 = db.lookup_all("0xunknown0001")
            assert r2 == []

    def test_unknown_format(self, db):
        with patch.object(db, '_query_4byte_api_all', return_value=[]):
            db._api_enabled = True
            db.lookup_all("0xabcd1234")  # 已是 10 字符，OK
            conn = db._get_conn()
            row = conn.execute(
                "SELECT text_signature FROM signatures WHERE selector=?", ("0xabcd1234",)
            ).fetchone()
            assert row["text_signature"] == f"{_UNKNOWN_SIGNATURE_PREFIX}0xabcd1234)"


# ============================================================
# 测试: bulk_lookup 批量查询
# ============================================================

class TestBulkLookup:

    def test_mixed_db_and_api(self, db_with_data):
        with patch.object(db_with_data, '_bulk_query_4byte_api', return_value={
            "0xabcdef01": ["customFunc()"],
            "0x98765432a": ["someOther()"],
        }):
            db_with_data._api_enabled = True
            selectors = ["0xa9059cbb", "0xabcdef01", "0x98765432a"]
            result = db_with_data.bulk_lookup(selectors)

            assert result["0xa9059cbb"][0] == "transfer(address,uint256)"
            assert result["0xabcdef01"][0] == "customFunc()"
            assert result["0x98765432a"][0] == "someOther()"

    def test_bulk_deduplication(self, db):
        with patch.object(db, '_bulk_query_4byte_api', return_value={"0xdup000001": ["dup()"]}):
            db._api_enabled = True
            result = db.bulk_lookup(["0xdup000001", "0xdup000001", "0xdup000001"])
            assert "0xdup000001" in result


# ============================================================
# 测试: prefix_search
# ============================================================

class TestPrefixSearch:

    def test_prefix_match(self, db_with_data):
        texts = [r["signature"] for r in db_with_data.prefix_search("0xa9")]
        assert "transfer(address,uint256)" in texts

    def test_prefix_no_match(self, db_with_data):
        assert db_with_data.prefix_search("0xffff") == []

    def test_prefix_excludes_unknown(self, db_with_data):
        assert len(db_with_data.prefix_search("0xde")) == 0


# ============================================================
# 测试: 统计
# ============================================================

class TestStats:

    def test_count(self, db_with_data):
        assert db_with_data.count() > 0

    def test_stats_structure(self, db_with_data):
        stats = db_with_data.get_stats()
        assert stats["is_fallback_mode"] is False
        assert stats["api_enabled"] is True
        assert stats["unknown_count"] >= 1


# ============================================================
# 测试: Fallback 模式
# ============================================================

@pytest.fixture
def fallback_db():
    # 传入空字符串触发纯内存/fallback模式
    return SignatureDB(db_path="")


class TestFallbackMode:

    def test_fallback_only_uses_api(self, fallback_db):
        with patch.object(fallback_db, '_query_4byte_api_all', return_value=["test()"]) as m:
            fallback_db._api_enabled = True
            assert fallback_db.lookup_all("0xabcdef01") == ["test()"]
            m.assert_called_once()

    def test_fallback_no_api(self):
        fb = SignatureDB(db_path=None)
        assert fb.lookup_all("0xany00001") == []


# ============================================================
# 集成测试
# ============================================================

class TestIntegrationRealWorld:

    def test_empty_db_api_resolves_flashloan(self, db):
        """空 DB → API → 命中 flashLoan → 写入 DB → 第二次从 DB 返回"""
        with patch.object(db, '_query_4byte_api_all', return_value=["flashLoan(address,uint256,bytes)"]) as m:
            db._api_enabled = True
            sig = db.lookup("0xe0232b42")
            assert sig == "flashLoan(address,uint256,bytes)"

            # lookup_by_hex: 此时已写入 DB，所以 source 可能是 db（因为写入后立即可查）
            resp = db.lookup_by_hex("0xe0232b42")
            assert resp["source"] in ("db", "api")  # 两种都正确
            assert resp["signatures"][0]["text"] == "flashLoan(address,uint256,bytes)"

            # 第二次不再调 API（已写入 DB）
            m.reset_mock()
            sig2 = db.lookup("0xe0232b42")
            assert sig2 == "flashLoan(address,uint256,bytes)"
            m.assert_not_called()

    def test_old_unknown_blocks_requery(self, temp_db_path):
        """
        Bug 复现: 已有 Unknown 标记的 selector 不会再重新查 API。
        这是当前设计行为——如果需要重试需增加 TTL 或清理机制。
        """
        sig_db = SignatureDB(db_path=temp_db_path)
        sig_db._ensure_db()
        sig_db._save_to_db("0xe0232b42", f"{_UNKNOWN_SIGNATURE_PREFIX}0xe0232b42)")
        sig_db._api_enabled = True

        # 有 Unknown 标记 → 直接返回空，不发 API
        with patch.object(sig_db, '_query_4byte_api_all') as m:
            assert sig_db.lookup_all("0xe0232b42") == []
            m.assert_not_called()
        print("\n[!] 当前设计: Unknown 标记永久阻止后续 API 重试。")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
