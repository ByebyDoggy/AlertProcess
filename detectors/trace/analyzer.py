"""
交易调用链分析器 — 基类
========================
职责:
  1. 通过 RPC 获取原始 trace 数据
  2. 将 flat trace 列表构建为嵌套 CallTree
  3. 通过 4-byte selector 解析函数签名 (查询本地签名库)
  4. 通过 to 地址匹配协议标签
  5. 将 receipt logs 中的 Events 关联到对应的 CallNode

使用方式:
  - 直接实例化: analyzer = TxTraceAnalyzer()
  - 继承扩展: class FlashLoanDetector(TxTraceAnalyzer): ...

参考文档: docs/dev-plan-trace-analysis.md §3.2
参考 PoC: scripts/tx_callchain_poc.py
"""

import asyncio
import time
import logging
from typing import Optional

from detectors.trace.models import (
    CallNode,
    EventRecord,
    TransactionInfo,
    ProtocolInfo,
    BehaviorResult,
    TokenFlowItem,
    BalanceChangeItem,
    FullAnalysisResult,
)
from detectors.trace.provider import MultiRpcClient
from detectors.trace.signature_db import SignatureDB
from detectors.trace.protocol_registry import ProtocolRegistry

logger = logging.getLogger(__name__)


# ================================================================
# 已知事件 Topic Hashes (用于解码 receipt logs)
# ================================================================
_EVENT_TOPICS: dict[str, tuple[str, list[str]]] = {
    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef": (
        "Transfer",
        ["address indexed from", "address indexed to", "uint256 value"],
    ),
    "0x8c5be1e5ebec7d5bd14f7f27da2898506d9e09ccf5c36a18b47b4dd681bc0b41": (
        "Approval",
        ["address indexed owner", "address indexed spender", "uint256 value"],
    ),
}


class TxTraceAnalyzer:
    """
    交易 Hash 解析基类

    所有行为检测器 (FlashLoan, Arbitrage, Sandwich 等) 都继承此类。
    """

    def __init__(
        self,
        signature_db_path: str | None = None,
        protocol_registry_path: str | None = None,
        rpc_client: MultiRpcClient | None = None,
    ):
        """
        Args:
            signature_db_path: 本地 4-byte 签名数据库路径 (SQLite)。
                               为 None 时使用内置 fallback 签名。
            protocol_registry_path: 自定义协议注册表 JSON 路径。
            rpc_client: 可选的外部 RPC 客户端实例 (用于测试注入)。
                        默认使用全局单例 get_rpc_client()，避免重复初始化池。
        """
        self._signature_db = SignatureDB(signature_db_path)
        self._protocol_registry = ProtocolRegistry(protocol_registry_path)
        if rpc_client is not None:
            self._rpc_client = rpc_client
        else:
            # 共享全局 RPC Client 单例，避免每次 new Analyzer 都重新登录/拉密钥
            from detectors.trace.provider import get_rpc_client
            self._rpc_client = get_rpc_client()

    # ===================================================================
    # 公开接口 — 子类可重写
    # ===================================================================

    async def analyze(
        self, tx_hash: str, chain_id: int = 1, run_behavior_detect: bool = True
    ) -> FullAnalysisResult:
        """
        完整分析流程 (模板方法模式)

        步骤:
        1. get_raw_trace()      -- 获取原始 trace
        2. build_call_tree()    -- 构建调用树
        3. resolve_signatures() -- 解析所有节点的函数签名
        4. identify_protocols() -- 识别协议标签
        5. link_events()        -- 关联 Events 到节点
        6. extract_token_flow() -- 提取 Token 流转
        7. detect_behaviors()   -- 运行行为检测 (子类实现)
        8. assemble_result()    -- 组装最终结果

        Args:
            tx_hash: 交易哈希 (带 0x 前缀)
            chain_id: 链 ID
            run_behavior_detect: 是否运行行为检测

        Returns:
            FullAnalysisResult
        """
        t_start = time.time()

        # 预处理钩子
        await self.pre_analyze(tx_hash, chain_id)

        # Step 1: 获取原始数据
        logger.info(f"[analyze] Starting analysis for {tx_hash[:16]}... on chain {chain_id}")

        # 并行获取: trace + receipt + tx_detail (三者无依赖关系)
        raw_traces_task = self._get_raw_trace(tx_hash, chain_id)
        receipt_task = self._rpc_client.get_transaction_receipt(tx_hash, chain_id)
        tx_detail_task = self._rpc_client.get_transaction_by_hash(tx_hash, chain_id)

        raw_traces, receipt, tx_detail = await asyncio.gather(
            raw_traces_task, receipt_task, tx_detail_task,
            return_exceptions=True,
        )

        # 处理 trace 结果 (trace 已有内部节点切换逻辑，失败直接抛出)
        if isinstance(raw_traces, Exception):
            raise ValueError(
                f"No trace data available for {tx_hash}. "
                f"The RPC may not support tracing. Error: {raw_traces}"
            )
        if not raw_traces:
            raise ValueError(
                f"No trace data available for {tx_hash}. "
                f"The RPC may not support tracing."
            )

        # 处理 receipt / tx_detail 结果 — 必须拿到有效数据，重试而非降级
        receipt = await self._ensure_valid_data(
            receipt, "receipt", tx_hash,
            lambda: self._rpc_client.get_transaction_receipt(tx_hash, chain_id),
        )
        tx_detail = await self._ensure_valid_data(
            tx_detail, "tx_detail", tx_hash,
            lambda: self._rpc_client.get_transaction_by_hash(tx_hash, chain_id),
        )

        receipt_logs = receipt.get("logs", []) if isinstance(receipt, dict) else []

        # Step 2: 构建调用树
        root = self.build_call_tree(raw_traces)

        # Step 3: 解析签名
        self.resolve_signatures(root)

        # Step 4: 识别协议
        protocols = self.identify_protocols(root, chain_id)

        # Step 5: 关联 events (receipt_logs 已在 Step 1 并行获取)
        self.link_events(root, receipt_logs)

        # Step 6: 提取 token 流转
        token_flows = self.extract_token_flows(root)

        # Step 6.1: 提取 call tree 中的 transfer 函数调用 (BlockSec 风格资金流)
        call_transfers = self.extract_call_transfers(root)

        # Step 6.5: 计算余额变化 (Balance Changes)
        balance_changes = await self.compute_balance_changes(
            root,
            tx_from=tx_detail.get("from", ""),
            tx_to_addr=tx_detail.get("to"),
            receipt_logs=receipt_logs,
            chain_id=chain_id,
        )

        # Step 6.6: 用动态数据源补全 CallNode 的 tokenSymbol
        # identify_protocols 只查静态表，很多代币(如 USR)不在其中
        await self._enrich_token_symbols(root, chain_id)

        # Step 7: 行为检测
        behaviors: list[BehaviorResult] = []
        if run_behavior_detect:
            tx_info = self._build_tx_info(tx_hash, chain_id, tx_detail, receipt)
            behaviors = await self.detect_behaviors(root, tx_info)

        # Step 8: 组装结果
        result = self.assemble_result(
            root=root,
            tx_hash=tx_hash,
            chain_id=chain_id,
            tx_detail=tx_detail,
            receipt=receipt,
            behaviors=behaviors,
            protocols=protocols,
            token_flows=token_flows,
            call_transfers=call_transfers,
            balance_changes=balance_changes,
            raw_trace_count=len(raw_traces),
            elapsed=time.time() - t_start,
        )

        # 后处理钩子
        result = self.post_analyze(result)

        return result

    async def _get_raw_trace(self, tx_hash: str, chain_id: int) -> list[dict]:
        """获取原始 trace 数据"""
        return await self._rpc_client.get_transaction_trace(tx_hash, chain_id)

    async def _ensure_valid_data(
        self,
        first_result,
        label: str,
        tx_hash: str,
        fetch_fn,
        max_retries: int = 5,
    ):
        """
        确保 RPC 返回有效数据（非 None / 非 Exception / 非 null dict）。

        RPC 内核层 (apipool-ng) 只在网络错误/限流时切换节点，
        但 HTTP 200 + null 响应被视为"成功"，不触发节点轮换。
        本方法在应用层补充重试逻辑：首次结果无效时重新调用 fetch_fn
        （每次调用都会触发内核层的 key 轮换），直到拿到有效数据或达到上限。

        Args:
            first_result: asyncio.gather 的首次返回值
            label: 日志标签，如 "receipt" / "tx_detail"
            tx_hash: 交易哈希 (用于日志)
            fetch_fn: 无参异步函数，用于重新获取数据
            max_retries: 最大重试次数

        Returns:
            dict 类型的有效数据

        Raises:
            ValueError: 所有重试耗尽仍未拿到有效数据
        """
        import inspect

        result = first_result
        for attempt in range(max_retries + 1):
            # 检查是否为有效数据
            if isinstance(result, Exception):
                logger.warning(
                    f"[analyze] {label} attempt {attempt + 1}/{max_retries + 1} "
                    f"raised {type(result).__name__}: {result}"
                )
            elif result is None:
                # RPC 返回 HTTP 200 但 body 为 null — 需要换节点重试
                logger.warning(
                    f"[analyze] {label} attempt {attempt + 1}/{max_retries + 1} "
                    f"returned None for {tx_hash[:16]}"
                )
            elif isinstance(result, dict) and not result.get("blockNumber"):
                # 部分节点可能返回空 dict 或缺少关键字段
                if not any(v is not None for v in result.values()):
                    logger.warning(
                        f"[analyze] {label} attempt {attempt + 1}/{max_retries + 1} "
                        f"returned empty-like dict for {tx_hash[:16]}"
                    )
                    result = None  # 标记为无效以触发重试
                else:
                    return result
            else:
                return result

            # 还有剩余次数则重试
            if attempt < max_retries:
                logger.info(f"[analyze] Retrying {label} (attempt {attempt + 2})...")
                await asyncio.sleep(0.3 * (attempt + 1))  # 渐进退避
                try:
                    result = await fetch_fn()
                except Exception as e:
                    logger.warning(f"[analyze] {label} retry failed: {e}")
                    result = e

        raise ValueError(
            f"Failed to get valid {label} after {max_retries + 1} attempts "
            f"for tx={tx_hash[:16]}. Last value: {result!r}"
        )

    def build_call_tree(self, raw_traces: list[dict]) -> CallNode:
        """
        将 flat trace 列表构建为嵌套 CallNode 树

        trace_transaction 返回的是 BFS 顺序的 flat list
        traceAddress 表示每个节点的位置, e.g. [0, 2, 1] 表示第0个节点的第2个子节点的第1个

        使用迭代式构建 (防止递归溢出)。

        参考 PoC: CallChainBuilder.build()
        """
        if not raw_traces:
            raise ValueError("Empty trace list")

        valid_traces = []
        for entry in raw_traces:
            action = entry.get("action")
            if action and isinstance(action, dict):
                call_type = action.get("callType", "")
                ttype = entry.get("type", "")
                if call_type in ("call", "delegatecall", "staticcall") or \
                   ttype == "create" or (not call_type and action.get("to")):
                    valid_traces.append(entry)

        logger.info(f"[build_tree] Valid traces: {len(valid_traces)} / {len(raw_traces)}")

        root: CallNode | None = None
        node_map: dict[tuple, CallNode] = {}

        for entry in valid_traces:
            raw_addr = entry.get("traceAddress")
            if raw_addr is None:
                continue
            trace_addr = tuple(raw_addr) if isinstance(raw_addr, list) else ()

            if trace_addr in node_map:
                logger.debug(f"[build_tree] Duplicate traceAddress: {trace_addr}")
                continue

            depth = len(trace_addr)
            node = self._make_call_node(entry, depth)

            parent_key = trace_addr[:-1] if trace_addr else ()
            parent = node_map.get(parent_key)

            if parent is None:
                if root is None:
                    root = node
                    node_map[trace_addr] = node
                else:
                    logger.debug(
                        f"[build_tree] Multiple roots at {trace_addr}, skipping"
                    )
            else:
                if id(parent) == id(node):
                    logger.debug(f"[build_tree] Self-reference at {trace_addr}")
                    continue
                parent.children.append(node)
                node_map[trace_addr] = node

        if root is None and node_map:
            root = next(iter(node_map.values()))

        if root is None:
            raise ValueError("Failed to build call tree from traces")

        return root

    @staticmethod
    def _make_call_node(entry: dict, depth: int) -> CallNode:
        """从单个 trace entry 创建 CallNode 对象"""
        action = entry.get("action", {})
        result = entry.get("result", {})

        input_hex = _to_hex(action.get("input", "0x"))
        output_hex = _to_hex(result.get("output", ""))

        node = CallNode(
            depth=depth,
            trace_address=list(entry.get("traceAddress", [])) or [],
            call_type=action.get("callType", entry.get("type", "?")),
            from_address=_to_hex(action.get("from", "")).lower(),
            to_address=_to_hex(
                action.get("to", action.get("address", ""))
            ).lower(),
            input_data=input_hex,
            output_data=output_hex,
            value=int(action.get("value", "0x0"), 16)
            if action.get("value") else 0,
            gas_limit=int(action.get("gas", "0x0"), 16)
            if action.get("gas") else 0,
            gas_used=int(result.get("gasUsed", "0x0"), 16)
            if result.get("gasUsed") else 0,
            error=result.get("error"),
            created_address=_to_hex(result.get("address", "")).lower(),
            selector=input_hex[:10] if len(input_hex) >= 10 else "",
        )
        return node

    def resolve_signatures(self, root: CallNode) -> None:
        """
        遍历所有 CallNode, 通过本地签名库解析 selector → function_signature
        并进行基本参数解码
        """
        # 收集所有唯一 selectors
        all_selectors: set[str] = set()
        nodes_by_selector: dict[str, list[CallNode]] = {}

        stack: list[CallNode] = [root]
        visited: set[int] = set()
        while stack:
            node = stack.pop()
            nid = id(node)
            if nid in visited:
                continue
            visited.add(nid)

            sel = node.selector
            if sel and not node.function_signature:
                all_selectors.add(sel)
                nodes_by_selector.setdefault(sel, []).append(node)

            stack.extend(node.children)

        if not all_selectors:
            return

        # 批量查询签名库
        sig_map = self._signature_db.bulk_lookup(list(all_selectors))

        # 回填到节点
        for sel, nodes in nodes_by_selector.items():
            sig_list = sig_map.get(sel)
            # 取最佳签名（第一个）作为主显示，其余候选可通过 API 查看全部
            sig = sig_list[0] if isinstance(sig_list, list) and len(sig_list) > 0 else sig_list
            for node in nodes:
                node.function_signature = sig
                if sig:
                    node.params = self._decode_params(node.input_data, sig)

        logger.info(
            f"[resolve_signatures] Resolved {len(sig_map)}/{len(all_selectors)} signatures"
        )

    @staticmethod
    def _decode_params(input_data: str, function_sig: str) -> list:
        """
        简单参数解码 — 处理基本类型
        生产环境可扩展使用 eth-abi 库做完整 ABI 解码
        """
        params = []

        # 从签名的括号内提取参数类型列表
        idx_start = function_sig.find("(")
        idx_end = function_sig.find(")")
        if idx_start < 0 or idx_end <= idx_start:
            return params

        param_str = function_sig[idx_start + 1 : idx_end]
        if not param_str.strip():
            return params

        # 分割参数类型
        parts = [p.strip() for p in param_str.split(",")]
        data_part = input_data[10:] if len(input_data) >= 10 else ""

        from detectors.trace.models import DecodedParam

        offset = 0
        for i, ptype in enumerate(parts):
            if offset + 64 > len(data_part):
                break

            raw = data_part[offset : offset + 64]
            name = f"param_{i}"

            try:
                val_int = int(raw, 16)
                if ptype.startswith("uint") or ptype.startswith("int"):
                    if val_int > 1e15:
                        val_str = f"{val_int:,}"
                    else:
                        val_str = str(val_int)
                elif ptype == "address" and len(raw) >= 40:
                    val_str = "0x" + raw[-40:]
                elif ptype == "bool":
                    val_str = str(bool(val_int))
                elif ptype == "bytes":
                    val_str = "0x" + raw
                else:
                    val_str = raw
            except (ValueError, IndexError):
                val_str = raw

            params.append(DecodedParam(name=name, type_hint=ptype, value=val_str))
            offset += 64

            # 简单跳过动态数组/bytes (实际偏移更复杂，这里简化)
            if "[]" in ptype or ptype.startswith("bytes"):
                pass

        return params

    def identify_protocols(self, root: CallNode, chain_id: int) -> list[ProtocolInfo]:
        """通过 to 地址匹配协议注册表, 返回识别到的协议列表"""
        visited: set[int] = set()
        found_protocols: dict[str, ProtocolInfo] = {}
        stack: list[CallNode] = [root]

        while stack:
            node = stack.pop()
            nid = id(node)
            if nid in visited:
                continue
            visited.add(nid)

            addr = node.to_address
            info = self._protocol_registry.match(addr, chain_id)
            if info:
                proto_key = addr.lower()
                if proto_key not in found_protocols:
                    found_protocols[proto_key] = ProtocolInfo(
                        name=info["name"],
                        category=info["category"],
                        address=addr,
                        chain_id=chain_id,
                        confidence=1.0,
                    )
                node.label = info["name"]

            # Token 符号
            tok_sym = self._protocol_registry.get_token_symbol(addr)
            if tok_sym:
                node.token_symbol = tok_sym

            stack.extend(node.children)

        result = list(found_protocols.values())
        logger.info(f"[identify_protocols] Found {len(result)} protocols")
        return result

    def link_events(self, root: CallNode, receipt_logs: list[dict]) -> None:
        """
        将 receipt logs 中的 Events 匹配到对应的 CallNode

        这是一个启发式算法:
        根据 gasUsed 和地址匹配来关联 event 到最近的调用帧
        """
        if not receipt_logs:
            return

        # DFS 按序收集所有节点
        ordered_nodes: list[tuple[CallNode, int]] = []  # (node, start_gas)
        visited: set[int] = set()
        stack: list[tuple[CallNode, int]] = [(root, 0)]

        while stack:
            node, start_gas = stack.pop()
            nid = id(node)
            if nid in visited:
                continue
            visited.add(nid)
            ordered_nodes.append((node, start_gas))

            child_gas = 0
            for child in reversed(node.children):
                stack.append((child, start_gas + child_gas))
                child_gas += child.gas_used

        linked_count = 0
        for log_idx, log in enumerate(receipt_logs):
            decoded = self._decode_event_log(log)
            if not decoded:
                continue

            log_addr = _to_hex(log.get("address", "")).lower()

            best_node: CallNode | None = None
            best_score = -1.0

            for node, _ in ordered_nodes:
                score = 0.0
                if log_addr == node.to_address.lower():
                    score += 10
                if node.call_type == "call" and node.children:
                    score += 2
                score += node.depth * 0.5

                if score > best_score:
                    best_score = score
                    best_node = node

            if best_node:
                # 分离 EventRecord 标准字段和自定义解码字段
                ev_name = decoded.pop("name", "Unknown")
                topic0 = decoded.pop("topic0", "")
                # 剩余的 from/to/value 等放入 decoded 字段
                best_node.events.append(EventRecord(
                    name=ev_name,
                    topic0=topic0,
                    log_index=log_idx,
                    decoded=decoded,
                    raw=log,
                ))
                linked_count += 1

        logger.info(f"[link_events] Linked {linked_count}/{len(receipt_logs)} events")

    @staticmethod
    def _decode_event_log(log: dict) -> dict | None:
        """解码事件日志"""
        topics = [_to_hex(t) for t in log.get("topics", [])]
        if not topics:
            return None

        topic0 = topics[0].lower()
        event_info = _EVENT_TOPICS.get(topic0)
        if not event_info:
            return {"name": f"Unknown(0x{topic0[:8]}...)", "topic0": topic0}

        event_name, indexed_params = event_info
        decoded: dict = {"name": event_name, "topic0": topic0}

        for idx, param in enumerate(indexed_params):
            if idx + 1 < len(topics):
                # 参数格式: "address indexed from" → 取最后一个词作为字段名
                parts = param.split()
                field_name = parts[-1] if len(parts) >= 3 else parts[0]
                decoded[field_name] = "0x" + topics[idx + 1][-40:]

        data = log.get("data", "")
        data_hex = _to_hex(data)
        if data_hex and len(data_hex) > 2:
            try:
                val = int(data_hex, 16)
                decoded["value"] = f"{val:,}"
            except (ValueError, IndexError):
                pass

        return decoded

    def extract_call_transfers(self, root: CallNode) -> list:
        """
        从 call tree 中提取所有 transfer 函数调用，按调用顺序编号。
        
        用于绘制 BlockSec 风格的资金流转图。
        匹配的函数签名包括:
          - transfer(address,uint256)
          - transferFrom(address,address,uint256)
        """
        from detectors.trace.models import CallTransferItem

        TRANSFER_SIGS = {
            "transfer(address,uint256)",
            "transferfrom(address,address,uint256)",
        }
        # 也匹配已知 selector
        TRANSFER_SELECTORS = {
            "0xa9059cbb",  # transfer(address,uint256)
            "0x23b872dd",  # transferFrom(address,address,uint256)
        }

        transfers: list[CallTransferItem] = []
        order_id = 0
        visited: set[int] = set()
        stack: list[CallNode] = [root]

        while stack:
            node = stack.pop()
            nid = id(node)
            if nid in visited:
                continue
            visited.add(nid)

            sig = (node.function_signature or "").lower().strip()
            sel = (node.selector or "").lower()

            # 仅处理 CALL 类型的 transfer 调用（参考 BlockSec: DELEGATECALL 不绘制）
            if node.call_type.lower() != "call":
                stack.extend(reversed(node.children))
                continue

            if sig in TRANSFER_SIGS or sel in TRANSFER_SELECTORS:
                order_id += 1
                # 解析参数
                from_addr = ""
                to_addr = ""
                amount_raw = 0

                if node.params and len(node.params) >= 2:
                    try:
                        from_addr = _to_hex(node.params[0].value).lower()  # param_0: to (recipient for transfer)
                        to_addr = _to_hex(node.params[1].value).lower()    # param_1: amount — wait, let me re-check
                        # transfer(address,uint256): param_0=to, param_1=amount
                        # transferFrom(address,address,uint256): param_0=from, param_1=to, param_2=amount
                        if sig.startswith("transferfrom") or len(node.params) >= 3:
                            # transferFrom: params are (from, to, amount)
                            from_addr = _to_hex(node.params[0].value).lower()
                            to_addr = _to_hex(node.params[1].value).lower()
                            amt_str = node.params[2].value.replace(",", "") if len(node.params) >= 3 else "0"
                        else:
                            # transfer: params are (to, amount), from is the caller
                            from_addr = node.from_address.lower()  # msg.sender calling transfer
                            to_addr = _to_hex(node.params[0].value).lower()
                            amt_str = node.params[1].value.replace(",", "") if len(node.params) >= 2 else "0"

                        amount_raw = int(amt_str) if amt_str else 0
                    except (ValueError, IndexError):
                        amount_raw = 0

                    # 格式化金额
                    decimals = self._protocol_registry.get_token_decimals(
                        node.to_address
                    )
                    divisor = 10 ** (decimals or 18)
                    if amount_raw > 0:
                        formatted = f"{amount_raw / divisor:.4f}"
                        # 千分位格式化整数部分
                        parts = formatted.split(".")
                        if len(parts) == 2:
                            int_part = float(parts[0])
                            formatted = (
                                f"{int(int_part):,}.{parts[1]}"
                                if int_part >= 10000
                                else formatted
                            )
                    else:
                        formatted = "0"

                    token_sym = (
                        self._protocol_registry.get_token_symbol(node.to_address)
                        or ""
                    )

                    transfers.append(CallTransferItem(
                        order_id=order_id,
                        from_address=from_addr,
                        to_address=to_addr,
                        amount=amount_raw,
                        amount_formatted=formatted,
                        value=node.value,
                        token_symbol=token_sym,
                        token_address=node.to_address,
                        function_signature=node.function_signature or "",
                        selector=node.selector,
                        depth=node.depth,
                        trace_address=list(node.trace_address),
                        caller_contract=node.to_address,
                    ))

            stack.extend(reversed(node.children))

        logger.info(f"[call_transfers] Extracted {len(transfers)} transfer calls")
        return transfers

    def extract_token_flows(self, root: CallNode) -> list[TokenFlowItem]:
        """
        从调用树中提取所有 Token 流转记录，按事件出现顺序排列（仿 BlockSec Fund Flow）。

        数据来源: node.events 中关联的 Transfer 事件
        排序依据: logIndex（receipt logs 原始顺序）
        输出: 按从上到下的调用/事件顺序排列的流转列表
        """
        flows: list[tuple[int, TokenFlowItem]] = []  # (log_index, flow) 用于排序

        # BFS 遍历收集所有 Transfer 事件
        visited: set[int] = set()
        queue = [root]
        while queue:
            node = queue.pop(0)  # FIFO — 保持调用树从上到下顺序
            nid = id(node)
            if nid in visited:
                continue
            visited.add(nid)

            for ev in node.events:
                if ev.name != "Transfer" or "value" not in ev.decoded:
                    continue

                from_addr = ev.decoded.get("from", "")
                to_addr = ev.decoded.get("to", "")
                amount_str = ev.decoded.get("value", "0")
                try:
                    amount = int(amount_str.replace(",", ""))
                except ValueError:
                    amount = 0
                if amount == 0:
                    continue

                token_addr = _to_hex(ev.raw.get("address", "") if ev.raw else "")
                if not token_addr:
                    continue

                # 获取代币信息
                token_sym = (
                    self._protocol_registry.get_token_symbol(token_addr)
                    or "UNKNOWN"
                )
                dec = self._protocol_registry.get_token_decimals(token_addr) or 18
                divisor = 10 ** dec

                # 格式化金额
                raw_fmt = f"{amount / divisor:.4f}"
                parts = raw_fmt.split(".")
                if len(parts) == 2 and float(parts[0]) >= 10000:
                    raw_fmt = f"{int(float(parts[0])):,}.{parts[1]}"
                elif len(parts) == 2 and int(float(parts[0])) > 0:
                    raw_fmt = f"{int(float(parts[0])):,}.{parts[1]}"

                # 判断方向: 收入(to=root地址) / 支出(其他)
                is_incoming = to_addr.lower() == root.to_address.lower()

                flow = TokenFlowItem(
                    token_address=token_addr,
                    token_symbol=token_sym,
                    decimals=dec,
                    amount_raw=amount,
                    amount_formatted=raw_fmt,
                    direction="in" if is_incoming else "out",
                    from_label=(
                        self._protocol_registry.get_label(from_addr)
                        or shorten_addr(from_addr)
                    ),
                    to_label=(
                        self._protocol_registry.get_label(to_addr)
                        or shorten_addr(to_addr)
                    ),
                    from_address=from_addr.lower(),
                    to_address=to_addr.lower(),
                )
                flows.append((ev.log_index, flow))

            queue.extend(node.children)

        # 按 log_index 排序，确保与 BlockSec 一致的从上到下顺序
        flows.sort(key=lambda x: x[0])
        return [f for _, f in flows]

    async def compute_balance_changes(
        self,
        root: CallNode,
        tx_from: str,
        tx_to_addr: str | None,
        receipt_logs: list[dict] | None = None,
        chain_id: int = 1,
    ) -> list[BalanceChangeItem]:
        """
        计算每个地址在每个 Token/ETH 上的净余额变化 (仿 BlockSec Balance Changes)

        数据来源:
          1. ETH 余额变化: 从 trace 中每帧的 value 字段汇总 (from 支出, to 收入)
          2. ERC20 余额变化: 优先从 receipt_logs 原始数据提取 (可靠),
             兜底从 node.events 提取 (可能因启发式匹配丢失)
          3. USD 估值: 通过 TokenPriceCache 从 MarketDataBase 获取实时价格
        """
        from collections import defaultdict

        # key = (address_lower, token_address_lower) -> net amount in wei/raw units
        balances: dict[tuple[str, str], int] = defaultdict(int)
        # token_address -> {symbol, decimals, price_usd, logo_url}
        token_info: dict[str, dict] = {}

        # ── 1. ETH 余额变化: 遍历所有 trace 帧的 value ──
        visited: set[int] = set()
        stack: list[CallNode] = [root]
        while stack:
            node = stack.pop()
            nid = id(node)
            if nid in visited:
                continue
            visited.add(nid)

            if node.value > 0:
                fr = node.from_address.lower()
                to = node.to_address.lower()
                balances[(fr, "")] -= node.value   # ETH key: token_addr=""
                balances[(to, "")] += node.value

            stack.extend(node.children)

        # ── 2. ERC20 余额变化 ──

        # 2a) 优先从原始 receipt_logs 直接解码 Transfer 事件（最可靠）
        erc20_from_logs = self._extract_erc20_balances(receipt_logs or [])
        for (addr, tok_addr), amount in erc20_from_logs.items():
            if amount == 0:
                continue
            balances[(addr, tok_addr)] += amount
            if tok_addr and tok_addr not in token_info:
                sym = self._protocol_registry.get_token_symbol(tok_addr) or ""
                dec = self._protocol_registry.get_token_decimals(tok_addr)
                token_info[tok_addr] = {"symbol": sym, "decimals": dec}

        # NOTE: 不再从 node.events 补充提取 ERC20 余额变化。
        # node.events 由 link_events() 从同一批 receipt_logs 生成，
        # _extract_erc20_balances(2a) 已完整覆盖所有 Transfer 日志，
        # 若再遍历 node.events 会导致同一事件被重复计数（数值翻倍）。

        # ── 3. 批量获取代币价格（用于 USD 估值） ──
        price_map: dict[str, float] = {}  # token_address_lower -> price_usd
        native_price: float | None = None  # 原生代币价格
        native_logo: str | None = None     # 原生代币 logo URL

        # 收集所有涉及的 token 地址（排除 ETH，用空串表示）
        involved_tokens: list[str] = [
            tok_addr for (addr, tok_addr), net in balances.items()
            if tok_addr and net != 0
        ]

        # 判断是否有 ETH 余额变化
        has_eth_change = any(
            tok_addr == "" and net != 0
            for (addr, tok_addr), net in balances.items()
        )

        if involved_tokens or has_eth_change:
            try:
                from detectors.trace.token_price_cache import get_token_price_cache
                cache = get_token_price_cache()
                meta_results = await cache.batch_fetch(
                    chain_id=chain_id,
                    addresses=[t.lower() for t in set(involved_tokens)],
                    include_native=has_eth_change,
                )

                # 更新 symbol/decimals/price/logo 信息
                for addr, meta in meta_results.items():
                    if not addr:
                        # 原生代币 (key="")
                        native_price = meta.price_usd
                        native_logo = getattr(meta, 'logo_url', None)
                        continue
                    addr_lower = addr.lower()
                    existing = token_info.get(addr_lower, {})
                    if meta.symbol:
                        existing["symbol"] = meta.symbol
                    if meta.decimals:
                        existing["decimals"] = meta.decimals
                    if meta.price_usd is not None:
                        existing["price_usd"] = float(meta.price_usd)
                    if getattr(meta, 'logo_url', None):
                        existing["logo_url"] = meta.logo_url
                    token_info[addr_lower] = existing
                    if meta.price_usd is not None:
                        price_map[addr_lower] = float(meta.price_usd)

                logger.info(
                    f"[balance_changes] Price lookup: "
                    f"{len(meta_results)} tokens, {len(price_map)} with prices, "
                    f"native_price={'%.2f' % native_price if native_price else 'N/A'}"
                )
            except Exception as e:
                logger.warning(f"[balance_changes] Failed to fetch prices: {e}")

        # ── 4. 构建结果列表, 过滤掉 0 变化项 ──
        results: list[BalanceChangeItem] = []

        for (addr, tok_addr), net_amount in sorted(balances.items()):
            if net_amount == 0:
                continue

            if not tok_addr:
                # ETH (原生代币)
                symbol = "ETH"
                decimals = 18
                formatted = _format_eth_change(net_amount)
                value_usd = round(net_amount / 1e18 * (native_price or 0), 2) if native_price else None
                item_price_usd = native_price
                item_logo_url = native_logo
            else:
                info = token_info.get(tok_addr, {})
                symbol = info.get("symbol") or ""
                if not symbol:
                    symbol = shorten_addr(tok_addr, width=10).upper()
                decimals = info.get("decimals", 18)
                divisor = 10 ** decimals
                formatted = f"{net_amount / divisor:.4f}"
                token_lower = tok_addr.lower()
                token_price = price_map.get(token_lower)
                value_usd = round(net_amount / divisor * (token_price or 0), 2) if token_price else None
                item_price_usd = info.get("price_usd")
                item_logo_url = info.get("logo_url")

            label = self._protocol_registry.get_label(addr) or shorten_addr(addr)

            results.append(BalanceChangeItem(
                address=addr,
                address_label=label,
                token_address=tok_addr,
                token_symbol=symbol,
                decimals=decimals,
                amount_raw=net_amount,
                amount_formatted=formatted,
                value_usd=value_usd or 0.0,
                price_usd=item_price_usd,
                logo_url=item_logo_url,
            ))

        logger.info(f"[balance_changes] Computed {len(results)} entries")
        return results

    async def _enrich_token_symbols(self, root: CallNode, chain_id: int) -> None:
        """
        用动态数据源补全 CallNode 的 tokenSymbol。

        identify_protocols() 只查询静态 _TOKEN_SYMBOLS 表，
        很多代币（如 USR、自定义 ERC20）不在其中，导致 call tree 中
        显示原始地址而非代币符号。

        本方法通过 TokenPriceCache (MarketDataBase) 动态获取 symbol，
        回填到尚未设置 tokenSymbol 的节点上。
        """
        # 1. 收集所有 to_address（排除已有 label 或 token_symbol 的节点）
        unknown_addrs: set[str] = set()
        node_by_addr: dict[str, list[CallNode]] = {}
        visited: set[int] = set()
        stack: list[CallNode] = [root]

        while stack:
            node = stack.pop()
            nid = id(node)
            if nid in visited:
                continue
            visited.add(nid)

            # 只处理没有 label 且没有 token_symbol 的节点
            if (not node.label and not node.token_symbol
                    and node.to_address
                    and len(node.to_address) == 42):
                addr_lower = node.to_address.lower()
                unknown_addrs.add(addr_lower)
                node_by_addr.setdefault(addr_lower, []).append(node)

            stack.extend(reversed(node.children))

        if not unknown_addrs:
            return

        # 2. 批量从 TokenPriceCache 获取元数据
        try:
            from detectors.trace.token_price_cache import get_token_price_cache
            cache = get_token_price_cache()
            meta_results = await cache.batch_fetch(
                chain_id=chain_id,
                addresses=list(unknown_addrs),
                include_native=False,
            )

            enriched_count = 0
            for addr_lower, meta in meta_results.items():
                if not addr_lower or not getattr(meta, 'symbol', None):
                    continue
                for node in node_by_addr.get(addr_lower, []):
                    node.token_symbol = meta.symbol
                    enriched_count += 1

            logger.info(
                f"[enrich_token] Enriched {enriched_count}/{len(unknown_addrs)} "
                f"nodes with dynamic token symbols"
            )
        except Exception as e:
            logger.warning(f"[enrich_token] Failed to enrich token symbols: {e}")

    @staticmethod
    def _extract_erc20_balances(receipt_logs: list[dict]) -> dict[tuple[str, str], int]:
        """直接从 receipt logs 解码 ERC20 Transfer 事件，返回 {(addr, token_addr): net_amount}"""
        from collections import defaultdict
        balances: dict[tuple[str, str], int] = defaultdict(int)

        transfer_topic0 = (
            "0xddf252ad1be2c89b69c2b068fc378daa952ba7"
            "f163c4a11628f55a4df523b3ef"
        )

        for log in receipt_logs:
            topics = log.get("topics") or []
            if len(topics) < 3:
                continue
            topic0 = _to_hex(topics[0]).lower()
            if topic0 != transfer_topic0:
                continue

            # 解码 from / to (indexed params in topics[1], topics[2])
            fr = "0x" + _to_hex(topics[1])[-40:].lower()
            to = "0x" + _to_hex(topics[2])[-40:].lower()

            # 解码 value (non-indexed data field)
            data_hex = _to_hex(log.get("data", "0x"))
            try:
                amount = int(data_hex, 16) if data_hex and len(data_hex) > 2 else 0
            except (ValueError, OverflowError):
                amount = 0

            if amount == 0:
                continue

            tok_addr = _to_hex(log.get("address", "")).lower()

            balances[(fr, tok_addr)] -= amount
            balances[(to, tok_addr)] += amount

        return dict(balances)

    # ===================================================================
    # 可被子类覆盖的钩子
    # ===================================================================

    async def detect_behaviors(
        self, root: CallNode, tx_info: TransactionInfo
    ) -> list[BehaviorResult]:
        """
        行为检测钩子 — 默认返回空列表

        子类 (FlashLoanDetector 等) 重写此方法添加具体检测逻辑
        """
        return []

    async def pre_analyze(self, tx_hash: str, chain_id: int) -> None:
        """分析前钩子 — 可用于预热缓存等"""

    def post_analyze(self, result: FullAnalysisResult) -> FullAnalysisResult:
        """分析后钩子 — 可用于补充额外数据"""
        return result

    # ===================================================================
    # 结果组装
    # ===================================================================

    def assemble_result(
        self,
        root: CallNode,
        tx_hash: str,
        chain_id: int,
        tx_detail: dict,
        receipt: dict,
        behaviors: list[BehaviorResult],
        protocols: list[ProtocolInfo],
        token_flows: list[TokenFlowItem],
        call_transfers: list = None,
        balance_changes: list[BalanceChangeItem] | None = None,
        raw_trace_count: int = 0,
        elapsed: float = 0.0,
    ) -> FullAnalysisResult:
        """组装最终的分析结果对象"""

        total_nodes = count_nodes(root)
        max_depth = get_max_depth(root)
        total_events = count_events(root)

        # 统计 selector 调用次数
        selector_stats = compute_selector_stats(root)

        tx_info = self._build_tx_info(tx_hash, chain_id, tx_detail, receipt)

        meta = {
            "totalNodes": total_nodes,
            "maxDepth": max_depth,
            "totalEvents": total_events,
            "rawTraceCount": raw_trace_count,
            "elapsedSeconds": round(elapsed, 3),
            "analyzedAt": int(__import__("time").time()),
        }

        return FullAnalysisResult(
            meta=meta,
            tx_info=tx_info,
            root=root,
            behaviors=behaviors,
            protocols=protocols,
            token_flows=token_flows,
            call_transfers=call_transfers or [],
            balance_changes=balance_changes or [],
            selector_stats=selector_stats,
        )

    def _build_tx_info(
        self,
        tx_hash: str,
        chain_id: int,
        tx_detail: dict,
        receipt: dict,
    ) -> TransactionInfo:
        """从 RPC 返回值构建 TransactionInfo"""
        status_raw = receipt.get("status", "0x1")
        return TransactionInfo(
            tx_hash=tx_hash,
            chain_id=chain_id,
            block_number=int(receipt.get("blockNumber", "0x0"), 16),
            from_address=_to_hex(tx_detail.get("from", "")).lower(),
            to_address=(
                _to_hex(tx_detail.get("to")).lower() if tx_detail.get("to") else None
            ),
            value=int(tx_detail.get("value", "0x0"), 16)
            if tx_detail.get("value") else 0,
            gas_used=int(receipt.get("gasUsed", "0x0"), 16)
            if receipt.get("gasUsed") else 0,
            gas_limit=int(tx_detail.get("gas", "0x0"), 16)
            if tx_detail.get("gas") else 0,
            gas_price=int(tx_detail.get("gasPrice", "0x0"), 16)
            if tx_detail.get("gasPrice") else 0,
            status=status_raw == "0x1" or status_raw == 1,
        )

    async def close(self) -> None:
        """关闭资源"""
        await self._rpc_client.close()
        self._signature_db.close()


# ================================================================
# 工具函数
# ================================================================


def _to_hex(data) -> str:
    """统一转为 hex 字符串"""
    if isinstance(data, bytes):
        return "0x" + data.hex()
    if isinstance(data, str):
        return data if data.startswith("0x") else "0x" + data
    if data is None:
        return "0x"
    return "0x" + format(int(data), "x")


def shorten_addr(addr: str, width: int = 12) -> str:
    """缩短地址显示"""
    h = _to_hex(addr).lower()
    if len(h) > width:
        return h[:width] + "..."
    return h


def _format_eth_change(amount_wei: int) -> str:
    """格式化 ETH 余额变化, 如 '+13.9000' 或 '+1,211.0544'"""
    if amount_wei == 0:
        return "0"
    divisor = 1e18
    val = abs(amount_wei) / divisor
    # 使用千分位逗号分隔，不进行额外的数量级缩放（避免差 1000x 的错误）
    if val >= 1e6:
        s = f"{val:,.4f}"
    elif val >= 1e3:
        s = f"{val:,.4f}"
    else:
        s = f"{val:.4f}"
    prefix = "+" if amount_wei > 0 else "-"
    return f"{prefix}{s}"


def count_nodes(node: CallNode) -> int:
    """迭代式计算节点总数"""
    total = 0
    stack = [node]
    visited = set()
    while stack:
        n = stack.pop()
        nid = id(n)
        if nid in visited:
            continue
        visited.add(nid)
        total += 1
        stack.extend(n.children)
    return total


def get_max_depth(node: CallNode) -> int:
    """迭代式计算最大深度"""
    max_d = 0
    stack: list[tuple[CallNode, int]] = [(node, 0)]
    visited = set()
    while stack:
        n, d = stack.pop()
        nid = id(n)
        if nid in visited:
            continue
        visited.add(nid)
        max_d = max(max_d, d)
        for c in n.children:
            stack.append((c, d + 1))
    return max_d


def count_events(node: CallNode) -> int:
    """迭代式统计事件数"""
    total = 0
    stack = [node]
    visited = set()
    while stack:
        n = stack.pop()
        nid = id(n)
        if nid in visited:
            continue
        visited.add(nid)
        total += len(n.events)
        stack.extend(n.children)
    return total


def compute_selector_stats(root: CallNode) -> list[dict]:
    """
    计算每个 selector 的调用统计
    Returns: [{"selector":"...", "sig":"...", "count":N}, ...]
    """
    counter: dict[str, tuple[str | None, int]] = {}
    stack = [root]
    visited = set()

    while stack:
        n = stack.pop()
        nid = id(n)
        if nid in visited:
            continue
        visited.add(nid)
        if n.selector:
            existing = counter.get(n.selector)
            if existing:
                _, cnt = existing
                counter[n.selector] = (existing[0], cnt + 1)
            else:
                counter[n.selector] = (n.function_signature, 1)
        stack.extend(n.children)

    stats = [
        {"selector": sel, "sig": sig or "unknown", "count": cnt}
        for sel, (sig, cnt) in sorted(counter.items(), key=lambda x: -x[1][1])
    ]
    return stats
