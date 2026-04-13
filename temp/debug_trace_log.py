"""
Debug: 导出 ETH trace 完整原始数据到日志文件

用法:
    python -m temp.debug_trace_log 0x41b6b9376d174165cbd54ba576c8f6675ff966f17609a7b80d27d8652db1f18f [chain_id]

输出:
    temp/trace_raw_<tx_hash_short>.json  — 完整原始 trace 数据 (JSON)
    temp/trace_analysis_<tx_hash_short>.log — 分析过程日志
"""

import asyncio
import json
import logging
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ── 双输出：同时写文件和控制台 ──
LOG_FILE = ""


class FileHandler(logging.Handler):
    def __init__(self, filename):
        super().__init__()
        self.fh = open(filename, 'w', encoding='utf-8')

    def emit(self, record):
        msg = self.format(record)
        self.fh.write(msg + '\n')
        self.fh.flush()

    def close(self):
        super().close()
        if self.fh and not self.fh.closed:
            self.fh.close()


def setup_logging(tx_short: str):
    global LOG_FILE
    log_dir = os.path.join(PROJECT_ROOT, 'temp')
    LOG_FILE = os.path.join(log_dir, f'trace_analysis_{tx_short}.log')
    os.makedirs(log_dir, exist_ok=True)

    fmt = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    datefmt = '%H:%M:%S'

    # 控制台 handler (INFO 级别)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(fmt, datefmt=datefmt))

    # 文件 handler (DEBUG 级别，记录所有细节)
    file_handler = FileHandler(LOG_FILE)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(console)
    root_logger.addHandler(file_handler)

    return LOG_FILE


async def main():
    if len(sys.argv) < 2:
        print("Usage: python -m temp.debug_trace_log <tx_hash> [chain_id]")
        print("Example: python -m temp.debug_trace_log 0x41b6...18f 1")
        return

    TX_HASH = sys.argv[1].strip()
    CHAIN_ID = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    tx_short = TX_HASH[:12]

    log_file = setup_logging(tx_short)
    logger = logging.getLogger('debug_trace')

    logger.info("=" * 100)
    logger.info(f"TRACE DEBUG LOG — TX={TX_HASH}  Chain={CHAIN_ID}")
    logger.info(f"Log file: {log_file}")
    logger.info("=" * 100)

    # ── 1. 初始化 RPC client ──
    from detectors.trace.provider import get_rpc_client
    rpc_client = get_rpc_client()

    # ── 2. 获取原始 trace ──
    logger.info(f"\n{'='*60}")
    logger.info("[STEP 1] 调用 get_transaction_trace() ...")
    logger.info(f"{'='*60}")

    try:
        raw_traces = await rpc_client.get_transaction_trace(TX_HASH, CHAIN_ID)
        logger.info(f"✅ 成功获取 {len(raw_traces)} 条 trace entries")
    except Exception as e:
        logger.error(f"❌ 获取 trace 失败: {type(e).__name__}: {e}", exc_info=True)
        await rpc_client.close()
        return

    # ── 3. 保存完整原始数据到 JSON ──
    json_path = os.path.join(PROJECT_ROOT, 'temp', f'trace_raw_{tx_short}.json')
    try:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(raw_traces, f, indent=2, ensure_ascii=False, default=str)
        logger.info(f"📄 完整原始数据已保存: {json_path} ({os.path.getsize(json_path):,} bytes)")
    except Exception as e:
        logger.warning(f"保存 JSON 失败: {e}")

    # ── 4. 详细打印每一条 entry ──
    logger.info(f"\n{'='*60}")
    logger.info("[STEP 2] 逐条解析 trace entries")
    logger.info(f"{'='*60}")

    for i, entry in enumerate(raw_traces):
        action = entry.get('action', {})
        result_data = entry.get('result', {})
        call_type = action.get('callType', entry.get('type', '?'))
        t_type = entry.get('type', '')
        to_addr = _to_hex(action.get('to', action.get('address', ''))).lower()
        from_addr = _to_hex(action.get('from', '')).lower()
        input_hex = _to_hex(action.get('input', '0x'))
        output_hex = _to_hex(result_data.get('output', ''))
        selector = input_hex[:10] if len(input_hex) >= 10 else ''
        value_hex = action.get('value', '0x0')
        gas_hex = action.get('gas', '0x0')
        gas_used_hex = result_data.get('gasUsed', '0x0')
        error = result_data.get('error')
        trace_addr = entry.get('traceAddress', [])

        # 已知 selector 映射
        known_sels = {
            "0xa9059cbb": "transfer(address,uint256)",
            "0x23b872dd": "transferFrom(addr,addr,uint256)",
            "0x40c10f19": "mint(address,uint256)",
            "0x095ea7b3": "approve(address,uint256)",
            "0x66a1e3e10": "mint(bytes32,address,uint256)",
        }
        sig_hint = known_sels.get(selector.lower(), '?')

        logger.info(f"\n── Entry #{i} ──────────────────────────────────────")
        logger.info(f"  traceAddress : {list(trace_addr)}")
        logger.info(f"  type         : {t_type or '(empty)'}")
        logger.info(f"  callType     : {call_type or '(none)'}")
        logger.info(f"  from         : {from_addr}")
        logger.info(f"  to           : {to_addr}")
        logger.info(f"  selector     : {selector or '(none)'}  →  {sig_hint}")
        logger.info(f"  value(hex)   : {value_hex}")
        logger.info(f"  gas(hex)     : {gas_hex}")
        logger.info(f"  gasUsed(hex) : {gas_used_hex}")

        if input_hex and input_hex != '0x':
            logger.info(f"  input(len={len(input_hex)}): {input_hex[:200]}...")
        else:
            logger.info(f"  input: 0x (empty)")

        if output_hex and output_hex != '0x' and output_hex != '0x0':
            logger.info(f"  output(len={len(output_hex)}): {output_hex[:120]}...")
        else:
            logger.info(f"  output: empty/0x")

        if error:
            logger.error(f"  ⚠️ ERROR: {error}")

        # 完整 JSON dump（仅 DEBUG 级别写入文件）
        logger.debug(f"  FULL ENTRY JSON:\n{json.dumps(entry, indent=4, default=str)[:800]}")

    # ── 5. 构建调用树 ──
    logger.info(f"\n{'='*60}")
    logger.info("[STEP 3] build_call_tree()")
    logger.info(f"{'='*60}")

    from detectors.trace.analyzer import TxTraceAnalyzer
    analyzer = TxTraceAnalyzer(rpc_client=rpc_client)

    root = analyzer.build_call_tree(raw_traces)
    total_nodes = _count_nodes(root)
    max_depth = _get_max_depth(root)
    logger.info(f"✅ 树构建完成: root.to={root.to_address}, nodes={total_nodes}, depth={max_depth}")

    # ── 6. DFS 打印树结构 ──
    logger.info(f"\n{'='*60}")
    logger.info("[STEP 4] DFS 遍历调用树 — 完整结构")
    logger.info(f"{'='*60}")

    def print_tree(node, prefix="", is_last=True):
        connector = "└── " if is_last else "├── "
        sig_str = node.function_signature or node.selector or "(unknown)"
        addr_display = (
            node.label or
            node.token_symbol or
            (node.to_address[:10] + "..." + node.to_address[-4:] if node.to_address else "?")
        )
        token_info = ""
        if node.token_symbol:
            token_info = f" [tokenSymbol={node.token_symbol}]"
        elif not node.label:
            token_info = " [NO_SYMBOL_NO_LABEL]"

        line = f"{prefix}{connector}[{node.callType.upper():>11s}] {addr_display}{token_info}"
        line += f"  {sig_str}"
        if node.value > 0:
            line += f"  val={node.value:,}"

        logger.info(line)

        children = node.children or []
        for ci, child in enumerate(children):
            ext = "    " if is_last else "│   "
            print_tree(child, prefix + ext, ci == len(children) - 1)

        # Events
        for ev in node.events:
            ev_line = f"{prefix}{'    ' if is_last else '│   '}├── [EVENT] "
            ev_line += f"{ev.name}  decoded={ev.decoded}"
            logger.info(ev_line)

    print_tree(root)

    # ── 7. 重点检查 mint 节点 ──
    logger.info(f"\n{'='*60}")
    logger.info("[STEP 5] 检查所有 transfer/mint 相关节点")
    logger.info(f"{'='*60}")

    TRANSFER_SEL = {"0xa9059cbb", "0x23b872dd"}
    MINT_SEL = {"0x40c10f19", "0x66a1e3e10"}

    visited = set()
    stack = [(root, 0)]
    while stack:
        node, depth = stack.pop()
        nid = id(node)
        if nid in visited:
            continue
        visited.add(nid)

        sel = (node.selector or "").lower()
        ct = node.call_type.lower()

        if sel in TRANSFER_SEL or sel in MINT_SEL:
            tag = "TRANSFER" if sel in TRANSFER_SEL else "MINT"
            logger.info(
                f"\n  📌 [{tag}] depth={depth} callType={ct} "
                f"sel={node.selector}  "
                f"sig={node.function_signature}  "
                f"from={node.from_address}  to={node.to_address}  "
                f"symbol={repr(node.token_symbol)}  label={repr(node.label)}"
            )
            logger.info(f"     params={[p.value for p in node.params]}")
            logger.info(f"     children={len(node.children)}")

            if node.children:
                for ci, ch in enumerate(node.children):
                    logger.info(
                        f"       child[{ci}]: type={ch.callType:>12s}  "
                        f"sel={(ch.selector or ''):<12s}  "
                        f"sig={(ch.function_signature or '')[:50]:<50s}  "
                        f"from={ch.from_address[:10]}..  to={ch.to_address[:10]}.."
                    )
                    if ch.params:
                        for pi, p in enumerate(ch.params):
                            logger.info(f"         param_{pi}: {p.type_hint} = {p.value}")
            else:
                logger.warning(f"     ⚠️ 无子节点!")

        for child in reversed(node.children):
            stack.append((child, depth + 1))

    # ── 8. 运行完整 analyze 并检查结果中的 tokenSymbol ──
    logger.info(f"\n{'='*60}")
    logger.info("[STEP 6] 完整 analyze() 后的 tokenSymbol 分布")
    logger.info(f"{'='*60}")

    try:
        result = await analyzer.analyze(TX_HASH, CHAIN_ID, run_behavior_detect=False)

        # 统计有/无 tokenSymbol 的节点
        has_sym = 0
        no_sym_no_label = 0
        no_sym_has_label = 0
        no_sym_addrs = []

        visited = set()
        stack = [result.root]
        while stack:
            n = stack.pop()
            nid = id(n)
            if nid in visited:
                continue
            visited.add(nid)

            if n.token_symbol:
                has_sym += 1
            elif n.label:
                no_sym_has_label += 1
            else:
                no_sym_no_label += 1
                no_sym_addrs.append(n.to_address)

            if n.children:
                stack.extend(n.children)

        logger.info(f"  有 tokenSymbol:      {has_sym} 个节点")
        logger.info(f"  有 label 无 symbol:   {no_sym_has_label} 个节点")
        logger.info(f"  既无 symbol 也无label: {no_sym_no_label} 个节点")

        if no_sym_addrs:
            logger.info(f"  无标识的地址:")
            for addr in set(no_sym_addrs):
                logger.info(f"    {addr}")

    except Exception as e:
        logger.error(f"analyze 失败: {e}", exc_info=True)

    await rpc_client.close()
    analyzer._signature_db.close()

    logger.info(f"\n{'='*100}")
    logger.info("DONE ✅  查看日志文件获取完整信息:")
    logger.info(f"  原始数据: {json_path}")
    logger.info(f"  分析日志: {log_file}")
    logger.info(f"{'='*100}")


# ── 工具函数 ──

def _to_hex(data) -> str:
    if isinstance(data, bytes):
        return "0x" + data.hex()
    if isinstance(data, str):
        return data if data.startswith("0x") else "0x" + data
    if data is None:
        return "0x"
    return "0x" + format(int(data), "x")


def _count_nodes(node):
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
        if n.children:
            stack.extend(n.children)
    return total


def _get_max_depth(node):
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
        if n.children:
            for c in n.children:
                stack.append((c, d + 1))
    return max_d


if __name__ == "__main__":
    asyncio.run(main())
