"""Offline Ekubo callback drain fixture for detector regression tests."""

ATTACK_TX_HASH = "0x770bc9a1f7c32cb63a5002b9ceb5c7994cd3af0fc6b2309cb32d3c46f629daa0"
ATTACKER = "0xa911ff351b143634dbc5af3e204ea074583a83e3"
ENTRY_CONTRACT = "0x61b0dad9628d3e644eb560a5c9b0f960430e3a75"
HELPER = "0x8ccb1ffd5c2aa6bd926473425dea4c8c15de60fd"
EKUBO_CORE = "0xe0e0e08a6a4b9dc7bd67bcb7aade5cf48157d444"
VICTIM = "0x765decf4fa157756e850c1079f60801b9219edd1"
WBTC = "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599"
WBTC_DECIMALS = 8
WBTC_PRICE = 81023.323
RAW_AMOUNT_PER_LOOP = 20_000_000
REPEAT_COUNT = 85
TOTAL_RAW_AMOUNT = RAW_AMOUNT_PER_LOOP * REPEAT_COUNT


def build_ekubo_context() -> dict:
    erc20_calls = []
    transfers = []
    trace_calls = []

    for i in range(REPEAT_COUNT):
        erc20_calls.append({
            "method": "transferFrom",
            "token": WBTC,
            "from": VICTIM,
            "to": EKUBO_CORE,
            "amount_raw": str(RAW_AMOUNT_PER_LOOP),
            "caller": HELPER,
        })
        erc20_calls.append({
            "method": "transfer",
            "token": WBTC,
            "from": EKUBO_CORE,
            "to": ATTACKER,
            "amount_raw": str(RAW_AMOUNT_PER_LOOP),
            "caller": EKUBO_CORE,
        })
        transfers.extend([
            {"token": WBTC, "from": VICTIM, "to": EKUBO_CORE, "amount_raw": str(RAW_AMOUNT_PER_LOOP)},
            {"token": WBTC, "from": EKUBO_CORE, "to": ATTACKER, "amount_raw": str(RAW_AMOUNT_PER_LOOP)},
        ])
        trace_calls.extend([
            {"name": "lock", "to": EKUBO_CORE, "index": i * 7},
            {"name": "locked", "to": HELPER, "index": i * 7 + 1},
            {"name": "withdraw", "to": EKUBO_CORE, "index": i * 7 + 2},
            {"name": "transfer", "to": WBTC, "index": i * 7 + 3},
            {"name": "pay", "to": EKUBO_CORE, "index": i * 7 + 4},
            {"name": "payCallback", "to": HELPER, "index": i * 7 + 5},
            {"name": "transferFrom", "to": WBTC, "index": i * 7 + 6},
        ])

    return {
        "chain_id": 1,
        "tx_hash": ATTACK_TX_HASH,
        "block_number": 25030409,
        "from_address": ATTACKER,
        "to_address": ENTRY_CONTRACT,
        "value": 0,
        "gas_used": 1_735_786,
        "timestamp": "2026-05-05T17:50:35Z",
        "erc20_calls": erc20_calls,
        "transfers": transfers,
        "trace_calls": trace_calls,
        "top_profit_address": ATTACKER,
        "top_loss_address": VICTIM,
        "token_prices": {WBTC: WBTC_PRICE},
        "token_decimals": {WBTC: WBTC_DECIMALS},
    }


def build_normal_router_swap_context() -> dict:
    user = "0x1111111111111111111111111111111111111111"
    router = "0x2222222222222222222222222222222222222222"
    weth = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
    usdc = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"

    return {
        "chain_id": 1,
        "tx_hash": "0xnormalrouter",
        "from_address": user,
        "to_address": router,
        "value": 0,
        "erc20_calls": [
            {"method": "transferFrom", "token": weth, "from": user, "to": router, "amount_raw": str(10**18), "caller": router},
            {"method": "transfer", "token": usdc, "from": router, "to": user, "amount_raw": str(3000 * 10**6), "caller": router},
        ],
        "transfers": [
            {"token": weth, "from": user, "to": router, "amount_raw": str(10**18)},
            {"token": usdc, "from": router, "to": user, "amount_raw": str(3000 * 10**6)},
        ],
        "top_profit_address": user,
        "top_loss_address": user,
        "token_prices": {weth: 3000.0, usdc: 1.0},
        "token_decimals": {weth: 18, usdc: 6},
    }
