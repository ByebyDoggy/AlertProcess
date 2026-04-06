"""
4-byte 函数签名查询服务（三级缓存）
===================================
查询优先级:
  1. 内置常用签名 (内存)
  2. 本地 SQLite 数据库 (data/signatures.db)
  3. 4byte.directory 在线 API
     GET /api/v1/signatures/?hex_signature=0xa9059cbb
  4. Unknown 标记回填到本地数据库

重要: 一个 selector 可能对应多个函数签名 (多义性),
      lookup_all() 返回该 selector 的全部候选签名列表。

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
_DEFAULT_DB_PATH = Path(__file__).resolve().parents[3] / "data" / "signatures.db"
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


# 内置常用签名 (在 SQLite 库未就绪时的 fallback)
_BUILTIN_SIGNATURES: dict[str, str] = {
    "0xa9059cbb": "transfer(address,uint256)",
    "0x23b872dd": "transferFrom(address,address,uint256)",
    "0x095ea7b3": "approve(address,uint256)",
    "0x70a08231": "balanceOf(address)",
    "0x18160ddd": "totalSupply()",
    "0xdd62ed3e": "allowance(address,address)",
    "0x38ed1739": "swapExactTokensForTokens(uint256,uint256,address[],address,uint256)",
    "0x18cbafe5": "swapExactTokensForETH(uint256,uint256,address[],address,uint256)",
    "0x7ff36ab5": "swapExactETHForTokens(uint256[],address[],address,uint256)",
    "0x414bf389": "exactInputSingle((address,uint24,address,uint256,uint256,uint256))",
    "0x04e45aaf": "exactInput(bytes)",
    "0xd0e30db0": "deposit()",
    "0x2e1a7d4d": "withdraw(uint256)",
    "0x8afff657": "flashLoan(address,address,uint256,bytes,uint16)",
    "0xa5215b6a": "flashLoanSimple(address,address,uint256,uint16)",
    "0x9e9623cd": "supply(address,uint256,address,uint16)",
    "0x41c728b9": "withdraw(address,uint256,address)",
    "0x4a58c4c4": "borrow(address,uint256,uint256,uint16,address)",
    "0xa15cc3a3": "repay(address,uint256,uint256,address)",
    "0xac9650d8": "multicall(bytes[])",
}

# Unknown 签名标记
_UNKNOWN_SIGNATURE_PREFIX = "Unknown("


class SignatureDB:
    """
    本地 4-byte 签名数据库 (三级查询: DB → 4byte API → Unknown 回填)

    用法:
        db = SignatureDB()
        sig = db.lookup("0xa9059cbb")         # → "transfer(address,uint256)"
        results = db.prefix_search("0xa90")     # → [{"selector":..., "signature":...}, ...]
        count = db.count()

    查询链路:
        1. 本地 SQLite → 命中则返回
        2. 4byte.directory API → 命中则返回并写入 DB
        3. 标记为 Unknown(0x...) → 写入 DB 避免重复查询
    """

    def __init__(self, db_path: str | Path | None = None):
        """
        Args:
            db_path: SQLite 数据库路径。默认使用项目 data/signatures.db。
                     若传入 None 则使用内置签名 (纯内存模式，无持久化)。
        """
        if db_path is None:
            self.db_path = None
            self._conn = None
            self._use_fallback = True
            self._api_enabled = False  # fallback 模式下不调 API
            logger.info("[SignatureDB] Using built-in fallback signatures only")
            return

        self.db_path = Path(db_path)
        self._use_fallback = not self.db_path.exists()
        # API 查询开关: 即使有 DB 也启用在线回退
        self._api_enabled = bool(httpx or requests)

        if self._use_fallback:
            logger.warning(
                f"[SignatureDB] DB not found at {db_path}, using fallback + API fallback"
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
        精确查询 selector 对应的全部函数签名列表（三级查找，多结果）

        查询链路:
          1. 内置签名 → 命中则返回 [best]
          2. 本地数据库 → 返回全部匹配的 text_signature 列表（排除 Unknown）
          3. 4byte API   → 获取全部 results 并写入 DB，返回全部
          4. Unknown     → 标记并写入 DB

        Args:
            selector: 10字符 hex string

        Returns:
            签名文本列表，按 num_results DESC 排序。
            空列表表示完全未命中（连 Unknown 都没标记）。
        """
        sel = self._normalize_selector(selector)
        if not sel:
            return []

        # Level 1: 内置签名 → 单条
        if sel in _BUILTIN_SIGNATURES:
            return [_BUILTIN_SIGNATURES[sel]]

        # Level 2: 本地数据库 → 全部
        db_results = self._lookup_db_all(sel)
        if db_results is not None:
            return db_results  # 已有数据（可能为空列表 = 只有 Unknown）

        # Level 3: 4byte API 在线查询 → 获取全部结果
        if self._api_enabled:
            api_results = self._query_4byte_api_all(sel)
            if api_results:
                # API 命中 → 写入本地数据库并返回
                for sig in api_results:
                    self._save_to_db(sel, sig)
                return api_results

        # Level 4: 全部未命中 → 标记 Unknown 并入库
        unknown_sig = f"{_UNKNOWN_SIGNATURE_PREFIX}{sel})"
        self._save_to_db(sel, unknown_sig)
        return []

    def bulk_lookup(self, selectors: list[str]) -> dict[str, list[str]]:
        """
        批量查询 — 分析时一次性传入所有需要解析的 selector
        使用并发 API 查询提升性能。

        Returns:
            {selector: [signature_list], ...}  每个 selector 对应全部候选签名列表
        """
        if not selectors:
            return {}

        normalized = set()
        for s in selectors:
            ns = self._normalize_selector(s)
            if ns:
                normalized.add(ns)

        result: dict[str, list[str]] = {}
        remaining: list[str] = []

        # Level 1: 内置签名
        for sel in normalized:
            if sel in _BUILTIN_SIGNATURES:
                result[sel] = [_BUILTIN_SIGNATURES[sel]]
            else:
                remaining.append(sel)

        if not remaining:
            return result

        # Level 2: 本地数据库批量查询
        if not self._use_fallback:
            db_result = self._bulk_lookup_db(remaining)
            for sel in remaining:
                sigs = db_result.get(sel)
                if sigs is not None and len(sigs) > 0:
                    result[sel] = sigs
            # 收集仍未命中的 selector（DB 中无任何非 Unknown 记录）
            missing = [s for s in remaining if s not in result]
        else:
            missing = remaining.copy()

        # Level 3: 并发 API 查询未命中的 selector
        if missing and self._api_enabled:
            api_results = self._bulk_query_4byte_api(missing)
            for sel, sig_list in api_results.items():
                if sig_list:  # 非空列表
                    result[sel] = sig_list
                    for sig in sig_list:
                        self._save_to_db(sel, sig)

        # Level 4: 对仍然未命中的标记 Unknown
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
                    {"text": "transfer(address,uint256)", "num_results": 12345},
                    {"text": "transfer(address,address,uint256)", ...},
                    ...
                ],
                "total": 2,
                "source": "db" | "api" | "builtin" | "unknown"
            }
        """
        sel = self._normalize_selector(hex_sig)
        if not sel:
            return {"selector": sel, "signatures": [], "total": 0, "source": "invalid"}

        # Level 1: 内置
        if sel in _BUILTIN_SIGNATURES:
            return {
                "selector": sel,
                "signatures": [{"text": _BUILTIN_SIGNATURES[sel], "num_results": 0}],
                "total": 1,
                "source": "builtin",
            }

        # Level 2: 本地数据库
        if not self._use_fallback:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT text_signature, num_results FROM signatures "
                "WHERE selector=? AND NOT text_signature LIKE ? "
                "ORDER BY num_results DESC",
                (sel, f"{_UNKNOWN_SIGNATURE_PREFIX}%"),
            ).fetchall()
            if rows:
                sigs = [{"text": r["text_signature"], "num_results": r["num_results"]} for r in rows]
                return {"selector": sel, "signatures": sigs, "total": len(sigs), "source": "db"}

            # 检查是否已有 Unknown 标记
            has_unknown = conn.execute(
                "SELECT 1 FROM signatures WHERE selector=? AND text_signature LIKE ? LIMIT 1",
                (sel, f"{_UNKNOWN_SIGNATURE_PREFIX}%"),
            ).fetchone()
            if has_unknown:
                return {"selector": sel, "signatures": [], "total": 0, "source": "unknown"}

        # Level 3: API
        if self._api_enabled:
            api_sigs = self._query_4byte_api_all(sel)
            if api_sigs:
                for s in api_sigs:
                    self._save_to_db(sel, s)
                return {
                    "selector": sel,
                    "signatures": [{"text": s, "num_results": 0} for s in api_sigs],
                    "total": len(api_sigs),
                    "source": "api",
                }

        # Level 4: Unknown
        unknown_sig = f"{_UNKNOWN_SIGNATURE_PREFIX}{sel})"
        self._save_to_db(sel, unknown_sig)
        return {
            "selector": sel,
            "signatures": [],
            "total": 0,
            "source": "unknown",
            "unknown_label": unknown_sig,
        }
        pfx = prefix.strip().lower()
        if not pfx.startswith("0x"):
            pfx = "0x" + pfx

        # Fallback 模式
        if self._use_fallback:
            results = []
            for sel, sig in _BUILTIN_SIGNATURES.items():
                if sel.startswith(pfx):
                    results.append({"selector": sel, "signature": sig})
                if len(results) >= limit:
                    break
            return results

        conn = self._get_conn()
        rows = conn.execute(
            "SELECT DISTINCT selector, text_signature FROM signatures "
            "WHERE selector LIKE ? ORDER BY selector LIMIT ?",
            (pfx + "%", limit),
        ).fetchall()
        return [
            {"selector": r["selector"], "signature": r["text_signature"]}
            for r in rows
        ]

    def count(self, conn: sqlite3.Connection | None = None) -> int:
        """返回数据库中总条数"""
        if self._use_fallback:
            return len(_BUILTIN_SIGNATURES)
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
            unique_selectors = total

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
          签名列表 (按 num_results DESC)，或 None 表示 DB 中无任何记录
        """
        if self._use_fallback:
            return None
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT text_signature FROM signatures "
            "WHERE selector=? AND NOT text_signature LIKE ? "
            "ORDER BY num_results DESC",
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
        """批量数据库查询（每个 selector 返回全部签名列表）"""
        if not selectors or self._use_fallback:
            return {}
        conn = self._get_conn()
        placeholders = ",".join("?" for _ in selectors)
        rows = conn.execute(
            f"SELECT selector, text_signature FROM signatures "
            f"WHERE selector IN ({placeholders}) "
            f"AND NOT text_signature LIKE ? "
            f"ORDER BY num_results DESC",
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
            全部签名文本列表（按 num_results DESC），空列表表示无结果
        """
        url = f"{_4BYTE_API_BASE}?hex_signature={selector}"
        data = self._http_get(url)
        if data is None:
            return []

        results = data.get("results", [])
        if results:
            # 返回全部结果，按 num_results 降序排列（API 默认排序）
            sigs = []
            for item in results:
                text_sig = item.get("text_signature")
                if text_sig:
                    sigs.append(text_sig)
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

        hit_count = sum(1 for v in result.values() if v is not None)
        if hit_count > 0:
            logger.debug(
                "[SignatureDB] 批量 API 查询完成: %d/%d 命中",
                hit_count, len(selectors),
            )

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
