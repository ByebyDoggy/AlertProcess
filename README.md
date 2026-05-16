# AlertProcessor

AlertProcessor is being migrated from a visual rule-chain/node product into a script-first blockchain attack detection and alerting platform.

The product direction is now:

- Ordinary users subscribe to monitoring services, configure watched objects, and receive alerts.
- Developers and researchers write Python detection scripts, freeze offline fixtures, and replay attacks without live RPC dependencies.
- Rule-chain graph editing and `nodes/` are retired as primary development paths.

## Current architecture

```text
AlertProcessor/
├── detection/      # Core detection context, result, script, strategy pack, and runtime models
├── strategies/     # Concrete attack detection scripts
├── replay/         # Offline fixture replay runner
├── alerting/       # Alert payloads, dry-run dispatch, and channel abstractions
├── tests/          # Unit, strategy, replay, alerting, and architecture tests
└── docs/           # Design specs and implementation plans
```

### `detection/`

The core script platform.

- `DetectionContext` normalizes transaction, trace, transfer, price, label, and enrichment data for scripts.
- `DetectionEvidence` stores structured explanation items.
- `DetectionResult` stores score, severity, labels, entities, evidence, and alert details.
- `DetectionScript` is the developer-facing interface for new detection logic.
- `DetectionRuntime` validates script requirements, executes scripts, isolates script failures, and returns alert candidates.
- `StrategyPack` groups scripts into monitoring or research bundles.

### `strategies/`

Concrete Python detection scripts live here.

The first migrated strategy is `token_contract_active_lp_drain`, which detects token contracts that actively participate in fund and call flow while an LP is drained and the sender or token contract profits.

New strategy development should prioritize generalized behavior evidence:

1. Fund flow and balance changes.
2. Call structure, callback-like behavior, delegatecall, and fanout.
3. Address roles, temporary contracts, LP/vault/proxy-like structures.
4. Generic selectors only as supporting evidence.
5. Protocol/project-specific selectors only as debug or auxiliary evidence.

A production detector should not pass solely because a protocol-specific selector or function name matched.

### `replay/`

Replay is the required research and regression workflow.

Replay cases must use offline fixtures and must not depend on live RPC, explorer pages, Phalcon pages, WebSearch, or WebFetch. A replay case defines normalized context data, selected scripts, expected passing scripts, minimum scores, labels, and evidence checks.

### `alerting/`

Alerting is separate from detection.

- `AlertPayload` converts detection results into outbound alert data.
- `AlertDispatcher` sends payloads to configured channels.
- Dry-run mode guarantees that no channel `send()` method is called.
- Channel failures are isolated so one failed channel does not prevent later channels from being attempted.
- `WebhookChannel` and `TelegramChannel` are currently safe placeholders until real transports are added.

## Retired architecture

The legacy `nodes/` directory has been removed from the main product path. The following concepts are no longer the core architecture:

- `NodeRegistry`
- visual rule-chain graph execution
- node ports and node categories
- provider/detector/action node composition
- user-facing detector graph editing
- detector development through node registration

Useful algorithms from the old implementation may be migrated, but new detection logic must be implemented as `DetectionScript` modules.

## Developer workflow

1. Analyze an attack transaction.
2. Write a detector strategy document.
3. Implement a `DetectionScript`.
4. Freeze trace, transfer, balance-change, and enrichment data into an offline fixture.
5. Run replay tests.
6. Add the script to a `StrategyPack` when it is ready for bundled monitoring.
7. Use alerting dry-run tests before enabling real external notification transports.

## Adding a detection script

A detection script should be a normal Python module that can be tested directly.

```python
from detection import DetectionContext, DetectionResult, DetectionScript


class ExampleScript(DetectionScript):
    id = "example_script"
    version = "1.0.0"
    name = "Example Script"
    description = "Detects one behavior-first attack pattern."
    required_inputs = ("transfers", "trace_calls")
    default_threshold = 40.0

    async def detect(self, ctx: DetectionContext) -> DetectionResult:
        return DetectionResult.no_match(self.id, "pattern not present")
```

Each new script needs direct unit coverage and at least one replay fixture before it is considered production-ready.

## Testing

Use the project virtual environment first:

```bash
.venv/Scripts/python.exe -m pytest tests/architecture tests/detection tests/strategies tests/replay tests/alerting -v
```

Targeted suites:

```bash
.venv/Scripts/python.exe -m pytest tests/detection -v
.venv/Scripts/python.exe -m pytest tests/strategies -v
.venv/Scripts/python.exe -m pytest tests/replay -v
.venv/Scripts/python.exe -m pytest tests/alerting -v
```

Old `tests/nodes` and rule-chain graph tests are not part of the new script-first verification path after the `nodes/` removal.
