"""
测试 4byte.directory API 查询 selector 签名
用法: python temp/test_4byte_api.py [selector]
"""

import sys
import json

try:
    import httpx
except ImportError:
    httpx = None

try:
    import requests
except ImportError:
    requests = None


def query_4byte_api(selector: str) -> dict | None:
    """调用 4byte.directory API 查询 selector 的全部签名"""
    url = f"https://www.4byte.directory/api/v1/signatures/?hex_signature={selector}"
    print(f"\n[请求] GET {url}")

    if httpx:
        try:
            resp = httpx.get(url, timeout=15, follow_redirects=True)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"[httpx] 请求失败: {e}")
            data = None
    elif requests:
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"[requests] 请求失败: {e}")
            data = None
    else:
        print("[错误] 未安装 httpx 或 requests 库")
        return None

    if data is not None:
        print(f"[响应状态] 成功")
        # Pretty print JSON
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print("[响应状态] 无数据")
    return data


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "0xe0232b42"
    result = query_4byte_api(target)

    if result and "results" in result:
        results = result["results"]
        total = len(results)
        print(f"\n{'='*60}")
        print(f"Selector: {target}")
        print(f"命中数量: {total}")
        print(f"{'='*60}")

        if total > 0:
            # 按 id 升序排列（ID最小的优先）
            sorted_results = sorted(results, key=lambda x: int(x.get("id", 0)))
            for i, item in enumerate(sorted_results):
                sig_id = item.get("id", "?")
                text_sig = item.get("text_signature", "?")
                num_res = item.get("num_results", "?")
                created_at = item.get("created_at", "?")
                print(f"  [{i+1}] id={sig_id}  num_results={num_res}")
                print(f"      signature: {text_sig}")
                print(f"      created:   {created_at}")
                print()

            print(f">> 最佳匹配 (ID最小): {sorted_results[0]['text_signature']}")
        else:
            print("  (无签名结果)")
    else:
        print("\nAPI 未返回有效结果")
