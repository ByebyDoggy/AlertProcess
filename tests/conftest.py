"""tests/conftest.py — shared test fixtures."""
import pytest

try:
    from nodes import init_registry
except ModuleNotFoundError:
    init_registry = None
else:
    init_registry()


@pytest.fixture
def mock_external_services():
    from tests.mocks import MockExternalServices
    return MockExternalServices.with_default_prices()
