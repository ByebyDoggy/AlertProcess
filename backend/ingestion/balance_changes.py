from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


def _addr(value: Any) -> str:
    return str(value or "").lower()


def _amount(value: Any) -> int:
    if value in (None, ""):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value)
    return int(text, 16) if text.lower().startswith("0x") else int(text)


def _token_usd_value(token: str, raw_amount: int, token_prices: dict[str, Any], token_decimals: dict[str, Any]) -> float:
    token_key = _addr(token)
    price_value = token_prices.get(token_key, token_prices.get(token, 0.0))
    decimal_value = token_decimals.get(token_key, token_decimals.get(token, 18))
    price = float(price_value if price_value is not None else 0.0)
    decimals = int(decimal_value if decimal_value is not None else 18)
    return raw_amount / (10 ** decimals) * price


@dataclass(frozen=True)
class AddressBalanceChange:
    address: str
    net_by_token: dict[str, int] = field(default_factory=dict)
    net_usd: float = 0.0

    @property
    def loss_usd(self) -> float:
        return abs(self.net_usd) if self.net_usd < 0 else 0.0

    @property
    def profit_usd(self) -> float:
        return self.net_usd if self.net_usd > 0 else 0.0

    def to_context_dict(self) -> dict[str, Any]:
        return {
            "address": self.address,
            "net_usd": self.net_usd,
            "loss_usd": self.loss_usd,
            "profit_usd": self.profit_usd,
            "net_by_token": {token: str(amount) for token, amount in self.net_by_token.items()},
        }


@dataclass(frozen=True)
class BalanceChangeSummary:
    changes_by_address: dict[str, AddressBalanceChange]
    top_loss_address: str = ""
    top_loss_usd: float = 0.0
    top_profit_address: str = ""
    top_profit_usd: float = 0.0

    def to_context_balance_changes(self) -> list[dict[str, Any]]:
        return [change.to_context_dict() for _, change in sorted(self.changes_by_address.items())]


class BalanceChangeCalculator:
    def calculate(
        self,
        transfers: list[dict[str, Any]],
        token_prices: dict[str, Any],
        token_decimals: dict[str, Any],
    ) -> BalanceChangeSummary:
        prices = {_addr(token): price for token, price in token_prices.items()}
        decimals = {_addr(token): value for token, value in token_decimals.items()}
        raw_by_address: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

        for transfer in transfers:
            token = _addr(transfer.get("token"))
            from_address = _addr(transfer.get("from", transfer.get("from_address")))
            to_address = _addr(transfer.get("to", transfer.get("to_address")))
            amount = _amount(transfer.get("amount_raw", transfer.get("amount", transfer.get("value"))))
            if not token or amount == 0:
                continue
            if from_address:
                raw_by_address[from_address][token] -= amount
            if to_address:
                raw_by_address[to_address][token] += amount

        changes: dict[str, AddressBalanceChange] = {}
        for address, net_by_token in raw_by_address.items():
            net_usd = 0.0
            for token, amount in net_by_token.items():
                usd = _token_usd_value(token, abs(amount), prices, decimals)
                net_usd += usd if amount > 0 else -usd
            changes[address] = AddressBalanceChange(address=address, net_by_token=dict(net_by_token), net_usd=net_usd)

        top_loss = min(changes.values(), key=lambda change: change.net_usd, default=None)
        top_profit = max(changes.values(), key=lambda change: change.net_usd, default=None)
        return BalanceChangeSummary(
            changes_by_address=changes,
            top_loss_address=top_loss.address if top_loss and top_loss.net_usd < 0 else "",
            top_loss_usd=top_loss.loss_usd if top_loss else 0.0,
            top_profit_address=top_profit.address if top_profit and top_profit.net_usd > 0 else "",
            top_profit_usd=top_profit.profit_usd if top_profit else 0.0,
        )
