"""
4-byte 函数签名同步工具
========================
从 https://www.4byte.directory/ 分页拉取函数签名，写入本地 SQLite 数据库。

用法:
    # 全量同步 (首次使用)
    python scripts/download_4bytes/sync_4bytes.py

    # 增量更新 (跳过已有签名)
    python scripts/download_4bytes/sync_4bytes.py --incremental

    # 仅同步前 10000 条 (测试)
    python scripts/download_4bytes/sync_4bytes.py --limit 10000

输出:
    data/signatures.db (SQLite)
    - 表: signatures(selector, text_signature, num_results, created_at)

改造说明:
  原脚本写入 known_hashes.py (Python dict), 现改为:
  1. 写入 SQLite signatures.db
  2. 批量 INSERT 提升性能 (每批 5000 条)
  3. 支持增量更新 (--incremental 跳过已有 selector)
  4. 记录同步时间戳

参考: detectors/trace/signature_db.py
"""

import sys
import sqlite3
import time
import argparse
from pathlib import Path

try:
    import requests
except ImportError:
    print('Run "pip install requests" to run this script')
    sys.exit(1)


# 数据库路径 (项目根目录下的 data/signatures.db)
DB_PATH = Path(__file__).resolve().parents[3] / "data" / "signatures.db"

# API 基础 URL
API_BASE = "https://www.4byte.directory/api/v1/signatures/"

# 批量写入大小
BATCH_SIZE = 5000


def ensure_db(conn: sqlite3.Connection) -> None:
    """初始化数据库表结构"""
    conn.executescript("""
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
    """)
    conn.commit()


def get_existing_selectors(conn: sqlite3.Connection) -> set[str]:
    """获取已有的 selector 集合 (用于增量模式)"""
    row = conn.execute("SELECT COUNT(DISTINCT selector) FROM signatures").fetchone()
    total = row[0] if row else 0
    if total == 0:
        return set()
    rows = conn.execute("SELECT DISTINCT selector FROM signatures").fetchall()
    return {r[0] for r in rows}


def save_batch_to_sqlite(
    conn: sqlite3.Connection,
    batch: list[tuple[str, str, int]],
) -> int:
    """
    将一批签名数据写入 SQLite

    Args:
        batch: [(selector, text_signature, num_results), ...]

    Returns:
        实际插入的行数 (去重后)
    """
    if not batch:
        return 0

    cursor = conn.cursor()
    inserted = 0

    try:
        cursor.executemany(
            "INSERT OR IGNORE INTO signatures (selector, text_signature, num_results) "
            "VALUES (?, ?, ?)",
            batch,
        )
        inserted = cursor.rowcount
        conn.commit()

    except Exception as e:
        print(f"[ERROR] Batch insert failed: {e}")
        conn.rollback()

    return inserted


def fetch_page(url: str) -> tuple[list[dict], str | None]:
    """
    从 4byte.directory API 获取一页数据

    Returns:
        (results_list, next_url_or_None)
    """
    retries = 5
    while retries > 0:
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            next_url = data.get("next")
            return results, next_url
        except requests.exceptions.RequestException as e:
            retries -= 1
            if retries <= 0:
                raise RuntimeError(f"Failed to fetch {url}: {e}")
            time.sleep(2 ** (5 - retries))  # 指数退避


def iterate_paginated_results(
    conn: sqlite3.Connection,
    incremental: bool = False,
    limit: int | None = None,
) -> dict:
    """
    分页遍历 4byte.directory API，将签名批量写入 SQLite

    Returns:
        统计信息字典
    """
    existing: set[str] = set()
    if incremental:
        print("[*] Incremental mode: fetching existing selectors...")
        existing = get_existing_selectors(conn)
        print(f"[*] Already have {len(existing)} unique selectors")

    url = API_BASE
    total_fetched = 0
    total_inserted = 0
    total_skipped = 0
    batch: list[tuple[str, str, int]] = []
    start_time = time.time()

    page_num = 0
    total_count_estimate = 0

    while True:
        page_num += 1
        results, next_url = fetch_page(url)

        if page_num == 1 and results:
            # 尝试获取总数估计 (API 返回 count 字段)
            pass

        cur_page_inserted = 0
        cur_page_skipped = 0

        for result in results:
            hex_sig = result["hex_signature"]
            text_sig = result["text_signature"]
            total_fetched += 1

            # 标准化 selector 为 10 字符格式
            if not hex_sig.startswith("0x"):
                hex_sig = "0x" + hex_sig
            selector = hex_sig[:10].lower() if len(hex_sig) >= 10 else hex_sig.lower()

            # 增量模式跳过已有
            if incremental and selector in existing:
                total_skipped += 1
                cur_page_skipped += 1
                continue

            batch.append((selector, text_sig, 1))

            if len(batch) >= BATCH_SIZE:
                n = save_batch_to_sqlite(conn, batch)
                total_inserted += n
                cur_page_inserted += n
                batch.clear()

        # 处理剩余的批次
        if batch and (next_url is None or (limit and total_fetched >= limit)):
            n = save_batch_to_sqlite(conn, batch)
            total_inserted += n
            cur_page_inserted += n
            batch.clear()

        # 进度显示
        elapsed = time.time() - start_time
        rate = total_fetched / elapsed if elapsed > 0 else 0
        print(
            f"  [Page {page_num:>4}] "
            f"fetched={total_fetched:,} "
            f"inserted={total_inserted:,} "
            f"skipped={total_skipped:,} "
            f"({rate:.0f} sig/s)"
        )

        # 达到限制
        if limit and total_fetched >= limit:
            print(f"\n[*] Reached --limit of {limit}")
            break

        if not next_url:
            break

        url = next_url

        # 礼貌性延迟
        time.sleep(0.1)

    final_stats = {
        "total_fetched": total_fetched,
        "total_inserted": total_inserted,
        "total_skipped": total_skipped,
        "pages_processed": page_num,
        "elapsed_seconds": round(time.time() - start_time, 2),
        "mode": "incremental" if incremental else "full",
    }

    return final_stats


def main():
    parser = argparse.ArgumentParser(
        description="Sync 4-byte function signatures from 4byte.directory into local SQLite DB"
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Incremental mode: skip already-imported selectors",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max signatures to fetch (for testing)",
    )
    parser.add_argument(
        "--db",
        type=str,
        default=None,
        help="Custom database path (default: data/signatures.db)",
    )
    args = parser.parse_args()

    db_path = Path(args.db) if args.db else DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[+] Database path: {db_path}")
    print(f"[+] Mode: {'incremental' if args.incremental else 'full sync'}")

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")   # 提升并发写入性能
    conn.execute("PRAGMA synchronous=NORMAL")  # 牺牲少量安全性换取速度
    ensure_db(conn)

    try:
        stats = iterate_paginated_results(
            conn,
            incremental=args.incremental,
            limit=args.limit,
        )
        print("\n" + "=" * 50)
        print(f"  Sync Complete!")
        print(f"  Mode:       {stats['mode']}")
        print(f"  Fetched:    {stats['total_fetched']:,}")
        print(f"  Inserted:   {stats['total_inserted']:,}")
        print(f"  Skipped:    {stats['total_skipped']:,}")
        print(f"  Pages:      {stats['pages_processed']}")
        print(f"  Elapsed:    {stats['elapsed_seconds']:.1f}s")
        print(f"  DB size:    {db_path.stat().st_size / 1024 / 1024:.1f} MB")
        print("=" * 50)

        # 显示最终统计
        row = conn.execute("SELECT COUNT(*) FROM signatures").fetchone()
        unique_sel = conn.execute(
            "SELECT COUNT(DISTINCT selector) FROM signatures"
        ).fetchone()
        print(f"\n  Total signatures in DB: {row[0]:,}")
        print(f"  Unique selectors:         {unique_sel[0]:,}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
