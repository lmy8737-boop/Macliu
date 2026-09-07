# 适配形态: agent + bot
"""
v6.2 数据采集层 (scripts/data/)
==============================
v6.2 新增：把 mattermost-bot/scripts/real_data_collector.py 内嵌的
数据采集逻辑剥离到这里，让 skill agent 形态和 mattermost-bot 形态共用。

模块划分：
  - kline_fetcher.py    K 线（akshare + 雪球 fallback）  [agent + bot 共用]
  - finance_fetcher.py  财务指标                          [agent + bot 共用]
  - scanner_fetcher.py  全市场扫描                        [仅 portfolio mode 用]
  - chip_fetcher.py     ETF 国家队筹码                    [仅 portfolio mode 用]
  - holdings_loader.py  持仓快照                          [agent + bot 共用]
  - macro_fetcher.py    宏观指标                          [agent + bot 共用]
  - structures_engine.py 把 K 线喂给 chanlun.py 产 structures.json [agent + bot 共用]

调用入口：
  agent 形态 → scripts/cli/prepare_data.py（一行命令拉数据）
  bot 形态  → mattermost-bot/scripts/real_data_collector.py（薄封装，内部 import 此处）
"""

from .common import (
    DataCollectionError,
    SKILL_HOME,
    DATA_DIR,
    patch_requests_user_agent,
    import_akshare,
    import_pandas,
    call_with_retry,
)
from .kline_fetcher import hist_kline_with_fallback, xueqiu_hist

__all__ = [
    "DataCollectionError",
    "SKILL_HOME",
    "DATA_DIR",
    "patch_requests_user_agent",
    "import_akshare",
    "import_pandas",
    "call_with_retry",
    "hist_kline_with_fallback",
    "xueqiu_hist",
]
