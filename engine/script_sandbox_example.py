"""
ScriptSandbox 使用示例

演示如何使用 ScriptSandbox 安全地执行用户自定义脚本。
"""

import asyncio
from engine.script_sandbox import ScriptSandbox, execute_script, validate_script


async def example_basic():
    """基础使用示例"""
    print("=" * 60)
    print("示例 1: 基础脚本执行")
    print("=" * 60)

    sandbox = ScriptSandbox()
    script = """
# 计算前 N 个数的平方和
n = 10
total = sum([x**2 for x in range(n)])
result = total
"""
    result = await sandbox.execute_async(script, {})
    print(f"成功: {result['success']}")
    print(f"结果: {result['result']}")
    print(f"执行时间: {result['execution_time_ms']:.2f}ms")
    print()


async def example_with_context():
    """上下文注入示例"""
    print("=" * 60)
    print("示例 2: 上下文注入")
    print("=" * 60)

    sandbox = ScriptSandbox()
    script = """
# 处理告警数据
alert_value = int(alert_data['value']) / 10**18  # wei to ETH
alert_from = alert_data['from_address']
alert_to = alert_data['to_address']

result = {
    'from': alert_from,
    'to': alert_to,
    'value_eth': alert_value,
    'is_large': alert_value > 1.0
}
"""
    context = {
        'alert_data': {
            'from_address': '0x1234',
            'to_address': '0x5678',
            'value': '2000000000000000000',  # 2 ETH
        }
    }
    result = await sandbox.execute_async(script, context)
    print(f"成功: {result['success']}")
    print(f"结果: {result['result']}")
    print()


async def example_with_modules():
    """使用预导入模块示例"""
    print("=" * 60)
    print("示例 3: 使用预导入模块")
    print("=" * 60)

    sandbox = ScriptSandbox()
    script = """
# 使用 re 模块提取地址
tx_data = "Transfer from 0xabcd1234 to 0xef567890"
pattern = r'0x[a-fA-F0-9]{8}'
addresses = re.findall(pattern, tx_data)

# 使用 json 模块
data = {'addresses': addresses, 'count': len(addresses)}
json_str = json.dumps(data)

# 使用 math 模块
sqrt_count = math.sqrt(len(addresses))

result = {
    'addresses': addresses,
    'json': json_str,
    'sqrt_count': sqrt_count
}
"""
    result = await sandbox.execute_async(script, {})
    print(f"成功: {result['success']}")
    print(f"结果: {result['result']}")
    print()


async def example_datetime():
    """日期时间处理示例"""
    print("=" * 60)
    print("示例 4: 日期时间处理")
    print("=" * 60)

    sandbox = ScriptSandbox()
    script = """
# datetime 和 timedelta 已预导入
tx_time = datetime(2024, 1, 1, 12, 0, 0)
window_start = datetime(2024, 1, 1, 10, 0, 0)
window_end = datetime(2024, 1, 1, 14, 0, 0)

in_window = window_start <= tx_time <= window_end
hours_diff = (tx_time - window_start).total_seconds() / 3600

result = {
    'in_window': in_window,
    'hours_from_start': hours_diff
}
"""
    result = await sandbox.execute_async(script, {})
    print(f"成功: {result['success']}")
    print(f"结果: {result['result']}")
    print()


async def example_collections():
    """集合操作示例"""
    print("=" * 60)
    print("示例 5: 集合操作")
    print("=" * 60)

    sandbox = ScriptSandbox()
    script = """
# Counter 已预导入
transactions = ['0x1', '0x2', '0x1', '0x3', '0x2', '0x1']
counter = Counter(transactions)

# 使用 defaultdict
grouped = defaultdict(list)
for i, addr in enumerate(transactions):
    grouped[addr].append(i)

result = {
    'most_common': counter.most_common(2),
    'grouped': dict(grouped)
}
"""
    result = await sandbox.execute_async(script, {})
    print(f"成功: {result['success']}")
    print(f"结果: {result['result']}")
    print()


async def example_validation():
    """脚本验证示例"""
    print("=" * 60)
    print("示例 6: 脚本验证")
    print("=" * 60)

    # 验证有效脚本
    valid_script = "result = 1 + 1"
    validation = validate_script(valid_script)
    print(f"有效脚本验证: {validation}")

    # 验证语法错误
    invalid_script = "result = 1 +"
    validation = validate_script(invalid_script)
    print(f"语法错误验证: {validation}")

    # 验证危险操作
    dangerous_script = "import os\nresult = os.getcwd()"
    validation = validate_script(dangerous_script)
    print(f"危险操作验证: {validation}")
    print()


async def example_error_handling():
    """错误处理示例"""
    print("=" * 60)
    print("示例 7: 错误处理")
    print("=" * 60)

    sandbox = ScriptSandbox()

    # 运行时错误
    script = "result = 1 / 0"
    result = await sandbox.execute_async(script, {})
    print(f"除零错误: {result['error']}")

    # KeyError
    script = "data = {'a': 1}\nresult = data['b']"
    result = await sandbox.execute_async(script, {})
    print(f"KeyError: {result['error']}")
    print()


async def example_convenience_function():
    """便捷函数示例"""
    print("=" * 60)
    print("示例 8: 便捷函数")
    print("=" * 60)

    # 使用便捷函数
    result = await execute_script(
        script_code="result = x * 2",
        context={'x': 21},
        timeout=10
    )
    print(f"便捷函数结果: {result}")
    print()


async def example_custom_timeout():
    """自定义超时示例"""
    print("=" * 60)
    print("示例 9: 自定义超时")
    print("=" * 60)

    # 短超时
    sandbox = ScriptSandbox(timeout=0.1)
    script = """
# 模拟长时间计算
total = 0
for i in range(1000000):
    total += i
result = total
"""
    result = await sandbox.execute_async(script, {})
    print(f"成功: {result['success']}")
    if not result['success']:
        print(f"错误: {result['error']}")
    else:
        print(f"结果: {result['result']}")
    print()


async def example_helper_methods():
    """辅助方法示例"""
    print("=" * 60)
    print("示例 10: 辅助方法")
    print("=" * 60)

    # 获取允许的模块
    modules = ScriptSandbox.get_allowed_modules()
    print(f"允许的模块: {modules}")

    # 获取允许的内置函数
    builtins = ScriptSandbox.get_allowed_builtins()
    print(f"允许的内置函数数量: {len(builtins)}")
    print(f"部分内置函数: {builtins[:10]}")
    print()


async def main():
    """运行所有示例"""
    print("\n" + "=" * 60)
    print("ScriptSandbox 使用示例")
    print("=" * 60 + "\n")

    await example_basic()
    await example_with_context()
    await example_with_modules()
    await example_datetime()
    await example_collections()
    await example_validation()
    await example_error_handling()
    await example_convenience_function()
    await example_custom_timeout()
    await example_helper_methods()

    print("=" * 60)
    print("所有示例执行完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
