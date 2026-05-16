# Log-First Staged Risk Pipeline Design

## Context

AlertProcessor 已经从 rule-chain / nodes 架构转向脚本优先的检测平台。当前核心能力包括 `DetectionContext`、`DetectionScript`、`DetectionRuntime`、`ReplayRunner` 和 alert dispatcher，但旧的 trace provider、Moralis/address-age provider 已在目录重构中移除。

用户希望实现一个固定的单交易分层检测策略：先从日志计算参与方资金净流出，只有当某地址净流出超过 1,000,000 USD 时才拉取 trace；随后运行协议/trace 检测器识别历史攻击特征；如果存在敏感特征，再查询攻击者/盈利者/调用者/合约地址创建时间；若关键地址是 2 天内新建地址，则发出告警。后续时序检测也应复用这一分层思想。

## Goals

1. 建立单交易 log-first staged pipeline。
2. 将日志资金流、trace 拉取、检测脚本运行、地址年龄查询拆成清晰边界。
3. 保证 trace 和 address-age provider 可替换，第一阶段优先支持 fake/offline provider 和单元测试。
4. 复用现有 `DetectionRuntime` 和 `DetectionScript` 作为中段敏感特征检测层。
5. 为后续 temporal/sequence pipeline 留出复用接口，但不在第一阶段实现完整时序引擎。

## Non-goals

- 不恢复旧 `nodes/` 或 rule-chain graph editor。
- 不在第一阶段接入真实 Moralis / Blocksec / RPC 网络调用。
- 不把所有逻辑写成一个巨大的 detection script。
- 不实现完整多交易窗口状态机；只设计接口兼容未来扩展。

## Architecture

采用固定 gate pipeline：

```text
raw log message / parsed logs
        |
        v
Log Balance Gate
        |
        | only if max net outflow >= 1,000,000 USD
        v
Trace Provider
        |
        v
DetectionRuntime with trace-sensitive DetectionScript list
        |
        | only if any script passes
        v
Address Age Provider
        |
        | only if key address age <= 2 days
        v
Alert candidate
```

### 1. Log Balance Gate

This stage parses transfer-like log data and computes net USD movement by address.

Responsibilities:

- Normalize transfer events into `{token, from, to, amount_raw}`.
- Compute per-address, per-token net raw amount.
- Convert token outflows to USD using `token_prices` and `token_decimals`.
- Identify top loss address and top profit address.
- Stop the pipeline before trace fetch if no address has net outflow above threshold.

The threshold defaults to `1_000_000.0` USD.

### 2. Trace Provider

This stage fetches and normalizes transaction trace calls only after the log gate passes.

Provider interface should be narrow:

```python
class TraceProvider(Protocol):
    async def get_trace_calls(self, chain_id: int, tx_hash: str) -> list[dict[str, Any]]:
        ...
```

First implementation:

- `StaticTraceProvider` or fake provider for unit tests and offline replay.

Future implementation:

- Moralis / Blocksec / RPC-backed provider, depending on available API and accuracy.

### 3. Sensitive Feature Stage

This stage builds a `DetectionContext` with:

- original tx/log fields;
- computed `transfers`;
- computed `balance_changes`;
- `trace_calls` from provider;
- `metadata.top_loss_address`;
- `metadata.top_profit_address`.

Then it runs existing script-first detectors through `DetectionRuntime`.

First reusable script:

- `TokenContractActiveLPDrainScript`.

Future scripts:

- flash-loan behavior detector;
- callback third-party drain detector;
- delegatecall/proxy privilege anomaly detector;
- oracle manipulation detector;
- arbitrary external-call fanout detector.

The pipeline only continues if at least one detection result has `passed is True`.

### 4. Address Age Gate

This stage queries creation/first-seen time only after a sensitive detector passes.

Provider interface:

```python
class AddressAgeProvider(Protocol):
    async def get_address_age(self, chain_id: int, address: str, reference_time: datetime) -> AddressAge:
        ...
```

`AddressAge` should include:

- `address`;
- `created_at` or `first_seen_at`;
- `age_seconds`;
- `is_new` based on a configurable threshold.

Candidate addresses should be derived from:

- tx sender;
- top profit address;
- top loss address when useful for context;
- `DetectionResult.entities` values such as token contract, entry contract, executor, attacker, caller, profit address;
- optionally tx `to_address`.

The default new-address threshold is 2 days.

### 5. Alert Candidate

The pipeline should return a structured result rather than directly sending messages. Alert dispatch remains a separate concern handled by existing alerting infrastructure.

A pipeline alert candidate should include:

- `tx_hash`;
- `chain_id`;
- top loss/profit addresses and USD amounts;
- passed detection script IDs;
- max score/severity;
- new key addresses and their age details;
- evidence/details from passed detection results.

## Proposed files

Create:

- `backend/ingestion/balance_changes.py`
  - Transfer normalization and net USD balance calculation.

- `backend/providers/trace.py`
  - `TraceProvider` protocol and static/fake trace provider.

- `backend/providers/address_age.py`
  - `AddressAge`, `AddressAgeProvider`, static/fake age provider.

- `backend/pipeline/single_transaction.py`
  - `SingleTransactionRiskPipeline`, pipeline config, pipeline result models.

- `tests/ingestion/test_balance_changes.py`
  - Unit tests for log/transfer net flow calculation.

- `tests/providers/test_static_providers.py`
  - Unit tests for fake/static provider behavior.

- `tests/pipeline/test_single_transaction_pipeline.py`
  - Gate behavior and alert candidate tests.

Modify:

- `backend/detection/context.py`
  - Only if needed to support new metadata cleanly; avoid broad changes.

- `backend/strategies/__init__.py`
  - Export reusable built-in scripts if pipeline needs a default strategy list.

- `README.md`
  - Document staged log-first strategy and provider boundaries after tests pass.

## Test strategy

Follow strict TDD.

Required regression scenarios:

1. **No large outflow skips trace provider**
   - Input has transfers/logs below 1,000,000 USD net outflow.
   - Assert trace provider is not called.
   - Assert no alert candidate.

2. **Large outflow fetches trace**
   - Input has one address net outflow above 1,000,000 USD.
   - Assert trace provider is called with `chain_id` and `tx_hash`.

3. **No sensitive feature skips address age provider**
   - Trace provider returns trace calls.
   - Detection scripts return no passed result.
   - Assert address-age provider is not called.

4. **Sensitive feature with old addresses does not alert**
   - A fake script passes.
   - Address-age provider returns ages older than 2 days.
   - Assert pipeline result records detection but has no alert candidate.

5. **Sensitive feature with new key address alerts**
   - A fake script passes and returns entities containing attacker/profit/caller-like addresses.
   - Address-age provider marks one key address as new within 2 days.
   - Assert alert candidate is produced.

6. **Existing LP-drain strategy can run inside pipeline**
   - Use an offline fixture compatible with `TokenContractActiveLPDrainScript`.
   - Assert the pipeline can pass data into `DetectionRuntime` and preserve detection evidence.

## Provider recovery plan

Because trace and address providers are no longer present in the current tree, implementation should start with internal provider protocols and fake providers. If real provider behavior is needed later:

1. Check git history for removed Moralis/trace provider code.
2. If history is insufficient, use the `web-access` skill only to inspect official provider docs or existing examples.
3. Implement real providers behind the same protocol without changing pipeline tests.

## Temporal extension path

The first phase implements `SingleTransactionRiskPipeline`. A future `TemporalRiskPipeline` should reuse:

- balance-change calculator;
- trace provider protocol;
- address-age provider protocol;
- detection scripts and `DetectionRuntime`.

Temporal-specific logic should add:

- event window grouping by watched address / token / pool / caller cluster;
- cumulative outflow/profit thresholds;
- sequence features such as repeated small drains, staged approvals, repeated callback entries, or new-address fanout;
- delayed trace fetch only when a window crosses a risk threshold.

This keeps the core strategy consistent: cheap log-first filtering, expensive enrichment only after gates pass, and alerting only when behavior plus address freshness support high confidence.

## Approval status

User approved this design direction on 2026-05-16. Next step is to write an implementation plan before coding.
