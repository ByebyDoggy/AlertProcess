# Script-First Detection Platform Design

## Summary

AlertProcessor will stop treating rule-chain graphs and `nodes/` as the primary product architecture. The new architecture is a script-first detection platform: developers write detection scripts and replay them against offline fixtures; ordinary users buy monitoring services, configure watched objects and notification channels, and receive alerts.

This is a deliberate hard pivot. The old rule-chain/node model should not remain as a compatibility-first design center. Valuable detection algorithms can be migrated, but `NodeRegistry`, visual graph execution, provider/detector/action node composition, and user-facing rule-chain editing are no longer core product paths.

## Product positioning

Ordinary users do not need to know which detector runs or how detectors are connected. They need:

1. Service subscription or entitlement.
2. Watched-object configuration:
   - chain
   - address
   - contract
   - token
   - LP / vault / protocol object
3. Notification channel configuration:
   - Webhook
   - Telegram
   - later Email or SaaS notification center
4. Alert output with:
   - transaction hash
   - risk score
   - severity
   - attack category
   - key evidence
   - affected assets and addresses

The product is a blockchain attack monitoring and alerting service, not a rule-chain editor.

## Developer workflow

Developers and researchers should work in this loop:

1. Analyze an attack transaction.
2. Write a detector strategy document.
3. Implement a `DetectionScript`.
4. Freeze relevant trace / transfer / balance-change data into an offline fixture.
5. Run replay tests.
6. Add the script to a `StrategyPack`.
7. Let the monitoring service execute the pack and emit alerts.

The preferred development unit is a Python detection script, not a graph node.

## New top-level architecture

```text
AlertProcessor/
  detection/        # Core detection script platform
  strategies/       # Concrete attack detection scripts and strategy packs
  replay/           # Offline fixtures and replay runner
  alerting/         # Alert formatting, dry-run, channel dispatch
  ingestion/        # Input adapters for tx, trace, fund-flow, balance changes
  legacy/           # Optional temporary reference area during migration only
```

`nodes/` and `engine/` are no longer primary architecture. If old code is useful, migrate the algorithm or model into the new directories. Do not preserve node abstractions just for compatibility.

## Core abstractions

### DetectionContext

`DetectionContext` is the normalized input object consumed by scripts.

It should preserve useful fields from the existing `TransactionContext` while making script requirements explicit.

Minimum fields:

- `chain_id`
- `tx_hash`
- `block_number`
- `timestamp`
- `from_address`
- `to_address`
- `value`
- `input_data`
- `logs`
- `trace_calls`
- `transfers`
- `balance_changes`
- `token_prices`
- `address_labels`
- `metadata`

The model should allow missing optional enrichment fields, but each script declares which fields it requires.

### DetectionEvidence

Evidence is a structured explanation item.

Recommended fields:

- `kind`
- `description`
- `weight`
- `data`
- `source`

Evidence should prioritize generalized behavior:

- fund flow
- balance change
- call structure
- callback / delegatecall / fanout
- address role
- temporary contract behavior
- LP / vault / proxy-like structure

Protocol-specific selector or function-name evidence may be included for debugging, but it should not be the primary trigger unless it is a highly generic interface.

### DetectionResult

`DetectionResult` is the script output.

Recommended fields:

- `script_id`
- `strategy_id`
- `score`
- `passed`
- `severity`
- `attack_type`
- `labels`
- `evidence`
- `entities`
- `summary`
- `details`

This should replace `DetectorOutputMixin` as the primary result model, while retaining familiar score/severity/labels semantics.

### DetectionScript

A detection script is the core developer-facing unit.

Example interface:

```python
class DetectionScript:
    id: str
    version: str
    name: str
    description: str
    required_inputs: list[str]
    default_threshold: float

    async def detect(self, ctx: DetectionContext) -> DetectionResult:
        raise NotImplementedError
```

Scripts should be normal Python modules, easy to test directly, and independent of graph execution.

### StrategyPack

A strategy pack groups scripts into a product or research bundle.

Example pack types:

- `basic_monitoring`
- `defi_attack_monitoring`
- `bsc_high_risk_pack`
- `protocol_research_pack`

A pack defines:

- pack id
- version
- scripts included
- default thresholds
- required input enrichments
- alerting policy hints

### DetectionRuntime

The runtime executes scripts.

Responsibilities:

1. Validate context against script requirements.
2. Load selected strategy packs.
3. Execute scripts, preferably concurrently where safe.
4. Catch script errors and return structured runtime errors without crashing the whole batch.
5. Aggregate results into alert candidates.
6. Preserve per-script evidence for explainability.

### ReplayRunner

Replay is a first-class testing and research tool.

A replay case should contain:

- fixture id
- chain id
- transaction hash
- normalized context fixture
- selected scripts or strategy pack
- expected passed scripts
- expected severity / labels / evidence fragments

Replay must not depend on live RPC, Phalcon, explorer pages, or third-party APIs.

### AlertDispatcher

Alerting is separate from detection.

Responsibilities:

- Convert detection results into alert payloads.
- Respect dry-run mode.
- Dispatch to configured channels.
- Return structured delivery results.

Initial channels:

- Webhook
- Telegram

Dry-run must guarantee no external message is sent.

## What to delete or retire

The following concepts should be removed from the main product path:

- `NodeRegistry`
- visual rule-chain graph execution
- node ports
- node categories
- provider/detector/action graph composition
- user-facing chain editor
- detector development through node registration

Old algorithms may be migrated. Old abstractions should not be preserved unless a migration task explicitly needs temporary reference code.

## Migration strategy

This rewrite should be implemented as a new vertical slice first, then old paths can be removed or ignored.

First migrated detector candidate:

- `token_contract_active_lp_drain`

Reason:

- It already has a real attack fixture.
- It uses behavior-first evidence.
- It has unit and replay tests.
- It represents the desired future development workflow.

First vertical slice:

1. Create core detection models.
2. Create script interface and runtime.
3. Migrate `token_contract_active_lp_drain` into `strategies/` as a `DetectionScript`.
4. Create replay fixture and replay runner around the existing JUDAO fixture data.
5. Add alert dispatcher dry-run tests.
6. Update documentation to state that new detector development must use scripts, not nodes.

## Testing requirements

Every new module needs direct unit coverage.

Minimum tests for the first slice:

1. `DetectionContext` accepts normalized transaction data and keeps enrichment fields.
2. `DetectionScript` implementations can be called directly.
3. `DetectionRuntime` executes one script and returns a result.
4. `DetectionRuntime` executes multiple scripts and isolates script failures.
5. `ReplayRunner` runs an offline fixture without network access.
6. Migrated JUDAO strategy passes on malicious fixture.
7. Migrated JUDAO strategy does not pass on a benign control fixture.
8. `AlertDispatcher` dry-run does not send real Webhook or Telegram messages.

## Documentation requirements

After implementation and tests pass, update development documentation to say:

- `nodes/` and rule-chain editing are retired as primary development paths.
- New detection logic must be written as `DetectionScript`.
- Real attacks should produce strategy docs and offline replay fixtures.
- Selector/function-name evidence is auxiliary unless it is a generic standard interface.
- Ordinary users interact with monitoring services and alert channels, not detector graphs.

## Non-goals for the first slice

- Do not migrate every existing detector immediately.
- Do not build a new visual editor.
- Do not add live RPC dependencies to replay tests.
- Do not redesign frontend subscription flows in this slice.
- Do not preserve old node abstractions just to avoid deleting code later.

## Approval decision

The selected approach is full script-platform rewrite, not gradual node compatibility.

Implementation should optimize for a clean new architecture and only reuse old code when it directly supports the new script-first workflow.
