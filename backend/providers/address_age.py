from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol


@dataclass(frozen=True)
class AddressAge:
    address: str
    created_at: datetime | None
    age_seconds: int | None
    is_new: bool


class AddressAgeProvider(Protocol):
    async def get_address_age(self, chain_id: int, address: str, reference_time: datetime) -> AddressAge:
        ...


class StaticAddressAgeProvider:
    def __init__(
        self,
        created_at_by_address: dict[str, datetime] | None = None,
        new_address_window: timedelta = timedelta(days=2),
    ) -> None:
        self.created_at_by_address = {
            address.lower(): created_at for address, created_at in (created_at_by_address or {}).items()
        }
        self.new_address_window = new_address_window
        self.calls: list[tuple[int, str]] = []

    async def get_address_age(self, chain_id: int, address: str, reference_time: datetime) -> AddressAge:
        normalized = address.lower()
        self.calls.append((chain_id, normalized))
        created_at = self.created_at_by_address.get(normalized)
        if created_at is None:
            return AddressAge(address=normalized, created_at=None, age_seconds=None, is_new=False)
        age = reference_time - created_at
        return AddressAge(
            address=normalized,
            created_at=created_at,
            age_seconds=int(age.total_seconds()),
            is_new=age <= self.new_address_window,
        )
