#!/usr/bin/env python3
"""
校验一张「五要素任务卡」是否真的可执行。

零依赖，Python 3.8+。用法：

    python scripts/validate_brief.py <任务卡.md>
    python scripts/validate_brief.py <任务卡.md> --strict

检查项：
1. 五个字段（任务 / 背景 / 输出格式 / 限制 / 示例）是否齐全
2. 兜底句「信息不够就问我」是否存在
3. 字段是否被占位文本敷衍
4. 「限制」「输出格式」里有没有残留模糊形容词
5. 「限制」条目有没有以可落地的动词开头

退出码：0 通过，1 未通过，2 用法/读取错误。
"""

import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FIELDS = [
    ("1", "任务"),
    ("2", "背景"),
    ("3", "输出格式"),
    ("4", "限制"),
    ("5", "示例"),
]

SAFETY_LINE = "信息不够就问我"

FUZZY_WORDS = [
    "更美观", "更漂亮", "更高级", "更准确", "更简洁", "更口语",
    "更好", "更专业", "美观一点", "准确一点", "好看一点", "有质感",
    "高大上", "爆款感", "尽量", "大概", "差不多", "看着办", "随便",
    "适当", "合理即可", "自行判断", "自由发挥",
]

LANDING_VERBS = [
    "包含", "列出", "逐条", "覆盖", "分为", "附上", "保留", "注明", "标注",
    "排除", "删除", "不要", "不", "禁止", "避免", "跳过", "不出现", "不使用",
    "不超过", "不少于", "至少", "至多", "等于", "限制在", "控制在",
    "以", "改成", "替换", "对齐", "保持", "采用", "参照", "参考", "使用",
    "输出", "写", "改为", "不新增", "不补充", "只", "共", "每",
]

PLACEHOLDERS = {"待补充", "无", "暂无", "随便", "你看着办", "n/a", "todo", "-", ""}


def strip_noise(text):
    """去掉注释、代码围栏、表格行与引用行，只留需要判定的正文。"""
    text = re.sub(r"<!--[\s\S]*?-->", "", text)
    text = re.sub(r"```[\s\S]*?```", "", text)
    kept = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("|") or s.startswith(">") or "→" in s:
            continue
        if s.startswith("#"):
            continue
        kept.append(s)
    return kept


def extract_sections(text):
    sections = {}
    current = None
    buf = []
    for line in text.splitlines():
        m = re.match(r"^##\s*([1-5])[.、]\s*(.+?)\s*$", line)
        if m:
            if current is not None:
                sections[current] = buf
                buf = []
            current = m.group(1)
            continue
        if current is not None and re.match(r"^##\s", line):
            sections[current] = buf
            current = None
            buf = []
            continue
        if current is not None:
            buf.append(line)
    if current is not None:
        sections[current] = buf
    return {k: "\n".join(v) for k, v in sections.items()}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if "--help" in flags or "-h" in flags or not args:
        print(__doc__)
        return 2
    strict = "--strict" in flags

    path = Path(args[0])
    if not path.is_file():
        print(f"[!!] 找不到文件：{path}")
        return 2
    text = path.read_text(encoding="utf-8")

    errors = []
    warnings = []
    oks = []

    # 1. 字段齐全
    for num, name in FIELDS:
        pattern = r"^##\s*" + num + r"[.、]\s*" + re.escape(name) + r"\s*$"
        if re.search(pattern, text, flags=re.MULTILINE):
            oks.append(f"字段 {num} {name} 存在")
        else:
            errors.append(f"缺少字段标题：## {num}. {name}")

    # 2. 兜底句
    if SAFETY_LINE in text:
        oks.append("兜底句「信息不够就问我」存在")
    else:
        errors.append("缺少兜底句「信息不够就问我，不要编造」")

    sections = extract_sections(text)

    # 3. 占位 / 空字段
    empty_count = 0
    for num, name in FIELDS:
        body = sections.get(num, "")
        cleaned = strip_noise(body)
        joined = " ".join(cleaned).strip(" -*\t")
        if not cleaned or joined.lower() in PLACEHOLDERS:
            empty_count += 1
            warnings.append(f"字段 {num} {name} 为空或仍是占位文本")
        elif "本轮不使用示例" in body and num == "5":
            oks.append("字段 5 示例：已显式声明不使用（有效填写）")
    if empty_count == len(FIELDS):
        errors.append("五个字段全为空：这是空白模板，请先填写再校验")

    # 4. 模糊形容词（只看输出格式与限制，避免误伤叙述和对照表）
    for num, name in [("3", "输出格式"), ("4", "限制")]:
        for line in strip_noise(sections.get(num, "")):
            hits = [w for w in FUZZY_WORDS if w in line]
            if hits:
                errors.append(f"{name} 里出现模糊词 {'、'.join(hits)}：{line[:60]}")

    # 5. 限制条目是否有落地动词
    bullets = []
    for line in strip_noise(sections.get("4", "")):
        if re.match(r"^([-*]|\d+[.)])\s+", line):
            bullets.append(re.sub(r"^([-*]|\d+[.)])\s+", "", line))
    if not bullets:
        warnings.append("限制字段没有检到条目行（建议用 - 列表写 3-6 条）")
    for b in bullets:
        if not any(v in b for v in LANDING_VERBS):
            warnings.append(f"限制条目缺少落地动词：{b[:60]}")
    if bullets:
        oks.append(f"限制字段共 {len(bullets)} 条")

    if strict:
        errors.extend(warnings)
        warnings = []

    for line in oks:
        print(f"[OK] {line}")
    for line in warnings:
        print(f"[--] 提示：{line}")
    for line in errors:
        print(f"[!!] {line}")

    print("")
    if errors:
        print(f"结论：未通过（{len(errors)} 项错误）。按 references/constraints.md 改写后重试。")
        return 1
    note = "" if not warnings else f"，另有 {len(warnings)} 项提示"
    print(f"结论：通过{note}。仍需按 references/checklist.md 做自检与人工核查。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
