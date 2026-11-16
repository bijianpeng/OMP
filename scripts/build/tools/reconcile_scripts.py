"""scripts 目录对账工具：repo 与线上 /data/omp/scripts 快照对齐。

规则（spec：线上为准）：
- 冲突（两边都有、内容不同）→ 报告列出；--apply 时用线上版覆盖 repo
- 线上独有 → 报告列出；--apply 时拷入 repo
- repo 独有 → 仅报告列出（默认保留，由所有者逐个判定）
- 运行时痕迹（wal/、__pycache__/、*.log、*.pyc）排除在对账外

用法：
  python reconcile_scripts.py <repo_scripts_dir> <online_scripts_dir> <report_path> [--apply]
"""
import argparse
import hashlib
import shutil
import sys
from pathlib import Path

EXCLUDE_DIRS = {"wal", "__pycache__"}
EXCLUDE_SUFFIXES = (".log", ".pyc")


def _is_excluded(path: Path) -> bool:
    return (
        any(part in EXCLUDE_DIRS for part in path.parts)
        or path.suffix in EXCLUDE_SUFFIXES
    )


def _scan(root: Path):
    """返回 {相对路径: sha256}，排除运行时痕迹。

    行尾规范化（CRLF→LF）后比较：Windows autocrlf 工作区与线上 LF 快照
    仅行尾不同不算冲突；--apply 拷贝仍保留线上原始字节。
    """
    files = {}
    for p in root.rglob("*"):
        if p.is_dir() or _is_excluded(p):
            continue
        normalized = p.read_bytes().replace(b"\r\n", b"\n")
        files[p.relative_to(root).as_posix()] = hashlib.sha256(normalized).hexdigest()
    return files


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo_dir", help="repo 内 scripts 目录")
    parser.add_argument("online_dir", help="线上 scripts 快照目录")
    parser.add_argument("report_path", help="对账报告输出路径（markdown）")
    parser.add_argument("--apply", action="store_true",
                        help="执行合并：冲突用线上版覆盖、线上独有拷入；repo 独有不动")
    args = parser.parse_args(argv)

    repo_dir, online_dir = Path(args.repo_dir), Path(args.online_dir)
    if not repo_dir.is_dir() or not online_dir.is_dir():
        print(f"目录不存在: {repo_dir} / {online_dir}", file=sys.stderr)
        return 2

    repo_files, online_files = _scan(repo_dir), _scan(online_dir)
    conflict = sorted(k for k in repo_files.keys() & online_files.keys()
                      if repo_files[k] != online_files[k])
    same = sorted(repo_files.keys() & online_files.keys() - set(conflict))
    online_only = sorted(online_files.keys() - repo_files.keys())
    repo_only = sorted(repo_files.keys() - online_files.keys())

    if args.apply:
        for rel in conflict:
            shutil.copy2(online_dir / rel, repo_dir / rel)
        for rel in online_only:
            target = repo_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(online_dir / rel, target)

    def _items(names):
        return [f"- `{r}`" for r in names] or ["- 无"]

    lines = [
        "# scripts 对账报告",
        "",
        f"- repo: `{repo_dir}`  线上快照: `{online_dir}`  模式: {'--apply（已合并）' if args.apply else '干跑（未改动）'}",
        f"- 冲突 {len(conflict)} 项（线上为准）、线上独有 {len(online_only)} 项（并入）、"
        f"repo 独有 {len(repo_only)} 项（保留待判）、一致 {len(same)} 项",
        "",
        "## 冲突（线上为准）",
        *_items(conflict),
        "",
        "## 线上独有（并入）",
        *_items(online_only),
        "",
        "## repo 独有（保留，待所有者判定）",
        *_items(repo_only),
        "",
        "## 一致",
        *_items(same),
        "",
    ]
    report = Path(args.report_path)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines), encoding="utf-8")
    print(f"报告: {report}（冲突 {len(conflict)} / 线上独有 {len(online_only)} / "
          f"repo 独有 {len(repo_only)} / 一致 {len(same)}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
