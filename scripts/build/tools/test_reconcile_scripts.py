"""reconcile_scripts.py 对账工具测试。

场景构造：repo 与线上快照各一个临时目录，覆盖三类清单 + 排除规则 + --apply 行为。
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from reconcile_scripts import main  # noqa: E402


@pytest.fixture
def tree(tmp_path):
    """构造 repo / online 两棵树并返回 (repo_dir, online_dir, report_path)。"""
    repo = tmp_path / "repo"
    online = tmp_path / "online"
    for d in (repo / "source", online / "source"):
        d.mkdir(parents=True)
    # 冲突：两边都有但内容不同 → 线上为准
    (repo / "omp").write_text("repo version")
    (online / "omp").write_text("online version")
    # 一致：内容相同
    (repo / "install.sh").write_text("same")
    (online / "install.sh").write_text("same")
    # 线上独有：并入 repo
    (online / "source" / "new_tool.py").write_text("# online only")
    # repo 独有：保留，仅列报告
    (repo / "source" / "v120_new.py").write_text("# repo only")
    # 运行时痕迹：排除在对账外
    (online / "wal").mkdir()
    (online / "wal" / "000001").write_text("")
    (online / "source" / "__pycache__").mkdir()
    (online / "source" / "__pycache__" / "x.pyc").write_text("")
    report = tmp_path / "report.md"
    return repo, online, report


def _run(repo, online, report, *extra):
    return main([str(repo), str(online), str(report), *extra])


def test_dry_run_classifies_three_lists(tree):
    repo, online, report = tree
    assert _run(repo, online, report) == 0
    text = report.read_text(encoding="utf-8")
    assert "omp" in text.split("## 冲突")[1].split("##")[0]  # omp 列在冲突节
    assert "source/new_tool.py" in text.split("## 线上独有")[1].split("##")[0]
    assert "source/v120_new.py" in text.split("## repo 独有")[1].split("##")[0]
    assert "install.sh" in text.split("## 一致")[1].split("##")[0]
    # 排除项不出现
    assert "wal" not in text
    assert "__pycache__" not in text


def test_dry_run_does_not_modify_repo(tree):
    repo, online, report = tree
    before = (repo / "omp").read_text()
    _run(repo, online, report)
    assert (repo / "omp").read_text() == before          # 冲突未被覆盖
    assert not (repo / "source" / "new_tool.py").exists()  # 线上独有未拷入
    assert (repo / "source" / "v120_new.py").exists()      # repo 独有未动


def test_apply_overrides_conflict_and_copies_online_only(tree):
    repo, online, report = tree
    assert _run(repo, online, report, "--apply") == 0
    assert (repo / "omp").read_text() == "online version"
    assert (repo / "source" / "new_tool.py").read_text() == "# online only"
    assert (repo / "source" / "v120_new.py").read_text() == "# repo only"
    assert not (repo / "wal").exists()


def test_line_ending_only_difference_is_same(tree):
    """仅行尾差异（CRLF vs LF，autocrlf 环境）不算冲突。"""
    repo, online, report = tree
    (repo / "source" / "crlf.sh").write_bytes(b"line1\r\nline2\r\n")
    (online / "source" / "crlf.sh").write_bytes(b"line1\nline2\n")
    assert _run(repo, online, report) == 0
    text = report.read_text(encoding="utf-8")
    assert "source/crlf.sh" in text.split("## 一致")[1].split("##")[0]
    conflict_section = text.split("## 冲突")[1].split("##")[0]
    assert "crlf.sh" not in conflict_section


def test_apply_is_idempotent(tree):
    repo, online, report = tree
    _run(repo, online, report, "--apply")
    assert _run(repo, online, report, "--apply") == 0
    # 二次 apply 后报告应无冲突、无线上独有
    text = report.read_text(encoding="utf-8")
    conflict_section = text.split("## 冲突")[1].split("##")[0]
    online_only_section = text.split("## 线上独有")[1].split("##")[0]
    assert "omp" not in conflict_section
    assert "new_tool.py" not in online_only_section
