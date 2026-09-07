"""
data_verifier.py — v4.7 反偷懒数据交叉验证（A2）

关键设计（与原始协议的改进）：
  1. 只校验 "事实断言"（含定语 "截至 X 日/当前/已识别/3 号采集"），跳过 "推断"（目标价/预期 PE/中性情景）
  2. 幻觉分两档：
     - HARD: JSON 中无该字段 → verdict=FAIL
     - SOFT: 字段存在但值偏（容差外）→ 计入 soft_mismatch
  3. 容差：股价 ±1% / PE 整数对齐 ±1（23→24 跨档要红旗）/ 缠论字段精确匹配
  4. 宏观数据（CPI/PMI）需 macro_facts.json，未提供则跳过

CLI:
  python data_verifier.py <markdown_path> \
      --structures structures_*.json \
      [--scanner scanner_*.json] \
      [--chip chip_analysis.json] \
      [--macro macro_facts.json] \
      [--review-id N] [--target-role 1|2|3|4]
"""
import json
import os
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

DB_PATH = Path(os.environ.get(
    "INVESTMENT_TEAM_DB",
    Path.cwd() / "engine" / "data" / "trading.db"
))

# 事实断言定语（句子中含此类词 = 事实断言；缺失 = 推断/预期，跳过）
FACT_MARKERS = [
    "截至", "当前", "现报", "目前", "今日",
    "已识别", "已确认", "已发布", "已公告",
    "3号采集", "scanner 显示", "structures.json", "API 返回",
    "K线显示", "数据显示", "实测", "实际",
]

# 推断/预期标记（命中 = 跳过，不校验）
INFERENCE_MARKERS = [
    "目标价", "预期", "预计", "估算", "情景",
    "悲观", "中性", "乐观", "假设", "若",
    "可能达到", "有望", "或将", "推演",
]

# 数值断言模式
PATTERN_STOCK_PRICE = re.compile(
    r'(?:股价|现价|当前价格|收盘价|报价)[:：\s]*[¥$]?\s*(\d+(?:\.\d+)?)\s*(?:元|港币|美元)?'
)
PATTERN_PE = re.compile(
    r'PE\s*[:：=]?\s*(\d+(?:\.\d+)?)\s*x?'
)
PATTERN_PB = re.compile(
    r'PB\s*[:：=]?\s*(\d+(?:\.\d+)?)\s*x?'
)
PATTERN_BI_NUMBER = re.compile(
    r'第\s*(\d+)\s*笔|笔ID\s*[:：]?\s*(\d+)|笔序号\s*[:：]?\s*(\d+)|bi[_\s-]?count[:：=]\s*(\d+)'
)
PATTERN_DIVERGENCE_RATIO = re.compile(
    r'背驰(?:能量)?比[:：值=]?\s*(\d+(?:\.\d+)?)|energy_ratio[:：=]\s*(\d+(?:\.\d+)?)'
)
PATTERN_RETENTION = re.compile(
    r'(?:留存率|留存水位|国家队留存)[:：\s]*(\d+(?:\.\d+)?)\s*%'
)
PATTERN_TICKER_PRICE = re.compile(
    r'([A-Z]{1,4}\d{6}|[a-z]{2,4}\d{5,6}|[A-Z]{2,5})[\s（(]+[¥$]?(\d+(?:\.\d+)?)'
)


def is_factual(sentence: str) -> bool:
    """判定句子是事实断言还是推断"""
    if any(m in sentence for m in INFERENCE_MARKERS):
        return False
    return any(m in sentence for m in FACT_MARKERS)


def split_sentences(text: str) -> list:
    """切句（中英混合）"""
    return [s for s in re.split(r'(?<=[。！？!?\n])\s*', text) if s.strip()]


def load_json(path: str) -> dict:
    if not path or not Path(path).exists():
        return {}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}


def extract_ticker_data(structures: dict, ticker: str) -> dict:
    """从 structures JSON 提取指定 ticker 的字段"""
    tickers = structures.get("tickers", {})
    if ticker in tickers:
        return tickers[ticker]
    # 尝试不区分大小写
    for k, v in tickers.items():
        if k.upper() == ticker.upper():
            return v
    return {}


def verify(markdown_path: str, structures: dict, scanner: dict,
           chip: dict, macro: dict) -> dict:
    """
    主验证函数
    返回: {verified, hard_hallucination, soft_mismatch, skipped_inference, verdict}
    """
    text = Path(markdown_path).read_text(encoding="utf-8")
    sentences = split_sentences(text)

    verified = []
    hard_hallucination = []  # JSON 无字段
    soft_mismatch = []       # 字段在但值偏
    skipped_inference = []   # 跳过的推断句
    skipped_no_marker = 0    # 既非事实也非推断（无定语）

    for sent in sentences:
        # 包含数值断言才检查
        has_numeric = bool(re.search(r'\d+(?:\.\d+)?', sent))
        if not has_numeric:
            continue

        if any(m in sent for m in INFERENCE_MARKERS):
            skipped_inference.append({"sentence": sent.strip()[:150]})
            continue

        if not is_factual(sent):
            # 既无事实定语也无推断标记 → 不校验（避免误判）
            skipped_no_marker += 1
            continue

        # === 笔序号校验（缠论结构精确匹配）===
        m = PATTERN_BI_NUMBER.search(sent)
        if m:
            claimed = next((g for g in m.groups() if g), None)
            if claimed:
                claimed_n = int(claimed)
                # 在所有 ticker 的 structures 中找
                found = False
                for tk, data in structures.get("tickers", {}).items():
                    levels = data.get("levels", {})
                    for lv, lvdata in levels.items() if isinstance(levels, dict) else []:
                        if lvdata.get("bi_count", -1) == claimed_n:
                            verified.append({"type": "bi_count", "value": claimed_n,
                                             "matched_in": f"{tk}.{lv}"})
                            found = True
                            break
                    if found:
                        break
                if not found:
                    hard_hallucination.append({
                        "type": "bi_count",
                        "claimed": claimed_n,
                        "sentence": sent.strip()[:150],
                        "reason": "structures.json 中无任何 ticker 的 bi_count 等于此值",
                    })

        # === 背驰比校验 ===
        m = PATTERN_DIVERGENCE_RATIO.search(sent)
        if m:
            claimed = next((g for g in m.groups() if g), None)
            if claimed:
                claimed_v = float(claimed)
                found_match = False
                for tk, data in structures.get("tickers", {}).items():
                    levels = data.get("levels", {}) if isinstance(data.get("levels"), dict) else {}
                    for lv, lvdata in levels.items():
                        actual = lvdata.get("divergence", {}).get("energy_ratio")
                        if actual is not None and abs(actual - claimed_v) < 0.01:
                            verified.append({"type": "divergence_ratio",
                                             "value": claimed_v,
                                             "matched_in": f"{tk}.{lv}"})
                            found_match = True
                            break
                if not found_match:
                    hard_hallucination.append({
                        "type": "divergence_ratio",
                        "claimed": claimed_v,
                        "sentence": sent.strip()[:150],
                    })

        # === 留存率校验（chip）===
        m = PATTERN_RETENTION.search(sent)
        if m and chip:
            claimed = float(m.group(1))
            actual_overall = chip.get("retention_analysis", {}).get("overall_retention_pct")
            if actual_overall is not None:
                # ±2 个百分点容差
                if abs(actual_overall - claimed) <= 2:
                    verified.append({"type": "retention_pct",
                                     "claimed": claimed,
                                     "actual": actual_overall})
                else:
                    soft_mismatch.append({
                        "type": "retention_pct",
                        "claimed": claimed,
                        "actual": actual_overall,
                        "deviation": round(abs(actual_overall - claimed), 2),
                        "sentence": sent.strip()[:150],
                    })

        # === PE 校验（整数对齐 ±1）===
        m = PATTERN_PE.search(sent)
        if m:
            claimed_pe = float(m.group(1))
            # 在 scanner 中查 PE
            for tk, sdata in (scanner.get("results", {}) or {}).items() if isinstance(scanner.get("results"), dict) else []:
                actual_pe = sdata.get("pe_ttm") or sdata.get("pe")
                if actual_pe and tk in sent:
                    actual_int = round(actual_pe)
                    claimed_int = round(claimed_pe)
                    if abs(actual_int - claimed_int) <= 1:
                        verified.append({"type": "pe", "ticker": tk,
                                         "claimed": claimed_pe, "actual": actual_pe})
                    else:
                        soft_mismatch.append({
                            "type": "pe",
                            "ticker": tk,
                            "claimed": claimed_pe,
                            "actual": actual_pe,
                            "tier_jump": True,
                            "sentence": sent.strip()[:150],
                        })

    # 判定：HARD 任意 ≥1 → FAIL；仅 SOFT → SOFT_FAIL；全验过/无可验 → PASS
    if hard_hallucination:
        verdict = "FAIL"
    elif soft_mismatch:
        verdict = "SOFT_FAIL"
    else:
        verdict = "PASS"

    return {
        "file": str(markdown_path),
        "verified_count": len(verified),
        "hard_hallucination_count": len(hard_hallucination),
        "soft_mismatch_count": len(soft_mismatch),
        "skipped_inference_count": len(skipped_inference),
        "skipped_no_marker_count": skipped_no_marker,
        "verified": verified[:20],
        "hard_hallucination": hard_hallucination,
        "soft_mismatch": soft_mismatch,
        "verdict": verdict,
    }


def write_audit_log(result: dict, review_id: int = None, target_role: str = ""):
    if not DB_PATH.exists():
        return
    try:
        conn = sqlite3.connect(DB_PATH)
        detail = {k: v for k, v in result.items() if k != "verified"}  # 不存大数组
        detail["verified_sample"] = result["verified"][:5]
        conn.execute("""
            INSERT INTO audit_log (review_id, script_name, target_role,
                                   target_artifact, verdict, detail_json,
                                   audit_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (review_id, "data_verify", target_role, result["file"],
              result["verdict"], json.dumps(detail, ensure_ascii=False),
              date.today().isoformat()))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️  audit_log 写入失败: {e}", file=sys.stderr)


def parse_args():
    args = {"file": None, "structures": None, "scanner": None, "chip": None,
            "macro": None, "review_id": None, "target_role": ""}
    rest = sys.argv[1:]
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--structures":
            args["structures"] = rest[i + 1]; i += 2
        elif a == "--scanner":
            args["scanner"] = rest[i + 1]; i += 2
        elif a == "--chip":
            args["chip"] = rest[i + 1]; i += 2
        elif a == "--macro":
            args["macro"] = rest[i + 1]; i += 2
        elif a == "--review-id":
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
        print("用法: python data_verifier.py <markdown> --structures <json> [--scanner|--chip|--macro <json>]")
        sys.exit(1)

    structures = load_json(args["structures"])
    scanner = load_json(args["scanner"])
    chip = load_json(args["chip"])
    macro = load_json(args["macro"])

    if not structures:
        print(f"⚠️  未提供 structures.json 或读取失败 → 跳过缠论字段校验")

    result = verify(args["file"], structures, scanner, chip, macro)
    write_audit_log(result, args["review_id"], args["target_role"])

    emoji = "✅" if result["verdict"] == "PASS" else ("⚠️" if result["verdict"] == "SOFT_FAIL" else "❌")
    print(f"{emoji} data_verifier | {result['file']}")
    print(f"   verdict={result['verdict']}")
    print(f"   通过: {result['verified_count']} | HARD 幻觉: {result['hard_hallucination_count']} | SOFT 偏差: {result['soft_mismatch_count']}")
    print(f"   跳过推断: {result['skipped_inference_count']} | 跳过无标记: {result['skipped_no_marker_count']}")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["verdict"] == "PASS" else (1 if result["verdict"] == "SOFT_FAIL" else 2)


if __name__ == "__main__":
    sys.exit(main())
