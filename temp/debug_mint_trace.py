"""
Debug: 检查 mint 函数调用下为何没有 transfer 子调用

问题: Call Tree 中 mint 函数下应该有从 0 地址到 receiver 的 transfer 调用，
     但实际显示没有。本脚本用于排查原因。

用法:
    python -m temp.debug_mint_trace
"""

import asyncio
import json
import logging
import os
import sys

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("debug_mint")


async def main():
    # ================================================================
    # 1. 获取 RPC client 和 analyzer
    # ================================================================
    from detectors.trace.provider import get_rpc_client
    from detectors.trace.analyzer import TxTraceAnalyzer

    rpc_client = get_rpc_client()
    analyzer = TxTraceAnalyzer(rpc_client=rpc_client)

    # ================================================================
    # 2. 目标交易 hash — 支持命令行参数或从截图提取
    # ================================================================
    # 用法: python -m temp.debug_mint_trace <tx_hash> [chain_id]
    if len(sys.argv) > 1:
        TX_HASH = sys.argv[1]
        CHAIN_ID = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    else:
        TX_HASH = ""  # 需要用户提供
        CHAIN_ID = 1

    # 尝试从最近的 alert 或数据库获取完整 tx_hash
    logger.info("=" * 80)
    logger.info("Debug: mint 函数下缺少 transfer 子调用")
    logger.info("=" * 80)

    # 如果 TX_HASH 不完整，尝试从数据库查找
    if not TX_HASH or len(TX_HASH) < 10:
        logger.error("请提供完整的 tx_hash!")
        logger.error("用法: python -m temp.debug_mint_trace <tx_hash> [chain_id]")
        return

    # 尝试补全 (如果用户输入了短 hash)
    if len(TX_HASH) < 66:
        import sqlite3
        db_path = os.path.join(PROJECT_ROOT, "alerts.db")
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute(
                "SELECT message FROM alerts WHERE message LIKE ? LIMIT 5",
                (f"%{TX_HASH}%",)
            )
            rows = cur.fetchall()
            for row in rows:
                import re
                m = re.search(r'0x[a-fA-F0-9]{64}', row[0])
                if m:
                    TX_HASH = m.group(0)
                    logger.info(f"从数据库找到完整 tx_hash: {TX_HASH}")
                    break
            conn.close()

    if len(TX_HASH) != 66:
        logger.error(f"TX_HASH 不完整或未找到: {TX_HASH}")
        logger.error("请手动设置完整的 66 字符 tx_hash 后重试")
        return

    # ================================================================
    # 3. 获取原始 trace 数据
    # ================================================================
    logger.info(f"\n{'='*80}")
    logger.info(f"[Step 1] 获取原始 trace: {TX_HASH[:20]}...")
    logger.info(f"{'='*80}")

    try:
        raw_traces = await rpc_client.get_transaction_trace(TX_HASH, CHAIN_ID)
        logger.info(f"获取到 {len(raw_traces)} 条 trace entries")
    except Exception as e:
        logger.error(f"获取 trace 失败: {e}")
        return

    # ================================================================
    # 4. 打印所有 trace entry 的摘要 (traceAddress + callType + selector)
    # ================================================================
    logger.info(f"\n{'='*80}")
    logger.info("[Step 2] 所有 trace entries 摘要")
    logger.info(f"{'='*80}")

    for i, entry in enumerate(raw_traces):
        action = entry.get("action", {})
        call_type = action.get("callType", entry.get("type", "?"))
        to_addr = action.get("to", action.get("address", ""))
        input_hex = action.get("input", "0x")
        selector = input_hex[:10] if len(input_hex) >= 10 else ""
        trace_addr = entry.get("traceAddress", [])

        # 解码方法名（简单匹配）
        method_name = "?"
        known_sels = {
            "0xa9059cbb": "transfer(address,uint256)",
            "0x23b872dd": "transferFrom(addr,addr,uint256)",
            "0x40c10f19": "mint(address,uint256)",
            "0x66a1e3e10": "mint(bytes32,address,uint256)",  # 可能的 mint 变体
        }
        if selector.lower() in known_sels:
            method_name = known_sels[selector.lower()]

        logger.info(
            f"  [{i:>3d}] {'['+','.join(str(a) for a in trace_addr)+']':>16s} "
            f"{call_type:>12s}  {selector}  {method_name:<40s}  "
            f"to={to_addr[:10]}..."
        )

    # ================================================================
    # 5. 构建调用树并定位 mint 节点
    # ================================================================
    logger.info(f"\n{'='*80}")
    logger.info("[Step 3] 构建调用树，重点分析 mint 节点")
    logger.info(f"{'='*80}")

    root = analyzer.build_call_tree(raw_traces)

    # DFS 遍历找到所有 mint 相关节点
    MINT_SELECTORS = {"0x40c10f19", "0x66a1e3e10"}
    mint_nodes = []

    visited = set()
    stack = [root]
    while stack:
        node = stack.pop()
        nid = id(node)
        if nid in visited:
            continue
        visited.add(nid)

        if node.selector and node.selector.lower() in MINT_SELECTORS:
            mint_nodes.append(node)
        stack.extend(reversed(node.children))

    logger.info(f"找到 {len(mint_nodes)} 个 mint 节点")

    for idx, mint_node in enumerate(mint_nodes):
        logger.info(f"\n--- Mint 节点 #{idx + 1} ---")
        logger.info(f"  traceAddress : {mint_node.trace_address}")
        logger.info(f"  callType      : {mint_node.call_type}")
        logger.info(f"  selector      : {mint_node.selector}")
        logger.info(f"  signature     : {mint_node.function_signature}")
        logger.info(f"  from          : {mint_node.from_address}")
        logger.info(f"  to            : {mint_node.to_address}")
        logger.info(f"  params        : {[p.value for p in mint_node.params]}")
        logger.info(f"  value         : {mint_node.value}")
        logger.info(f"  children count: {len(mint_node.children)}")

        if mint_node.children:
            logger.info(f"  子节点列表:")
            for ci, child in enumerate(mint_node.children):
                logger.info(
                    f"    [{ci}] callType={child.call_type:>12s}  "
                    f"selector={child.selector or '(none)':<12s}  "
                    f"sig={(child.function_signature or '')[:50]:<50s}  "
                    f"from={child.from_address[:10]}...  "
                    f"to={child.to_address[:10]}...  "
                    f"value={child.value}"
                )
                if child.params:
                    for pi, p in enumerate(child.params):
                        logger.info(f"         param_{pi}: {p.type_hint} = {p.value}")
        else:
            logger.warning("  ⚠️  mint 节点没有任何子节点!")

        # 同时检查 events
        if mint_node.events:
            logger.info(f"  关联事件 ({len(mint_node.events)}):")
            for ei, ev in enumerate(mint_node.events):
                logger.info(
                    f"    event[{ei}]: name={ev.name}, decoded={ev.decoded}"
                )
        else:
            logger.info("  无关联事件")

    # ================================================================
    # 6. 对比: 直接在 raw_traces 中找 mint 的子调用
    # ================================================================
    logger.info(f"\n{'='*80}")
    logger.info("[Step 4] 原始数据层面: 找 mint 对应 traceAddress 的直接子项")
    logger.info(f"{'='*80}")

    for mint_node in mint_nodes:
        target_addr = mint_node.trace_address
        logger.info(f"\nmint 节点 traceAddress = {target_addr}")

        # 在 raw_traces 中找所有以 target_addr 为前缀的下一级子项
        child_prefix_len = len(target_addr)
        found_children_in_raw = []

        for entry in raw_traces:
            entry_addr = entry.get("traceAddress", [])
            if (len(entry_addr) == child_prefix_len + 1 and
                entry_addr[:child_prefix_len] == list(target_addr)):
                action = entry.get("action", {})
                ct = action.get("callType", entry.get("type", "?"))
                inp = action.get("input", "0x")
                sel = inp[:10] if len(inp) >= 10 else ""
                to_a = action.get("to", "")
                found_children_in_raw.append({
                    "traceAddress": entry_addr,
                    "callType": ct,
                    "selector": sel,
                    "to": to_a,
                    "action": action,
                })

        if found_children_in_raw:
            logger.info(f"  在 raw_traces 中找到 {len(found_children_in_raw)} 个直接子项:")
            for ch in found_children_in_raw:
                logger.info(
                    f"    addr={ch['traceAddress']}  type={ch['callType']:>12s}  "
                    f"sel={ch['selector']}  to={ch['to']}"
                )
                # 打印 input 前100字符
                inp = ch["action"].get("input", "")
                if inp:
                    logger.info(f"    input={inp[:120]}...")
        else:
            logger.warning(
                f"  ⚠️  raw_traces 中 mint(traceAddr={target_addr}) 下也没有任何直接子项!"
            )
            # 打印附近的所有 entry 帮助排查
            logger.info("  附近的 trace entries:")
            for entry in raw_traces:
                ea = entry.get("traceAddress", [])
                # 找同级别或父级别的
                if (ea[:child_prefix_len - 1] == list(target_addr[:child_prefix_len - 1])
                    and len(ea) >= child_prefix_len - 1):
                    action = entry.get("action", {})
                    ct = action.get("callType", entry.get("type", "?"))
                    inp = action.get("input", "0x")
                    sel = inp[:10] if len(inp) >= 10 else ""
                    marker = " <<< MINT" if ea == list(target_addr) else ""
                    logger.info(
                        f"    addr={ea}  type={ct:>12s}  sel={sel}{marker}"
                    )

    # ================================================================
    # 7. 完整运行 analyze 并检查 extract_call_transfers 结果
    # ================================================================
    logger.info(f"\n{'='*80}")
    logger.info("[Step 5] 运行完整 analyze → 提取 call_transfers")
    logger.info(f"{'='*80}")

    try:
        result = await analyzer.analyze(TX_HASH, CHAIN_ID, run_behavior_detect=False)

        transfers = result.call_transfers
        logger.info(f"\ncall_transfers 总数: {len(transfers)}")
        for t in transfers:
            logger.info(
                f"  [{t.order_id}] {t.function_signature or t.selector}: "
                f"{t.from_address[:10]}... → {t.to_address[:10]}...  "
                f"amount={t.amount_formatted} {t.token_symbol}  "
                f"(callType from node depth={t.depth})"
            )

        # 特别检查: 是否有任何 transfer 的 trace_address 以 mint 的地址为前缀
        logger.info("\n检查是否有 transfer 位于 mint 之下:")
        for mint_node in mint_nodes:
            mint_addr_str = ",".join(str(a) for a in mint_node.trace_address)
            under_mint = [
                t for t in transfers
                if str(t.trace_address)[:len(mint_addr_str)] == mint_addr_str
                and len(t.trace_address) > len(mint_node.trace_address)
            ]
            if under_mint:
                logger.info(f"  mint({mint_addr_str}) 下有 {len(under_mint)} 个 transfer:")
                for t in under_mint:
                    logger.info(
                        f"    [{t.order_id}] traceAddr={t.trace_address}  "
                        f"{t.from_address[:10]}..→{t.to_address[:10]}..  "
                        f"{t.amount_formatted} {t.token_symbol}"
                    )
            else:
                logger.warning(
                    f"  mint({mint_addr_str}) 下没有 transfer 记录!"
                )

    except Exception as e:
        logger.error(f"analyze 失败: {e}", exc_info=True)

    # ================================================================
    # 清理
    # ================================================================
    await rpc_client.close()
    analyzer._signature_db.close()
    logger.info("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
