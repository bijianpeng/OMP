import pytest

from db_models.models import Env, UserEnv, UserProfile


@pytest.mark.django_db
def test_env_code_backfilled_and_unique():
    # 迁移后 default 行 code=="default"（data migration 随测试库 migrate 执行）
    assert Env.objects.get(id=1).code == "default"
    # code 全局唯一：重复创建同 code 环境应触发唯一约束
    with pytest.raises(Exception):
        Env.objects.create(name="dup", code="default")


@pytest.mark.django_db
def test_user_env_unique_together():
    env = Env.objects.get(id=1)
    user = UserProfile.objects.filter(role="readonlyuser").first() \
        or UserProfile.objects.create(username="u1", password="x")
    UserEnv.objects.create(user=user, env=env)
    with pytest.raises(Exception):
        UserEnv.objects.create(user=user, env=env)
