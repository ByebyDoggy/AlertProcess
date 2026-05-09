"""tests/conftest.py — 确保所有测试的节点注册表已初始化"""
import pytest

from nodes import init_registry
init_registry()


@pytest.fixture
def mock_external_services():
    from tests.mocks import MockExternalServices
    return MockExternalServices.with_default_prices()
