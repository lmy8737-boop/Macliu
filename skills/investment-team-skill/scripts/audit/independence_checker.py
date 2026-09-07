"""
independence_checker.py — v4.7 反偷懒抄袭/橡皮图章检测（A3）

关键设计（与原始协议的改进）：
  1. 1↔2 检测：从 2 号 Watchlist 表 "催化剂" 列文本，与 1 号 "地缘风险/宏观预警" 两节做
     Jaccard 相似度（中文分词后），>0.6 判 COPYING
  2. 2↔4 检测：独立性 = (4 号 ticker ∉ 2 号 Watchlist 集) ∨ (对 2 号 ticker 给出 EXIT/观望)
     两者皆无 → FAIL（不再用 "全 LONG" 简单误判）
  3. 行业重合度：从 1 号 "建议超配" 段抽取行业，从 2 号 Top 3 行业表抽取，重合 100% +
     2 号无新数据点 → COPYING（保留原协议规则）

CLI:
  python independence_checker.py \
      --macro 01_周期与配置.md \
      --industry 02_Watchlist.md \
      --trader 04_信号.md \
      --signals 04_signals.json \
      [--review-id N]
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

# 阈值
JACCARD_THRESHOLD = 0.6
INDUSTRY_OVERLAP_THRESHOLD = 1.0  # 100% 重合才判抄袭

# 中文常见停用词（简化版，避免 Jaccard 被噪音拉高）
CN_STOPWORDS = {
    "的", "是", "在", "了", "和", "与", "及", "等",
    "或", "但", "也", "都", "及其", "而", "为", "以",
    "对", "从", "到", "由", "因", "由于", "至",
    "之", "其", "此", "本", "该", "我", "我们",
    "可", "可以", "需要", "应当", "应该", "或将",
    "市场", "行业", "经济", "政策", "影响", "发展",
    "增长", "上涨", "下跌", "目前", "近期", "短期",
}

# 行业关键词（用于从 1 号文中抽取超配建议）
INDUSTRY_KEYWORDS = [
    "AI算力", "光通信", "CPO", "半导体", "新能源", "光伏", "锂电", "风电",
    "机器人", "人工智能", "云计算", "数据中心", "5G", "6G", "通信",
    "医药", "创新药", "CXO", "医疗器械", "医疗服务",
    "消费", "白酒", "免税", "家电", "汽车", "新能源车", "智能驾驶",
    "金融", "银行", "证券", "保险", "地产",
    "军工", "国防", "航空航天", "卫星",
    "化工", "有色", "钢铁", "煤炭", "石油石化",
    "传媒", "游戏", "影视", "出版",
    "农业", "种业", "养殖",
]


def tokenize_cn(text: str) -> set:
    """简易中文 token 化：2-4 字滑窗 + 数字 + 英文词，去停用词"""
    text = re.sub(r'[，。、；：！？\(\)（）【】\[\]"""''《》<>\-—\s]+', ' ', text)
    tokens = set()
    # 英文 / 数字 / 行业名（≥2 字符）
    for m in re.finditer(r'[A-Za-z]{2,}|\d+(?:\.\d+)?[%a-zA-Z]?', text):
        tokens.add(m.group().lower())
    # 中文 2-4 字 n-gram
    cn_only = re.sub(r'[A-Za-z0-9]+', ' ', text)
    for chunk in cn_only.split():
        for n in (2, 3, 4):
            for i in range(len(chunk) - n + 1):
                tk = chunk[i:i + n]
                if tk not in CN_STOPWORDS and len(tk) >= 2:
                    tokens.add(tk)
    return tokens


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def extract_section(md: str, section_keywords: list) -> str:
    """提取 Markdown 中匹配关键词的小节正文"""
    lines = md.split("\n")
    result = []
    capture = False
    for line in lines:
        if line.startswith("#"):
            if capture:
                # 遇下一个标题且非更深层级 → 停
                if line.startswith("# ") or line.startswith("## "):
                    capture = False
            if any(kw in line for kw in section_keywords):
                capture = True
                continue
        if capture:
            result.append(line)
    return "\n".join(result)


def extract_industries_from_macro(macro_md: str) -> set:
    """从 1 号文中抽取 '建议超配' 的行业关键词"""
    target_text = extract_section(macro_md, ["建议超配", "超配", "权重表", "跨资产配置"])
    if not target_text:
        target_text = macro_md  # fallback
    found = set()
    for kw in INDUSTRY_KEYWORDS:
        if kw in target_text:
            found.add(kw)
    return found


def extract_industries_from_industry(industry_md: str) -> set:
    """从 2 号文 'Top 3 / 高优行业' 段抽取行业"""
    target_text = extract_section(industry_md, ["Top 3", "高优行业", "A2", "推荐行业"])
    if not target_text:
        target_text = industry_md
    found = set()
    for kw in INDUSTRY_KEYWORDS:
        if kw in target_text:
            found.add(kw)
    return found


def extract_watchlist_catalysts(industry_md: str) -> str:
    """从 2 号 Watchlist 表的 '催化剂' 列提取所有文本"""
    # 查找含 "催化剂" 的表格行
    target_text = extract_section(industry_md, ["Watchlist", "新发现", "A3"])
    if not target_text:
        target_text = industry_md
    # 简单按行读，含 | 且不是表头分隔行
    catalyst_texts = []
    for line in target_text.split("\n"):
        if "|" not in line:
            continue
        if re.match(r'^\s*\|[\s\-:|]+\|\s*$', line):
            continue
        # 取最后几列（催化剂通常在右侧）
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) >= 3:
            catalyst_texts.extend(cells[-3:])
    return " ".join(catalyst_texts)


def extract_macro_narrative(macro_md: str) -> str:
    """从 1 号文 '地缘风险/宏观预警' 段抽取叙事"""
    sections = extract_section(macro_md, ["地缘风险", "宏观预警", "宏观风险", "核心结论"])
    return sections or macro_md[:3000]


def extract_watchlist_tickers(industry_md: str) -> set:
    """从 2 号 Watchlist 提取 ticker 集合"""
    tickers = set()
    # 常见 ticker 模式：sh510300 / hk03033 / usNVDA.OQ / 002837 / NVDA
    for m in re.finditer(r'\b(?:sh|sz|hk|us)?[A-Z]{0,4}\d{4,6}(?:\.[A-Z]{1,3})?\b|\b[A-Z]{2,5}\b', industry_md):
        tk = m.group().upper()
        # 过滤表头噪音
        if tk in {"PE", "PB", "ETF", "AI", "API", "JSON", "CPO", "Q1", "Q2", "Q3", "Q4", "FAIL", "PASS",
                  "TOP", "SOFT", "HARD", "BUY", "SELL", "EXIT", "LONG", "SHORT", "HOLD", "MD", "HSI"}:
            continue
        # 必须含数字（A股/港股代码）或 长度 >=3 全大写英文
        if re.search(r'\d{4,}', tk) or (len(tk) >= 3 and tk.isalpha()):
            tickers.add(tk)
    return tickers


def extract_signals_directions(signals_json: dict) -> dict:
    """从 04_signals.json 提取 {ticker: direction}"""
    result = {}
    sigs = signals_json.get("signals", []) if isinstance(signals_json, dict) else signals_json
    if not isinstance(sigs, list):
        return result
    for s in sigs:
        tk = s.get("ticker", "").upper()
        direction = s.get("direction", "").upper()
        if tk and direction:
            result[tk] = direction
    return result


def check(macro_md: str, industry_md: str, trader_md: str, signals_json: dict) -> dict:
    """主检测函数"""
    findings = []

    # === 1↔2 检测：行业重合度 + 催化剂 Jaccard ===
    macro_industries = extract_industries_from_macro(macro_md)
    industry_top = extract_industries_from_industry(industry_md)
    overlap = macro_industries & industry_top
    overlap_pct = len(overlap) / len(industry_top) if industry_top else 0.0

    macro_narrative = extract_macro_narrative(macro_md)
    catalysts_text = extract_watchlist_catalysts(industry_md)
    macro_tokens = tokenize_cn(macro_narrative)
    catalyst_tokens = tokenize_cn(catalysts_text)
    similarity_12 = jaccard(macro_tokens, catalyst_tokens)

    copying_12 = False
    reason_12 = []
    if overlap_pct >= INDUSTRY_OVERLAP_THRESHOLD and len(industry_top) > 0:
        reason_12.append(f"2 号 Top {len(industry_top)} 行业 100% 复制 1 号超配（{sorted(overlap)}）")
        copying_12 = True
    if similarity_12 >= JACCARD_THRESHOLD:
        reason_12.append(f"2 号 Watchlist 催化剂 vs 1 号宏观叙事 Jaccard={similarity_12:.2f} >= {JACCARD_THRESHOLD}")
        copying_12 = True

    findings.append({
        "pair": "2_vs_1",
        "industry_overlap_pct": round(overlap_pct, 2),
        "overlap_industries": sorted(overlap),
        "macro_industries": sorted(macro_industries),
        "industry_top": sorted(industry_top),
        "catalyst_macro_jaccard": round(similarity_12, 3),
        "verdict": "FAIL" if copying_12 else "PASS",
        "reasons": reason_12,
    })

    # === 2↔4 检测：独立扩展 ∨ 独立否决 ===
    watchlist_tickers = extract_watchlist_tickers(industry_md)
    signal_dirs = extract_signals_directions(signals_json)
    signal_tickers = set(signal_dirs.keys())

    # 独立扩展：4 号有 ticker 不在 2 号 Watchlist
    independent_extension = signal_tickers - watchlist_tickers
    # 独立否决：4 号对 2 号 ticker 给出 EXIT/观望
    overlap_4_2 = signal_tickers & watchlist_tickers
    independent_veto = {tk for tk in overlap_4_2 if signal_dirs.get(tk) in ("EXIT", "观望", "WATCH", "PASS")}

    has_independence = bool(independent_extension) or bool(independent_veto)
    rubber_stamp = (not has_independence) and len(overlap_4_2) > 0

    reasons_24 = []
    if rubber_stamp:
        reasons_24.append("4 号信号全部在 2 号 Watchlist 内 + 0 个 EXIT/观望 → 橡皮图章")
    else:
        if independent_extension:
            reasons_24.append(f"独立扩展：{sorted(independent_extension)}")
        if independent_veto:
            reasons_24.append(f"独立否决：{sorted(independent_veto)}")

    findings.append({
        "pair": "4_vs_2",
        "watchlist_tickers": sorted(watchlist_tickers),
        "signal_tickers": sorted(signal_tickers),
        "signal_directions": signal_dirs,
        "independent_extension": sorted(independent_extension),
        "independent_veto": sorted(independent_veto),
        "rubber_stamp": rubber_stamp,
        "verdict": "FAIL" if rubber_stamp else "PASS",
        "reasons": reasons_24,
    })

    overall = "FAIL" if any(f["verdict"] == "FAIL" for f in findings) else "PASS"

    return {
        "findings": findings,
        "verdict": overall,
        "summary": {
            "1_vs_2_copying": copying_12,
            "4_vs_2_rubber_stamp": rubber_stamp,
        },
    }


def write_audit_log(result: dict, review_id: int = None,
                    target_role: str = "2", artifact: str = ""):
    if not DB_PATH.exists():
        return
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            INSERT INTO audit_log (review_id, script_name, target_role,
                                   target_artifact, verdict, detail_json,
                                   audit_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (review_id, "independence", target_role, artifact,
              result["verdict"], json.dumps(result, ensure_ascii=False),
              date.today().isoformat()))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️  audit_log 写入失败: {e}", file=sys.stderr)


def parse_args():
    args = {"macro": None, "industry": None, "trader": None, "signals": None,
            "review_id": None}
    rest = sys.argv[1:]
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--macro":
            args["macro"] = rest[i + 1]; i += 2
        elif a == "--industry":
            args["industry"] = rest[i + 1]; i += 2
        elif a == "--trader":
            args["trader"] = rest[i + 1]; i += 2
        elif a == "--signals":
            args["signals"] = rest[i + 1]; i += 2
        elif a == "--review-id":
            args["review_id"] = int(rest[i + 1]); i += 2
        else:
            i += 1
    return args


def main():
    args = parse_args()
    if not args["macro"] or not args["industry"]:
        print("用法: python independence_checker.py --macro 1.md --industry 2.md "
              "[--trader 4.md --signals 04_signals.json] [--review-id N]")
        sys.exit(1)

    macro_md = Path(args["macro"]).read_text(encoding="utf-8")
    industry_md = Path(args["industry"]).read_text(encoding="utf-8")
    trader_md = Path(args["trader"]).read_text(encoding="utf-8") if args["trader"] and Path(args["trader"]).exists() else ""
    signals_json = {}
    if args["signals"] and Path(args["signals"]).exists():
        try:
            signals_json = json.loads(Path(args["signals"]).read_text(encoding="utf-8"))
        except Exception:
            pass

    result = check(macro_md, industry_md, trader_md, signals_json)
    write_audit_log(result, args["review_id"], "2", args["industry"])

    emoji = "✅" if result["verdict"] == "PASS" else "❌"
    print(f"{emoji} independence_checker | verdict={result['verdict']}")
    for f in result["findings"]:
        sub_emoji = "✅" if f["verdict"] == "PASS" else "❌"
        print(f"   {sub_emoji} {f['pair']}: {f['verdict']}")
        for r in f.get("reasons", []):
            print(f"     - {r}")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["verdict"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
