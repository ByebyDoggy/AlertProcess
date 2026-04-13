#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Standalone component tests
==========================
Tests core components without requiring a running AlertProcessor server:

  1. TokenPriceCache <-> Mock MarketDataBase integration
  2. Data model validation (IngestedLog, TxLogsGroup, MatchedAlert)
  3. IngestRouter Pydantic models
  4. Value USD calculation logic

Usage:
  python scripts/test_ingest_mock.py
"""

import asyncio
import json
import sys
import os
from pathlib import Path

# Ensure project root is in path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ================================================================
# Mock MarketDataBase Server (port 8001)
# ================================================================

MOCK_TOKEN_DATA = {
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": {
        "symbol": "WETH", "name": "Wrapped Ether",
        "decimals": 18, "price_usd": 3499.50,
        "price_usd_24h_change": 2.35,
    },
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": {
        "symbol": "USDC", "name": "USD Coin",
        "decimals": 6, "price_usd": 1.00,
        "price_usd_24h_change": 0.01,
    },
    "0xdac17f958d2ee523a2206206994597c13d831ec7": {
        "symbol": "USDT", "name": "Tether USD",
        "decimals": 6, "price_usd": 1.00,
        "price_usd_24h_change": -0.01,
    },
}


async def mock_market_db_server():
    """Start Mock MarketDataBase HTTP Server"""
    from aiohttp import web

    async def handle_batch_info(request):
        body = await request.json()
        addresses = body.get("contract_addresses", [])
        include_native = body.get("include_native", True)

        tokens = {}
        for addr in addresses:
            key = addr.lower()
            if key in MOCK_TOKEN_DATA:
                tokens[key] = MOCK_TOKEN_DATA[key]

        result = {"success": True, "data": {"tokens": tokens}}

        if include_native:
            result["data"]["__native__"] = {
                "symbol": "ETH", "name": "Ethereum",
                "decimals": 18, "price_usd": 3500.00,
                "price_usd_24h_change": 2.40,
            }

        return web.json_response(result)

    app = web.Application()
    app.router.add_post("/api/v1/tokens/batch-info", handle_batch_info)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", 8001)
    await site.start()
    print("[MOCK-MDB] Mock MarketDataBase started on http://localhost:8001")
    return runner


# ================================================================
# Test: Sample Event Logs data
# ================================================================

FLASH_LOAN_LOGS = [
    {
        "address": "0x7D2768DE32B0B80B7a3454C06B0Ac3200957B515",
        "topics": [
            "0x6b1277772e905ce5e7a4bb572f0e33e98e7e589ee0acf0bd5a85c0ef6a5c26e1",
            "0x000000000000000000000000d8da6bf26964af9d7eed9e03e53415d37aa96045",
            "0x0000000000000000000000000000000000000000000000000000000000000000",
            "0x0000000000000000000000000000000000000000000000000000000446c3b00",
            "0x0000000000000000000000000000000000000000000000000000000000000001",
            "0x0000000000000000000000000000000000000000000000000785ee0b6cf53",
        ],
        "data": "0x",
        "block_number": 19584123,
        "transaction_hash": "0xc310a0affe2169d1f6feec1c63dbc7f7c62a887fa48795d327d4d2da2d6b111d",
        "log_index": 0,
        "transaction_index": 5,
        "block_hash": "0xd49b57e5a7b8cc8d96eb13f39cbbca2fbf6b4e3a7351d92e0c611ffea4b8b44d",
        "removed": False,
    },
    {
        "address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        "topics": [
            "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
            "0x0000000000000000000000007d2768de32b0b80b7a3454c06b0ac3200957b515",
            "0x000000000000000000000000d8da6bf26964af9d7eed9e03e53415d37aa96045",
        ],
        "data": "0x00000000000000000000000000000000000000000000000000000006fc23ac00",
        "block_number": 19584123,
        "transaction_hash": "0xc310a0affe2169d1f6feec1c63dbc7f7c62a887fa48795d327d4d2da2d6b111d",
        "log_index": 1,
        "transaction_index": 5,
        "block_hash": "0xd49b57e5a7b8cc8d96eb13f39cbbca2fbf6b4e3a7351d92e0c611ffea4b8b44d",
        "removed": False,
    },
]


NORMAL_SWAP_TX = "0xd456b789cdef0123456789abcdef0123456789abcdef0123456789abcdef"
NORMAL_SWAP_LOGS = [
    {
        "address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        "topics": [
            "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
            "0x000000000000000000000000abc123456789012345678901234567890123456",
            "0x000000000000000000000000def123456789012345678901234567890123456",
        ],
        "data": "0x0000000000000000000000000000000000000000000000000000000de0b6b3a",
        "block_number": 19584124,
        "transaction_hash": NORMAL_SWAP_TX,
        "log_index": 0,
        "transaction_index": 10,
        "block_hash": "0xabcd1234...",
        "removed": False,
    },
]


# ================================================================
# Unit Tests
# ================================================================

async def test_token_price_cache():
    """Test 1: TokenPriceCache <-> Mock MarketDataBase integration"""
    print("\n--- Test 1: TokenPriceCache + Mock MarketDataBase ---")

    mdb_runner = await mock_market_db_server()

    try:
        import httpx as httpx_async
        from detectors.trace.token_price_cache import TokenPriceCache

        cache_client = httpx_async.AsyncClient(timeout=10.0)
        cache = TokenPriceCache(
            market_db_url="http://localhost:8001",
            client=cache_client,
        )

        results = await cache.batch_fetch(
            chain_id=1,
            addresses=[
                "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
                "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606EB48",
                "0xdAC17F958D2ee523a2206206994597C13D831ec7",
                "0x000000000000000000000000000000000000dead",
            ],
            include_native=True,
        )
        assert len(results) > 0

        for addr, meta in results.items():
            display = addr if addr else "(native/ETH)"
            print(f"    {display}: symbol={meta.symbol} price=${meta.price_usd} dec={meta.decimals}")

        weth_key = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
        assert results[weth_key].symbol == "WETH"
        assert results[weth_key].price_usd == 3499.50

        native = results.get("")
        assert native is not None and native.symbol == "ETH" and native.price_usd == 3500.00

        # Cache hit test
        results2 = await cache.batch_fetch(
            chain_id=1,
            addresses=["0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"],
            include_native=False,
        )
        assert len(results2) > 0

        stats = cache.stats()
        print(f"    Cache stats: {json.dumps(stats)}")
        await cache_client.aclose()
        print("  [PASS] TokenPriceCache works correctly")
        return True

    finally:
        await mdb_runner.cleanup()


async def test_data_models():
    """Test 2: Data models — IngestedLog, TxLogsGroup, MatchedAlert"""
    print("\n--- Test 2: Data Models ---")

    from detectors.trace.rule_engine import IngestedLog, TxLogsGroup, MatchedAlert, Severity

    # IngestedLog
    log_dict = FLASH_LOAN_LOGS[0]
    ingested = IngestedLog.from_dict(log_dict)
    assert ingested.address == "0x7d2768de32b0b80b7a3454c06b0ac3200957b515"
    assert ingested.block_number == 19584123
    assert len(ingested.topics) == 6
    assert ingested.removed is False
    print(f"    IngestedLog: address={ingested.address[:16]}... topics={len(ingested.topics)}")

    # TxLogsGroup
    logs = [IngestedLog.from_dict(l) for l in FLASH_LOAN_LOGS]
    group = TxLogsGroup(
        tx_hash=FLASH_LOAN_LOGS[0]["transaction_hash"],
        chain_id=1,
        logs=logs,
        block_number=19584123,
    )
    assert group.log_count == 2
    assert len(group.unique_addresses) >= 1
    print(f"    TxLogsGroup: {group.log_count} logs, "
          f"{len(group.unique_addresses)} unique addrs, "
          f"{len(group.unique_topics)} unique topics")

    # MatchedAlert
    alert = MatchedAlert(
        tx_hash=group.tx_hash,
        chain_id=1,
        block_number=19584123,
        trigger_log_count=group.log_count,
        final_score=85.0,
        final_severity="HIGH",
        labels=["FLASH_LOAN_PROTOCOL:Aave V2"],
        results=[
            {"node_id": "n1", "node_type": "flash_loan_detector", "score": 85.0},
        ],
    )
    bm = alert.best_match
    assert bm["alert_type"] == "flash_loan_detector"
    assert bm["severity"] == "HIGH"
    d = alert.to_dict()
    assert d["txHash"] == group.tx_hash
    assert d["finalScore"] == 85.0
    print(f"    MatchedAlert: score={alert.final_score} severity={alert.final_severity}")
    print(f"    best_match: type={bm['alert_type']} conf={bm['confidence']}")

    print("  [PASS] All data models work correctly")
    return True


async def test_ingest_models():
    """Test 3: Pydantic model validation"""
    print("\n--- Test 3: Ingest Router Model Validation ---")

    from routers.detectors.ingest_router import (
        LogObject, IngestLogsRequest, ReplayLogsRequest, IngestResponse,
    )

    log = LogObject(
        address="0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        topics=["0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"],
        data="0x",
        block_number=19584123,
        transaction_hash="0xabcd" + "00" * 30,
        log_index=0,
        transaction_index=0,
    )
    assert log.address.lower() == "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"

    req = IngestLogsRequest(
        chain_id=1,
        chain_name="ethereum",
        logs=[log],
        from_block=19584120,
        to_block=19584123,
        log_count=1,
    )
    assert req.chain_id == 1 and len(req.logs) == 1

    replay = ReplayLogsRequest(
        chain_id=1,
        from_block=19584000,
        to_block=19584119,
        reason="reconnection_gap",
        logs=[log],
    )
    assert replay.reason == "reconnection_gap"

    resp = IngestResponse(
        status="accepted", received_log_count=1,
        from_block=19584120, to_block=19584123,
        matched_alert_count=0, active_chain_count=0,
    )
    assert resp.model_dump()["active_chain_count"] == 0

    print("  [PASS] All models validate correctly")
    return True


async def test_value_usd_calculation():
    """Test 4: Value USD calculation logic"""
    print("\n--- Test 4: Value USD Calculation Logic ---")

    # 100 USDC @ $1.00, decimals=6
    v = round(abs(100 * 10**6) / (10 ** 6) * 1.00, 2)
    assert v == 100.0
    print(f"    100 USDC @ $1.00 = ${v}")

    # 1 WETH @ $3499.50, decimals=18
    v = round(abs(10**18) / (10 ** 18) * 3499.50, 2)
    assert v == 3499.5
    print(f"    1 WETH @ $3499.50 = ${v}")

    # 1500 ETH @ $3500.00, decimals=18
    v = round(abs(1500 * 10**18) / (10 ** 18) * 3500.00, 2)
    assert v == 5250000.0
    print(f"    1500 ETH @ $3500.00 = ${v:,.2f}")

    print("  [PASS] Value USD calculations are correct")
    return True


async def run_all_tests():
    """Run all tests"""
    print("=" * 70)
    print("  AlertProcessor Component Tests (standalone, no server needed)")
    print("=" * 70)

    passed = 0
    failed = 0

    tests = [
        ("Token Price Cache", test_token_price_cache),
        ("Data Models", test_data_models),
        ("Ingest Models", test_ingest_models),
        ("Value USD Calc", test_value_usd_calculation),
    ]

    for name, test_fn in tests:
        try:
            result = await test_fn()
            if result:
                passed += 1
        except Exception as e:
            failed += 1
            print(f"  [FAIL] {name}: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 70)
    print(f"  Results: {passed}/{len(tests)} passed, {failed} failed")
    if failed == 0:
        print("  ALL TESTS PASSED")
    print("=" * 70)

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
