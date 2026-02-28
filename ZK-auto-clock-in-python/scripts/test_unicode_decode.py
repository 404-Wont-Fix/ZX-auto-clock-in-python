"""
测试Unicode解码功能
"""
import json


def test_decode():
    # 模拟API返回的Unicode转义序列
    test_cases = [
        r"\u505a\u4efb\u4f55\u4e00\u4ef6\u4e8b\u90fd\u8981\u5c3d\u60c5\u4eab\u53d7\u5b83",
        r"\u8d2a\u56fe\u5c0f\u5229\uff0c\u96be\u6210\u5927\u4e8b",
    ]

    print("测试Unicode解码：\n")

    for text in test_cases:
        # 方法1: 使用 json.loads
        decoded = json.loads(f'"{text}"')
        print(f"原始: {text}")
        print(f"解码: {decoded}")
        print()


if __name__ == '__main__':
    test_decode()
