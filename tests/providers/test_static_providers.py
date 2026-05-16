from datetime import UTC, datetime, timedelta

import pytest

from backend.providers.address_age import StaticAddressAgeProvider
from backend.providers.trace import StaticTraceProvider


@pytest.mark.asyncio
async def test_static_trace_provider_returns_calls_by_chain_and_hash():
    provider = StaticTraceProvider({(56, "0xabc"): [{"caller": "0x1", "callee": "0x2"}]})

    assert await provider.get_trace_calls(56, "0xABC") == [{"caller": "0x1", "callee": "0x2"}]
    assert await provider.get_trace_calls(1, "0xabc") == []


@pytest.mark.asyncio
async def test_static_address_age_provider_marks_new_addresses():
    reference_time = datetime(2026, 5, 16, tzinfo=UTC)
    provider = StaticAddressAgeProvider(
        created_at_by_address={"0xnew": reference_time - timedelta(hours=12)},
        new_address_window=timedelta(days=2),
    )

    age = await provider.get_address_age(56, "0xNEW", reference_time)

    assert age.address == "0xnew"
    assert age.age_seconds == 43_200
    assert age.is_new is True


@pytest.mark.asyncio
async def test_static_address_age_provider_treats_unknown_addresses_as_old():
    reference_time = datetime(2026, 5, 16, tzinfo=UTC)
    provider = StaticAddressAgeProvider(created_at_by_address={})

    age = await provider.get_address_age(56, "0xmissing", reference_time)

    assert age.address == "0xmissing"
    assert age.created_at is None
    assert age.is_new is False
