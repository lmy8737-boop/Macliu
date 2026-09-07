"""
buzzword_detector.py — v4.7 反偷懒模糊词检测（A1）

算法（与原始协议的关键改进）：
  1. 同句内 + 禁词右侧 60 字符内是否出现 数字/百分比/日期/具体名词 → "有数据支撑"
  2. 任一类别 ≥2 处 "零数据支撑" 命中 → verdict=FAIL（不再用总数阈值）
  3. 词库外置 references/buzzword_lexicon.yaml（A1 + A4 共用）

CLI:
  python buzzword_detector.py <markdown_path> [--review-id N] [--target-role 1|2|3|4]

输出 JSON 到 stdout + 写 audit_log（如 review_id 提供）。
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

# 句子切分（中文/英文混合）：。！？!?\n
SENTENCE_SPLIT = re.compile(r'(?<=[。！？!?\n])\s*')
# 数据支撑右窗口（字符数）
RIGHT_WINDOW = 60


def load_lexicon(path: Path = LEXICON_PATH) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"找不到词库 {path}")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def has_data_support(right_context: str, support_patterns: list) -> tuple:
    """检查禁词右侧 60 字符内是否含数据支撑。返回 (bool, label)"""
    for entry in support_patterns:
        if re.search(entry["regex"], right_context):
            return True, entry["label"]
    return False, None


def detect(markdown_path: str, lexicon: dict = None) -> dict:
    """
    主检测函数
    返回: {file, total_hits, by_category, hits[...], verdict}
    """
    lexicon = lexicon or load_lexicon()
    support_patterns = lexicon["data_support_rules"]["patterns"]
    buzzword_groups = lexicon["buzzwords"]

    text = Path(markdown_path).read_text(encoding="utf-8")
    sentences = SENTENCE_SPLIT.split(text)

    hits = []
    by_category = {}  # {category_key: {label, total, no_data, with_data}}

    # 计算每行号（用于定位）
    line_offsets = []
    cursor = 0
    for line in text.split("\n"):
        line_offsets.append(cursor)
        cursor += len(line) + 1

    def char_to_line(char_idx: int) -> int:
        for i, off in enumerate(line_offsets):
            if off > char_idx:
                return i  # 上一行
        return len(line_offsets)

    # 句子级扫描
    sent_cursor = 0
    for sent in sentences:
        sent_start = text.find(sent, sent_cursor) if sent else sent_cursor
        if sent_start < 0:
            sent_start = sent_cursor
        sent_cursor = sent_start + len(sent)

        for cat_key, cat_data in buzzword_groups.items():
            label = cat_data["label"]
            if cat_key not in by_category:
                by_category[cat_key] = {"label": label, "total": 0, "no_data": 0, "with_data": 0}

            for word in cat_data["patterns"]:
                idx = 0
                while True:
                    pos = sent.find(word, idx)
                    if pos < 0:
                        break
                    abs_pos = sent_start + pos
                    line_no = char_to_line(abs_pos)
                    right_ctx = sent[pos + len(word):pos + len(word) + RIGHT_WINDOW]
                    has_data, support_label = has_data_support(right_ctx, support_patterns)

                    by_category[cat_key]["total"] += 1
                    if has_data:
                        by_category[cat_key]["with_data"] += 1
                    else:
                        by_category[cat_key]["no_data"] += 1

                    hits.append({
                        "category": cat_key,
                        "category_label": label,
                        "word": word,
                        "line": line_no,
                        "sentence": sent.strip()[:200],
                        "right_context": right_ctx.strip(),
                        "has_data_support": has_data,
                        "data_support_type": support_label,
                    })
                    idx = pos + len(word)

    # 判定：任一类别 no_data >= 2 → FAIL
    fail_categories = [k for k, v in by_category.items() if v["no_data"] >= 2]
    verdict = "FAIL" if fail_categories else "PASS"

    return {
        "file": str(markdown_path),
        "total_hits": len(hits),
        "no_data_hits": sum(v["no_data"] for v in by_category.values()),
        "by_category": by_category,
        "hits": hits,
        "fail_categories": fail_categories,
        "verdict": verdict,
        "threshold_rule": "任一类别 ≥2 处零数据支撑 → FAIL",
    }


def write_audit_log(result: dict, review_id: int = None, target_role: str = ""):
    """写入 audit_log 表（如 DB 存在）"""
    if not DB_PATH.exists():
        return
    try:
        conn = sqlite3.connect(DB_PATH)
        # 精简版 detail_json（不存全部 hits 避免膨胀，只存命中位置摘要）
        detail = {
            "verdict": result["verdict"],
            "no_data_hits": result["no_data_hits"],
            "by_category": result["by_category"],
            "fail_categories": result["fail_categories"],
            "hit_count": len(result["hits"]),
            "sample_hits": result["hits"][:10],  # 取前 10 条作为样本
        }
        conn.execute("""
            INSERT INTO audit_log (review_id, script_name, target_role,
                                   target_artifact, verdict, detail_json,
                                   audit_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (review_id, "buzzword", target_role, result["file"],
              result["verdict"], json.dumps(detail, ensure_ascii=False),
              date.today().isoformat()))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️  audit_log 写入失败: {e}", file=sys.stderr)


def parse_args():
    args = {"file": None, "review_id": None, "target_role": ""}
    rest = sys.argv[1:]
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--review-id":
            args["review_id"] = int(rest[i + 1]); i += 2
        elif a == "--target-role":
            args["target_role"] = rest[i + 1]; i += 2
        elif not args["file"]:
            args["file"] = a; i += 1
        else:
            i += 1
    return args


def main():
    args = parse_args()
    if not args["file"]:
        print("用法: python buzzword_detector.py <markdown> [--review-id N] [--target-role 1|2|3|4]")
        sys.exit(1)

    result = detect(args["file"])
    write_audit_log(result, args["review_id"], args["target_role"])

    # CLI 友好打印
    emoji = "✅" if result["verdict"] == "PASS" else "❌"
    print(f"{emoji} buzzword_detector | {result['file']}")
    print(f"   verdict={result['verdict']} | 总命中 {result['total_hits']} 处 | 零数据 {result['no_data_hits']} 处")
    if result["fail_categories"]:
        print(f"   FAIL 类别: {result['fail_categories']}")
    for cat, stats in result["by_category"].items():
        if stats["total"] > 0:
            print(f"   - {stats['label']}: {stats['no_data']}/{stats['total']} 零数据")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["verdict"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
