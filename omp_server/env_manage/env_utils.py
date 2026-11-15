# -*- coding: utf-8 -*-
"""
环境配置复制工具（多环境架构 Task 5）

copy_env_config：将来源环境的七张环境级配置表快照式复制到目标环境
（AlertRule、HostThreshold、ServiceThreshold、ServiceCustomThreshold、
ModuleSendEmailSetting、AlertSendWaySetting、SelfHealingSetting，
见设计 §6.3）。

复制为快照式：行 pk 重生成、env 指向目标环境，复制完成后两环境
配置互不影响；AlertRule 的 hash_data 唯一 hash 按目标环境重算，
保证 (env, hash) 不冲突（存量口径仅由 expr+severity 生成，跨环境
同规则必然撞 hash）。
"""
import hashlib
import logging

from db_models.models import (
    AlertRule, AlertSendWaySetting, HostThreshold,
    ModuleSendEmailSetting, SelfHealingSetting,
    ServiceCustomThreshold, ServiceThreshold)

logger = logging.getLogger("server")

# 除 AlertRule 外的六张配置表：纯行复制，无环境相关唯一键
CONFIG_COPY_MODELS = (
    HostThreshold,
    ServiceThreshold,
    ServiceCustomThreshold,
    ModuleSendEmailSetting,
    AlertSendWaySetting,
    SelfHealingSetting,
)


def rebuild_alert_rule_hash(env_id, expr, name, severity):
    """
    按目标环境重算 AlertRule 唯一 hash

    :param env_id: 目标环境 id
    :param expr: 监控指标表达式
    :param name: 内置指标名称
    :param severity: 告警级别
    :return: md5 hexdigest 字符串
    """
    data = f"{env_id}:{expr}:{name}:{severity}"
    return hashlib.md5(data.encode(encoding="UTF-8")).hexdigest()


def copy_env_config(source_env_id, target_env_id):
    """
    复制来源环境的环境级配置到目标环境（快照式，复制后互不影响）

    :param source_env_id: 来源环境 id
    :param target_env_id: 目标环境 id
    :return: None
    """
    # 1. AlertRule：hash_data 按目标环境重算，目标环境内撞 hash 时追加序号
    target_hashes = set(
        AlertRule.objects.filter(env_id=target_env_id)
        .values_list("hash_data", flat=True))
    rules = []
    for rule in AlertRule.objects.filter(env_id=source_env_id):
        rule.pk = None
        rule.env_id = target_env_id
        hash_data = rebuild_alert_rule_hash(
            target_env_id, rule.expr, rule.name, rule.severity)
        base_hash, index = hash_data, 1
        while hash_data in target_hashes:
            hash_data = f"{base_hash}-{index}"
            index += 1
        target_hashes.add(hash_data)
        rule.hash_data = hash_data
        rules.append(rule)
    AlertRule.objects.bulk_create(rules)

    # 2. 其余六表：逐表整行复制（pk 重生成，env 指向目标环境）
    for model in CONFIG_COPY_MODELS:
        rows = list(model.objects.filter(env_id=source_env_id))
        for row in rows:
            row.pk = None
            row.env_id = target_env_id
        model.objects.bulk_create(rows)

    logger.info(
        f"copy env config finished: env {source_env_id} -> "
        f"env {target_env_id}, copied alert rules {len(rules)}")
