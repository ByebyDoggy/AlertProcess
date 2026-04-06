#!/usr/bin/env python3
"""
4-byte 函数签名同步工具（并发版）
==================================
从 4byte.directory 并发分页拉取函数签名，导入本地 SQLite 数据库。

用法:
    # 全量同步（首次使用）
    python scripts/sync_signatures.py

    # 增量更新（跳过已有 selector）
    python scripts/sync_signatures.py --incremental

    # 限制条数（快速测试）
    python scripts/sync_signatures.py --limit 5000

    # 从第 2000 页开始拉取（断点续传 / 多机分段）
    python scripts/sync_signatures.py --start-page 2000

    # 8 个并发 worker（默认 5）
    python scripts/sync_signatures.py --workers 8

    # 指定数据库路径
    python scripts/sync_signatures.py --db ./my_sigs.db

    # 仅查看当前数据库状态
    python scripts/sync_signatures.py --stats

输出:
    data/signatures.db  (SQLite)
"""

import sys
import sqlite3
import time
import argparse
import logging
import threading
from pathlib import Path
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
except ImportError:
    print('[ERROR] 需要安装 requests: pip install requests')
    sys.exit(1)

# ── 路径配置 ──────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DB_PATH = PROJECT_ROOT / "data" / "signatures.db"

API_BASE = "https://www.4byte.directory/api/v1/signatures/"
BATCH_SIZE = 1000       # 每攒够 1000 条就写入 DB（降低延迟，方便观察进度）
PAGE_SIZE = 100          # API 默认每页大小
REQUEST_TIMEOUT = 30
DEFAULT_WORKERS = 5      # 默认并发数
RETRY_DELAYS = [1, 2, 4, 8, 16]
QUEUE_MAX_SIZE = 200     # URL 队列最大长度（反压）

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("sync_sigs")


# ── 数据库操作（线程安全，仅主线程写入） ─────────────────────

def init_db(conn: sqlite3.Connection) -> None:
    """创建表和索引"""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS signatures (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            selector    TEXT    NOT NULL,
            text_sig    TEXT    NOT NULL,
            num_results INTEGER DEFAULT 1,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_sig_unique
            ON signatures(selector, text_sig);

        CREATE INDEX IF NOT EXISTS idx_selector_prefix
            ON signatures(selector);

        CREATE TABLE IF NOT EXISTS sync_meta (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
    """)
    conn.commit()


def get_existing_selectors(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT DISTINCT selector FROM signatures").fetchall()
    return {r[0] for r in rows}


def get_db_stats(conn: sqlite3.Connection) -> dict:
    total = conn.execute("SELECT COUNT(*) FROM signatures").fetchone()[0]
    unique_sel = conn.execute("SELECT COUNT(DISTINCT selector) FROM signatures").fetchone()[0]
    last_sync = conn.execute(
        "SELECT value FROM sync_meta WHERE key='last_sync_time'"
    ).fetchone()
    return {
        "total_signatures": total,
        "unique_selectors": unique_sel,
        "last_sync": last_sync[0] if last_sync else "never",
    }


def save_batch(conn: sqlite3.Connection, batch: list[tuple]) -> int:
    if not batch:
        return 0
    try:
        cur = conn.cursor()
        # 用前后计数差值计算实际写入数（INSERT OR IGNORE 的 rowcount 不可靠）
        before = conn.execute("SELECT COUNT(*) FROM signatures").fetchone()[0]
        
        # 对于已存在的 (selector, text_sig) 组合，更新 num_results +1
        # 对于新记录，直接插入
        for selector, text_sig, _ in batch:
            existing = conn.execute(
                "SELECT id FROM signatures WHERE selector=? AND text_sig=?",
                (selector, text_sig),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE signatures SET num_results=num_results+1 WHERE id=?",
                    (existing[0],),
                )
            else:
                conn.execute(
                    "INSERT INTO signatures (selector, text_sig, num_results) VALUES (?, ?, 1)",
                    (selector, text_sig),
                )
        
        conn.commit()
        after = conn.execute("SELECT COUNT(*) FROM signatures").fetchone()[0]
        return after - before
    except Exception as e:
        log.error("批量写入失败: %s", e)
        conn.rollback()
        return 0


def cleanup_duplicates(conn: sqlite3.Connection, dry_run: bool = False) -> dict:
    """
    冲突清洗：每个 selector 只保留 num_results 最高的一条最佳签名。
    
    策略:
      - 同一 selector 下，保留出现次数最多（num_results 最大）的签名
      - 删除其余低置信度签名
      - 可先 --cleanup-dry-run 预览将要删除的数量
    
    Returns: 清洗统计
    """
    log.info("开始冲突清洗...")
    
    total_rows = conn.execute("SELECT COUNT(*) FROM signatures").fetchone()[0]
    unique_sel = conn.execute("SELECT COUNT(DISTINCT selector) FROM signatures").fetchone()[0]
    
    # 找出每个 selector 的最佳行 id（num_results 最大，若相等则取 id 最小的）
    best_ids = set()
    for row in conn.execute("""
        SELECT MAX(id) as keep_id FROM (
            SELECT id, selector, num_results,
                   ROW_NUMBER() OVER (PARTITION BY selector ORDER BY num_results DESC, id ASC) as rn
            FROM signatures
        )
        WHERE rn = 1 GROUP BY selector
    """).fetchall():
        best_ids.add(row[0])
    
    # 也可以用更简单的子查询（兼容性更好）:
    if not best_ids:
        # 回退方案：用子查询找每组的 max(id)
        for row in conn.execute("""
            SELECT MAX(id) FROM signatures GROUP BY selector
        """).fetchall():
            best_ids.add(row[0])
    
    conflicts_to_remove = total_rows - len(best_ids)
    log.info("总签名: %s  唯一 selector: %s  冲突行数(待删): %s",
             f"{total_rows:,}", f"{unique_sel:,}", f"{conflicts_to_remove:,}")
    
    if dry_run or conflicts_to_remove == 0:
        return {"total": total_rows, "unique_selectors": unique_sel,
                "conflicts_to_remove": conflicts_to_remove, "removed": 0}
    
    before = conn.execute("SELECT COUNT(*) FROM signatures").fetchone()[0]
    
    # 删除不在 best_ids 中的所有行
    placeholders = ",".join("?" for _ in best_ids)
    conn.execute(
        f"DELETE FROM signatures WHERE id NOT IN ({placeholders})",
        list(best_ids),
    )
    conn.commit()
    
    after = conn.execute("SELECT COUNT(*) FROM signatures").fetchone()[0]
    removed = before - after
    
    log.info("清洗完成: 删除了 %s 条冗余签名，剩余 %s 条",
             f"{removed:,}", f"{after:,}")
    return {"total": after, "unique_selectors": unique_sel,
            "conflicts_removed": removed}


def update_sync_meta(conn: sqlite3.Connection, stats: dict) -> None:
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO sync_meta (key, value) VALUES ('last_sync_time', ?)",
        (time.strftime("%Y-%m-%d %H:%M:%S"),),
    )
    cur.execute(
        "INSERT OR REPLACE INTO sync_meta (key, value) VALUES ('last_sync_stats', ?)",
        (str(stats),),
    )
    conn.commit()


# ── API 拉取（线程内执行） ──────────────────────────────────

_session = requests.Session()

def fetch_page(url: str) -> tuple[list[dict], str | None]:
    """
    从 API 获取一页数据。
    Returns: (results_list, next_url_or_None)
    Raises: RuntimeError on final retry failure
    """
    for attempt, delay in enumerate(RETRY_DELAYS):
        try:
            resp = _session.get(url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            return data.get("results", []), data.get("next")
        except requests.exceptions.RequestException as e:
            log.warning("请求失败 (尝试 %d/%d): %s", attempt + 1, len(RETRY_DELAYS), e)
            if attempt < len(RETRY_DELAYS) - 1:
                time.sleep(delay)

    raise RuntimeError(f"无法获取页面 (已重试 {len(RETRY_DELAYS)} 次): {url}")


# ── Worker：从队列取 URL，返回结果 ──────────────────────────

def _worker_fetch(url: str) -> tuple[str, list[dict], str | None, Exception | None]:
    """
    线程池 worker: 获取一页。
    Returns: (url, results, next_url, error)
    """
    try:
        results, next_url = fetch_page(url)
        return url, results, next_url, None
    except Exception as e:
        return url, [], None, e


def normalize_selector(hex_sig: str) -> str:
    s = hex_sig.lower().strip()
    if not s.startswith("0x"):
        s = "0x" + s
    return s[:10] if len(s) >= 10 else s


# ── 主同步逻辑（生产者-消费者模式） ─────────────────────────

def run_sync(
    conn: sqlite3.Connection,
    incremental: bool = False,
    limit: int | None = None,
    start_page: int = 1,
    workers: int = DEFAULT_WORKERS,
) -> dict:
    """
    并发同步任务。
    
    架构:
      主线程作为调度器，维护一个待请求 URL 队列。
      线程池 worker 从队列消费 URL → 返回结果。
      主线程收集结果 → 写入 SQLite（单线程写 DB）。

    Args:
        start_page: 起始页码（用于断点续传 / 多机并行）
        workers:    并发线程数
    """
    existing: set[str] = set()
    if incremental:
        log.info("增量模式: 加载已有 selectors...")
        existing = get_existing_selectors(conn)
        log.info("已有 %d 个唯一 selector", len(existing))

    # 初始 URL：如果指定 start_page > 1，直接构造 offset URL
    initial_offset = (start_page - 1) * PAGE_SIZE
    if start_page > 1:
        first_url = f"{API_BASE}?page_size={PAGE_SIZE}&offset={initial_offset}"
        log.info("起始页: %d (offset=%d)", start_page, initial_offset)
    else:
        first_url = f"{API_BASE}?page_size={PAGE_SIZE}"

    # 统计
    stats_lock = threading.Lock()
    total_fetched = 0
    total_inserted = 0
    total_skipped = 0
    page_done = 0
    errors: list[str] = []
    batch: list[tuple] = []
    start_time = time.time()

    # 待处理 URL 队列 + 已提交集合（防止重复提交）
    url_queue: deque[str] = deque([first_url])
    submitted_urls: set[str] = {first_url}
    # 用于发现新 URL 时通知调度器
    new_urls_event = threading.Event()

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="fetch") as pool:
        # active_futures: {url: Future}
        active_futures: dict[str, object] = {}

        def _submit_pending():
            """将队列中的 URL 提交到线程池"""
            while url_queue and len(active_futures) < workers * 2:
                u = url_queue.popleft()
                if u in active_futures:
                    continue
                ft = pool.submit(_worker_fetch, u)
                active_futures[u] = ft

        _submit_pending()

        while active_futures:
            # 等任意一个 future 完成
            done_futs = [ft for ft in active_futures.values() if ft.done()]
            if not done_futs:
                # 用短 sleep 配合 event 避免 busy loop
                time.sleep(0.02)
                continue

            for fut in done_futs:
                # 找到对应的 url
                done_url = None
                for u, ft in list(active_futures.items()):
                    if ft is fut:
                        done_url = u
                        break
                if done_url is None:
                    continue
                del active_futures[done_url]

                page_done += 1
                _, results, next_url, err = fut.result()

                if err:
                    log.error("[Page ?] 错误: %s", err)
                    errors.append(str(err))
                    continue

                # 处理本页数据
                cur_inserted = 0
                cur_skipped = 0
                for item in results:
                    selector = normalize_selector(item["hex_signature"])
                    text_sig = item["text_signature"]

                    with stats_lock:
                        total_fetched += 1

                    if incremental and selector in existing:
                        with stats_lock:
                            total_skipped += 1
                            cur_skipped += 1
                        continue

                    batch.append((selector, text_sig, 1))

                    if len(batch) >= BATCH_SIZE:
                        n = save_batch(conn, batch)
                        with stats_lock:
                            total_inserted += n
                            cur_inserted += n
                        batch.clear()

                # 达到 limit 时写入剩余并退出
                if limit and total_fetched >= limit:
                    if batch:
                        n = save_batch(conn, batch)
                        with stats_lock:
                            total_inserted += n
                        batch.clear()
                    log.info("已达 --limit: %d", limit)
                    break

                # 将下一页 URL 入队
                if next_url and next_url not in submitted_urls:
                    submitted_urls.add(next_url)
                    url_queue.append(next_url)

                # 进度日志
                elapsed = time.time() - start_time
                rate = total_fetched / elapsed if elapsed > 0 else 0
                log.info(
                    "[Page ~%4d] 获取=%s  插入=%s  跳过=%s  待写=%d  (%.0f sig/s)  活跃=%d",
                    page_done,
                    f"{total_fetched:,}",
                    f"{total_inserted:,}",
                    f"{total_skipped:,}",
                    len(batch),
                    rate,
                    len(active_futures),
                )

            if limit and total_fetched >= limit:
                break

            # 补充新任务
            _submit_pending()

    # 最终剩余批次
    if batch:
        n = save_batch(conn, batch)
        total_inserted += n
        batch.clear()

    result_stats = {
        "mode": f"incremental(start={start_page})" if incremental else f"full(start={start_page})",
        "total_fetched": total_fetched,
        "total_inserted": total_inserted,
        "total_skipped": total_skipped,
        "pages_processed": page_done,
        "errors": len(errors),
        "elapsed_seconds": round(time.time() - start_time, 2),
        "workers": workers,
    }
    update_sync_meta(conn, result_stats)
    return result_stats


# ── CLI 入口 ────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="从 4byte.directory 并发同步函数签名到本地 SQLite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/sync_signatures.py                       # 全量同步 (5 并发)
  python scripts/sync_signatures.py --incremental         # 增量更新
  python scripts/sync_signatures.py --limit 10000         # 测试用，限制 1 万条
  python scripts/sync_signatures.py --start-page 2000     # 从第 2000 页开始（断点续传）
  python scripts/sync_signatures.py --workers 10          # 10 个并发 worker
  python scripts/sync_signatures.py --stats               # 查看数据库状态
  python scripts/sync_signatures.py --cleanup             # 冲突清洗：每个 selector 只保留最佳签名
  python scripts/sync_signatures.py --cleanup-dry-run     # 预览冲突清洗效果（不实际删除）
        """,
    )
    parser.add_argument("--incremental", action="store_true", help="增量模式：跳过已导入的 selector")
    parser.add_argument("--limit", type=int, default=None, help="最大拉取条数（用于测试）")
    parser.add_argument("--start-page", type=int, default=1, help="起始页码（默认 1，用于断点续传或多机并行）")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help=f"并发线程数（默认 {DEFAULT_WORKERS}）")
    parser.add_argument("--db", type=str, default=None, help="自定义数据库路径（默认: data/signatures.db）")
    parser.add_argument("--stats", action="store_true", help="仅显示当前数据库状态后退出")
    parser.add_argument("--cleanup", action="store_true", help="冲突清洗：每个 selector 只保留 num_results 最高的最佳签名")
    parser.add_argument("--cleanup-dry-run", action="store_true", help="预览冲突清洗效果（不实际删除）")
    args = parser.parse_args()

    db_path = Path(args.db) if args.db else DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-64000")
    init_db(conn)

    # 仅查看状态
    if args.stats:
        st = get_db_stats(conn)
        db_size_mb = db_path.stat().st_size / 1024 / 1024 if db_path.exists() else 0
        print("=" * 56)
        print(f"  数据库:       {db_path}")
        print(f"  总签名数:     {st['total_signatures']:,}")
        print(f"  唯一选择器:   {st['unique_selectors']:,}")
        print(f"  文件大小:     {db_size_mb:.1f} MB")
        print(f"  上次同步:     {st['last_sync']}")
        print("=" * 56)
        conn.close()
        return

    # 冲突清洗
    if args.cleanup or args.cleanup_dry_run:
        result = cleanup_duplicates(conn, dry_run=args.cleanup_dry_run)
        db_size_mb = db_path.stat().st_size / 1024 / 1024
        mode_str = "预览" if args.cleanup_dry_run else "已执行"
        print("\n" + "=" * 56)
        print(f"  冲突清洗 ({mode_str})")
        print(f"  总签名数:     {result['total']:,}")
        print(f"  唯一选择器:   {result.get('unique_selectors', '?'):,}")
        if 'conflicts_to_remove' in result:
            print(f"  待删除冲突:   {result['conflicts_to_remove']:,}")
            print("  (使用 --cleanup 实际执行删除)")
        elif 'conflicts_removed' in result:
            print(f"  已删除冗余:   {result['conflicts_removed']:,}")
        print("=" * 56)
        conn.close()
        return

    log.info("数据库路径: %s", db_path)
    log.info("模式: %s", "增量" if args.incremental else "全量")
    log.info("起始页: %d  并发: %d", args.start_page, args.workers)

    try:
        stats = run_sync(
            conn,
            incremental=args.incremental,
            limit=args.limit,
            start_page=args.start_page,
            workers=args.workers,
        )
        db_size_mb = db_path.stat().st_size / 1024 / 1024

        print("\n" + "=" * 56)
        print(f"  同步完成!")
        print(f"  模式:         {stats['mode']}")
        print(f"  并发数:       {stats['workers']}")
        print(f"  获取总数:     {stats['total_fetched']:,}")
        print(f"  新增入库:     {stats['total_inserted']:,}")
        print(f"  跳过重复:     {stats['total_skipped']:,}")
        print(f"  处理页数:     {stats['pages_processed']}")
        print(f"  错误数:       {stats['errors']}")
        print(f"  耗时:         {stats['elapsed_seconds']:.1f}s")
        print(f"  DB 大小:      {db_size_mb:.1f} MB")
        print("=" * 56)

        final = get_db_stats(conn)
        print(f"\n  库中总签名:     {final['total_signatures']:,}")
        print(f"  唯一 selector: {final['unique_selectors']:,}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
