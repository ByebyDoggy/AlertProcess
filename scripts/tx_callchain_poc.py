"""
交易调用链分析器 - 概念验证 (PoC)
=====================================
参考 BlockSec Phalcon Explorer 的 Invocation Flow 功能:
https://app.blocksec.com/phalcon/explorer/tx/bsc/{hash}

核心能力:
1. 通过 debug_traceTransaction / trace_transaction 获取完整调用链
2. 将 flat trace 构建为树形结构
3. 通过 4-byte selector 解析函数签名 (使用 openchain / 4bytes 在线索引)
4. 解码 ERC20 标准方法的参数
5. 捕获并关联 Events 到对应调用节点
6. 输出结构化 JSON + 终端可视化

用法:
    python scripts/tx_callchain_poc.py
    python scripts/tx_callchain_poc.py --tx 0x85ac5d15f16d49ae08f90ab0e554ebfcb145712342c5b7704e305d602146d452 --chain bsc
"""

import json
import argparse
import time
import httpx
import sys
import io
from typing import Optional

# Windows 终端强制 UTF-8 输出
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ============================================================
# 配置区
# ============================================================
CHAIN_CONFIG = {
    "bsc": {
        "rpc": [
            "https://bsc-dataseed1.binance.org",
            "https://bsc-dataseed.binance.org/",
            "https://rpc.ankr.com/bsc",
        ],
        "explorer": "https://api.bscscan.com/api",
        "name": "BSC",
    },
    "eth": {
        "rpc": [
            "https://ethereum-rpc.publicnode.com",
            "https://rpc.ankr.com/eth",
            "https://eth.llamarpc.com",
        ],
        "explorer": "https://api.etherscan.io/api",
        "name": "Ethereum",
    },
}

# 默认分析的交易 (以太坊上一个复杂的 Uniswap 交易)
DEFAULT_TX = "0xc310a0affe2169d1f6feec1c63dbc7f7c62a887fa48795d327d4d2da2d6b111d"
DEFAULT_CHAIN = "eth"

# 4-byte selector -> 函数签名映射 (常用标准方法)
# 生产环境应通过 https://www.4byte.directory/api/v1/signatures/?hex_signature=0xXXXXXX 动态查询
KNOWN_SELECTORS = {
    # ERC20 Standard
    "0xa9059cbb": ("transfer(address,uint256)", ["address to", "uint256 value"]),
    "0x23b872dd": ("transferFrom(address,address,uint256)", [
        "address from", "address to", "uint256 value"
    ]),
    "0x095ea7b3": ("approve(address,uint256)", ["address spender", "uint256 value"]),
    "0x70a08231": ("balanceOf(address)", ["address account"]),
    "0x18160ddd": ("totalSupply()", []),
    "0xdd62ed3e": ("allowance(address,address)", ["address owner", "address spender"]),
    # Uniswap V2 / PancakeSwap Router
    "0x38ed1739": ("swapExactTokensForTokens(uint256,uint256,address[],address,uint256)", [
        "uint256 amountIn", "uint256 amountOutMin", "address[] path",
        "address to", "uint256 deadline"
    ]),
    "0x18cbafe5": ("swapExactTokensForETH(uint256,uint256,address[],address,uint256)", [
        "uint256 amountIn", "uint256 amountOutMin", "address[] path",
        "address to", "uint256 deadline"
    ]),
    "0x7ff36ab5": ("swapExactETHForTokens(uint256[],address[],address,uint256)", [
        "uint256[] amountOutMin", "address[] path", "address to", "uint256 deadline"
    ]),
    "0xe8e33700": ("addLiquidity(address,address,uint256,uint256,uint256,uint256,address,uint256)", [
        "address tokenA", "address tokenB", "uint256 amountADesired",
        "uint256 amountBDesired", "uint256 amountAMin", "uint256 amountBMin",
        "address to", "uint256 deadline"
    ]),
    "0xf305d719": ("addLiquidityETH(address,uint256,uint256,uint256,address,uint256)", [
        "address token", "uint256 amountTokenDesired", "uint256 amountTokenMin",
        "uint256 amountETHMin", "address to", "uint256 deadline"
    ]),
    "0xbaa2abde": ("removeLiquidity(address,address,uint256,uint256,uint256,address,uint256)", [...]),
    "0x02751cec": ("removeLiquidityETH(address,uint256,uint256,uint256,address,uint256)", [...]),
    "0x21959995": ("removeLiquidityWithPermit(...)", [...]),
    "0xaf2979eb": ("removeLiquidityETHWithPermit(...)", [...]),
    "0x5ae401dc": ("removeLiquidityETHSupportingFeeOnTransferTokens(...)", [...]),
    # Uniswap V2 Pair
    "0xa6752b57": ("skim(address to)", ["address to"]),
    "0x128acb08": ("sync()", []),
    # WBNB / WETH
    "0xd0e30db0": ("deposit()", []),
    "0x2e1a7d4d": ("withdraw(uint256)", ["uint256 amount"]),
    # Uniswap V3
    "0x04e45aaf": ("exactInput((bytes,address,uint256,uint256,uint256))", ["struct ExactInputSingleParams params"]),
    "0x414bf389": ("exactInputSingle((address,uint24,address,uint256,uint256,uint256))", [
        "struct ExactInputSingleParams params"
    ]),
    "0xdb3e2198": ("exactOutput((bytes,address,uint256,uint256))", ["struct ExactOutputParams params"]),
    "0xb858183f": ("exactInputSingle(...)", [...]),
    # PancakeSwap Smart Router
    "0x04e45aaf": ("exactInput(bytes)", ["bytes pathData"]),
    "0xc04b8d59": ("exactInputSingle(...)", [...]),
    "0xf28c0498": ("exactInputSingleSupportingFeeOnTransferTokens(...)", [...]),
    "0x5023b4df": ("exactOutputSingle(...)", [...]),
    # Flash Loan / Lending
    "0x8afff657": ("flashLoan(address,address,uint256,bytes,uint16)", [
        "address receiverAddress", "address asset", "uint256 amount",
        "bytes params", "uint16 referralCode"
    ]),
    "0xa5215b6a": ("flashLoanSimple(address,address,uint256,uint16)", [
        "address receiverAddress", "address asset", "uint256 amount", "uint16 referralCode"
    ]),
    # Aave Pool
    "0x9e9623cd": ("supply(address,uint256,address,uint16)", [
        "address asset", "uint256 amount", "address onBehalfOf", "uint16 referralCode"
    ]),
    "0x41c728b9": ("withdraw(address,uint256,address)", [
        "address asset", "uint256 amount", "address to"
    ]),
    "0xa15cc3a3": ("repay(address,uint256,uint256,address)", [
        "address asset", "uint256 amount", "uint256 rateMode", "address onBehalfOf"
    ]),
    "0x4a58c4c4": ("borrow(address,uint256,uint256,uint16,address)", [
        "address asset", "uint256 amount", "uint256 interestRateMode",
        "uint16 referralCode", "address onBehalfOf"
    ]),
    # Multicall
    "0xac9650d8": ("multicall(bytes[])", ["bytes[] data"]),
    "0x5ae401dc": ("multicall(uint256,bytes[])", ["uint256 deadline", "bytes[] data"]),
    # Generic patterns
    "0x00000000": ("[Ether Transfer / Fallback]", []),
}

# 已知协议地址标签 (BSC)
KNOWN_LABELS_BSC = {
    "0x10ED43C718714eb63d5aA57B78B54704E256024E": "PancakeSwap: Router V2",
    "0x13f4EA83D0bd40E75C8222255bc855a974568Dd4": "PancakeSwap: WBNB",
    "0x55D398326f99059fF775485246999027B3197955": "USDT",
    "0x2170Ed0880ac9A755fd29B2688956BD959F933F8": "WETH",
    "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c": "WBNB",
    "0xE14fb593eE2f0B2f2f3b519b27A05bf0e66eA3e0": "PancakeSwap: MasterChef",
    "0x0Ed7e52944161450477ee417DE9Cd3a859b14Fd0": "PancakeSwap: MiniChefV2",
    "0x1b81D678ffb9C0263b24A97847620C99d213eB14": "PancakeSwap: Smart Router",
    "0x111111125421ca6dc452d289314280a0f8842a65": "1inch: SwapRouter",
    "0x1111111254eeb25477b68fb85ed929f73a960582": "1inch: SwapRouter v5",
    "0x05ff2b0db69458A0750badebc4f9e13add608c7f": "PancakeSwap: Smart Router",
}

# 已知协议地址标签 (以太坊 Mainnet)
KNOWN_PROTOCOLS = {
    "0x7a250d5630b4cf539739df2c5dacb4c659f2488d": "Uniswap V2 Router 02",
    "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45": "Uniswap V3 Router 02",
    "0xe592427a0aece92de3edee1f18e0157c05861564": "Uniswap V3 Router 01",
    "0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad": "Uniswap Universal Router",
    "0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2": "Aave V3 Pool",
    "0x7d2768de32b0b80b7a3454c06bdac94a69ddc7a9": "Aave V3 Pool (old)",
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": "WETH9",
    "0x5c2ed810328349100a66b82b0192e35303d9479a": "1inch V5 AggregationRouter",
    "0xba12222222228d8ba445958a75a0704d566bf2c8": "Balancer V2 Vault",
    "0x99a58482bd75cbab83b27ec03ca68ff489b5788f": "Curve 1Pool",
}

# 常用 Token 符号 (BSC)
TOKEN_SYMBOLS_BSC = {
    "0x55d398326f99059ff775485246999027b3197955": "USDT",
    "0x2170ed0880ac9a755fd29b2688956bd959f933f8": "WETH",
    "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c": "WBNB",
    "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d": "USDC",
    "0xe9e7cea3dedca5984780bafc599bd69add087d56": "BUSDT",
    "0x2170ed0880ac9a755fd29b2688956bd959f933f8": "ETH",
}

# Event Topic Hashes
EVENT_TOPICS = {
    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef": (
        "Transfer", ["address indexed from", "address indexed to", "uint256 value"]
    ),
    "0x8c5be1e5ebec7d5bd14f7f27da2898506d9e09ccf5c36a18b47b4dd681bc0b41": (
        "Approval", ["address indexed owner", "address indexed spender", "uint256 value"]
    ),
}


# ============================================================
# 工具函数
# ============================================================

def to_hex(data) -> str:
    """统一转为 hex 字符串"""
    if isinstance(data, bytes):
        return "0x" + data.hex()
    if isinstance(data, str):
        return data if data.startswith("0x") else "0x" + data
    return "0x" + format(int(data), "x")


def shorten(addr: str, width: int = 10) -> str:
    """缩短地址显示"""
    addr = to_hex(addr).lower()
    if len(addr) > width:
        return addr[:width] + "..."
    return addr


def get_label(chain: str, address: str) -> str | None:
    """获取地址的协议/合约标签"""
    addr_lower = to_hex(address).lower()
    if chain == "bsc":
        return KNOWN_LABELS_BSC.get(addr_lower)
    elif chain == "eth":
        return KNOWN_PROTOCOLS.get(addr_lower)  # 复用 query_tx.py 中的协议库
    return None


def resolve_selector(selector_hex: str) -> tuple[str, list[str]] | None:
    """
    通过 4-byte selector 解析函数签名
    返回: (函数签名, 参数名列表) 或 None
    """
    sel = to_hex(selector_hex)[:10].lower() if len(to_hex(selector_hex)) >= 10 else ""
    if not sel:
        return None

    # 先查本地字典
    if sel in KNOWN_SELECTORS:
        sig, param_names = KNOWN_SELECTORS[sel]
        return (sig, param_names)

    # TODO: 可扩展为远程查询 4byte.directory API
    # response = httpx.get(f"https://www.4byte.directory/api/v1/signatures/?hex_signature={sel}")
    # ...

    return None


def decode_params(input_data: str, param_names: list[str]) -> dict:
    """
    简单参数解码 - 仅处理基本类型
    生产环境应使用 eth-abi 或类似库做完整解码
    """
    result = {}
    hex_str = to_hex(input_data)
    # 跳过 4-byte selector
    data_part = hex_str[10:] if len(hex_str) >= 10 else ""

    offset = 0
    for i, pname in enumerate(param_names):
        if offset + 64 > len(data_part):
            break
        raw = data_part[offset:offset + 64]
        ptype = pname.split()[-1] if " " in pname else pname

        try:
            val_int = int(raw, 16)
            if ptype == "address":
                result[pname] = "0x" + raw[-40:]
            elif ptype.startswith("uint") or ptype.startswith("int"):
                if val_int > 1e15:
                    result[pname] = f"{val_int:,}"
                elif val_int < 1e9:
                    result[pname] = str(val_int)
                else:
                    result[pname] = str(val_int)
            elif ptype == "bool":
                result[pname] = True if val_int else False
            elif ptype == "bytes":
                result[pname] = "0x" + raw
            else:
                result[pname] = raw
        except ValueError:
            result[pname] = raw

        offset += 64

        # 处理动态类型数组 (简化: 跳过)
        if "[]" in pname or ptype.startswith("bytes"):
            # 动态类型的实际数据在 offset 指向的位置，这里做简单跳过
            pass

    return result


def decode_event_log(log: dict) -> dict | None:
    """解码事件日志"""
    topics = [to_hex(t) for t in log.get("topics", [])]
    if not topics:
        return None

    topic0 = topics[0]
    event_info = EVENT_TOPICS.get(topic0.lower())
    if not event_info:
        return {"name": f"Unknown(0x{topic0[:8]}...)"}

    event_name, indexed_params = event_info
    decoded = {"name": event_name}
    for idx, param in enumerate(indexed_params):
        if "indexed" in param and idx + 1 < len(topics):
            decoded[param.split()[0]] = "0x" + topics[idx + 1][-40:]

    # 非索引数据 (简化处理)
    data = log.get("data", "")
    if data and len(to_hex(data)) > 2:
        try:
            val = int(to_hex(data), 16)
            if "value" in indexed_params[-1]:
                decoded["value"] = f"{val:,}"
        except (ValueError, IndexError):
            pass

    return decoded


# ============================================================
# RPC 客户端
# ============================================================

class TxAnalyzer:
    def __init__(self, chain: str = DEFAULT_CHAIN):
        self.chain = chain
        config = CHAIN_CONFIG.get(chain, CHAIN_CONFIG["bsc"])
        self.rpc_urls = config["rpc"] if isinstance(config["rpc"], list) else [config["rpc"]]
        self.client = httpx.Client(timeout=30.0)
        self.request_id = 0
        self._current_rpc_idx = 0

    @property
    def rpc_url(self):
        return self.rpc_urls[self._current_rpc_idx % len(self.rpc_urls)]

    def _switch_rpc(self):
        """切换到下一个 RPC 节点"""
        self._current_rpc_idx += 1
        print(f"    [!] Switching to RPC #{self._current_rpc_idx}: {self.rpc_url}")

    def _rpc_call(self, method: str, params: list, retry_count: int = 0) -> dict:
        """发送 JSON-RPC 请求，支持多节点自动切换"""
        max_retries = len(self.rpc_urls)
        for attempt in range(max_retries):
            try:
                url = self.rpc_urls[(self._current_rpc_idx + attempt) % len(self.rpc_urls)]
                self.request_id += 1
                payload = {
                    "jsonrpc": "2.0",
                    "method": method,
                    "params": params,
                    "id": self.request_id,
                }
                resp = self.client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                if "error" in data:
                    raise RuntimeError(f"RPC Error: {data['error']}")
                return data.get("result")
            except Exception as e:
                print(f"    [!] RPC attempt {attempt+1}/{max_retries} failed ({url[:40]}...): {e}")
                if attempt < max_retries - 1:
                    continue
                raise

    def get_transaction(self, tx_hash: str) -> dict:
        """获取交易基本信息"""
        return self._rpc_call("eth_getTransactionByHash", [tx_hash])

    def get_receipt(self, tx_hash: str) -> dict:
        """获取交易收据"""
        return self._rpc_call("eth_getTransactionReceipt", [tx_hash])

    def trace_transaction(self, tx_hash: str) -> list:
        """
        获取交易的完整调用追踪
        使用 debug_traceTransaction 或 trace_transaction (取决于节点支持)
        """
        # 优先尝试 trace_transaction (OpenEthereum / Erigon / BSC 支持)
        try:
            result = self._rpc_call("trace_transaction", [tx_hash])
            if result is not None:
                return result
        except Exception:
            pass

        # 尝试 debug_traceTransaction (Geth)
        try:
            tracer_config = {
                "tracer": "callTracer",
                "tracerConfig": {"withLog": True},
            }
            result = self._rpc_call(
                "debug_traceTransaction", [tx_hash, tracer_config]
            )
            if isinstance(result, dict):
                return [result]
            return result or []
        except Exception as e:
            print(f"[WARN] trace failed: {e}")
            return []


# ============================================================
# 调用链构建器
# ============================================================

class CallTreeNode:
    """调用树节点"""

    def __init__(self, trace_entry: dict, depth: int = 0):
        action = trace_entry.get("action", {})
        result = trace_entry.get("result", {})

        self.depth = depth
        self.trace_address = trace_entry.get("traceAddress", [])
        self.call_type = action.get("callType", trace_entry.get("type", "?"))
        self.from_addr = to_hex(action.get("from", ""))
        self.to_addr = to_hex(action.get("to", action.get("address", "")))
        self.input_data = to_hex(action.get("input", "0x"))
        self.value = int(action.get("value", "0x0"), 16) if action.get("value") else 0
        self.gas = int(action.get("gas", "0x0"), 16) if action.get("gas") else 0
        self.gas_used = int(result.get("gasUsed", "0x0"), 16) if result.get("gasUsed") else 0
        self.output_data = to_hex(result.get("output", ""))
        self.error = result.get("error")
        self.created_address = to_hex(result.get("address", ""))

        # 子节点
        self.children: list["CallTreeNode"] = []

        # 关联的事件
        self.events: list[dict] = []

        # 解析后的信息 (lazy init)
        self._selector_resolved = False
        self._function_sig = None
        self._decoded_params = None
        self._label = None
        self._token_symbol = None

    @property
    def selector(self) -> str:
        return self.input_data[:10] if len(self.input_data) >= 10 else ""

    @property
    def is_create(self) -> bool:
        return self.call_type in ("create", "") and self.created_address

    @property
    def is_delegatecall(self) -> bool:
        return self.call_type == "delegatecall"

    @property
    def is_staticcall(self) -> bool:
        return self.call_type == "staticcall"

    @property
    def is_call(self) -> bool:
        return self.call_type == "call"

    def resolve(self, chain: str):
        """解析 selector 和地址标签"""
        if self._selector_resolved:
            return
        self._selector_resolved = True

        # 1. 解析函数签名
        resolved = resolve_selector(self.selector)
        if resolved:
            self._function_sig, param_names = resolved
            self._decoded_params = decode_params(self.input_data, param_names)
        else:
            self._function_sig = None
            self._decoded_params = {}

        # 2. 解析地址标签
        self._label = get_label(chain, self.to_addr)
        if not self._label and self.to_addr:
            self._token_symbol = TOKEN_SYMBOLS_BSC.get(self.to_addr.lower(), "")

    def to_dict(self) -> dict:
        """序列化为字典 (用于 JSON 输出)"""
        d = {
            "depth": self.depth,
            "traceAddress": self.trace_address,
            "type": self.call_type,
            "from": self.from_addr,
            "to": self.to_addr,
            "value": hex(self.value),
            "gas": self.gas,
            "gasUsed": self.gas_used,
            "selector": self.selector,
            "functionSig": self._function_sig,
            "params": self._decoded_params or {},
            "input": self.input_data if len(self.input_data) <= 132 else self.input_data[:132] + "...",
            "output": self.output_data if len(self.output_data) <= 132 else self.output_data[:132] + "...",
            "label": self._label,
            "error": self.error,
            "events": self.events,
            "childrenCount": len(self.children),
        }

        if self.is_create:
            d["created"] = self.created_address
        if self._token_symbol:
            d["tokenSymbol"] = self._token_symbol

        d["children"] = [child.to_dict() for child in self.children]
        return d


class CallChainBuilder:
    """将扁平 trace 列表构建为树形调用链"""

    @staticmethod
    def build(trace_list: list, chain: str = "bsc") -> CallTreeNode:
        """
        构建 Call Tree
        trace_transaction 返回的是 BFS 顺序的 flat list
        traceAddress 表示每个节点的位置, e.g. [0, 2, 1] 表示第0个子节点的第2个节点的第1个
        """
        if not trace_list:
            raise ValueError("Empty trace")

        # 过滤出有效的调用类型 (跳过 suicide/reward 等无 action 的条目)
        valid_traces = []
        for entry in trace_list:
            action = entry.get("action")
            # 只处理有 action 的条目 (call/delegatecall/staticcall/create)
            if action and isinstance(action, dict):
                call_type = action.get("callType", "")
                ttype = entry.get("type", "")
                if call_type in ("call", "delegatecall", "staticcall") or \
                   ttype == "create" or (not call_type and action.get("to")):
                    valid_traces.append(entry)

        print(f"  Valid call traces: {len(valid_traces)} / {len(trace_list)} total")

        root = None
        node_map: dict[tuple, CallTreeNode] = {}

        for entry in valid_traces:
            raw_trace_addr = entry.get("traceAddress")
            if raw_trace_addr is None:
                continue
            trace_addr = tuple(raw_trace_addr) if isinstance(raw_trace_addr, list) else ()

            # 跳过已处理过的地址（防止重复）
            if trace_addr in node_map:
                print(f"    [WARN] Duplicate traceAddress: {trace_addr}")
                continue

            depth = len(trace_addr)

            # 跳过无效类型
            action = entry.get("action", {})
            call_type = action.get("callType", entry.get("type", ""))
            if not call_type and not action.get("to") and not entry.get("result", {}).get("address"):
                continue

            node = CallTreeNode(entry, depth=depth)
            node.resolve(chain)

            # 找父节点: 父节点的 traceAddress 是当前地址去掉最后一个元素
            if trace_addr:
                parent_key = trace_addr[:-1]
            else:
                parent_key = ()

            parent = node_map.get(parent_key)

            if parent is None:
                # 这是根节点或父节点尚未出现(理论上不应发生，BFS顺序保证父先于子)
                if root is None:
                    root = node
                    node_map[trace_addr] = node
                else:
                    # 多根情况：作为独立节点记录但不挂载
                    print(f"    [WARN] Multiple roots at {trace_addr}, skipping")
            else:
                # 防止循环引用
                if id(parent) == id(node):
                    print(f"    [WARN] Self-reference at {trace_addr}")
                    continue
                parent.children.append(node)
                node_map[trace_addr] = node

        if root is None and node_map:
            # fallback: 取第一个节点作为根
            root = next(iter(node_map.values()))

        return root


# ============================================================
# 事件关联
# ============================================================

def link_events_to_nodes(root: CallTreeNode, receipt_logs: list):
    """
    将 receipt 中的 events 关联到对应的调用节点
    这是一个近似算法: 根据 gasUsed 排序和 traceAddress 进行匹配
    更精确的方式需要使用 debug_traceTransaction withLog tracer
    """

    # DFS 收集所有叶子节点的顺序和位置
    ordered_nodes = []
    stack = [(root, 0)]
    cumulative_gas = 0

    while stack:
        node, start_gas = stack.pop()
        node_start = start_gas
        node_end = start_gas + node.gas_used
        ordered_nodes.append({
            "node": node,
            "startGas": node_start,
            "endGas": node_end,
            "traceAddr": node.trace_address,
        })

        # 子节点按顺序入栈 (反向以保持正确顺序)
        child_gas = 0
        for child in reversed(node.children):
            stack.append((child, node_start + child_gas))
            child_gas += child.gas_used
        cumulative_gas += node.gas_used

    # 尝试按 traceAddress 匹配 logs
    # 注意: 这里的匹配是启发式的, 完全精确需要 tracer with log support
    for log_idx, log in enumerate(receipt_logs):
        decoded = decode_event_log(log)
        if not decoded:
            continue

        # 找到最可能产生这个 event 的节点
        # 使用简单的策略: 按 traceAddress 前缀匹配
        best_node = None
        best_score = -1

        for item in ordered_nodes:
            score = 0
            node = item["node"]
            # 如果 event 的 token 地址与节点的 to 地址相同, 高分
            log_addr = to_hex(log.get("address", "")).lower()
            if log_addr == node.to_addr.lower():
                score += 10
            # 如果是 CALL 且有子节点 (内部调用), 可能包含 events
            if node.is_call and node.children:
                score += 2
            # 深度越深, 越可能是内部操作产生的 event
            score += node.depth * 0.5

            if score > best_score:
                best_score = score
                best_node = node

        if best_node:
            decoded["_logIndex"] = log_idx
            best_node.events.append(decoded)


# ============================================================
# 可视化输出
# ============================================================

def visualize_tree(root: CallTreeNode, chain: str = "bsc", max_depth: int = 20) -> str:
    """生成类似 BlockSec Phalcon 的终端可视化 - 迭代式实现"""

    TYPE_ICONS = {
        "call": "CALL",
        "delegatecall": "DELEGATECALL",
        "staticcall": "STATICCALL",
        "create": "CREATE",
        "": "ROOT",
        "?": "?",
    }
    TYPE_COLORS = {
        "call": "\033[94m",       # blue
        "delegatecall": "\033[93m", # yellow
        "staticcall": "\033[96m",   # cyan
        "create": "\033[92m",      # green
        "": "\033[91m",           # red (root)
        "?": "\033[90m",          # gray
    }
    RESET = "\033[0m"
    EVENT_COLOR = "\033[92m"  # green for events
    ERROR_COLOR = "\033[31m"  # red for errors
    LABEL_COLOR = "\033[95m"  # magenta for labels
    SIG_COLOR = "\033[33m"    # orange/yellow for signatures

    def format_value(val: int) -> str:
        if val == 0:
            return ""
        if val >= 1e18:
            return f"{val / 1e18:.4f} ETH/BNB"
        if val >= 1e9:
            return f"{val / 1e9:.4g} Gwei"
        return f"{val} wei"

    def format_params(params: dict, limit: int = 80) -> str:
        if not params:
            return ""
        parts = []
        total_len = 0
        for k, v in params.items():
            s = f"{k.split()[-1]}={v}"
            if total_len + len(s) > limit and parts:
                parts.append("...")
                break
            parts.append(s)
            total_len += len(s) + 2
        return "(" + ", ".join(parts) + ")"

    # 迭代式树遍历: 使用栈存储 (node, prefix, is_last, parent_info)
    lines = []

    # 第一项是根节点，特殊处理（无前缀）
    stack = [(root, "", True)]
    visited_ids = set()

    while stack:
        node, prefix, is_last = stack.pop()
        nid = id(node)
        if nid in visited_ids or node.depth > max_depth:
            continue
        visited_ids.add(nid)

        # 行号
        line_num = f"{node.depth:<4}"

        # 类型图标
        icon = TYPE_ICONS.get(node.call_type, "?")
        color = TYPE_COLORS.get(node.call_type, "")

        # 缩进连接符
        connector = "+-" if (is_last and node.depth > 0) else "+-"

        # From/To 信息
        from_label = get_label(chain, node.from_addr) or shorten(node.from_addr, 10)
        to_label = node._label or node._token_symbol or shorten(node.to_addr, 10)

        # 函数签名或原始数据
        if node.is_create:
            sig_display = f"[CREATE → {shorten(node.created_address)}]"
        elif node._function_sig:
            short_sig = node._function_sig
            if len(short_sig) > 50:
                short_sig = short_sig[:47] + "..."
            sig_display = f".{SIG_COLOR}{short_sig}{RESET}"
        else:
            display_input = node.input_data[:20] + "..." if len(node.input_data) > 23 else node.input_data
            sig_display = f"[{display_input}]"

        # 参数
        params_str = format_params(node._decoded_params)

        # Value
        val_str = format_value(node.value)
        if val_str:
            val_str = f", {val_str}"

        # 主行
        main_line = (
            f"{prefix}{connector} "
            f"\033[1m{color}{icon}\033[0m "
            f"{LABEL_COLOR}{from_label}{RESET}"
            f" → {LABEL_COLOR}{to_label}{RESET}"
            f" {sig_display}"
            f"{params_str}"
            f"{val_str}"
        )

        # Gas info
        gas_info = f"(gas={node.gas_used:,})"
        if node.error:
            gas_info = f"{ERROR_COLOR}[REVERT: {node.error}] {RESET}{gas_info}"

        lines.append(f"{line_num} {main_line} {gas_info}")

        # Output
        indent_inner = prefix + ("    " if is_last else "|   ")
        if node.output_data and node.output_data != "0x":
            out_short = node.output_data[:30] + "..." if len(node.output_data) > 33 else node.output_data
            lines.append(f"     {indent_inner}-> return {out_short}")

        # Events
        for ev in node.events:
            ev_name = ev.get("name", "?")
            ev_parts = [f"{k}={v}" for k, v in ev.items() if not k.startswith("_")]
            ev_str = ", ".join(ev_parts)
            lines.append(
                f"     {indent_inner}-> "
                f"{EVENT_COLOR}EVENT{RESET} {ev_name}: {ev_str[:100]}"
            )

        # 子节点反向入栈（保持正确顺序）
        children = [c for c in node.children if id(c) not in visited_ids]
        for ci, child in reversed(list(enumerate(children))):
            child_is_last = (ci == len(children) - 1)
            child_prefix = prefix + ("    " if is_last else "│   ") if node.depth > 0 else ""
            stack.append((child, child_prefix, child_is_last))

    return "\n".join(lines)


# ============================================================
# 主流程
# ============================================================

def analyze_tx(tx_hash: str, chain: str = "bsc") -> dict:
    """完整的交易调用链分析流程"""
    analyzer = TxAnalyzer(chain=chain)

    print(f"\n{'='*80}")
    print(f"  TX CALLCHAIN ANALYZER - PoC")
    print(f"  Chain: {CHAIN_CONFIG.get(chain, {}).get('name', chain)}")
    print(f"  Tx:    {tx_hash}")
    print(f"{'='*80}\n")

    # 1. 获取基础信息
    print("[1/5] Fetching transaction basics...")
    tx = analyzer.get_transaction(tx_hash)
    if not tx:
        raise ValueError(f"Transaction not found: {tx_hash}")

    receipt = analyzer.get_receipt(tx_hash)
    status = "SUCCESS" if receipt.get("status") == "0x1" else "FAILED"

    print(f"  Status: {status}")
    print(f"  From:   {tx.get('from')}")
    print(f"  To:     {tx.get('to')}")
    print(f"  Value:  {int(tx.get('value', '0x0'), 16):,} wei")
    print(f"  Gas:    {receipt.get('gasUsed', '?')} used / {tx.get('gas', '?')} limit")

    # 2. 获取 Trace
    print("\n[2/5] Tracing transaction calls...")
    traces = analyzer.trace_transaction(tx_hash)
    print(f"  Found {len(traces)} trace entries")

    if not traces:
        print("[ERROR] No trace data available. The RPC may not support tracing.")
        print("  Try using an archive node with trace_transaction support.")
        return {"error": "no_trace"}

    # 3. 构建调用树
    print("\n[3/5] Building call tree...")
    root = CallChainBuilder.build(traces, chain=chain)

    # 统计
    total_calls = count_nodes(root)
    max_depth = get_max_depth(root)

    print(f"  Root: {root.to_addr} ({root._label or 'unknown'})")
    print(f"  Total nodes: {total_calls}")
    print(f"  Max depth: {max_depth}")

    # 4. 关联 Events
    print("\n[4/5] Linking events...")
    logs = receipt.get("logs", [])
    link_events_to_nodes(root, logs)
    event_count = count_events(root)
    print(f"  Linked {event_count}/{len(logs)} events")

    # 5. 输出结果
    print(f"\n[5/5] Generating output...\n")

    # --- 结构化 JSON ---
    struct_result = root.to_dict()
    struct_result.update({
        "_meta": {
            "txHash": tx_hash,
            "chain": chain,
            "status": status,
            "from": tx.get("from"),
            "to": tx.get("to"),
            "blockNumber": receipt.get("blockNumber"),
            "totalTraceEntries": len(traces),
            "totalCallNodes": total_calls,
            "maxDepth": max_depth,
            "totalEvents": event_count,
            "gasUsed": receipt.get("gasUsed"),
        }
    })

    # 保存 JSON
    json_output_path = f"d:/Programming/Python/AlertProcessor/scripts/callchain_{tx_hash[:10]}.json"
    with open(json_output_path, "w", encoding="utf-8") as f:
        json.dump(struct_result, f, indent=2, ensure_ascii=False)
    print(f"  JSON saved to: {json_output_path}")

    # --- 可视化 ---
    print(f"\n{'='*80}")
    print(f"  INVOCATION FLOW (BlockSec-style)")
    print(f"{'='*80}\n")

    viz = visualize_tree(root, chain=chain)
    print(viz)

    # --- 汇总 ---
    print(f"\n{'='*80}")
    print(f"  SUMMARY")
    print(f"{'='*80}")
    print_summary(root, tx, receipt, chain)

    return struct_result


def count_nodes(node: CallTreeNode) -> int:
    """迭代式计算节点总数 (避免递归溢出)"""
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


def get_max_depth(node: CallTreeNode) -> int:
    """迭代式计算最大深度"""
    max_d = 0
    stack = [(node, 0)]
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


def count_events(node: CallTreeNode) -> int:
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


def print_summary(root: CallTreeNode, tx: dict, receipt: dict, chain: str):
    """打印汇总信息"""
    all_selectors = set()
    all_protocols = set()
    visited = set()

    # 迭代式收集
    stack = [root]
    while stack:
        node = stack.pop()
        nid = id(node)
        if nid in visited:
            continue
        visited.add(nid)
        if node.selector:
            all_selectors.add((node.selector, node._function_sig))
        if node._label:
            all_protocols.add(node._label)
        stack.extend(node.children)

    print(f"\n  Transaction: {tx.get('from')[:10]}... → {tx.get('to', 'CONTRACT_CREATE')}")
    print(f"  Total Calls: {count_nodes(root)}, Max Depth: {get_max_depth(root)}")
    print(f"\n  Functions Called ({len(all_selectors)} unique selectors):")
    # 预计算每个 selector 的调用次数
    selector_counts = {}
    for sel, sig in all_selectors:
        cnt = sum(1 for _ in iter_all_with_selector(root, sel))
        selector_counts[sel] = cnt

    for sel, sig in sorted(all_selectors, key=lambda x: -selector_counts.get(x[0], 0)):
        count = selector_counts.get(sel, 0)
        count = sum(1 for _ in iter_all_with_selector(root, sel))
        display_sig = sig or f"unknown({sel})"
        print(f"    [{count:>3}x] {sel} → {display_sig}")

    print(f"\n  Protocols Involved ({len(all_protocols)}):")
    for proto in sorted(all_protocols):
        print(f"    • {proto}")


def iter_all_with_selector(node: CallTreeNode, selector: str):
    """迭代式查找所有匹配指定 selector 的节点"""
    stack = [node]
    visited = set()
    while stack:
        n = stack.pop()
        nid = id(n)
        if nid in visited:
            continue
        visited.add(nid)
        if n.selector == selector:
            yield n
        stack.extend(n.children)


# ============================================================
# CLI 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Tx CallChain Analyzer PoC - BlockSec-style invocation flow analysis"
    )
    parser.add_argument("--tx", default=DEFAULT_TX, help="Transaction hash to analyze")
    parser.add_argument("--chain", default=DEFAULT_CHAIN, choices=["bsc", "eth"], help="Blockchain network")
    parser.add_argument("--json-only", action="store_true", help="Only output JSON (no visualization)")
    args = parser.parse_args()

    try:
        result = analyze_tx(args.tx, args.chain)
        if args.json_only:
            print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
