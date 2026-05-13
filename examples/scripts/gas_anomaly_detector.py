"""
Gas 异常检测脚本

检测交易中的 Gas 异常，识别潜在的 DoS 攻击或资源滥用。
"""

# 获取调用栈
calls = ctx.get_trace_calls()

if not calls:
    result = False
    score = 0
else:
    # 计算总 Gas 消耗
    total_gas = 0
    high_gas_calls = []

    for call in calls:
        gas_str = call.get("gas", "0x0")

        # 转换 Gas 值
        try:
            if isinstance(gas_str, str) and gas_str.startswith("0x"):
                gas = int(gas_str, 16)
            else:
                gas = int(gas_str)
        except (ValueError, TypeError):
            gas = 0

        total_gas += gas

        # 记录高 Gas 调用（> 1M Gas）
        if gas > 1000000:
            high_gas_calls.append({
                "to": call.get("to_addr"),
                "selector": call.get("function_selector"),
                "gas": gas,
            })

    # 判断是否有异常
    if total_gas > 10000000 or len(high_gas_calls) > 5:
        result = True
        score = 75
        labels = ["gas_anomaly"]

        if total_gas > 20000000:
            score = 90
            labels.append("extremely_high_gas")

        ctx["total_gas"] = total_gas
        ctx["high_gas_calls"] = high_gas_calls
    else:
        result = False
        score = 10
