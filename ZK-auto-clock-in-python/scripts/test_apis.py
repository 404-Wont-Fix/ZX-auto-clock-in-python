"""
测试第三方API是否正常工作
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.poetry_service import PoetryService


async def test_poetry_apis():
    """测试文字/诗词API"""
    print("=" * 60)
    print("测试文字/诗词API")
    print("=" * 60)

    poetry_apis = ['poetry_all', 'hitokoto', 'cenguigui', 'yuanmeng', 'klapi']

    for api_type in poetry_apis:
        print(f"\n测试 {api_type}...")
        result = await PoetryService._fetch_poetry(api_type)
        if result:
            # 尝试打印中文，如果失败就显示编码后的形式
            try:
                print(f"  [OK] 成功: {result[:50]}")
            except:
                print(f"  [OK] 成功（已编码）: {result.encode('utf-8')[:50]}")
        else:
            print(f"  [FAIL] 失败")


async def test_image_apis():
    """测试图片API"""
    print("\n" + "=" * 60)
    print("测试图片API")
    print("=" * 60)

    # 测试 Bing
    print("\n测试 bing...")
    result = await PoetryService._fetch_bing_image()
    if result:
        print(f"  [OK] 成功: {result}")
    else:
        print(f"  [FAIL] 失败")

    # 测试 LoliAPI
    print("\n测试 loliapi...")
    result = await PoetryService._fetch_redirect_image('https://www.loliapi.com/acg/')
    if result:
        print(f"  [OK] 成功: {result}")
    else:
        print(f"  [FAIL] 失败")

    # 测试次元API
    print("\n测试 cimuapi (随机分类)...")
    result = await PoetryService._fetch_cimu_image('random')
    if result:
        print(f"  [OK] 成功: {result}")
    else:
        print(f"  [FAIL] 失败")

    # 测试 Komll
    print("\n测试 komll...")
    result = await PoetryService._fetch_redirect_image('https://api.komll.com/images')
    if result:
        print(f"  [OK] 成功: {result}")
    else:
        print(f"  [FAIL] 失败")


async def main():
    print("开始测试第三方API...")

    await test_poetry_apis()
    await test_image_apis()

    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)


if __name__ == '__main__':
    asyncio.run(main())
