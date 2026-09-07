"""
semantic_diff.py — v4.7 反偷懒返工敷衍检测（A4）

关键设计：
  1. 输入：原稿 + 返工稿 + 上一轮 5 号 REJECT 的结构化 requirements JSON（依赖步骤 3）
  2. 每条 requirement 三重判定（全过 = 实质性修改）：
     a. diff_chars >= 30
     b. 新增内容必须命中 structures.json 字段值（笔序号/背驰比/具体价位/百分比/日期）
     c. 不命中"敷衍模式词典"（与 buzzword_lexicon.yaml 共享）
  3. 任一 requirement 失败 → verdict=FAIL（PERFUNCTORY_REWORK）

输入 requirements JSON 格式（5 号产出的 ```requirements``` 代码块）:
  {
    "requirements": [
      {"id": 1, "target_section": "## 标题", "target_role": "2", "expected_change": "..."},
      ...
    ]
  }

CLI:
  python semantic_diff.py \
      --original old.md --rework new.md \
      --requirements reject_block.json \
      [--structures structures.json] \
      [--review-id N] [--target-role 2]
"""
import json
import os
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

try:
    import yaml
except ImportError:
    print("⚠️  缺少 PyYAML。请 pip install pyyaml", file=sys.stderr)
    sys.exit(1)

DB_PATH = Path(os.environ.get(
    "INVESTMENT_TEAM_DB",
    Path.cwd() / "engine" / "data" / "trading.db"
))
SKILL_ROOT = Path(__file__).resolve().parents[2]
LEXICON_PATH = SKILL_ROOT / "references" / "buzzword_lexicon.yaml"

DIFF_CHAR_THRESHOLD = 30


def load_lexicon() -> dict:
    if not LEXICON_PATH.exists():
        return {}
    return yaml.safe_load(LEXICON_PATH.read_text(encoding="utf-8"))


def load_perfunctory_patterns(lexicon: dict) -> list:
    """汇总所有敷衍模式词，返回扁平 list"""
    patterns = lexicon.get("perfunctory_patterns", {})
    flat = []
    for key, val in patterns.items():
        if isinstance(val, dict) and "examples" in val:
            for ex in val["examples"]:
                # 例子可能是 "较为 → 非常" 这种箭头格式，取右侧
                if "→" in ex:
                    flat.append(ex.split("→")[-1].strip())
                else:
                    flat.append(ex)
    return flat


def load_data_support_patterns(lexicon: dict) -> list:
    """加载数据支撑正则（命中 = 含具体数据）"""
    rules = lexicon.get("data_support_rules", {}).get("patterns", [])
    return [r["regex"] for r in rules]


def extract_section_text(md: str, section_title: str) -> str:
    """从 Markdown 抽取指定 section 标题下的内容（直到下一个同级或更高级标题）"""
    # 容错匹配：去空格、忽略 ## 数量
    section_clean = re.sub(r'^#+\s*', '', section_title.strip())

    lines = md.split("\n")
    capture = False
    captured = []
    capture_level = None
    for line in lines:
        m = re.match(r'^(#+)\s+(.+)$', line)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            if capture:
                # 同级或更高 → 停
                if capture_level and level <= capture_level:
                    break
            if section_clean in title or title in section_clean:
                capture = True
                capture_level = level
                continue
        if capture:
            captured.append(line)
    return "\n".join(captured)


def load_structures_values(structures_path: str) -> set:
    """从 structures.json 提取所有数值字段，用于后续匹配"""
    values = set()
    if not structures_path or not Path(structures_path).exists():
        return values
    try:
        data = json.loads(Path(structures_path).read_text(encoding="utf-8"))
    except Exception:
        return values

    def walk(obj):
        if isinstance(obj, dict):
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)
        elif isinstance(obj, (int, float)):
            # 保留有意义的数值（>0.1）
            if abs(obj) > 0.001:
                values.add(str(obj))
                values.add(str(round(obj, 2)))

    walk(data)
    return values


def has_concrete_data(text: str, support_regexes: list,
                     structures_values: set) -> tuple:
    """检查文本是否含 具体数据。返回 (bool, matched_evidence)"""
    # 1. 命中数据支撑正则 → 有
    for rx in support_regexes:
        if re.search(rx, text):
            return True, f"regex:{rx}"
    # 2. 含 structures.json 值 → 有
    for v in structures_values:
        if v in text:
            return True, f"structures_value:{v}"
    return False, None


def has_perfunctory_pattern(text: str, perfunctory_patterns: list) -> tuple:
    """检查是否命中敷衍模式词。返回 (bool, matched_pattern)"""
    for p in perfunctory_patterns:
        if p in text:
            return True, p
    return False, None


def diff_section(orig_md: str, new_md: str, section_title: str) -> dict:
    """对单个 section 做 diff，返回新增字符数 + 新增内容"""
    orig_text = extract_section_text(orig_md, section_title)
    new_text = extract_section_text(new_md, section_title)

    orig_chars = set(orig_text)
    new_only_chars = len(new_text) - len(orig_text)

    # 新增内容（粗略：取新稿中原稿没有的句子）
    orig_sents = set(s.strip() for s in re.split(r'[。！？\n]', orig_text) if s.strip())
    new_sents = re.split(r'[。！？\n]', new_text)
    added = [s.strip() for s in new_sents if s.strip() and s.strip() not in orig_sents]
    added_text = "\n".join(added)

    return {
        "diff_chars": max(new_only_chars, len(added_text)),
        "added_text": added_text,
        "orig_section_size": len(orig_text),
        "new_section_size": len(new_text),
    }


def check(orig_md: str, new_md: str, requirements: list,
          support_regexes: list, perfunctory_patterns: list,
          structures_values: set) -> dict:
    """主检测函数"""
    results = []
    perfunctory_count = 0

    for req in requirements:
        rid = req.get("id")
        section = req.get("target_section", "")
        expected = req.get("expected_change", "")
        target_role = req.get("target_role", "")

        diff_info = diff_section(orig_md, new_md, section)
        added_text = diff_info["added_text"]

        # 三重判定
        check_chars = diff_info["diff_chars"] >= DIFF_CHAR_THRESHOLD
        check_data, data_evidence = has_concrete_data(added_text, support_regexes, structures_values)
        check_perfunctory, perf_pattern = has_perfunctory_pattern(added_text, perfunctory_patterns)

        verdict = "PASS" if (check_chars and check_data and not check_perfunctory) else "FAIL"
        if verdict == "FAIL":
            perfunctory_count += 1

        fail_reasons = []
        if not check_chars:
            fail_reasons.append(f"diff_chars={diff_info['diff_chars']} < {DIFF_CHAR_THRESHOLD}")
        if not check_data:
            fail_reasons.append("新增内容未命中具体数据（无数字/日期/缠论字段）")
        if check_perfunctory:
            fail_reasons.append(f"命中敷衍模式词: '{perf_pattern}'")

        results.append({
            "id": rid,
            "target_section": section,
            "target_role": target_role,
            "expected_change": expected,
            "diff_chars": diff_info["diff_chars"],
            "added_text_preview": added_text[:300],
            "check_chars": check_chars,
            "check_data_concrete": check_data,
            "data_evidence": data_evidence,
            "check_no_perfunctory": not check_perfunctory,
            "perfunctory_pattern_matched": perf_pattern,
            "verdict": verdict,
            "fail_reasons": fail_reasons,
        })

    overall = "FAIL" if perfunctory_count > 0 else "PASS"

    return {
        "total_requirements": len(requirements),
        "perfunctory_count": perfunctory_count,
        "passed_count": len(requirements) - perfunctory_count,
        "requirements": results,
        "verdict": overall,
        "rule": "任一 requirement 三重判定不全过 → 整体 FAIL（PERFUNCTORY_REWORK）",
    }


def parse_requirements(req_path: str) -> list:
    """读取 requirements JSON 文件"""
    if not Path(req_path).exists():
        raise FileNotFoundError(f"找不到 requirements 文件 {req_path}")
    raw = Path(req_path).read_text(encoding="utf-8")
    # 容许包裹在 ```requirements ... ``` 代码块中
    m = re.search(r'```(?:requirements|json)?\s*\n(.+?)\n```', raw, re.DOTALL)
    if m:
        raw = m.group(1)
    data = json.loads(raw)
    return data.get("requirements", []) if isinstance(data, dict) else data


def write_audit_log(result: dict, review_id: int = None,
                    target_role: str = "", artifact: str = ""):
    if not DB_PATH.exists():
        return
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            INSERT INTO audit_log (review_id, script_name, target_role,
                                   target_artifact, verdict, detail_json,
                                   audit_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (review_id, "semantic_diff", target_role, artifact,
              result["verdict"], json.dumps(result, ensure_ascii=False),
              date.today().isoformat()))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️  audit_log 写入失败: {e}", file=sys.stderr)


def parse_args():
    args = {"original": None, "rework": None, "requirements": None,
            "structures": None, "review_id": None, "target_role": ""}
    rest = sys.argv[1:]
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--original":
            args["original"] = rest[i + 1]; i += 2
        elif a == "--rework":
            args["rework"] = rest[i + 1]; i += 2
        elif a == "--requirements":
            args["requirements"] = rest[i + 1]; i += 2
        elif a == "--structures":
            args["structures"] = rest[i + 1]; i += 2
        elif a == "--review-id":
            args["review_id"] = int(rest[i + 1]); i += 2
        elif a == "--target-role":
            args["target_role"] = rest[i + 1]; i += 2
        else:
            i += 1
    return args


def main():
    args = parse_args()
    if not all([args["original"], args["rework"], args["requirements"]]):
        print("用法: python semantic_diff.py --original old.md --rework new.md "
              "--requirements reqs.json [--structures structures.json]")
        sys.exit(1)

    orig_md = Path(args["original"]).read_text(encoding="utf-8")
    new_md = Path(args["rework"]).read_text(encoding="utf-8")
    requirements = parse_requirements(args["requirements"])

    lexicon = load_lexicon()
    support_regexes = load_data_support_patterns(lexicon)
    perfunctory_patterns = load_perfunctory_patterns(lexicon)
    structures_values = load_structures_values(args["structures"])

    result = check(orig_md, new_md, requirements,
                   support_regexes, perfunctory_patterns, structures_values)
    write_audit_log(result, args["review_id"], args["target_role"], args["rework"])

    emoji = "✅" if result["verdict"] == "PASS" else "❌"
    print(f"{emoji} semantic_diff | {args['rework']}")
    print(f"   verdict={result['verdict']}")
    print(f"   通过 {result['passed_count']}/{result['total_requirements']} 条 requirement | "
          f"敷衍 {result['perfunctory_count']} 条")
    for r in result["requirements"]:
        sub = "✅" if r["verdict"] == "PASS" else "❌"
        print(f"   {sub} req#{r['id']} ({r['target_section']}): "
              f"chars={r['diff_chars']} data={r['check_data_concrete']} "
              f"no_perf={r['check_no_perfunctory']}")
        for fr in r["fail_reasons"]:
            print(f"      - {fr}")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["verdict"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
