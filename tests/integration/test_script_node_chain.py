"""
ScriptNode 集成测试
"""

import pytest

from engine.executor import ChainExecutor
from engine.parser import ChainParser
from nodes.models import TransactionContext


@pytest.mark.asyncio
class TestScriptNodeInChain:
    """测试 ScriptNode 在规则链中的执行"""

    async def test_script_node_basic_execution(self):
        """测试基础脚本执行"""
        chain_config = {
            "nodes": [
                {
                    "id": "trigger",
                    "type": "alert_trigger",
                    "config": {},
                },
                {
                    "id": "script",
                    "type": "script_node",
                    "config": {
                        "language": "python",
                        "script": """
result = True
score = 80
labels = ["test"]
""",
                        "timeout": 5.0,
                    },
                },
            ],
            "edges": [
                {"from": "trigger", "to": "script"},
            ],
        }

        tx_context = TransactionContext(
            chain_id="1",
            tx_hash="0xabc",
            block_number=100,
            timestamp="1000000",
            from_address="0xsender",
            to_address="0xcontract",
            value="0",
            logs=[],
        )

        parser = ChainParser()
        chain = parser.parse(chain_config)

        executor = ChainExecutor()
        exec_ctx = await executor.execute(chain, tx_context.to_dict())

        assert "script" in exec_ctx.node_outputs
        script_result = exec_ctx.node_outputs["script"]
        assert script_result.passed is True
        assert script_result.score == 80
        assert "test" in script_result.labels

    async def test_script_node_with_context_api(self):
        """测试使用 ScriptContext API"""
        chain_config = {
            "nodes": [
                {
                    "id": "trigger",
                    "type": "alert_trigger",
                    "config": {},
                },
                {
                    "id": "script",
                    "type": "script_node",
                    "config": {
                        "language": "python",
                        "script": """
transfers = ctx.get_transfers()
result = len(transfers) > 0
score = len(transfers) * 10
""",
                        "timeout": 5.0,
                    },
                },
            ],
            "edges": [
                {"from": "trigger", "to": "script"},
            ],
        }

        tx_context = TransactionContext(
            chain_id="1",
            tx_hash="0xabc",
            block_number=100,
            timestamp="1000000",
            from_address="0xsender",
            to_address="0xcontract",
            value="0",
            logs=[],
            extra={
                "parsed_transfers": [
                    {
                        "token_address": "0xtoken1",
                        "from_address": "0xalice",
                        "to_address": "0xbob",
                        "amount": 100.0,
                    },
                    {
                        "token_address": "0xtoken2",
                        "from_address": "0xbob",
                        "to_address": "0xcharlie",
                        "amount": 200.0,
                    },
                ]
            },
        )

        parser = ChainParser()
        chain = parser.parse(chain_config)

        executor = ChainExecutor(chain)
        results = await executor.execute(tx_context)

        assert "script" in results
        script_result = results["script"]
        assert script_result.passed is True
        assert script_result.score == 20

    async def test_multiple_script_nodes_in_chain(self):
        """测试多个 ScriptNode 串联"""
        chain_config = {
            "nodes": [
                {
                    "id": "trigger",
                    "type": "alert_trigger",
                    "config": {},
                },
                {
                    "id": "script1",
                    "type": "script_node",
                    "config": {
                        "language": "python",
                        "script": """
result = True
score = 50
ctx['stage1_done'] = True
""",
                        "timeout": 5.0,
                    },
                },
                {
                    "id": "script2",
                    "type": "script_node",
                    "config": {
                        "language": "python",
                        "script": """
stage1 = ctx.get('stage1_done', False)
result = stage1
score = 100 if stage1 else 0
""",
                        "timeout": 5.0,
                    },
                },
            ],
            "edges": [
                {"from": "trigger", "to": "script1"},
                {"from": "script1", "to": "script2"},
            ],
        }

        tx_context = TransactionContext(
            chain_id="1",
            tx_hash="0xabc",
            block_number=100,
            timestamp="1000000",
            from_address="0xsender",
            to_address="0xcontract",
            value="0",
            logs=[],
        )

        parser = ChainParser()
        chain = parser.parse(chain_config)

        executor = ChainExecutor(chain)
        results = await executor.execute(tx_context)

        assert "script1" in results
        assert "script2" in results
        assert results["script1"].passed is True
        assert results["script2"].passed is True
        assert results["script2"].score == 100

    async def test_script_node_error_handling(self):
        """测试脚本错误处理"""
        chain_config = {
            "nodes": [
                {
                    "id": "trigger",
                    "type": "alert_trigger",
                    "config": {},
                },
                {
                    "id": "script",
                    "type": "script_node",
                    "config": {
                        "language": "python",
                        "script": """
raise ValueError("Test error")
""",
                        "timeout": 5.0,
                    },
                },
            ],
            "edges": [
                {"from": "trigger", "to": "script"},
            ],
        }

        tx_context = TransactionContext(
            chain_id="1",
            tx_hash="0xabc",
            block_number=100,
            timestamp="1000000",
            from_address="0xsender",
            to_address="0xcontract",
            value="0",
            logs=[],
        )

        parser = ChainParser()
        chain = parser.parse(chain_config)

        executor = ChainExecutor(chain)
        results = await executor.execute(tx_context)

        assert "script" in results
        script_result = results["script"]
        assert script_result.passed is False
        assert "error" in script_result.metadata


@pytest.mark.asyncio
class TestScriptNodePerformance:
    """测试 ScriptNode 性能"""

    async def test_script_execution_time(self):
        """测试脚本执行时间"""
        import time

        chain_config = {
            "nodes": [
                {
                    "id": "trigger",
                    "type": "alert_trigger",
                    "config": {},
                },
                {
                    "id": "script",
                    "type": "script_node",
                    "config": {
                        "language": "python",
                        "script": """
result = True
score = 80
""",
                        "timeout": 5.0,
                    },
                },
            ],
            "edges": [
                {"from": "trigger", "to": "script"},
            ],
        }

        tx_context = TransactionContext(
            chain_id="1",
            tx_hash="0xabc",
            block_number=100,
            timestamp="1000000",
            from_address="0xsender",
            to_address="0xcontract",
            value="0",
            logs=[],
        )

        parser = ChainParser()
        chain = parser.parse(chain_config)

        executor = ChainExecutor(chain)

        start_time = time.time()
        await executor.execute(tx_context)
        execution_time = time.time() - start_time

        assert execution_time < 1.0

    async def test_script_with_heavy_computation(self):
        """测试重计算脚本"""
        chain_config = {
            "nodes": [
                {
                    "id": "trigger",
                    "type": "alert_trigger",
                    "config": {},
                },
                {
                    "id": "script",
                    "type": "script_node",
                    "config": {
                        "language": "python",
                        "script": """
transfers = ctx.get_transfers()
balance_changes = ctx.get_balance_changes()
result = len(transfers) > 0
score = len(balance_changes) * 10
""",
                        "timeout": 5.0,
                    },
                },
            ],
            "edges": [
                {"from": "trigger", "to": "script"},
            ],
        }

        tx_context = TransactionContext(
            chain_id="1",
            tx_hash="0xabc",
            block_number=100,
            timestamp="1000000",
            from_address="0xsender",
            to_address="0xcontract",
            value="0",
            logs=[],
            extra={
                "parsed_transfers": [
                    {
                        "token_address": f"0xtoken{i}",
                        "from_address": f"0xalice{i}",
                        "to_address": f"0xbob{i}",
                        "amount": 100.0,
                    }
                    for i in range(100)
                ]
            },
        )

        parser = ChainParser()
        chain = parser.parse(chain_config)

        executor = ChainExecutor(chain)

        import time
        start_time = time.time()
        results = await executor.execute(tx_context)
        execution_time = time.time() - start_time

        assert execution_time < 5.0
        assert "script" in results
        assert results["script"].passed is True


@pytest.mark.asyncio
class TestScriptNodeSecurity:
    """测试 ScriptNode 安全性"""

    async def test_script_sandbox_blocks_file_access(self):
        """测试沙箱阻止文件访问"""
        chain_config = {
            "nodes": [
                {
                    "id": "trigger",
                    "type": "alert_trigger",
                    "config": {},
                },
                {
                    "id": "script",
                    "type": "script_node",
                    "config": {
                        "language": "python",
                        "script": """
open('/etc/passwd', 'r')
result = True
""",
                        "timeout": 5.0,
                    },
                },
            ],
            "edges": [
                {"from": "trigger", "to": "script"},
            ],
        }

        tx_context = TransactionContext(
            chain_id="1",
            tx_hash="0xabc",
            block_number=100,
            timestamp="1000000",
            from_address="0xsender",
            to_address="0xcontract",
            value="0",
            logs=[],
        )

        parser = ChainParser()
        chain = parser.parse(chain_config)

        executor = ChainExecutor(chain)
        results = await executor.execute(tx_context)

        assert "script" in results
        script_result = results["script"]
        assert script_result.passed is False

    async def test_script_sandbox_blocks_import(self):
        """测试沙箱阻止危险导入"""
        chain_config = {
            "nodes": [
                {
                    "id": "trigger",
                    "type": "alert_trigger",
                    "config": {},
                },
                {
                    "id": "script",
                    "type": "script_node",
                    "config": {
                        "language": "python",
                        "script": """
import os
os.system('ls')
result = True
""",
                        "timeout": 5.0,
                    },
                },
            ],
            "edges": [
                {"from": "trigger", "to": "script"},
            ],
        }

        tx_context = TransactionContext(
            chain_id="1",
            tx_hash="0xabc",
            block_number=100,
            timestamp="1000000",
            from_address="0xsender",
            to_address="0xcontract",
            value="0",
            logs=[],
        )

        parser = ChainParser()
        chain = parser.parse(chain_config)

        executor = ChainExecutor(chain)
        results = await executor.execute(tx_context)

        assert "script" in results
        script_result = results["script"]
        assert script_result.passed is False

    async def test_script_timeout(self):
        """测试脚本超时"""
        chain_config = {
            "nodes": [
                {
                    "id": "trigger",
                    "type": "alert_trigger",
                    "config": {},
                },
                {
                    "id": "script",
                    "type": "script_node",
                    "config": {
                        "language": "python",
                        "script": """
import time
time.sleep(10)
result = True
""",
                        "timeout": 1.0,
                    },
                },
            ],
            "edges": [
                {"from": "trigger", "to": "script"},
            ],
        }

        tx_context = TransactionContext(
            chain_id="1",
            tx_hash="0xabc",
            block_number=100,
            timestamp="1000000",
            from_address="0xsender",
            to_address="0xcontract",
            value="0",
            logs=[],
        )

        parser = ChainParser()
        chain = parser.parse(chain_config)

        executor = ChainExecutor(chain)
        results = await executor.execute(tx_context)

        assert "script" in results
        script_result = results["script"]
        assert script_result.passed is False
