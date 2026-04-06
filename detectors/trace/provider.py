"""
RPC 客户端 — 多节点自动切换
===========================
特性:
- 每个 chain 配置多个 RPC URL
- 自动故障切换 (timeout/错误时切换下一个)
- 支持 trace_transaction 和 debug_traceTransaction
- 异步 HTTP 客户端 (httpx.AsyncClient)

参考文档: docs/dev-plan-trace-analysis.md §3.6
"""

import httpx
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 默认链配置 — 每条链配置多个公共 RPC 节点
DEFAULT_CHAIN_CONFIG: dict[int, dict] = {
    1: {
        "name": "Ethereum",
        "rpc_urls": [
            "https://ethereum-rpc.publicnode.com",
            "https://rpc.ankr.com/eth",
            "https://eth.llamarpc.com",
            "https://ethereum.publicnode.com",
        ],
        "explorer": "https://etherscan.io/tx/",
    },
    56: {
        "name": "BSC",
        "rpc_urls": [
            "https://bsc-dataseed.binance.org/",
            "https://bsc-dataseed1.nariox.org",
            "https://rpc.ankr.com/bsc",
            "https://bsc.publicnode.com",
        ],
        "explorer": "https://bscscan.com/tx/",
    },
    137: {
        "name": "Polygon",
        "rpc_urls": [
            "https://polygon-rpc.com",
            "https://rpc.ankr.com/polygon",
            "https://polygon.publicnode.com",
        ],
        "explorer": "https://polygonscan.com/tx/",
    },
    42161: {
        "name": "Arbitrum One",
        "rpc_urls": [
            "https://arb1.arbitrum.io/rpc",
            "https://rpc.ankr.com/arbitrum",
            "https://arbitrum-one.publicnode.com",
        ],
        "explorer": "https://arbiscan.io/tx/",
    },
    10: {
        "name": "Optimism",
        "rpc_urls": [
            "https://mainnet.optimism.io",
            "https://rpc.ankr.com/optimism",
            "https://optimism.publicnode.com",
        ],
        "explorer": "https://optimistic.etherscan.io/tx/",
    },
    43114: {
        "name": "Avalanche C-Chain",
        "rpc_urls": [
            "https://api.avax.network/ext/bc/C/rpc",
            "https://rpc.ankr.com/avalanche",
            "https://avalanche-c-chain.publicnode.com",
        ],
        "explorer": "https://snowtrace.io/tx/",
    },
}


class MultiRpcClient:
    """
    多节点容错 RPC 客户端

    用法:
        client = MultiRpcClient()
        result = await client.call(1, "eth_getBlockByNumber", ["latest", False])
        traces = await client.get_transaction_trace("0xabc...", chain_id=56)
    """

    def __init__(self, timeout: float = 30.0):
        self._timeout = timeout
        self._clients: dict[int, httpx.AsyncClient] = {}
        self._chain_indices: dict[int, int] = {}
        self._request_id: int = 0

    def _get_client(self, chain_id: int) -> httpx.AsyncClient:
        """获取或创建指定链的 HTTP 客户端"""
        if chain_id not in self._clients:
            self._clients[chain_id] = httpx.AsyncClient(timeout=self._timeout)
        return self._clients[chain_id]

    def _get_rpc_url(self, chain_id: int, offset: int = 0) -> Optional[str]:
        """获取指定链的第 N 个 RPC URL"""
        config = DEFAULT_CHAIN_CONFIG.get(chain_id)
        if not config or not config.get("rpc_urls"):
            return None
        urls = config["rpc_urls"]
        idx = (self._chain_indices.get(chain_id, 0) + offset) % len(urls)
        return urls[idx]

    def _switch_rpc(self, chain_id: int) -> None:
        """切换到下一个 RPC 节点"""
        current = self._chain_indices.get(chain_id, 0)
        self._chain_indices[chain_id] = current + 1
        logger.debug(
            f"[RPC] Chain {chain_id}: switching to node #{current + 1}"
        )

    async def call(
        self,
        chain_id: int,
        method: str,
        params: list,
        retries: int | None = None,
    ) -> dict:
        """
        带自动切换的 JSON-RPC 调用

        Args:
            chain_id: 链 ID (如 1=Ethereum, 56=BSC)
            method: RPC 方法名, 如 "eth_getTransactionByHash"
            params: 参数列表
            retries: 最大重试次数, 默认使用所有可用节点数

        Returns:
            RPC result 字典

        Raises:
            RuntimeError: 所有节点均失败时抛出
        """
        config = DEFAULT_CHAIN_CONFIG.get(chain_id, {})
        max_retries = retries if retries is not None else len(config.get("rpc_urls", []))
        last_error: Exception | None = None

        for attempt in range(max_retries):
            url = self._get_rpc_url(chain_id, offset=attempt)
            if not url:
                raise RuntimeError(f"No RPC URLs configured for chain {chain_id}")

            try:
                self._request_id += 1
                payload = {
                    "jsonrpc": "2.0",
                    "method": method,
                    "params": params,
                    "id": self._request_id,
                }
                client = self._get_client(chain_id)
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()

                if "error" in data:
                    err = data["error"]
                    raise RuntimeError(f"RPC Error ({url[:30]}...): {err}")

                return data.get("result", {})

            except Exception as e:
                last_error = e
                logger.debug(
                    f"[RPC] Attempt {attempt + 1}/{max_retries} failed "
                    f"(chain={chain_id}, method={method}): {e}"
                )
                if attempt < max_retries - 1:
                    continue
                break

        raise RuntimeError(
            f"All RPC nodes failed for chain {chain_id} "
            f"(method={method}, attempts={max_retries}): {last_error}"
        )

    async def get_transaction_trace(self, tx_hash: str, chain_id: int) -> list[dict]:
        """
        获取交易的完整调用追踪

        策略:
          1. 优先尝试 trace_transaction (OpenEthereum/Erigon/BSC 支持)
          2. 回退 debug_traceTransaction + callTracer (Geth 支持)

        Args:
            tx_hash: 交易哈希 (带 0x 前缀)
            chain_id: 链 ID

        Returns:
            trace entry 列表
        """
        # 策略 1: trace_transaction (返回 flat list)
        try:
            result = await self.call(chain_id, "trace_transaction", [tx_hash])
            if result and isinstance(result, list) and len(result) > 0:
                logger.info(
                    f"[TRACE] Got {len(result)} entries via trace_transaction "
                    f"(chain={chain_id})"
                )
                return result
        except Exception as e:
            logger.debug(
                f"[TRACE] trace_transaction unavailable (chain={chain_id}): {e}"
            )

        # 策略 2: debug_traceTransaction (返回单个嵌套对象, 需展平)
        try:
            tracer_config = {
                "tracer": "callTracer",
                "tracerConfig": {"withLog": True},
            }
            result = await self.call(
                chain_id, "debug_traceTransaction", [tx_hash, tracer_config]
            )
            if result and isinstance(result, dict):
                logger.info("[TRACE] Got result via debug_traceTransaction")
                # 将 callTracer 的嵌套结构转为 flat 列表
                flattened = self._flatten_calltracer(result)
                return flattened
        except Exception as e:
            logger.debug(
                f"[TRACE] debug_traceTransaction unavailable (chain={chain_id}): {e}"
            )

        logger.warning(f"[TRACE] No tracing support available for chain {chain_id}")
        return []

    @staticmethod
    def _flatten_calltracer(result: dict) -> list[dict]:
        """将 callTracer 的嵌套输出展平为 trace 格式的列表"""
        entries = []
        _request_id = 0

        def _walk(node: dict, trace_addr: list[int]) -> None:
            nonlocal _request_id
            action = {
                "from": node.get("from", ""),
                "to": node.get("to", ""),
                "input": node.get("input", "0x"),
                "value": node.get("value", "0x0"),
                "gas": node.get("gas", "0x0"),
                "callType": node.get("type", "call"),
            }
            result_entry = node.get("result", {})
            output = {
                "gasUsed": result_entry.get("gasUsed", "0x0"),
                "output": result_entry.get("output", "0x"),
                "error": result_entry.get("error"),
            }

            _request_id += 1
            entries.append({
                "action": action,
                "result": output,
                "traceAddress": trace_addr,
                "sub": node.get("sub", []),
                "type": "call",
            })

            for idx, child in enumerate(node.get("calls", []) or []):
                _walk(child, trace_addr + [idx])

        _walk(result, [])
        return entries

    async def get_transaction_receipt(self, tx_hash: str, chain_id: int) -> dict:
        """获取交易收据"""
        return await self.call(chain_id, "eth_getTransactionReceipt", [tx_hash])

    async def get_transaction_by_hash(self, tx_hash: str, chain_id: int) -> dict:
        """获取交易基本信息"""
        return await self.call(chain_id, "eth_getTransactionByHash", [tx_hash])

    async def close(self) -> None:
        """关闭所有 HTTP 连接"""
        for client in self._clients.values():
            await client.aclose()
        self._clients.clear()

    @staticmethod
    def get_chain_name(chain_id: int) -> str:
        """获取链的可读名称"""
        config = DEFAULT_CHAIN_CONFIG.get(chain_id, {})
        return config.get("name", f"Chain-{chain_id}")

    @staticmethod
    def get_explorer_url(chain_id: int) -> str:
        """获取区块链浏览器的 URL 前缀"""
        config = DEFAULT_CHAIN_CONFIG.get(chain_id, {})
        return config.get("explorer", "")

    @staticmethod
    def supported_chains() -> list[dict]:
        """返回支持的所有链信息 (供 API 使用)"""
        chains = []
        for cid, cfg in DEFAULT_CHAIN_CONFIG.items():
            chains.append({
                "chainId": cid,
                "name": cfg["name"],
                "rpcCount": len(cfg.get("rpc_urls", [])),
                "explorer": cfg.get("explorer", ""),
            })
        return sorted(chains, key=lambda x: x["chainId"])
