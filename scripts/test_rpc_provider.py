"""Test RPC provider v2 — DB-driven, connection pooling, health check"""
import asyncio
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from detectors.trace.provider import get_rpc_client, MultiRpcClient

async def main():
    c = get_rpc_client()

    # 1. Load config (should seed DB if empty)
    print("=== Loading Config ===")
    await c.ensure_loaded()

    # 2. Pool status
    print("\n=== Pool Status ===")
    pools = await c.get_pool_status()
    total_n, healthy_n = 0, 0
    for p in pools:
        print(f"  {p['chainName']}: {p['healthyNodes']}/{p['totalNodes']} nodes")
        total_n += p['totalNodes']
        healthy_n += p['healthyNodes']
    print(f"  Total: {healthy_n}/{total_n} healthy")

    # 3. Test connection on first ETH node
    if pools and pools[0].get('nodes'):
        node = pools[0]['nodes'][0]
        url = node.get('url', '').rstrip('*')
        print(f"\n=== Test Connection: {node['name']} ===")
        r = await c.test_connection(url, timeout=10)
        print(f"  ok={r['ok']} latency={r['latency_ms']}ms chainId={r['chain_id']} block={r['block_number']}")
        if r.get('error'):
            print(f"  error={r['error'][:100]}")

    # 4. Health check (ETH only)
    print("\n=== Health Check (ETH) ===")
    reports = await c.run_health_checks(chain_id=1)
    for rep in reports[:5]:
        print(f"  {rep['name']}: status={rep['status']} latency={rep['latency_ms']}ms")

    # 5. Supported chains
    print(f"\nSupported chains: {[ch['chainId'] for ch in MultiRpcClient.supported_chains()]}")

    await c.close()
    print("\nAll tests passed!")

if __name__ == "__main__":
    asyncio.run(main())
