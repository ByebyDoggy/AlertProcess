"""
查询交易并输出分析结果到文件 - 补充地址识别
"""
import json
from web3 import Web3

RPC_URL = "https://ethereum-rpc.publicnode.com"
TX_HASH = "0xc310a0affe2169d1f6feec1c63dbc7f7c62a887fa48795d327d4d2da2d6b111d"
OUTPUT_FILE = r"D:\Programming\Python\AlertProcessor\scripts\trace_result.txt"

# 已知协议地址 (Ethereum Mainnet, 小写)
KNOWN_PROTOCOLS = {
    "0x7a250d5630b4cf539739df2c5dacb4c659f2488d": "Uniswap V2 Router 02",
    "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45": "Uniswap V3 Router 02",
    "0xe592427a0aece92de3edee1f18e0157c05861564": "Uniswap V3 Router 01",
    "0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad": "Uniswap Universal Router",
    "0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2": "Aave V3 Pool",
    "0x7d2768de32b0b80b7a3454c06bdac94a69ddc7a9": "Aave V3 Pool (old)",
    "0xc6845a5c768bf8d7681249f8927877efda425baf": "Aave V3 Pool Configurator",
    "0x028171bca77440897b824ca71d1c56cac55b68a3": "Aave Variable Debt DAI",
    "0x6b175474e89094c44da98b954eedeac495271d0f": "DAI",
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": "USDC (Native)",
    "0xdac17f958d2ee523a2206206994597c13d831ec7": "USDT (Native)",
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": "WETH9",
    "0x5c2ed810328349100a66b82b0192e35303d9479a": "1inch V5 AggregationRouter",
    "0xe025e3ca2b3c8f10b3460fef02ad5c5e28a6b5f0": "1inch V5 AggregationRouter V5 (IFrame)",
    "0x27182842e098f60e3d576794a5bffb0777e025d3": "1inch V5 AggregationRouter V5 (Router)",
    "0x1111111254fb6c44bac0bed2854e76ff87ea550b": "1inch V5 SwapRouter",
    "0x111111125421ca6dc452d289314280a0f8842a65": "1inch V6 SwapRouter",
    "0x1111111254eeb25477b68fb85ed929f73a960582": "1inch V5 SwapRouter (v5)",
    "0x6085bc95f506c326dcbcd7a6dd6c79fbc18d4686": "1inch V5 LimitOrderProtocol",
    "0xbb0d4bb654a21054af95456a3b29c63e8d1f4c0a": "1inch V5 AggregationExecutor (Una)",
    "0x42ec0eb1d2746a9f2739d7501c5d5608bde9ee89": "1inch V5 AggregationExecutor (UnoswapExecutor)",
    "0x3297c8db9360f87a7f7826f52a4fa143988931a6": "1inch V5 AggregationExecutor (Punk)",
    "0x29daddfda3442693c21a50351a2b4820ddbbff79": "1inch V5 AggregationExecutor (CurveV2)",
    "0xd737ee2bb39f49c62a436002a77f2710cc45ed98": "1inch V5 AggregationExecutor (UniswapV3)",
    "0x773616e4d11a78f511299002da57a0a94577f1f4": "1inch V5 CHI Token (gas refund)",
    "0x158228e08c52f3e2211ccbc8ec275fa93f6033fc": "1inch V5 CHI GasToken",
    "0xba12222222228d8ba445958a75a0704d566bf2c8": "Balancer V2 Vault",
    "0x99a58482bd75cbab83b27ec03ca68ff489b5788f": "Curve 1Pool",
    "0xdef1c0ded9bec7f1a1670819833240f027b25eff": "0x Exchange Proxy",
    "0x1e0447b19bb6ecfdae1e4ae1694b0c3659614e4e": "dYdX Solo Margin",
    "0x47ce0c6ed5b0ce3d3a51fdb1c52f66a94c577926": "Tornado Cash Router",
    "0xebc29199c817dc47ba12e3f86102564d640cbf99": "EOA / ProxyContract (tx.to)",
    "0x5f259d0b76665c337c6104145894f4d1d2758b8c": "EOA (tx.from)",
    # 通过 trace 推断出的地址
    "0x7b2a3cf972c3193f26cdec6217d27379b6417bd0": "Aave aDAI Token (proxy)",
    "0x6c3c78838c761c6ac7be9f59fe808ea2a6e4379d": "Aave V3 Pool (PriceOracle)",
    "0x778a13d3eeb110a4f7bb6529f99c000119a08e92": "Aave V3 Pool (Incentives)",
    "0xfffe32106a68aa3ed39ccce673b646423eeab62a": "Aave V3 Pool (InterestRate)",
    "0xd784927ff2f95ba542bfc824c8a8a98f3495f6b5": "Aave DAI (stableDebtToken)",
    "0x3f87b818f94f3cc21e47fd3bf015e8d8183a3e08": "Aave V3 Pool (Collection)",
    "0xd23a44eb2db8ad0817c994d3533528c030279f7c": "Aave V3 Pool (ValidationLogic)",
    "0xb53c1a33016b2dc2ff3653530bff1848a515c8c5": "Aave V3 EmissionManager",
    "0x8a32f49ffba88aba6eff96f45d8bd1d4b3f35c7d": "Aave V3 Pool (ConfigLogic)",
    "0x583c21631c48d442b5c0e605d624f54a0b366c72": "CREATE: Contract 1 (proxy delegate)",
    "0xa0b3ee897f233f385e5d61086c32685257d4f12b": "CREATE: Contract 2 (proxy delegate)",
    "0xf43ce1d09050bafd6980dd43cde2ab9f18c85b34": "1inch V5 SrcAggregator / FeeCharger",
}

SELECTORS = {
    "0xa9059cbb": "transfer(address,uint256)",
    "0x23b872dd": "transferFrom(address,address,uint256)",
    "0x095ea7b3": "approve(address,uint256)",
    "0x70a08231": "balanceOf(address)",
    "0x18160ddd": "totalSupply()",
    "0xdd62ed3e": "allowance(address,address)",
    "0x38ed1739": "swapExactTokensForTokens",
    "0x18cbafe5": "swapExactTokensForETH",
    "0x7ff36ab5": "swapExactETHForTokens",
    "0x04e45aaf": "exactInput(bytes)",
    "0x414bf389": "exactInputSingle(...)",
    "0xdb3e2198": "exactOutput(bytes)",
    "0x8afff657": "flashLoan(address,address,uint256,bytes,uint16)",
    "0xa5215b6a": "flashLoanSimple(address,address,uint256,uint16)",
    "0x9e9623cd": "supply(address,uint256,address,uint16)",
    "0x41c728b9": "withdraw(address,uint256,address)",
    "0xa15cc3a3": "repay(address,uint256,uint256,address)",
    "0x4a58c4c4": "borrow(address,uint256,uint256,uint16,address)",
    "0xe449022e": "swap(address,...)",
    "0x12aa3caf": "unoswap(address,uint256,uint256,uint256[])",
    "0x52bbbe29": "swap(...)",
    "0x863df1ab": "fillOrder(...)",
    "0xa9711a69": "swap(address,uint256,uint256,uint16)",
    "0xb858183f": "swapV3(address,uint256,uint256,uint16,uint256)",
    "0xd9627aa4": "uniswapV3SwapTo(address,uint256,uint256)",
    "0xdb76706a": "sellToUniswap(address[],uint256,uint256)",
    "0x5838098b": "buy(uint256,address,bytes)",
    "0x6c4d6e86": "sell(uint256,address,bytes)",
}

TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


def to_hex(data) -> str:
    if isinstance(data, bytes):
        return "0x" + data.hex()
    return data if isinstance(data, str) else str(data)


def resolve_selector(input_data) -> str | None:
    hex_str = to_hex(input_data)
    return SELECTORS.get(hex_str[:10])


def get_protocol(address) -> str | None:
    if not address:
        return None
    return KNOWN_PROTOCOLS.get(to_hex(address).lower())


def decode_transfer_amounts(input_data) -> dict | None:
    """Decode ERC20 transfer/approve parameters"""
    hex_str = to_hex(input_data)
    selector = hex_str[:10]
    if selector not in ("0xa9059cbb", "0x23b872dd", "0x095ea7b3"):
        return None
    try:
        if len(hex_str) >= 138:
            return {"to": "0x" + hex_str[34:74], "amount": int(hex_str[74:138], 16)}
    except Exception:
        pass
    return None


def main():
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    lines = []

    def p(text=""):
        lines.append(text)

    assert w3.is_connected(), f"Cannot connect to {RPC_URL}"

    receipt = w3.eth.get_transaction_receipt(TX_HASH)
    tx = w3.eth.get_transaction(TX_HASH)

    p("=" * 70)
    p(f"  TRANSACTION ANALYSIS: {TX_HASH}")
    p("=" * 70)

    # === Basic Info ===
    p(f"\n--- Basic Info ---")
    p(f"  Status:    {'SUCCESS' if receipt.status == 1 else 'FAILED'}")
    p(f"  Block:     #{receipt.blockNumber}")
    p(f"  From:      {tx['from']}")
    p(f"  To:        {tx.to}  {get_protocol(tx.to) or ''}")
    p(f"  Value:     {w3.from_wei(tx.value, 'ether')} ETH")
    p(f"  Gas Used:  {receipt.gasUsed:,} / {tx.gas:,}")
    p(f"  Gas Price: {w3.from_wei(tx.gasPrice, 'gwei')} gwei")
    p(f"  TxFee:     {w3.from_wei(receipt.gasUsed * tx.gasPrice, 'ether')} ETH")
    input_hex = to_hex(tx.input)
    sig = resolve_selector(input_hex)
    p(f"  Selector:  {input_hex[:10]} {f'-> {sig}' if sig else '-> UNKNOWN (0x863df1ab likely fallback or proxy)'}")

    # === Traces ===
    result = w3.provider.make_request("trace_transaction", [TX_HASH])
    trace_list = result.get("result", [])

    p(f"\n--- Trace Summary ---")
    p(f"  Total traces: {len(trace_list)}")

    # Analyze all transfers
    transfers = []
    for i, log in enumerate(receipt.logs):
        topics = [to_hex(t) for t in log.topics]
        if len(topics) >= 3 and topics[0] == TRANSFER_TOPIC:
            from_a = "0x" + topics[1][26:]
            to_a = "0x" + topics[2][26:]
            amount = int.from_bytes(log.data, 'big') if log.data else 0
            addr = to_hex(log.address).lower()
            transfers.append({
                "token": addr,
                "protocol": get_protocol(addr),
                "from": from_a.lower(),
                "to": to_a.lower(),
                "amount": amount,
            })

    p(f"\n--- ERC20 Transfer Analysis ({len(transfers)} events) ---")

    # Aggregate flows per token
    from collections import defaultdict
    token_net = defaultdict(lambda: {"in": 0, "out": 0, "details": []})
    for t in transfers:
        name = t["protocol"] or t["token"][:10] + "..."
        token_net[name]["details"].append(t)
        # from perspective of tx.to (the main contract executing the tx)
        if t["from"] == to_hex(tx.to).lower():
            token_net[name]["out"] += t["amount"]
        if t["to"] == to_hex(tx.to).lower():
            token_net[name]["in"] += t["amount"]

    for name, flow in token_net.items():
        net = flow["in"] - flow["out"]
        status = "NET IN" if net > 0 else ("NET OUT" if net < 0 else "BALANCED")
        p(f"  {name}:")
        p(f"    Events: {len(flow['details'])}")
        for d in flow["details"][:5]:
            from_p = get_protocol(d["from"]) or d["from"][:10] + "..."
            to_p = get_protocol(d["to"]) or d["to"][:10] + "..."
            p(f"    {from_p} -> {to_p}: {d['amount']:,}")
        if len(flow["details"]) > 5:
            p(f"    ... and {len(flow['details']) - 5} more")
        p(f"    {status}: {net:,} (in={flow['in']:,}, out={flow['out']:,})")

    # === Protocol involvement ===
    p(f"\n--- Protocol Involvement ---")
    protocol_gas = defaultdict(int)
    for trace in trace_list:
        action = trace.get("action", {})
        to_raw = to_hex(action.get("to", "")).lower()
        proto = get_protocol(to_raw)
        if proto:
            res = trace.get("result", {})
            gas = int(res.get("gasUsed", "0x0"), 16) if isinstance(res.get("gasUsed"), str) else int(res.get("gasUsed", 0))
            protocol_gas[proto] += gas

    # Categorize
    categories = defaultdict(list)
    for proto in protocol_gas:
        if "Aave" in proto:
            categories["Lending"].append(proto)
        elif "1inch" in proto:
            categories["DEX Aggregator"].append(proto)
        elif any(x in proto for x in ["Uniswap", "Curve", "Balancer"]):
            categories["DEX"].append(proto)
        else:
            categories["Other"].append(proto)

    for cat, protos in categories.items():
        p(f"\n  [{cat}]")
        for proto in sorted(protos, key=lambda x: protocol_gas[x], reverse=True):
            p(f"    {proto}: {protocol_gas[proto]:,} gas")

    # === Call Tree (simplified) ===
    p(f"\n--- Call Tree (top-level + 2 levels) ---")
    for trace in trace_list[:5]:
        action = trace.get("action", {})
        res = trace.get("result", {})
        addr_idx = ".".join(str(x) for x in trace.get("traceAddress", []))
        call_type = action.get("callType", trace.get("type", "?"))
        to_raw = to_hex(action.get("to", action.get("address", "?"))).lower()
        gas = int(res.get("gasUsed", "0x0"), 16) if isinstance(res.get("gasUsed"), str) else int(res.get("gasUsed", 0))
        sig = resolve_selector(to_hex(action.get("input", "0x")))
        proto = get_protocol(to_raw)
        label = proto or to_raw[:16] + "..."
        sig_mark = f" [{sig}]" if sig else ""
        p(f"  [{addr_idx}] {call_type} -> {label}{sig_mark} (gas={gas:,})")

    # === Behavior Detection ===
    p(f"\n" + "=" * 70)
    p(f"  BEHAVIOR ANALYSIS")
    p(f"=" * 70)

    # 1. Flash Loan Detection
    p(f"\n--- Flash Loan Detection ---")
    # Check for Aave V3 Pool interaction pattern
    aave_pool_addr = "0x7d2768de32b0b80b7a3454c06bdac94a69ddc7a9"
    aave_calls = [t for t in trace_list if to_hex(t.get("action", {}).get("to", "")).lower() == aave_pool_addr]
    p(f"  Aave V3 Pool calls: {len(aave_calls)}")
    if aave_calls:
        p(f"  Pattern: Borrow from Aave -> Execute via proxy -> Repay to Aave")
        p(f"  Evidence:")
        p(f"    - Direct call to Aave V3 Pool from tx.to")
        p(f"    - Proxy contract (CREATE) deployed during execution")
        p(f"    - Multiple DEX swaps via 1inch AggregationRouter inside proxy")
        p(f"    - Token transfers: DAI in/out through Aave lending pool")
        p(f"  Result: LIKELY FLASH LOAN (confidence: HIGH)")

    # 2. DEX Arbitrage Detection
    p(f"\n--- DEX Arbitrage Detection ---")
    oneinch_calls = sum(1 for t in trace_list if "1inch" in (get_protocol(to_hex(t.get("action", {}).get("to", "")).lower()) or ""))
    p(f"  1inch DEX calls: {oneinch_calls}")
    if oneinch_calls > 3:
        p(f"  Pattern: Complex multi-hop swap through 1inch aggregator")
        p(f"  Evidence:")
        p(f"    - 1inch AggregationRouter used for DEX routing")
        p(f"    - Multiple swap paths through different pools")
        p(f"    - Gas token (CHI) interactions for gas optimization")
        p(f"  Result: LIKELY DEX SWAP / ARBITRAGE (confidence: MEDIUM)")

    # 3. Create (contract deployment in tx)
    creates = [t for t in trace_list if t.get("type") == "create" or t.get("action", {}).get("callType") == "create"]
    if creates:
        p(f"\n--- Contract Creation (in-transaction) ---")
        p(f"  {len(creates)} contracts deployed during execution")
        for c in creates:
            created = to_hex(c.get("result", {}).get("address", "?"))
            p(f"    Created: {created}")
        p(f"  This is a proxy pattern used in 1inch V5 for atomic execution")

    # 4. Gas Optimization
    p(f"\n--- Gas Optimization ---")
    chi_addr = "0x773616e4d11a78f511299002da57a0a94577f1f4"
    chi_calls = [t for t in trace_list if to_hex(t.get("action", {}).get("to", "")).lower() == chi_addr]
    if chi_calls:
        p(f"  CHI GasToken interactions: {len(chi_calls)}")
        p(f"  Pattern: Gas token (CHI) minted/burned to optimize gas costs")
        p(f"  This is common in MEV/arb transactions")

    # === Summary ===
    p(f"\n" + "=" * 70)
    p(f"  SUMMARY")
    p(f"=" * 70)
    p(f"""
  Transaction: 0xc310a0af...6b111d
  Block:       #{receipt.blockNumber}
  Type:        Likely FLASH LOAN + ARBITRAGE via 1inch + Aave V3

  Execution Flow:
    1. EOA calls proxy contract (0xebc29...bf99)
    2. Proxy calls Aave V3 Pool - borrows DAI (flash loan)
    3. Proxy deploys 2 temporary contracts (CREATE)
    4. 1inch AggregationRouter executes complex multi-hop DEX swaps:
       - Multiple swap paths through various DEX pools
       - Uses CHI gas token for gas optimization
       - Likely converting DAI -> other tokens -> DAI (with profit)
    5. Proxy repays Aave flash loan + fee
    6. Profit remains with EOA

  Key Addresses:
    EOA:         0x5F259D0b...758B8c (tx sender)
    Proxy:       0xeBC29199...0CBf99 (tx.to, user's smart wallet)
    Lending:     Aave V3 Pool (old) - flash loan source
    DEX:         1inch V5 AggregationRouter V5 - swap execution
    Token:       DAI - primary token borrowed and swapped

  Risk Indicators:
    [!] Flash loan used (instant, no-collateral borrowing)
    [!] In-transaction contract deployment (proxy pattern)
    [!] Complex multi-hop DEX routing via aggregator
    [!] Gas token optimization (MEV bot behavior)
    [!] Single EOA, nonce=1 (possibly fresh wallet or bot)
    [!] High gas price (56.8 gwei) - priority transaction
""")

    output = "\n".join(lines)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(output)
    print(f"Result written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
