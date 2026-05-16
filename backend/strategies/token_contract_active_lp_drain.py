from __future__ import annotations

from collections import defaultdict
from typing import Any

from backend.detection import DetectionContext, DetectionEvidence, DetectionResult, DetectionScript

BSC_USDT = "0x55d398326f99059ff775485246999027b3197955"
BSC_WBNB = "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c"
NATIVE_PLACEHOLDER = "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
PAIR_SWAP_SELECTOR = "0x022c0d9f"
GET_RESERVES_SELECTOR = "0x0902f1ac"
FLASH_LOAN_SELECTORS = {"0xe0232b42"}


def _addr(value: Any) -> str:
    return str(value or "").lower()


def _call_from(call: dict[str, Any]) -> str:
    return _addr(call.get("caller", call.get("from_address", call.get("from"))))


def _call_to(call: dict[str, Any]) -> str:
    return _addr(call.get("callee", call.get("to_address", call.get("to"))))


def _amount(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value, 16) if value.startswith("0x") else int(value)
        except ValueError:
            return 0
    return 0


def _usd_value(token: str, raw_amount: int, prices: dict[str, Any], decimals: dict[str, Any]) -> float:
    token_key = _addr(token)
    price = float(prices.get(token_key, prices.get(token, 0.0)) or 0.0)
    token_decimals = int(decimals.get(token_key, decimals.get(token, 18)) or 18)
    return raw_amount / (10 ** token_decimals) * price


def _net_by_token(address: str, transfers: list[dict[str, Any]]) -> dict[str, int]:
    target = _addr(address)
    net: dict[str, int] = defaultdict(int)
    for transfer in transfers:
        token = _addr(transfer.get("token"))
        amount = _amount(transfer.get("amount_raw", transfer.get("amount", transfer.get("value"))))
        if _addr(transfer.get("to")) == target:
            net[token] += amount
        if _addr(transfer.get("from")) == target:
            net[token] -= amount
    return dict(net)


def _total_positive_usd(net: dict[str, int], prices: dict[str, Any], decimals: dict[str, Any]) -> tuple[float, dict[str, str]]:
    total = 0.0
    raw: dict[str, str] = {}
    for token, amount in net.items():
        if amount <= 0:
            continue
        total += _usd_value(token, amount, prices, decimals)
        raw[token] = str(amount)
    return total, raw


def _total_loss_usd(net: dict[str, int], prices: dict[str, Any], decimals: dict[str, Any]) -> tuple[float, dict[str, str]]:
    total = 0.0
    raw: dict[str, str] = {}
    for token, amount in net.items():
        if amount >= 0:
            continue
        loss = abs(amount)
        total += _usd_value(token, loss, prices, decimals)
        raw[token] = str(loss)
    return total, raw


class TokenContractActiveLPDrainScript(DetectionScript):
    id = "token_contract_active_lp_drain"
    version = "1.0.0"
    name = "Token Contract Active LP Drain"
    description = "Detects token contracts that actively participate in fund/call flow while an LP is drained and the sender profits."
    required_inputs = ["transfers", "trace_calls", "token_prices", "token_decimals"]
    default_threshold = 40.0

    min_lp_loss_usd = 100_000.0
    critical_lp_loss_usd = 1_000_000.0
    min_sender_profit_usd = 10_000.0
    min_token_contract_call_count = 1

    async def detect(self, ctx: DetectionContext) -> DetectionResult:
        transfers = ctx.transfers
        trace_calls = ctx.trace_calls
        lp = _addr(ctx.metadata.get("top_loss_address"))
        top_profit = _addr(ctx.metadata.get("top_profit_address"))
        sender = _addr(ctx.from_address)
        prices = {_addr(k): v for k, v in ctx.token_prices.items()}
        decimals = {_addr(k): v for k, v in ctx.token_decimals.items()}
        stablecoins = {BSC_USDT, *[_addr(token) for token in ctx.metadata.get("stablecoins") or []]}
        wrapped_native = {BSC_WBNB, NATIVE_PLACEHOLDER, *[_addr(token) for token in ctx.metadata.get("wrapped_native_tokens") or []]}

        if not lp:
            return DetectionResult.no_match(self.id, "missing top loss address", "token_contract_active_lp_drain")
        if not self._looks_like_lp(lp, transfers, trace_calls, ctx.address_labels):
            return DetectionResult.no_match(self.id, "top loss is not confirmed lp", "token_contract_active_lp_drain")

        lp_loss_usd, lp_loss_raw_by_token = _total_loss_usd(_net_by_token(lp, transfers), prices, decimals)
        if lp_loss_usd < self.min_lp_loss_usd:
            return DetectionResult.no_match(self.id, "lp loss below threshold", "token_contract_active_lp_drain")

        sender_profit_usd, sender_profit_raw_by_token = _total_positive_usd(_net_by_token(sender, transfers), prices, decimals)
        if sender_profit_usd < self.min_sender_profit_usd:
            return DetectionResult.no_match(self.id, "sender profit below threshold", "token_contract_active_lp_drain")

        candidates = self._candidate_tokens(lp, transfers, stablecoins | wrapped_native)
        best: dict[str, Any] | None = None
        best_score = 0.0

        for token in candidates:
            fund_flow_count = self._token_fund_flow_count(token, lp, transfers, stablecoins | wrapped_native)
            call_count = sum(1 for call in trace_calls if _call_from(call) == token)
            token_is_top_profit = token == top_profit
            active_in_fund_flow = fund_flow_count > 0
            active_as_caller = call_count >= self.min_token_contract_call_count
            if not (token_is_top_profit or (active_in_fund_flow and active_as_caller)):
                continue

            pair_swap_count = self._selector_count(trace_calls, PAIR_SWAP_SELECTOR, lp)
            reserve_read_count = self._selector_count(trace_calls, GET_RESERVES_SELECTOR, lp)
            flash_loan_present = bool(ctx.metadata.get("flash_loan_present")) or any(
                _addr(call.get("selector")) in FLASH_LOAN_SELECTORS for call in trace_calls
            )
            temporary_contract_count = int(ctx.metadata.get("temporary_contract_count") or 0)
            if ctx.metadata.get("temporary_contract_count") is None:
                temporary_contract_count = sum(1 for call in trace_calls if str(call.get("operation") or "").upper() == "CREATE")

            score = 60.0
            if lp_loss_usd >= self.critical_lp_loss_usd:
                score += 20.0
            if token_is_top_profit:
                score += 20.0
            if active_in_fund_flow:
                score += 15.0
            if active_as_caller:
                score += 15.0
            if flash_loan_present:
                score += 10.0
            if temporary_contract_count >= 1:
                score += 10.0
            score = min(score, 100.0)

            if score > best_score:
                best_score = score
                best = {
                    "token_contract": token,
                    "lp_address": lp,
                    "sender_profit_address": sender,
                    "top_profit_address": top_profit,
                    "lp_loss_usd": round(lp_loss_usd, 2),
                    "sender_profit_usd": round(sender_profit_usd, 2),
                    "lp_loss_raw_by_token": lp_loss_raw_by_token,
                    "sender_profit_raw_by_token": sender_profit_raw_by_token,
                    "token_contract_fund_flow_count": fund_flow_count,
                    "token_contract_call_count": call_count,
                    "pair_swap_count": pair_swap_count,
                    "reserve_read_count": reserve_read_count,
                    "flash_loan_present": flash_loan_present,
                    "temporary_contract_count": temporary_contract_count,
                    "active_in_fund_flow": active_in_fund_flow,
                    "active_as_caller": active_as_caller,
                    "token_is_top_profit": token_is_top_profit,
                }

        if not best:
            return DetectionResult.no_match(self.id, "no active token contract lp drain", "token_contract_active_lp_drain")

        labels = ["token_contract_active_lp_drain", "lp_top_loss", "business_logic_anomaly"]
        if best["token_is_top_profit"]:
            labels.append("token_contract_top_profit")
        if best["flash_loan_present"]:
            labels.append("flash_loan_amplified")
        if best["temporary_contract_count"] >= 1:
            labels.append("temporary_contract_execution")

        evidence = [
            DetectionEvidence(
                kind="LP_TOP_LOSS",
                description="LP address has large net USD loss",
                weight=25.0,
                data={"lp_address": best["lp_address"], "lp_loss_usd": best["lp_loss_usd"]},
            ),
            DetectionEvidence(
                kind="SENDER_PROFIT",
                description="Transaction sender has positive realized profit",
                weight=25.0,
                data={"sender": best["sender_profit_address"], "sender_profit_usd": best["sender_profit_usd"]},
            ),
            DetectionEvidence(
                kind="TOKEN_CONTRACT_ACTIVE_FLOW",
                description="Token contract participates in both fund flow and call flow",
                weight=30.0,
                data={
                    "token_contract": best["token_contract"],
                    "fund_flow_count": best["token_contract_fund_flow_count"],
                    "call_count": best["token_contract_call_count"],
                },
            ),
        ]

        return DetectionResult.from_score(
            script_id=self.id,
            score=best_score,
            threshold=self.default_threshold,
            attack_type="token_contract_active_lp_drain",
            labels=labels,
            evidence=evidence,
            entities={
                "token_contract": best["token_contract"],
                "lp_address": best["lp_address"],
                "sender_profit_address": best["sender_profit_address"],
                "top_profit_address": best["top_profit_address"],
            },
            summary="Token contract active LP drain detected",
            details=best,
        )

    def _looks_like_lp(
        self,
        lp: str,
        transfers: list[dict[str, Any]],
        trace_calls: list[dict[str, Any]],
        labels: dict[str, Any],
    ) -> bool:
        label = str(labels.get(lp, labels.get(lp.lower(), ""))).lower()
        if any(marker in label for marker in ["lp", "pair", "cake-lp"]):
            return True
        if any(_call_to(call) == lp and _addr(call.get("selector")) in {GET_RESERVES_SELECTOR, PAIR_SWAP_SELECTOR} for call in trace_calls):
            return True
        lp_tokens = {_addr(transfer.get("token")) for transfer in transfers if _addr(transfer.get("from")) == lp or _addr(transfer.get("to")) == lp}
        return len(lp_tokens) >= 2

    def _candidate_tokens(self, lp: str, transfers: list[dict[str, Any]], excluded_tokens: set[str]) -> set[str]:
        candidates: set[str] = set()
        for transfer in transfers:
            if _addr(transfer.get("from")) != lp and _addr(transfer.get("to")) != lp:
                continue
            token = _addr(transfer.get("token"))
            if token and token not in excluded_tokens:
                candidates.add(token)
        return candidates

    def _token_fund_flow_count(
        self,
        token: str,
        lp: str,
        transfers: list[dict[str, Any]],
        stable_or_wrapped: set[str],
    ) -> int:
        count = 0
        for transfer in transfers:
            from_addr = _addr(transfer.get("from"))
            to_addr = _addr(transfer.get("to"))
            transfer_token = _addr(transfer.get("token"))
            if transfer_token == token and (from_addr, to_addr) in {(lp, token), (token, lp)}:
                count += 1
            elif from_addr == token and transfer_token in stable_or_wrapped and to_addr != lp:
                count += 1
        return count

    def _selector_count(self, trace_calls: list[dict[str, Any]], selector: str, lp: str) -> int:
        return sum(
            1
            for call in trace_calls
            if _addr(call.get("selector")) == selector and (not lp or _call_to(call) == lp)
        )
