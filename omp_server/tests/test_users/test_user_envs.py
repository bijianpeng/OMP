# -*- coding: utf-8 -*-
"""
用户环境授权（envs）相关测试（多环境架构 Task 6）

覆盖点：
1. 创建用户带 envs（可选）→ 全量写入 UserEnv；缺省不强制；
   对 role=superuser 的目标用户不写 UserEnv 行（收到 envs 也忽略）。
2. 编辑用户带 envs → 全量覆盖（删差集、增差集）；
   PATCH 缺 envs 键 → no-op（不强制、不清空）——前端编辑超管只发 {email} 的契约。
3. role 从 superuser 改为其它（如 readonlyuser）且 UserEnv 为空
   → 自动补 UserEnv(env_id=1)（spec 决策 #21 降级兜底）。
4. 用户列表 serializer 输出 envs: [int] 与 env_names: [str]（前端 Task 17 依赖）。
5. partial PATCH 不带 password/re_password 不再 KeyError 500，
   且不会用 make_password(None) 覆盖原密码。
"""
from rest_framework.reverse import reverse

from tests.base import AutoLoginTest
from db_models.models import Env, UserEnv, UserProfile


class UserEnvsTest(AutoLoginTest):
    """ 用户创建/编辑 envs 授权与降级兜底测试类 """

    def setUp(self):
        """ 初始化用户接口地址与测试环境 """
        super(UserEnvsTest, self).setUp()
        self.users_url = reverse("users-list")
        # default 环境（id=1）由 BaseTest 创建，这里再补两个环境做差集断言
        # （code 唯一，不能留空重复）
        self.env_prod = Env.objects.create(name="生产环境", code="prod")
        self.env_test = Env.objects.create(name="测试环境", code="test")

    # ---------- 辅助方法 ----------

    def _create_user(self, username, envs=None, role="readonlyuser"):
        """ 创建用户，envs 为 None 表示请求体不带 envs 键 """
        payload = {
            "username": username,
            "password": "passw0rd@OMP",
            "re_password": "passw0rd@OMP",
            "email": "{}@testmail.com".format(username),
            "role": role,
        }
        if envs is not None:
            payload["envs"] = envs
        return self.post(self.users_url, payload).json()

    def _granted_env_ids(self, user):
        """ 查询用户当前被授权的环境 id 集合 """
        return set(
            UserEnv.objects.filter(user=user)
            .values_list("env_id", flat=True))

    # ---------- 创建 ----------

    def test_create_user_with_envs(self):
        """ 测试创建用户带 envs 授权（含缺省与超管忽略） """
        # 创建普通用户并授权 [default, 生产环境] -> UserEnv 全量写入
        resp = self._create_user(
            "env_user", envs=[1, self.env_prod.id])
        self.assertEqual(resp.get("code"), 0)
        user = UserProfile.objects.get(username="env_user")
        self.assertEqual(
            self._granted_env_ids(user), {1, self.env_prod.id})
        # 创建响应 data 同步输出 envs / env_names
        self.assertEqual(resp.get("data", {}).get("envs"), [1, self.env_prod.id])
        self.assertEqual(
            resp.get("data", {}).get("env_names"),
            ["default", "生产环境"])

        # 创建用户不带 envs 键 -> 不强制授权（无默认环境）
        resp = self._create_user("env_free_user")
        self.assertEqual(resp.get("code"), 0)
        user = UserProfile.objects.get(username="env_free_user")
        self.assertEqual(self._granted_env_ids(user), set())

        # 创建超管时带了 envs -> 忽略，不写 UserEnv 行
        resp = self._create_user(
            "env_super_user", envs=[1, self.env_prod.id], role="superuser")
        self.assertEqual(resp.get("code"), 0)
        user = UserProfile.objects.get(username="env_super_user")
        self.assertEqual(self._granted_env_ids(user), set())

    # ---------- 编辑 ----------

    def test_update_user_envs_full_replace(self):
        """ 测试编辑用户 envs 全量覆盖（删差集、增差集、缺省 no-op） """
        self._create_user(
            "env_upd_user", envs=[1, self.env_prod.id])
        user = UserProfile.objects.get(username="env_upd_user")
        detail_url = reverse("users-detail", [user.id])

        # PATCH envs=[生产环境] -> 删除差集 default
        resp = self.patch(detail_url, {
            "email": "env_upd_user@testmail.com",
            "envs": [self.env_prod.id],
        }).json()
        self.assertEqual(resp.get("code"), 0)
        self.assertEqual(self._granted_env_ids(user), {self.env_prod.id})

        # PATCH envs=[生产环境, 测试环境] -> 新增差集 测试环境
        resp = self.patch(detail_url, {
            "email": "env_upd_user@testmail.com",
            "envs": [self.env_prod.id, self.env_test.id],
        }).json()
        self.assertEqual(resp.get("code"), 0)
        self.assertEqual(
            self._granted_env_ids(user), {self.env_prod.id, self.env_test.id})

        # PATCH 不带 envs 键 -> no-op，不清空已有授权
        resp = self.patch(detail_url, {
            "email": "env_upd_user2@testmail.com",
        }).json()
        self.assertEqual(resp.get("code"), 0)
        self.assertEqual(
            self._granted_env_ids(user), {self.env_prod.id, self.env_test.id})

    def test_patch_superuser_without_envs_noop(self):
        """ 测试编辑超管只发 {email}（无 envs 键）：不报错、不写 UserEnv """
        self._create_user("env_sudo_edit", role="superuser")
        user = UserProfile.objects.get(username="env_sudo_edit")
        detail_url = reverse("users-detail", [user.id])

        resp = self.patch(detail_url, {
            "email": "env_sudo_edit@testmail.com",
        }).json()
        self.assertEqual(resp.get("code"), 0)
        self.assertEqual(self._granted_env_ids(user), set())

    # ---------- 降级兜底 ----------

    def test_downgrade_superuser_gets_default(self):
        """ 测试 superuser 降级为其它角色且无 UserEnv 时自动补 default 环境 """
        self._create_user("env_down_user", role="superuser")
        user = UserProfile.objects.get(username="env_down_user")
        detail_url = reverse("users-detail", [user.id])
        self.assertEqual(self._granted_env_ids(user), set())

        # role: superuser -> readonlyuser 且 UserEnv 为空 -> 自动补 env=1
        resp = self.patch(detail_url, {"role": "readonlyuser"}).json()
        self.assertEqual(resp.get("code"), 0)
        self.assertEqual(self._granted_env_ids(user), {1})

        # 非降级场景不触发兜底：普通用户 PATCH 邮箱不会凭空补环境
        self._create_user("env_plain_user", envs=[self.env_test.id])
        plain = UserProfile.objects.get(username="env_plain_user")
        resp = self.patch(
            reverse("users-detail", [plain.id]),
            {"email": "env_plain_user2@testmail.com"}).json()
        self.assertEqual(resp.get("code"), 0)
        self.assertEqual(self._granted_env_ids(plain), {self.env_test.id})

        # 已有授权的用户降级 -> 保持原授权，不重复插 default
        resp = self.patch(
            reverse("users-detail", [plain.id]), {"role": "superuser"}).json()
        self.assertEqual(resp.get("code"), 0)
        resp = self.patch(
            reverse("users-detail", [plain.id]), {"role": "readonlyuser"}).json()
        self.assertEqual(resp.get("code"), 0)
        self.assertEqual(self._granted_env_ids(plain), {self.env_test.id})

    # ---------- 列表输出 ----------

    def test_list_users_returns_envs(self):
        """ 测试用户列表输出 envs / env_names 字段 """
        self._create_user(
            "env_list_user", envs=[1, self.env_prod.id])
        self._create_user("env_list_empty")

        resp = self.get(self.users_url).json()
        self.assertEqual(resp.get("code"), 0)
        records = resp.get("data", {}).get("results", [])
        records_map = {item.get("username"): item for item in records}

        # 授权用户 -> envs 为 id 列表，env_names 为名称列表（顺序一致）
        granted = records_map.get("env_list_user")
        self.assertIsNotNone(granted)
        self.assertEqual(granted.get("envs"), [1, self.env_prod.id])
        self.assertEqual(
            granted.get("env_names"), ["default", "生产环境"])

        # 未授权用户 -> 空列表（字段必须存在）
        empty = records_map.get("env_list_empty")
        self.assertIsNotNone(empty)
        self.assertEqual(empty.get("envs"), [])
        self.assertEqual(empty.get("env_names"), [])

    # ---------- partial PATCH 密码契约 ----------

    def test_patch_without_password_keeps_password(self):
        """ 测试 PATCH 不带 password/re_password 不再 KeyError 且不覆盖原密码 """
        self._create_user("env_pwd_user", envs=[1])
        user = UserProfile.objects.get(username="env_pwd_user")
        detail_url = reverse("users-detail", [user.id])

        # 修复前：validate 中 attrs.pop('re_password') 抛 KeyError（500）
        resp = self.patch(detail_url, {
            "email": "env_pwd_user2@testmail.com",
        }).json()
        self.assertEqual(resp.get("code"), 0)

        # 修复前：make_password(None) 会把密码覆盖成不可用密码
        user.refresh_from_db()
        self.assertTrue(user.check_password("passw0rd@OMP"))
