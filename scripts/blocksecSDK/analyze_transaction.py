from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.blocksecSDK.client import BlockSecClient


async def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze a transaction through BlockSec APIs")
    parser.add_argument("--chain-id", type=int, required=True)
    parser.add_argument("--tx-hash", required=True)
    parser.add_argument("--output", default="")
    parser.add_argument("--no-fundflow", action="store_true")
    args = parser.parse_args()

    client = BlockSecClient()
    result = await client.analyze_transaction(
        chain_id=args.chain_id,
        tx_hash=args.tx_hash,
        include_fundflow=not args.no_fundflow,
    )

    payload = {
        "chain_id": result.chain_id,
        "tx_hash": result.tx_hash,
        "attack_event": result.attack_event.raw if result.attack_event else None,
        "basic_info": result.basic_info.raw if result.basic_info else None,
        "balance_change_summary": {
            "largest_inflow": result.balance_changes.largest_inflow.account if result.balance_changes and result.balance_changes.largest_inflow else None,
            "largest_outflow": result.balance_changes.largest_outflow.account if result.balance_changes and result.balance_changes.largest_outflow else None,
            "net_value_by_account": result.balance_changes.net_value_by_account if result.balance_changes else {},
        },
        "invocation_flow_summary": {
            "node_count": len(result.invocation_flow.nodes) if result.invocation_flow else 0,
            "root_ids": result.invocation_flow.root_ids if result.invocation_flow else [],
            "max_depth": result.invocation_flow.max_depth if result.invocation_flow else 0,
            "nodes": [
                {
                    "id": node.node_id,
                    "parent_id": node.parent_id,
                    "depth": node.depth,
                    "from": node.from_address,
                    "to": node.to_address,
                    "call_type": node.call_type,
                    "selector": node.selector,
                    "value": node.value,
                    "children": node.children,
                }
                for node in (result.invocation_flow.nodes[:50] if result.invocation_flow else [])
            ],
        },
        "alert_data_blocksec": result.to_alert_data_blocksec(),
    }

    content = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(content, encoding="utf-8")
    else:
        print(content)


if __name__ == "__main__":
    asyncio.run(main())
