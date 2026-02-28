"""
API 测试脚本
测试所有主要的 API 端点
"""
import asyncio
import httpx
import json
from typing import Optional


BASE_URL = "http://localhost:8000"


class APITester:
    """API 测试类"""

    def __init__(self):
        self.token: Optional[str] = None
        self.user_id: Optional[str] = None

    async def test_login(self):
        """测试登录"""
        print("[测试] 登录...")
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BASE_URL}/api/auth/login",
                json={
                    "username": "admin",
                    "password": "admin"
                }
            )

            if response.status_code == 200:
                data = response.json()
                self.token = data.get('token')
                print(f"  ✓ 登录成功, Token: {self.token[:20]}...")
                return True
            else:
                print(f"  ✗ 登录失败: {response.status_code}")
                print(f"  响应: {response.text}")
                return False

    async def test_get_users(self):
        """测试获取用户列表"""
        print("[测试] 获取用户列表...")
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{BASE_URL}/api/users",
                params={"token": self.token}
            )

            if response.status_code == 200:
                data = response.json()
                users = data.get('data', [])
                print(f"  ✓ 获取成功, 用户数: {len(users)}")
                return True
            else:
                print(f"  ✗ 获取失败: {response.status_code}")
                return False

    async def test_create_user(self):
        """测试创建用户"""
        print("[测试] 创建用户...")
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BASE_URL}/api/users",
                params={"token": self.token},
                json={
                    "username": "test_user",
                    "password": "test123",
                    "nickname": "测试用户",
                    "enabled": True
                }
            )

            if response.status_code == 200:
                data = response.json()
                self.user_id = data.get('data', {}).get('id')
                print(f"  ✓ 创建成功, 用户ID: {self.user_id}")
                return True
            else:
                print(f"  ✗ 创建失败: {response.status_code}")
                print(f"  响应: {response.text}")
                return False

    async def test_get_stats(self):
        """测试获取统计"""
        print("[测试] 获取统计...")
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{BASE_URL}/api/clockin/stats",
                params={"token": self.token}
            )

            if response.status_code == 200:
                data = response.json()
                stats = data.get('data', {})
                print(f"  ✓ 获取成功")
                print(f"    - 总用户: {stats.get('total_users')}")
                print(f"    - 已启用: {stats.get('enabled_users')}")
                return True
            else:
                print(f"  ✗ 获取失败: {response.status_code}")
                return False

    async def test_get_config(self):
        """测试获取配置"""
        print("[测试] 获取配置...")
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{BASE_URL}/api/config",
                params={"token": self.token}
            )

            if response.status_code == 200:
                data = response.json()
                config = data.get('data', {})
                print(f"  ✓ 获取成功")
                print(f"    - API URL: {config.get('clockin_api_url')}")
                print(f"    - 批处理大小: {config.get('batch_size')}")
                return True
            else:
                print(f"  ✗ 获取失败: {response.status_code}")
                return False

    async def test_health(self):
        """测试健康检查"""
        print("[测试] 健康检查...")
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/health")

            if response.status_code == 200:
                data = response.json()
                print(f"  ✓ 服务正常")
                print(f"    - 状态: {data.get('status')}")
                print(f"    - 版本: {data.get('version')}")
                return True
            else:
                print(f"  ✗ 服务异常: {response.status_code}")
                return False

    async def run_all_tests(self):
        """运行所有测试"""
        print("====================================")
        print("ZK Admin - API 测试")
        print("====================================")
        print(f"基础 URL: {BASE_URL}")
        print()

        tests = [
            ("健康检查", self.test_health),
            ("登录", self.test_login),
            ("获取用户列表", self.test_get_users),
            ("创建用户", self.test_create_user),
            ("获取统计", self.test_get_stats),
            ("获取配置", self.test_get_config),
        ]

        passed = 0
        failed = 0

        for name, test_func in tests:
            try:
                result = await test_func()
                if result:
                    passed += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"  ✗ 测试异常: {e}")
                failed += 1
            print()

        print("====================================")
        print(f"测试完成: {passed} 通过, {failed} 失败")
        print("====================================")


async def main():
    """主函数"""
    tester = APITester()
    await tester.run_all_tests()


if __name__ == '__main__':
    asyncio.run(main())
