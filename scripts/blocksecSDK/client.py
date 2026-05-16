from __future__ import annotations

import json
import os
from typing import Any

import httpx
from playwright.async_api import Page, async_playwright

from .models import (
    BlockSecAccountChange,
    BlockSecAnalysisResult,
    BlockSecAssetChange,
    BlockSecAttackEvent,
    BlockSecBalanceChangeSummary,
    BlockSecBasicInfo,
    BlockSecInvocationFlow,
    BlockSecInvocationNode,
)


class BlockSecClientError(Exception):
    pass


class BlockSecClient:
    BASE_URL = "https://app.blocksec.com"
    API_PREFIX = "/api/explorer/v2/onchain/tx"
    BROWSER_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"

    def __init__(self, base_url: str | None = None, timeout: float = 20.0, cookie: str | None = None, use_playwright: bool = True) -> None:
        self.base_url = (base_url or self.BASE_URL).rstrip("/")
        self.timeout = timeout
        self.cookie = self._resolve_cookie(cookie)
        self.use_playwright = use_playwright
        self.headers = {
            "User-Agent": self.BROWSER_USER_AGENT,
            "Accept": "application/json",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Content-Type": "application/json;charset=utf-8",
            "Origin": self.base_url,
        }

    async def analyze_transaction(self, chain_id: int, tx_hash: str, include_fundflow: bool = True) -> BlockSecAnalysisResult:
        tx_hash = self.normalize_tx_hash(tx_hash)
        chain_id = self.normalize_chain_id(chain_id)

        if self.use_playwright:
            attack_event, basic_info, balance_changes, invocation_flow, fundflow = await self._fetch_all_with_playwright(
                chain_id=chain_id,
                tx_hash=tx_hash,
                include_fundflow=include_fundflow,
            )
        else:
            async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers, cookies=self._httpx_cookies()) as client:
                attack_event, basic_info, balance_changes, invocation_flow, fundflow = await self._fetch_all(
                    client=client,
                    chain_id=chain_id,
                    tx_hash=tx_hash,
                    include_fundflow=include_fundflow,
                )

        return BlockSecAnalysisResult(
            chain_id=chain_id,
            tx_hash=tx_hash,
            attack_event=self._normalize_attack_event(attack_event),
            basic_info=self._normalize_basic_info(chain_id, tx_hash, basic_info),
            balance_changes=self._normalize_balance_changes(balance_changes),
            invocation_flow=self._normalize_invocation_flow(invocation_flow),
            fundflow=fundflow,
        )

    async def get_attack_event(self, chain_id: int, tx_hash: str) -> BlockSecAttackEvent | None:
        payload = await self._post("attack-event", chain_id, tx_hash)
        return self._normalize_attack_event(payload)

    async def get_basic_info(self, chain_id: int, tx_hash: str) -> BlockSecBasicInfo:
        payload = await self._post("basic-info", chain_id, tx_hash)
        return self._normalize_basic_info(chain_id, tx_hash, payload)

    async def get_balance_changes(self, chain_id: int, tx_hash: str) -> BlockSecBalanceChangeSummary:
        payload = await self._post("balance-change", chain_id, tx_hash)
        return self._normalize_balance_changes(payload)

    async def get_invocation_flow(self, chain_id: int, tx_hash: str) -> BlockSecInvocationFlow:
        payload = await self._post("trace", chain_id, tx_hash)
        return self._normalize_invocation_flow(payload)

    async def get_fundflow(self, chain_id: int, tx_hash: str) -> dict[str, Any]:
        return await self._post("fundflow", chain_id, tx_hash)

    async def _fetch_all(self, client: httpx.AsyncClient, chain_id: int, tx_hash: str, include_fundflow: bool) -> tuple[Any, Any, Any, Any, Any]:
        import asyncio

        coros = [
            self._post_with_client(client, "attack-event", chain_id, tx_hash),
            self._post_with_client(client, "basic-info", chain_id, tx_hash),
            self._post_with_client(client, "balance-change", chain_id, tx_hash),
            self._post_with_client(client, "trace", chain_id, tx_hash),
        ]
        if include_fundflow:
            coros.append(self._post_with_client(client, "fundflow", chain_id, tx_hash))
        else:
            coros.append(self._return_none())

        results = await asyncio.gather(*coros)
        return tuple(results)

    async def _fetch_all_with_playwright(self, chain_id: int, tx_hash: str, include_fundflow: bool) -> tuple[Any, Any, Any, Any, Any]:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=self.BROWSER_USER_AGENT,
                locale="zh-CN",
                extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9"},
            )
            if self.cookie:
                await context.add_cookies(self._playwright_cookies())
            page = await context.new_page()
            page_url = f"{self.base_url}/phalcon/explorer/tx/eth/{tx_hash}"
            try:
                await page.goto(page_url, wait_until="domcontentloaded", timeout=int(self.timeout * 1000))
                attack_event, basic_info, balance_changes, invocation_flow, fundflow = await self._fetch_all_from_page(
                    page=page,
                    chain_id=chain_id,
                    tx_hash=tx_hash,
                    include_fundflow=include_fundflow,
                )
                return attack_event, basic_info, balance_changes, invocation_flow, fundflow
            finally:
                await context.close()
                await browser.close()

    async def _fetch_all_from_page(self, page: Page, chain_id: int, tx_hash: str, include_fundflow: bool) -> tuple[Any, Any, Any, Any, Any]:
        import asyncio

        coros = [
            self._post_with_page(page, "attack-event", chain_id, tx_hash),
            self._post_with_page(page, "basic-info", chain_id, tx_hash),
            self._post_with_page(page, "balance-change", chain_id, tx_hash),
            self._post_with_page(page, "trace", chain_id, tx_hash),
        ]
        if include_fundflow:
            coros.append(self._post_with_page(page, "fundflow", chain_id, tx_hash))
        else:
            coros.append(self._return_none())

        results = await asyncio.gather(*coros)
        return tuple(results)

    async def _return_none(self) -> None:
        return None

    async def _post(self, endpoint: str, chain_id: int, tx_hash: str) -> dict[str, Any]:
        if self.use_playwright:
            tx_hash = self.normalize_tx_hash(tx_hash)
            chain_id = self.normalize_chain_id(chain_id)
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent=self.BROWSER_USER_AGENT,
                    locale="zh-CN",
                    extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9"},
                )
                if self.cookie:
                    await context.add_cookies(self._playwright_cookies())
                page = await context.new_page()
                try:
                    await page.goto(f"{self.base_url}/phalcon/explorer/tx/eth/{tx_hash}", wait_until="domcontentloaded", timeout=int(self.timeout * 1000))
                    return await self._post_with_page(page, endpoint, chain_id, tx_hash)
                finally:
                    await context.close()
                    await browser.close()

        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers, cookies=self._httpx_cookies()) as client:
            return await self._post_with_client(client, endpoint, chain_id, self.normalize_tx_hash(tx_hash))

    async def _post_with_client(self, client: httpx.AsyncClient, endpoint: str, chain_id: int, tx_hash: str) -> dict[str, Any]:
        tx_hash = self.normalize_tx_hash(tx_hash)
        url = f"{self.base_url}{self.API_PREFIX}/{endpoint}"
        body = {
            "chainId": self.normalize_chain_id(chain_id),
            "txnHash": tx_hash,
            "blocked": False,
        }
        request_headers = {"Referer": f"{self.base_url}/phalcon/explorer/tx/eth/{tx_hash}"}
        try:
            response = await client.post(url, json=body, headers=request_headers)
            response.raise_for_status()
        except httpx.TimeoutException as e:
            raise BlockSecClientError(f"BlockSec request timed out for {endpoint}") from e
        except httpx.HTTPStatusError as e:
            raise BlockSecClientError(f"BlockSec request failed for {endpoint}: HTTP {e.response.status_code}") from e
        except httpx.HTTPError as e:
            raise BlockSecClientError(f"BlockSec request failed for {endpoint}: {e}") from e

        try:
            payload = response.json()
        except json.JSONDecodeError as e:
            raise BlockSecClientError(f"BlockSec returned non-JSON for {endpoint}") from e

        if not isinstance(payload, dict):
            raise BlockSecClientError(f"BlockSec returned invalid payload for {endpoint}")
        return payload

    async def _post_with_page(self, page: Page, endpoint: str, chain_id: int, tx_hash: str) -> dict[str, Any]:
        tx_hash = self.normalize_tx_hash(tx_hash)
        chain_id = self.normalize_chain_id(chain_id)
        url = f"{self.base_url}{self.API_PREFIX}/{endpoint}"
        body = {"chainId": chain_id, "txnHash": tx_hash, "blocked": False}
        script = """
async ({ url, body }) => {
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'accept': 'application/json',
      'content-type': 'application/json;charset=utf-8'
    },
    body: JSON.stringify(body),
    credentials: 'include'
  });
  const text = await response.text();
  return { status: response.status, text };
}
"""
        try:
            result = await page.evaluate(script, {"url": url, "body": body})
        except Exception as e:
            raise BlockSecClientError(f"BlockSec Playwright request failed for {endpoint}: {e}") from e

        status = int(result.get("status") or 0)
        if status >= 400:
            raise BlockSecClientError(f"BlockSec request failed for {endpoint}: HTTP {status}")

        text = result.get("text") or "{}"
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as e:
            raise BlockSecClientError(f"BlockSec returned non-JSON for {endpoint}") from e

        if not isinstance(payload, dict):
            raise BlockSecClientError(f"BlockSec returned invalid payload for {endpoint}")
        return payload

    def _httpx_cookies(self) -> dict[str, str]:
        value = str(self.cookie or "").strip()
        if not value:
            return {}

        cookies: dict[str, str] = {}
        for part in value.split(";"):
            item = part.strip()
            if not item or "=" not in item:
                continue
            name, cookie_value = item.split("=", 1)
            name = name.strip()
            cookie_value = cookie_value.strip()
            if name:
                cookies[name] = cookie_value

        if cookies:
            return cookies

        return {"cf_clearance": value}

    def _playwright_cookies(self) -> list[dict[str, Any]]:
        cookies = self._httpx_cookies()
        return [
            {
                "name": name,
                "value": value,
                "domain": ".blocksec.com",
                "path": "/",
                "httpOnly": name == "cf_clearance",
                "secure": True,
                "sameSite": "None" if name == "cf_clearance" else "Lax",
            }
            for name, value in cookies.items()
        ]

    @staticmethod
    def _resolve_cookie(cookie: str | None) -> str | None:
        if cookie is not None:
            value = str(cookie).strip()
            return value or None

        env_cookie = os.getenv("BLOCKSEC_COOKIE")
        if env_cookie:
            value = env_cookie.strip()
            if value:
                return value

        try:
            from config.model import settings

            value = str(settings.blocksec_cookie or "").strip()
            return value or None
        except Exception:
            return None

    @staticmethod
    def _cookie_header_value(cookie: str | None) -> str | None:
        value = str(cookie or "").strip()
        if not value:
            return None
        if "=" in value and ";" in value:
            return value
        if "=" in value and " " not in value:
            return value
        return f"cf_clearance={value}"

    @staticmethod
    def normalize_tx_hash(tx_hash: str) -> str:
        value = str(tx_hash or "").strip().lower()
        if not value.startswith("0x"):
            value = f"0x{value}"
        if len(value) != 66 or any(ch not in "0123456789abcdefx" for ch in value):
            raise BlockSecClientError("Invalid tx_hash format")
        return value

    @staticmethod
    def normalize_chain_id(chain_id: int) -> int:
        try:
            value = int(chain_id)
        except (TypeError, ValueError) as e:
            raise BlockSecClientError("Invalid chain_id") from e
        if value <= 0:
            raise BlockSecClientError("Invalid chain_id")
        return value

    def _normalize_attack_event(self, payload: dict[str, Any] | None) -> BlockSecAttackEvent | None:
        if not payload:
            return None
        return BlockSecAttackEvent(
            blocksec_id=self._to_int(payload.get("id")),
            project=str(payload.get("project") or ""),
            project_logo=str(payload.get("projectLogo") or ""),
            loss=self._to_float(payload.get("loss")),
            media=str(payload.get("media") or ""),
            root_cause=str(payload.get("rootCause") or ""),
            poc=str(payload.get("poc") or ""),
            rescued=self._to_float(payload.get("rescued")),
            raw=payload,
        )

    def _normalize_basic_info(self, chain_id: int, tx_hash: str, payload: dict[str, Any] | None) -> BlockSecBasicInfo:
        payload = payload or {}
        return BlockSecBasicInfo(
            chain_id=chain_id,
            tx_hash=tx_hash,
            block_number=self._to_int(payload.get("blockNumber")),
            sender=str(payload.get("sender") or ""),
            receiver=str(payload.get("receiver") or ""),
            timestamp=self._to_int(payload.get("timestamp")),
            calldata=str(payload.get("calldata") or ""),
            gas_used=self._to_int(payload.get("gasUsed")),
            event_count=self._to_int(payload.get("eventCount")),
            int_txn_count=self._to_int(payload.get("intTxnCount")),
            raw=payload,
        )

    def _normalize_balance_changes(self, payload: dict[str, Any] | None) -> BlockSecBalanceChangeSummary:
        payload = payload or {}
        accounts: list[BlockSecAccountChange] = []
        net_value_by_account: dict[str, float] = {}
        largest_inflow: BlockSecAccountChange | None = None
        largest_outflow: BlockSecAccountChange | None = None

        for item in payload.get("balanceChanges") or []:
            raw_assets = item.get("assets") or []
            assets = [
                BlockSecAssetChange(
                    token_address=str(asset.get("tokenAddress") or asset.get("token") or ""),
                    token_symbol=str(asset.get("symbol") or asset.get("tokenSymbol") or ""),
                    amount=str(asset.get("amount") or ""),
                    value_usd=self._to_float(asset.get("value") or asset.get("valueUsd") or asset.get("usdValue")),
                    sign=self._to_bool_or_none(asset.get("sign")),
                    raw=asset,
                )
                for asset in raw_assets
                if isinstance(asset, dict)
            ]
            account = BlockSecAccountChange(
                account=str(item.get("account") or ""),
                total_value_usd=self._to_float(item.get("totalValue") or item.get("totalValueUsd") or item.get("value")),
                sign=self._to_bool_or_none(item.get("sign")),
                extremum=bool(item.get("extremum")),
                assets=assets,
                raw=item,
            )
            accounts.append(account)
            if account.account and account.total_value_usd is not None:
                signed_value = account.total_value_usd
                if account.sign is False:
                    signed_value = -abs(signed_value)
                elif account.sign is True:
                    signed_value = abs(signed_value)
                net_value_by_account[account.account.lower()] = signed_value
                if signed_value > 0 and (largest_inflow is None or signed_value > (net_value_by_account.get(largest_inflow.account.lower(), float("-inf")))):
                    largest_inflow = account
                if signed_value < 0 and (largest_outflow is None or signed_value < (net_value_by_account.get(largest_outflow.account.lower(), float("inf")))):
                    largest_outflow = account

        return BlockSecBalanceChangeSummary(
            accounts=accounts,
            largest_inflow=largest_inflow,
            largest_outflow=largest_outflow,
            net_value_by_account=net_value_by_account,
            raw=payload,
        )

    def _normalize_invocation_flow(self, payload: dict[str, Any] | None) -> BlockSecInvocationFlow:
        payload = payload or {}
        node_infos = payload.get("nodeInfos") or payload.get("nodes") or []
        nodes: list[BlockSecInvocationNode] = []
        parent_to_children: dict[str, list[str]] = {}
        root_ids: list[str] = []
        max_depth = 0

        for raw in node_infos:
            if not isinstance(raw, dict):
                continue
            node_id = str(raw.get("id") or raw.get("nodeId") or raw.get("traceId") or "")
            parent_id = str(raw.get("parentId") or raw.get("parent") or "")
            depth = self._to_int(raw.get("depth")) or 0
            action = raw.get("action") or {}
            from_address = str(raw.get("from") or action.get("from") or "")
            to_address = str(raw.get("to") or action.get("to") or "")
            input_data = str(raw.get("input") or action.get("input") or "")
            selector = input_data[:10].lower() if input_data.startswith("0x") and len(input_data) >= 10 else ""
            call_type = str(raw.get("callType") or action.get("callType") or raw.get("type") or "")
            value = str(raw.get("value") or action.get("value") or "")

            node = BlockSecInvocationNode(
                node_id=node_id,
                parent_id=parent_id,
                depth=depth,
                from_address=from_address,
                to_address=to_address,
                call_type=call_type,
                selector=selector,
                value=value,
                children=[],
                raw=raw,
            )
            nodes.append(node)
            if parent_id:
                parent_to_children.setdefault(parent_id, []).append(node_id)
            else:
                root_ids.append(node_id)
            max_depth = max(max_depth, depth)

        for node in nodes:
            node.children = parent_to_children.get(node.node_id, [])

        return BlockSecInvocationFlow(
            nodes=nodes,
            root_ids=root_ids,
            max_depth=max_depth,
            raw=payload,
        )

    @staticmethod
    def _to_int(value: Any) -> int | None:
        try:
            if value is None or value == "":
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_float(value: Any) -> float | None:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_bool_or_none(value: Any) -> bool | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1"}:
                return True
            if lowered in {"false", "0"}:
                return False
        if isinstance(value, (int, float)):
            return bool(value)
        return None
