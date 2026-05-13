"""
权限检查脚本

检查交易中的权限相关操作，识别潜在的权限提升攻击。
"""

# 获取调用栈
calls = ctx.get_trace_calls()

# 危险函数列表
dangerous_functions = [
    "0x8da5cb5b",  # owner()
    "0xf2fde38b",  # transferOwnership(address)
    "0x715018a6",  # renounceOwnership()
    "0xa217fddf",  # DEFAULT_ADMIN_ROLE()
    "0x2f2ff15d",  # grantRole(bytes32,address)
    "0xd547741f",  # revokeRole(bytes32,address)
]

# 检查是否有权限相关调用
permission_calls = []
for call in calls:
    selector = call.get("function_selector", "")
    if selector in dangerous_functions:
        permission_calls.append(call)

        # 解码函数签名
        signature = ctx.decode_function_selector(selector)
        call["signature"] = signature

if permission_calls:
    result = True
    score = 85
    labels = ["permission_change"]

    # 检查是否有所有权转移
    ownership_transfer = any(
        "transferOwnership" in call.get("signature", "")
        for call in permission_calls
    )

    if ownership_transfer:
        score = 95
        labels.append("ownership_transfer")

    ctx["permission_calls"] = permission_calls
else:
    result = False
    score = 0
