#!/usr/bin/env python3
"""
BlockSec 安全事件异步爬虫。

直接调用 https://blocksec.com/security-incident 页面使用的分页接口：
POST /api/v1/attack/events，抓取项目方、损失、chainID、txHash、事件原因等字段。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
str_root = str(PROJECT_ROOT)
if str_root not in sys.path:
    sys.path.insert(0, str_root)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_BASE_URL = "https://blocksec.com"
EVENTS_API_PATH = "/api/v1/attack/events"
ROOT_CAUSE_API_PATH = "/api/v1/attack/events-root-cause"

CHAIN_NAMES = {
    1: "Ethereum",
    10: "Optimism",
    56: "BNB Chain",
    137: "Polygon",
    250: "Fantom",
    8453: "Base",
    42161: "Arbitrum",
    43114: "Avalanche",
    59144: "Linea",
    81457: "Blast",
    534352: "Scroll",
}


@dataclass
class TransactionRecord:
    tx_hash: str
    chain_id: int | None = None
    chain_name: str = ""
    tx_time: str | None = None
    tx_timestamp_ms: int | None = None
    attacker: str = ""
    label: str = ""


@dataclass
class IncidentRecord:
    blocksec_id: int
    project: str
    title: str
    loss_usd: float | None = None
    loss_display: str = ""
    chain_ids: list[int] = field(default_factory=list)
    chain_names: list[str] = field(default_factory=list)
    root_cause: str = ""
    event_time: str | None = None
    event_timestamp_ms: int | None = None
    media_url: str = ""
    poc_url: str = ""
    rescued_usd: float | None = None
    project_logo: str = ""
    tx_hashes: list[str] = field(default_factory=list)
    attackers: list[str] = field(default_factory=list)
    transactions: list[TransactionRecord] = field(default_factory=list)
    description: str = ""
    tags: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    knowledge_base_candidates: list[dict[str, Any]] = field(default_factory=list)


def timestamp_ms_to_iso(value: Any) -> str | None:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return None
    if timestamp <= 0:
        return None
    return datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).isoformat()


def parse_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def format_loss(value: float | None) -> str:
    if value is None:
        return ""
    if value >= 1_000_000_000:
        return f"~ ${value / 1_000_000_000:.2f} B"
    if value >= 1_000_000:
        return f"~ ${value / 1_000_000:.2f} M"
    if value >= 1_000:
        return f"~ ${value / 1_000:.2f} K"
    return f"~ ${value:.2f}"


def normalize_chain_ids(item: dict[str, Any], transactions: list[TransactionRecord]) -> list[int]:
    chain_ids: set[int] = set()
    for value in item.get("chainIds") or []:
        try:
            chain_ids.add(int(value))
        except (TypeError, ValueError):
            pass
    for tx in transactions:
        if tx.chain_id is not None:
            chain_ids.add(tx.chain_id)
    return sorted(chain_ids)


def build_tags(root_cause: str, chain_names: list[str]) -> list[str]:
    tags = ["blocksec", "security_incident"]
    if root_cause:
        tags.append(root_cause.lower().replace(" ", "_").replace("/", "_"))
    tags.extend(name.lower().replace(" ", "_") for name in chain_names)
    return sorted(set(tags))


def build_description(project: str, loss_display: str, root_cause: str, chain_names: list[str]) -> str:
    parts = [f"{project} security incident"]
    if loss_display:
        parts.append(f"loss {loss_display}")
    if chain_names:
        parts.append(f"chains: {', '.join(chain_names)}")
    if root_cause:
        parts.append(f"root cause: {root_cause}")
    return "; ".join(parts) + "."


def build_knowledge_base_candidates(record: IncidentRecord) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for tx in record.transactions:
        if not tx.tx_hash or tx.chain_id is None:
            continue
        candidates.append(
            {
                "title": record.title,
                "description": record.description,
                "category": "security_incident",
                "tags": record.tags,
                "chain_id": tx.chain_id,
                "tx_hash": tx.tx_hash,
                "attacked_address": None,
                "exploiter_address": tx.attacker or None,
                "alert_data": {
                    "source": "blocksec",
                    "blocksec_id": record.blocksec_id,
                    "project": record.project,
                    "project_logo": record.project_logo,
                    "loss_usd": record.loss_usd,
                    "loss_display": record.loss_display,
                    "root_cause": record.root_cause,
                    "event_time": record.event_time,
                    "event_timestamp_ms": record.event_timestamp_ms,
                    "media_url": record.media_url,
                    "poc_url": record.poc_url,
                    "rescued_usd": record.rescued_usd,
                    "chain_id": tx.chain_id,
                    "chain_name": tx.chain_name,
                    "tx_hash": tx.tx_hash,
                    "tx_time": tx.tx_time,
                    "tx_timestamp_ms": tx.tx_timestamp_ms,
                    "attacker": tx.attacker or None,
                    "tx_label": tx.label or "",
                    "raw_incident": record.raw,
                },
                "expected_severity": None,
                "expected_labels": [tag for tag in record.tags if tag not in {"blocksec", "security_incident"}],
                "expected_min_score": None,
                "source": "blocksec",
                "tx_explorer_url": None,
            }
        )
    return candidates


def parse_incident(item: dict[str, Any]) -> IncidentRecord:
    transactions: list[TransactionRecord] = []
    for tx in item.get("transactions") or []:
        chain_id = tx.get("chainId")
        try:
            chain_id = int(chain_id) if chain_id is not None else None
        except (TypeError, ValueError):
            chain_id = None
        transactions.append(
            TransactionRecord(
                tx_hash=str(tx.get("txnHash") or "").lower(),
                chain_id=chain_id,
                chain_name=CHAIN_NAMES.get(chain_id or 0, str(chain_id or "")),
                tx_time=timestamp_ms_to_iso(tx.get("txnHashDate")),
                tx_timestamp_ms=tx.get("txnHashDate"),
                attacker=str(tx.get("attacker") or ""),
                label=str(tx.get("label") or ""),
            )
        )

    loss_usd = parse_float(item.get("loss"))
    chain_ids = normalize_chain_ids(item, transactions)
    chain_names = [CHAIN_NAMES.get(chain_id, str(chain_id)) for chain_id in chain_ids]
    root_cause = str(item.get("rootCause") or "")
    project = str(item.get("project") or "Unknown")
    loss_display = format_loss(loss_usd)
    record = IncidentRecord(
        blocksec_id=int(item.get("id") or 0),
        project=project,
        title=f"{project} - {root_cause}" if root_cause else project,
        loss_usd=loss_usd,
        loss_display=loss_display,
        chain_ids=chain_ids,
        chain_names=chain_names,
        root_cause=root_cause,
        event_time=timestamp_ms_to_iso(item.get("date")),
        event_timestamp_ms=item.get("date"),
        media_url=str(item.get("media") or ""),
        poc_url=str(item.get("poc") or ""),
        rescued_usd=parse_float(item.get("rescued")),
        project_logo=str(item.get("projectLogo") or ""),
        tx_hashes=sorted({tx.tx_hash for tx in transactions if tx.tx_hash}),
        attackers=sorted({tx.attacker for tx in transactions if tx.attacker}),
        transactions=transactions,
        raw=item,
    )
    record.tags = build_tags(record.root_cause, record.chain_names)
    record.description = build_description(record.project, record.loss_display, record.root_cause, record.chain_names)
    record.knowledge_base_candidates = build_knowledge_base_candidates(record)
    return record


class BlockSecIncidentCrawler:
    def __init__(
        self,
        base_url: str,
        page_size: int,
        concurrency: int,
        timeout: float,
        delay: float,
        max_pages: int | None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.events_api_url = urljoin(self.base_url, EVENTS_API_PATH)
        self.root_cause_api_url = urljoin(self.base_url, ROOT_CAUSE_API_PATH)
        self.page_size = max(1, page_size)
        self.concurrency = max(1, concurrency)
        self.timeout = timeout
        self.delay = max(0.0, delay)
        self.max_pages = max_pages
        self.errors: list[dict[str, Any]] = []

    async def fetch_root_causes(self, client: httpx.AsyncClient) -> list[str]:
        try:
            response = await client.get(self.root_cause_api_url)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, list):
                return [str(item) for item in payload]
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            self.errors.append({"url": self.root_cause_api_url, "error": exc.__class__.__name__, "message": str(exc)})
        return []

    async def fetch_page(self, client: httpx.AsyncClient, page: int) -> dict[str, Any]:
        try:
            response = await client.post(
                self.events_api_url,
                json={"page": page, "pageSize": self.page_size, "ignoreEmpty": True},
            )
            if self.delay:
                await asyncio.sleep(self.delay)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("events API did not return a JSON object")
            return payload
        except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
            self.errors.append({"url": self.events_api_url, "page": page, "error": exc.__class__.__name__, "message": str(exc)})
            return {"count": 0, "list": []}

    async def fetch_pages(self, client: httpx.AsyncClient, pages: list[int]) -> list[dict[str, Any]]:
        semaphore = asyncio.Semaphore(self.concurrency)

        async def guarded_fetch(page: int) -> dict[str, Any]:
            async with semaphore:
                return await self.fetch_page(client, page)

        return await asyncio.gather(*(guarded_fetch(page) for page in pages))

    async def run(self) -> dict[str, Any]:
        headers = {
            "User-Agent": "AlertProcessor-BlockSecCrawler/1.0 (+security-research)",
            "Accept": "application/json,text/plain,*/*",
            "Content-Type": "application/json",
            "Referer": urljoin(self.base_url, "/security-incident"),
        }
        async with httpx.AsyncClient(timeout=self.timeout, headers=headers) as client:
            root_causes_task = asyncio.create_task(self.fetch_root_causes(client))
            first_page = await self.fetch_page(client, 1)
            total_count = int(first_page.get("count") or 0)
            total_pages = math.ceil(total_count / self.page_size) if total_count else 1
            if self.max_pages is not None:
                total_pages = min(total_pages, self.max_pages)
            remaining_pages = list(range(2, total_pages + 1))
            page_payloads = [first_page]
            page_payloads.extend(await self.fetch_pages(client, remaining_pages))
            root_causes = await root_causes_task

        incidents_by_id: dict[int, IncidentRecord] = {}
        for payload in page_payloads:
            for item in payload.get("list") or []:
                record = parse_incident(item)
                incidents_by_id[record.blocksec_id] = record

        incidents = sorted(
            incidents_by_id.values(),
            key=lambda item: (item.event_timestamp_ms or 0, item.blocksec_id),
            reverse=True,
        )
        return {
            "source": "blocksec",
            "source_url": urljoin(self.base_url, "/security-incident"),
            "events_api_url": self.events_api_url,
            "crawled_at": datetime.now(timezone.utc).isoformat(),
            "root_causes": root_causes,
            "stats": {
                "total_count": total_count,
                "requested_pages": total_pages,
                "page_size": self.page_size,
                "incident_count": len(incidents),
                "transaction_count": sum(len(item.transactions) for item in incidents),
                "knowledge_base_candidate_count": sum(len(item.knowledge_base_candidates) for item in incidents),
                "error_count": len(self.errors),
            },
            "incidents": [asdict(item) for item in incidents],
            "errors": self.errors,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="异步分页爬取 BlockSec 安全事件库并输出 JSON。")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="BlockSec 站点根地址。")
    parser.add_argument("--output", default="blocksec_incidents.json", help="输出 JSON 文件路径。")
    parser.add_argument("--page-size", type=int, default=100, help="每页事件数。")
    parser.add_argument("--concurrency", type=int, default=8, help="分页接口并发请求数。")
    parser.add_argument("--timeout", type=float, default=20.0, help="单请求超时时间（秒）。")
    parser.add_argument("--delay", type=float, default=0.0, help="每次请求后的延迟（秒）。")
    parser.add_argument("--max-pages", type=int, default=None, help="最多抓取分页数；不传表示按 count 全量翻页。")
    parser.add_argument("--pretty", action="store_true", help="格式化输出 JSON。")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    crawler = BlockSecIncidentCrawler(
        base_url=args.base_url,
        page_size=args.page_size,
        concurrency=args.concurrency,
        timeout=args.timeout,
        delay=args.delay,
        max_pages=args.max_pages,
    )
    result = await crawler.run()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None),
        encoding="utf-8",
    )

    stats = result["stats"]
    print(
        "Crawl complete: "
        f"total={stats['total_count']}, "
        f"pages={stats['requested_pages']}, "
        f"incidents={stats['incident_count']}, "
        f"transactions={stats['transaction_count']}, "
        f"kb_candidates={stats['knowledge_base_candidate_count']}, "
        f"errors={stats['error_count']}, "
        f"output={output_path}"
    )


if __name__ == "__main__":
    asyncio.run(main())
