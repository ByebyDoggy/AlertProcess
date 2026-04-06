"""
4-byte 函数签名查询服务（二级缓存 + 在线回退）
===================================
查询优先级:
  1. 本地 SQLite 数据库 (data/signatures.db)
  2. 4byte.directory 在线 API
     GET /api/v1/signatures/?hex_signature=0xa9059cbb
  3. Unknown 标记回填到本地数据库

重要: 一个 selector 可能对应多个函数签名 (多义性),
      lookup_all() 返回该 selector 的全部候选签名列表，按 id ASC 排序（ID最小优先）。

存储: SQLite (signatures.db)
表结构:
  signatures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    selector TEXT NOT NULL,           -- '0xa9059cbb' (10字符)
    text_signature TEXT NOT NULL,      -- 'transfer(address,uint256)'
    num_results INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  )
  UNIQUE INDEX idx_sig_unique ON signatures(selector, text_signature);
  INDEX idx_selector_prefix ON signatures(selector);

导入工具: scripts/sync_signatures.py

API:
  GET /detectors/trace/signatures?prefix=0xa905     -- 前缀搜索
  GET /detectors/trace/signatures?hex=0xa9059cbb    -- 精确查询全部签名
"""

import sqlite3
import logging
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import httpx  # 优先用 httpx (async 友好)
except ImportError:
    httpx = None

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger(__name__)

# ── 路径配置 ──────────────────────────────────────────────
_DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "signatures.db"
_4BYTE_API_BASE = "https://www.4byte.directory/api/v1/signatures/"
_API_TIMEOUT = 10  # 秒

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS signatures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    selector TEXT NOT NULL,
    text_signature TEXT NOT NULL,
    num_results INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sig_unique 
    ON signatures(selector, text_signature);

CREATE INDEX IF NOT EXISTS idx_selector_prefix 
    ON signatures(selector);
"""

# Unknown 签名标记
_UNKNOWN_SIGNATURE_PREFIX = "Unknown("


class SignatureDB:
    """
    本地 4-byte 签名数据库（二级查询: SQLite → 4byte API → Unknown 回退）

    排序规则: 多个签名时按 id ASC 升序排列，ID 最小的优先。

    用法:
        db = SignatureDB()
        sig = db.lookup("0xa9059cbb")         # → "transfer(address,uint256)"
        results = db.prefix_search("0xa90")     # → [{"selector":..., "signature":...}, ...]
        count = db.count()

    查询链路:
        1. 本地 SQLite (ORDER BY id ASC) → 命中则返回
        2. 4byte.directory API (按 API 返回的 id 升序) → 命中则返回并写入 DB
        3. 标记为 Unknown(0x...) → 写入 DB 避免重复查询
    """

    def __init__(self, db_path: str | Path | None = None):
        """
        Args:
            db_path: SQLite 数据库路径。默认使用项目 data/signatures.db。
                     若传入空字符串 "" 则使用纯内存模式（无持久化）。
        """
        self._conn = None  # 先初始化，避免 _ensure_db 访问未定义属性

        # 默认使用项目内置路径
        if db_path is None:
            self.db_path = _DEFAULT_DB_PATH
        elif isinstance(db_path, str) and db_path.strip() == "":
            # 空字符串 → 纯内存模式
            self.db_path = None
            self._conn = None
            self._use_fallback = True
            self._api_enabled = bool(httpx or requests)
            logger.info("[SignatureDB] Using in-memory mode only")
            return
        else:
            self.db_path = Path(db_path)

        self._use_fallback = not self.db_path.exists()
        # API 查询开关: 即使有 DB 也启用在线回退
        self._api_enabled = bool(httpx or requests)

        if self._use_fallback:
            logger.warning(
                f"[SignatureDB] DB not found at {self.db_path}, using API fallback"
            )
            self._conn = None
        else:
            self._ensure_db()

    def _ensure_db(self) -> None:
        """初始化数据库文件 (若不存在则创建空表)"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.executescript(_CREATE_TABLE_SQL)
        conn.commit()
        count = self.count(conn=conn)
        api_status = "enabled" if self._api_enabled else "disabled (no http client)"
        logger.info(
            "[SignatureDB] Initialized at %s, %s signatures, online API %s",
            self.db_path, count, api_status,
        )

    def _get_conn(self) -> sqlite3.Connection:
        """获取数据库连接"""
        if self._conn is None and not self._use_fallback:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn  # type: ignore[return-value]

    # ================================================================
    # 公共查询接口
    # ================================================================

    def lookup(self, selector: str) -> Optional[str]:
        """
        精确查询 selector 对应的最佳签名（三级查找，单结果）
        返回按 num_results 排序的第一个（最常用）签名。

        如需获取全部候选签名，请使用 lookup_all()。

        Args:
            selector: 10字符 hex string, 如 "0xa9059cbb"

        Returns:
            text_signature 或 None
        """
        all_sigs = self.lookup_all(selector)
        if not all_sigs:
            return None
        return all_sigs[0]  # 返回最佳匹配

    def lookup_all(self, selector: str) -> list[str]:
        """
        精确查询 selector 对应的全部函数签名列表（二级查找，多结果）

        查询链路:
          1. 本地数据库 → 返回全部匹配的 text_signature 列表（按 id ASC 排序，排除 Unknown）
          2. 4byte API   → 获取全部结果（按 API 返回的 id 升序）并写入 DB，返回全部
          3. Unknown     → 标记并写入 DB

        Args:
            selector: 10字符 hex string

        Returns:
            签名文本列表，按 id ASC 排序（ID最小的优先）。
            空列表表示完全未命中（连 Unknown 都没标记）。
        """
        sel = self._normalize_selector(selector)
        if not sel:
            return []

        # Level 1: 本地数据库 → 全部 (按 id ASC 排序)
        db_results = self._lookup_db_all(sel)
        if db_results is not None:
            return db_results  # 已有数据（可能为空列表 = 只有 Unknown）

        # Level 2: 4byte API 在线查询 → 获取全部结果
        if self._api_enabled:
            api_results = self._query_4byte_api_all(sel)
            if api_results:
                # API 命中 → 写入本地数据库并返回
                for sig in api_results:
                    self._save_to_db(sel, sig)
                return api_results

        # Level 3: 全部未命中 → 标记 Unknown 并入库
        unknown_sig = f"{_UNKNOWN_SIGNATURE_PREFIX}{sel})"
        self._save_to_db(sel, unknown_sig)
        return []

    def bulk_lookup(self, selectors: list[str]) -> dict[str, list[str]]:
        """
        批量查询 — 分析时一次性传入所有需要解析的 selector
        使用并发 API 查询提升性能。

        Returns:
            {selector: [signature_list], ...}  每个 selector 对应全部候选签名列表（按 id ASC 排序）
        """
        if not selectors:
            return {}

        normalized = set()
        for s in selectors:
            ns = self._normalize_selector(s)
            if ns:
                normalized.add(ns)

        result: dict[str, list[str]] = {}
        remaining: list[str] = list(normalized)

        # Level 1: 本地数据库批量查询
        if remaining and not self._use_fallback:
            db_result = self._bulk_lookup_db(remaining)
            for sel in remaining:
                sigs = db_result.get(sel)
                if sigs is not None and len(sigs) > 0:
                    result[sel] = sigs
                elif sigs == []:
                    # DB 中已有该 selector 的 Unknown 记录 → 直接标记为Unknown，不再查API
                    unknown_sig = f"{_UNKNOWN_SIGNATURE_PREFIX}{sel})"
                    result[sel] = [unknown_sig]
            # 收集仍需API查询的 selector（DB中完全无记录的）
            missing = [s for s in remaining if s not in result]
        elif self._use_fallback:
            missing = remaining.copy()
        else:
            missing = []

        # Level 2: 并发 API 查询未命中的 selector
        if missing and self._api_enabled:
            api_results = self._bulk_query_4byte_api(missing)
            for sel, sig_list in api_results.items():
                if sig_list:  # 非空列表
                    result[sel] = sig_list
                    for sig in sig_list:
                        self._save_to_db(sel, sig)

        # Level 3: 对仍然未命中的标记 Unknown
        final_missing = [s for s in missing if s not in result]
        for sel in final_missing:
            unknown_sig = f"{_UNKNOWN_SIGNATURE_PREFIX}{sel})"
            result[sel] = [unknown_sig]
            self._save_to_db(sel, unknown_sig)

        return result

    def lookup_by_hex(self, hex_sig: str) -> dict:
        """
        精确查询一个 selector 的全部签名信息（供 API 路由使用）

        Args:
            hex_sig: 10字符 selector，如 "0xa9059cbb"

        Returns:
            {
                "selector": "0xa9059cbb",
                "signatures": [
                    {"text": "transfer(address,uint256)", "id": 123},
                    ...
                ],
                "total": N,
                "source": "db" | "api" | "unknown"
            }
        """
        sel = self._normalize_selector(hex_sig)
        if not sel:
            return {"selector": sel, "signatures": [], "total": 0, "source": "invalid"}

        # Level 1: 本地数据库
        if not self._use_fallback:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT id, text_signature, num_results FROM signatures "
                "WHERE selector=? AND NOT text_signature LIKE ? "
                "ORDER BY id ASC",
                (sel, f"{_UNKNOWN_SIGNATURE_PREFIX}%"),
            ).fetchall()
            if rows:
                sigs = [{"text": r["text_signature"], "id": r["id"], "num_results": r["num_results"]} for r in rows]
                return {"selector": sel, "signatures": sigs, "total": len(sigs), "source": "db"}

            # 检查是否已有 Unknown 标记
            has_unknown = conn.execute(
                "SELECT 1 FROM signatures WHERE selector=? AND text_signature LIKE ? LIMIT 1",
                (sel, f"{_UNKNOWN_SIGNATURE_PREFIX}%"),
            ).fetchone()
            if has_unknown:
                return {"selector": sel, "signatures": [], "total": 0, "source": "unknown"}

        # Level 2: API
        if self._api_enabled:
            api_sigs = self._query_4byte_api_all(sel)
            if api_sigs:
                for s in api_sigs:
                    self._save_to_db(sel, s)
                return {
                    "selector": sel,
                    "signatures": [{"text": s} for s in api_sigs],
                    "total": len(api_sigs),
                    "source": "api",
                }

        # Level 3: Unknown
        unknown_sig = f"{_UNKNOWN_SIGNATURE_PREFIX}{sel})"
        self._save_to_db(sel, unknown_sig)
        return {
            "selector": sel,
            "signatures": [],
            "total": 0,
            "source": "unknown",
            "unknown_label": unknown_sig,
        }

    def prefix_search(self, prefix: str, limit: int = 20) -> list[dict]:
        """
        前缀模糊搜索签名

        Args:
            prefix: 选择器前缀，如 "0xa905"
            limit: 最大返回条数

        Returns:
            [{"selector": ..., "signature": ...}, ...]
        """
        pfx = prefix.strip().lower()
        if not pfx.startswith("0x"):
            pfx = "0x" + pfx

        # Fallback 模式（无 DB 时返回空列表）
        if self._use_fallback:
            return []

        conn = self._get_conn()
        rows = conn.execute(
            "SELECT DISTINCT selector, text_signature FROM signatures "
            "WHERE selector LIKE ? AND NOT text_signature LIKE ? ORDER BY id ASC LIMIT ?",
            (pfx + "%", f"{_UNKNOWN_SIGNATURE_PREFIX}%", limit),
        ).fetchall()
        return [
            {"selector": r["selector"], "signature": r["text_signature"]}
            for r in rows
        ]

    def count(self, conn: sqlite3.Connection | None = None) -> int:
        """返回数据库中总条数"""
        if self._use_fallback:
            return 0
        c = conn or self._get_conn()
        row = c.execute("SELECT COUNT(*) as cnt FROM signatures").fetchone()
        return row["cnt"] if row else 0  # type: ignore[index]

    def get_stats(self) -> dict:
        """返回签名库统计信息"""
        total = self.count()
        unique_selectors = 0
        unknown_count = 0
        if not self._use_fallback and self._conn:
            row = self._conn.execute(
                "SELECT COUNT(DISTINCT selector) as cnt FROM signatures"
            ).fetchone()
            unique_selectors = row["cnt"] if row else 0  # type: ignore[index]
            unk_row = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM signatures WHERE text_signature LIKE ?",
                (f"{_UNKNOWN_SIGNATURE_PREFIX}%",),
            ).fetchone()
            unknown_count = unk_row["cnt"] if unk_row else 0
        elif self._use_fallback:
            unique_selectors = 0

        return {
            "total_signatures": total,
            "unique_selectors": unique_selectors,
            "unknown_count": unknown_count,
            "db_path": str(self.db_path) if self.db_path else "(fallback mode)",
            "is_fallback_mode": self._use_fallback,
            "api_enabled": self._api_enabled,
        }

    @staticmethod
    def _normalize_selector(selector: str) -> str:
        """标准化 selector 为小写 10 字符格式"""
        s = selector.lower().strip()
        if not s.startswith("0x"):
            s = "0x" + s
        if len(s) >= 10:
            return s[:10]
        return ""

    def close(self) -> None:
        """关闭数据库连接"""
        if self._conn:
            self._conn.close()
            self._conn = None

    # ================================================================
    # 内部方法: 数据库操作
    # ================================================================

    def _lookup_db(self, selector: str) -> Optional[str]:
        """从本地数据库查询单个 selector 的最佳签名（跳过 Unknown 条目）"""
        all_sigs = self._lookup_db_all(selector)
        if all_sigs:
            return all_sigs[0]
        return None

    def _lookup_db_all(self, selector: str) -> Optional[list[str]]:
        """
        从本地数据库查询单个 selector 的全部签名（跳过 Unknown 条目）
        Returns:
          签名列表 (按 id ASC 升序，ID最小的优先)，或 None 表示 DB 中无任何记录
        """
        if self._use_fallback:
            return None
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT text_signature FROM signatures "
            "WHERE selector=? AND NOT text_signature LIKE ? "
            "ORDER BY id ASC",
            (selector, f"{_UNKNOWN_SIGNATURE_PREFIX}%"),
        ).fetchall()
        if not rows:
            # 检查是否有该 selector 的记录（包括 Unknown）
            has_any = conn.execute(
                "SELECT 1 FROM signatures WHERE selector=? LIMIT 1",
                (selector,),
            ).fetchone()
            # 有记录但只有 Unknown → 返回空列表（表示已查过但未知）
            # 无任何记录 → 返回 None（需要去 API 查）
            return [] if has_any else None
        return [r["text_signature"] for r in rows]

    def _bulk_lookup_db(self, selectors: list[str]) -> dict[str, list[str] | None]:
        """批量数据库查询（每个 selector 返回全部签名列表，按 id ASC 排序）"""
        if not selectors or self._use_fallback:
            return {}
        conn = self._get_conn()
        placeholders = ",".join("?" for _ in selectors)
        rows = conn.execute(
            f"SELECT selector, text_signature FROM signatures "
            f"WHERE selector IN ({placeholders}) "
            f"AND NOT text_signature LIKE ? "
            f"ORDER BY id ASC",
            [*selectors, f"{_UNKNOWN_SIGNATURE_PREFIX}%"],
        ).fetchall()
        result: dict[str, list[str] | None] = {}
        for r in rows:
            sel = r["selector"]
            if sel not in result:
                result[sel] = []
            result[sel].append(r["text_signature"])
        # 对没有命中的 selector，标记为 None 或空列表
        for sel in selectors:
            if sel not in result:
                # 检查是否有该 selector 的任何记录
                has_any = conn.execute(
                    "SELECT 1 FROM signatures WHERE selector=? LIMIT 1",
                    (sel,),
                ).fetchone()
                result[sel] = [] if has_any else None  # type: ignore[assignment]
        return result

    def _save_to_db(self, selector: str, signature: str) -> bool:
        """将单个签名写入数据库（INSERT OR IGNORE + 更新频率）"""
        if self._use_fallback:
            return False
        try:
            conn = self._get_conn()
            existing = conn.execute(
                "SELECT id, num_results FROM signatures WHERE selector=? AND text_signature=?",
                (selector, signature),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE signatures SET num_results=num_results+1 WHERE id=?",
                    (existing[0],),
                )
            else:
                conn.execute(
                    "INSERT INTO signatures (selector, text_signature, num_results) VALUES (?, ?, 1)",
                    (selector, signature),
                )
            conn.commit()
            return True
        except Exception as e:
            logger.warning("[SignatureDB] 保存签名失败 (%s): %s", selector, e)
            return False

    # ================================================================
    # 内部方法: 4byte API 查询
    # ================================================================

    def _query_4byte_api(self, selector: str) -> Optional[str]:
        """
        从 4byte.directory API 查询单个 selector 的最佳匹配签名（单结果）。
        兼容旧接口，内部调用 _query_4byte_api_all() 取第一个。

        Returns:
            最佳签名文本 或 None
        """
        results = self._query_4byte_api_all(selector)
        if results:
            return results[0]
        return None

    def _query_4byte_api_all(self, selector: str) -> list[str]:
        """
        从 4byte.directory API 查询单个 selector 的全部候选签名。

        API: GET https://www.4byte.directory/api/v1/signatures/?hex_signature=0xa9059cbb

        Returns:
            全部签名文本列表（按 API 返回的 id ASC 排列，ID最小的优先），空列表表示无结果
        """
        url = f"{_4BYTE_API_BASE}?hex_signature={selector}"
        data = self._http_get(url)
        if data is None:
            return []

        results = data.get("results", [])
        if results:
            # 按 API 的 id 升序排列（ID 最小的优先）
            sorted_results = sorted(results, key=lambda item: int(item.get("id", 0)))
            sigs = [item["text_signature"] for item in sorted_results if item.get("text_signature")]
            if sigs:
                logger.debug("[SignatureDB] API 命中 %s → %d 个签名", selector, len(sigs))
                return sigs
        return []

    def _bulk_query_4byte_api(self, selectors: list[str]) -> dict[str, list[str]]:
        """
        并发查询多个 selector 的 4byte API。
        使用线程池并行请求以减少总耗时。

        Returns:
            {selector: [signature_list]}  每个selector对应全部候选签名列表
        """
        if not selectors:
            return {}

        max_workers = min(8, len(selectors))
        result: dict[str, list[str]] = {}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(self._query_4byte_api_all, sel): sel
                for sel in selectors
            }
            for future in as_completed(future_map):
                sel = future_map[future]
                try:
                    sigs = future.result(timeout=_API_TIMEOUT + 5)
                    result[sel] = sigs  # list[str], 可能为空列表
                except Exception as e:
                    logger.warning("[SignatureDB] API 查询异常 %s: %s", sel, e)
                    result[sel] = []

        return result

    @staticmethod
    def _http_get(url: str) -> Optional[dict]:
        """发送 HTTP GET 请求并解析 JSON 响应"""
        if httpx:
            try:
                resp = httpx.get(url, timeout=_API_TIMEOUT, follow_redirects=True)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                logger.debug("[SignatureDB] httpx 请求失败: %s", e)

        if requests:
            try:
                resp = requests.get(url, timeout=_API_TIMEOUT)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                logger.debug("[SignatureDB] requests 请求失败: %s", e)

        return None
