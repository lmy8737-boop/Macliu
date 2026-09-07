"""
持仓表导入器 - 通用版（脱敏，无任何用户特定信息）

支持来源：
1. CSV/Excel/JSON 本地文件
2. 腾讯文档智能表（通过 Chrome CDP 自动导出 xlsx）
3. 用户手动粘贴

支持目标：
- 本地 SQLite（默认）
- 远程 MySQL（通过环境变量配置）

环境变量：
  INVESTMENT_TEAM_DB        SQLite 路径（默认 ./engine/data/trading.db）
  HOLDINGS_MYSQL_HOST       MySQL 地址（可选，启用 MySQL 模式）
  HOLDINGS_MYSQL_PORT       端口
  HOLDINGS_MYSQL_USER       用户
  HOLDINGS_MYSQL_PASSWORD   密码
  HOLDINGS_MYSQL_DATABASE   库名（默认 quantitative）

使用：
  # SQLite 模式
  python3 import_holdings.py -i holdings.csv

  # MySQL 模式
  export HOLDINGS_MYSQL_HOST=...
  export HOLDINGS_MYSQL_USER=...
  export HOLDINGS_MYSQL_PASSWORD=...
  python3 import_holdings.py -i holdings.csv --target mysql
"""
import argparse
import csv
import json
import os
import sqlite3
import sys
from datetime import date
from pathlib import Path


# -------- 字段映射（兼容多种列名写法）--------
ALIASES = {
    "ticker":        ["ticker", "code", "代码", "股票代码", "证券代码"],
    "name":          ["name", "名称", "股票名称", "证券名称", "投资品种"],
    "market":        ["market", "市场", "板块"],
    "industry":      ["industry", "sector", "行业"],
    "weight_pct":    ["weight", "weight_pct", "仓位", "占比", "比例"],
    "quantity":      ["quantity", "qty", "shares", "数量", "持股数", "持仓数量"],
    "cost_price":    ["cost", "cost_price", "成本", "成本价"],
    "current_price": ["price", "current_price", "现价", "最新价", "收盘价", "单价"],
    "market_value":  ["value", "market_value", "市值"],
    "profit_pct":    ["profit", "profit_pct", "盈亏", "盈亏率", "浮动盈亏"],
    "fx_rate":       ["fx_rate", "汇率"],
    "snapshot_date": ["date", "snapshot_date", "日期"],
}


def parse_pct(value):
    """6% / 6.5 / 0.065 → 6.50（百分比）"""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        f = float(value)
        return f if abs(f) > 1 else f * 100
    s = str(value).strip().replace("%", "").replace("，", "").replace(",", "")
    if not s:
        return None
    try:
        f = float(s)
        return f if abs(f) > 1 else f * 100
    except ValueError:
        return None


def parse_decimal(value):
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace("，", "").replace(",", "").replace("¥", "").replace("$", "").replace("￥", "")
    try:
        return float(s)
    except ValueError:
        return None


def load_holdings(filepath):
    p = Path(filepath)
    if not p.exists():
        raise FileNotFoundError(f"持仓表不存在: {filepath}")
    
    suffix = p.suffix.lower()
    if suffix == ".json":
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    elif suffix == ".csv":
        with open(p, encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    elif suffix in (".xlsx", ".xls"):
        try:
            import pandas as pd
        except ImportError:
            print("❌ 需要 pandas 读取 Excel: pip install pandas openpyxl")
            sys.exit(1)
        df = pd.read_excel(p)
        return [{k: (v if pd.notna(v) else None) for k, v in row.items()}
                for row in df.to_dict(orient="records")]
    else:
        raise ValueError(f"不支持的格式: {suffix}")


def normalize_record(row):
    def pick(field):
        for k in ALIASES.get(field, [field]):
            if k in row and row[k] is not None and str(row[k]).strip() != "":
                return row[k]
        return None
    
    name = str(pick("name") or "").strip()
    ticker = str(pick("ticker") or name).strip().upper()
    if not ticker and not name:
        return None
    
    return {
        "ticker": ticker,
        "name": name,
        "market": (str(pick("market") or "A").strip().upper())[:8],
        "industry": str(pick("industry") or "未分类").strip(),
        "weight_pct": parse_pct(pick("weight_pct")),
        "quantity": parse_decimal(pick("quantity")),
        "cost_price": parse_decimal(pick("cost_price")),
        "current_price": parse_decimal(pick("current_price")),
        "market_value": parse_decimal(pick("market_value")),
        "profit_pct": parse_pct(pick("profit_pct")),
    }


def check_risk_limits(holdings):
    """风控红线校验（可调阈值）"""
    SINGLE_TICKER_MAX = 7
    SINGLE_INDUSTRY_MAX = 25
    TOTAL_POSITION_MAX = 80
    
    warnings = []
    industry_total = {}
    total = 0
    
    for h in holdings:
        if h["weight_pct"] is None:
            continue
        w = h["weight_pct"]
        if w > SINGLE_TICKER_MAX:
            warnings.append(f"🚨 RED-1: {h['ticker']} 仓位 {w:.2f}% > {SINGLE_TICKER_MAX}%")
        total += w
        ind = h["industry"]
        industry_total[ind] = industry_total.get(ind, 0) + w
    
    for ind, w in industry_total.items():
        if w > SINGLE_INDUSTRY_MAX:
            warnings.append(f"🚨 RED-2: 行业 [{ind}] {w:.2f}% > {SINGLE_INDUSTRY_MAX}%")
    
    if total > TOTAL_POSITION_MAX:
        warnings.append(f"🚨 RED-3: 总仓位 {total:.2f}% > {TOTAL_POSITION_MAX}%")
    
    return total, industry_total, warnings


# -------- 写入 SQLite --------
def save_to_sqlite(holdings, snap_date):
    db_path = Path(os.environ.get(
        "INVESTMENT_TEAM_DB",
        Path.cwd() / "engine" / "data" / "trading.db"
    ))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM holdings_snapshot WHERE snapshot_date = ?", (snap_date,))
    for h in holdings:
        if h["weight_pct"] is None:
            continue
        conn.execute("""
            INSERT INTO holdings_snapshot 
            (snapshot_date, ticker, market, weight_pct, cost_price, current_price, profit_pct, industry)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (snap_date, h["ticker"], h["market"], h["weight_pct"],
              h["cost_price"], h["current_price"], h["profit_pct"], h["industry"]))
    conn.commit()
    conn.close()
    return db_path


# -------- 写入 MySQL（可选）--------
def save_to_mysql(holdings, snap_date, source="manual", source_url=None):
    try:
        import pymysql
        from pymysql.cursors import DictCursor
    except ImportError:
        print("❌ 需要 pymysql: pip install pymysql cryptography")
        sys.exit(1)
    
    cfg = {
        "host": os.environ.get("HOLDINGS_MYSQL_HOST"),
        "port": int(os.environ.get("HOLDINGS_MYSQL_PORT", 3306)),
        "user": os.environ.get("HOLDINGS_MYSQL_USER"),
        "password": os.environ.get("HOLDINGS_MYSQL_PASSWORD"),
        "database": os.environ.get("HOLDINGS_MYSQL_DATABASE", "quantitative"),
        "charset": "utf8mb4",
    }
    if not all([cfg["host"], cfg["user"], cfg["password"]]):
        print("❌ 需要环境变量 HOLDINGS_MYSQL_HOST/USER/PASSWORD")
        sys.exit(1)
    
    conn = pymysql.connect(**cfg)
    cur = conn.cursor()
    
    # 先建表（幂等）
    cur.execute("""
        CREATE TABLE IF NOT EXISTS holdings_daily (
            id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
            snapshot_date DATE NOT NULL,
            ticker VARCHAR(32) NOT NULL,
            name VARCHAR(64) DEFAULT '',
            market VARCHAR(8) DEFAULT 'A',
            industry VARCHAR(64) DEFAULT '未分类',
            weight_pct DECIMAL(8,4),
            quantity DECIMAL(20,4),
            cost_price DECIMAL(20,4),
            current_price DECIMAL(20,4),
            market_value DECIMAL(20,4),
            profit_pct DECIMAL(10,4),
            source VARCHAR(32) DEFAULT 'manual',
            source_url VARCHAR(512),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uk_date_ticker (snapshot_date, ticker)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)
    
    upsert = """
        INSERT INTO holdings_daily 
        (snapshot_date, ticker, name, market, industry, weight_pct, quantity,
         cost_price, current_price, market_value, profit_pct, source, source_url)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
            name=VALUES(name), market=VALUES(market), industry=VALUES(industry),
            weight_pct=VALUES(weight_pct), quantity=VALUES(quantity),
            cost_price=VALUES(cost_price), current_price=VALUES(current_price),
            market_value=VALUES(market_value), profit_pct=VALUES(profit_pct),
            source=VALUES(source), source_url=VALUES(source_url),
            updated_at=CURRENT_TIMESTAMP
    """
    
    inserted = updated = skipped = 0
    for h in holdings:
        if h["weight_pct"] is None:
            skipped += 1
            continue
        cur.execute(upsert, (
            snap_date, h["ticker"], h["name"], h["market"], h["industry"],
            h["weight_pct"], h["quantity"], h["cost_price"],
            h["current_price"], h["market_value"], h["profit_pct"],
            source, source_url,
        ))
        if cur.rowcount == 1:
            inserted += 1
        elif cur.rowcount == 2:
            updated += 1
    
    conn.commit()
    conn.close()
    return {"inserted": inserted, "updated": updated, "skipped": skipped}


def export_context_json(holdings, total_weight, industry_total, warnings, snap_date):
    """生成给 5/6号 Context 注入的极简 JSON"""
    out_dir = Path(os.environ.get(
        "INVESTMENT_TEAM_DATA_DIR",
        Path.cwd() / "engine" / "data"
    )) / "holdings"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    minimal = [
        {
            "ticker": h["ticker"], "name": h.get("name"),
            "market": h["market"],
            "weight": f"{h['weight_pct']:.2f}%" if h["weight_pct"] else None,
            "cost": h["cost_price"],
            "profit": f"{h['profit_pct']:+.2f}%" if h["profit_pct"] else None,
            "industry": h["industry"],
        }
        for h in holdings if h["weight_pct"] is not None
    ]
    
    context = {
        "snapshot_date": snap_date,
        "total_weight": f"{total_weight:.2f}%",
        "cash_pct": f"{max(0, 100-total_weight):.2f}%",
        "industry_concentration": {k: f"{v:.2f}%" for k, v in industry_total.items()},
        "risk_warnings": warnings,
        "holdings": minimal,
    }
    
    out_file = out_dir / f"holdings_{snap_date}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(context, f, ensure_ascii=False, indent=2)
    
    latest = out_dir / "holdings_latest.json"
    if latest.exists():
        latest.unlink()
    with open(latest, "w", encoding="utf-8") as f:
        json.dump(context, f, ensure_ascii=False, indent=2)
    
    return out_file


def main():
    parser = argparse.ArgumentParser(description="持仓表导入器")
    parser.add_argument("-i", "--input", required=True, help="持仓文件路径（csv/xlsx/json）")
    parser.add_argument("-d", "--date", default=None, help="快照日期（默认今天）")
    parser.add_argument("--target", choices=["sqlite", "mysql", "both"], default="sqlite",
                        help="存储目标")
    parser.add_argument("--source", default="manual", help="数据来源标记")
    parser.add_argument("--source-url", default=None, help="原始文档URL")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    
    snap_date = args.date or date.today().isoformat()
    
    print(f"📂 读取: {args.input}")
    raw = load_holdings(args.input)
    holdings = [normalize_record(r) for r in raw]
    holdings = [h for h in holdings if h is not None]
    print(f"✅ 解析 {len(holdings)} 条")
    
    total_weight, industry_total, warnings = check_risk_limits(holdings)
    print(f"\n📊 总仓位: {total_weight:.2f}%")
    print("🏭 行业集中度:")
    for ind, w in sorted(industry_total.items(), key=lambda x: -x[1]):
        print(f"   {ind}: {w:.2f}%")
    
    if warnings:
        print(f"\n🚨 风控告警 {len(warnings)} 条:")
        for w in warnings:
            print(f"   {w}")
    else:
        print("\n✅ 风控全部通过")
    
    if args.dry_run:
        print("\n🧪 DRY RUN")
        return
    
    if args.target in ("sqlite", "both"):
        db_path = save_to_sqlite(holdings, snap_date)
        print(f"\n💾 SQLite: {db_path}")
    
    if args.target in ("mysql", "both"):
        result = save_to_mysql(holdings, snap_date, args.source, args.source_url)
        print(f"\n💾 MySQL: inserted={result['inserted']} updated={result['updated']}")
    
    out_file = export_context_json(holdings, total_weight, industry_total, warnings, snap_date)
    print(f"💾 Context JSON: {out_file}")


if __name__ == "__main__":
    main()
