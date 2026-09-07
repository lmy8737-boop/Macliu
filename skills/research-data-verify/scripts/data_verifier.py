#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
data_verifier.py
────────────────────────────────────────────────────────────────
Multi-source data verification helper for financial research reports.

Usage (in report scripts):
    from data_verifier import DataVerifier, DataPoint, VerifyStatus

    dv = DataVerifier("卓越商企服务", "06989.HK")
    dv.add("revenue_2024",  "2024年营收",   [42.32, 42.3, 42.32], "亿元RMB",
           sources=["港交所年报", "新浪财经", "观点网"])
    dv.add("dividend_2024", "2024全年派息", [0.139, 0.1394],      "HKD/股",
           sources=["年报公告", "智通财经"])
    dv.add("stock_high",    "52W高点",      [61.45],              "HKD",
           sources=["Yahoo Finance"],
           note="2025-06-27, 需补充第二来源")

    print(dv.summary_table())
    dv.assert_no_conflicts()   # raises if any ❌ Conflicting items found
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional
import statistics
import sys
import os
import re
import unicodedata


class VerifyStatus(Enum):
    VERIFIED     = "✅ Verified"      # ≥2 independent, same-caliber sources; spread ≤2%
    SINGLE_SRC   = "⚠️  Single Source"  # only 1 source
    CONFLICTING  = "❌ Conflicting"   # same-caliber sources disagree >2%
    ESTIMATE     = "[E] Estimate"     # analyst forecast, not reported
    UNAVAILABLE  = "🚫 Unavailable"   # no source found


@dataclass
class DataPoint:
    key:       str
    label:     str
    values:    List[float]   # raw numbers from each source
    unit:      str
    sources:   List[str]
    is_estimate: bool = False
    note:      str = ""
    source_aliases: Dict[str, str] = field(default_factory=dict)
    source_metrics: List[str] = field(default_factory=list)
    source_units: List[str] = field(default_factory=list)

    @staticmethod
    def _normalize_source_name(source: str) -> str:
        """Normalize superficial source-name differences without guessing ownership."""
        text = unicodedata.normalize("NFKC", str(source or "")).strip().casefold()
        return re.sub(r"[^\w]+", "", text, flags=re.UNICODE)

    def _canonical_source_name(self, source: str) -> str:
        normalized = self._normalize_source_name(source)
        if not normalized:
            return ""

        aliases = {}
        for alias, canonical in (self.source_aliases or {}).items():
            alias_key = self._normalize_source_name(alias)
            canonical_key = self._normalize_source_name(canonical)
            if alias_key:
                aliases[alias_key] = canonical_key or alias_key
        return aliases.get(normalized, normalized)

    def _independent_values(self) -> Optional[List[float]]:
        """Return one median value per independent source, or None if provenance is invalid."""
        sources = self.sources or []
        if len(sources) != len(self.values):
            return None

        canonical_sources = [self._canonical_source_name(source) for source in sources]
        if not canonical_sources or any(not source for source in canonical_sources):
            return None

        grouped_values: Dict[str, List[float]] = {}
        for source, value in zip(canonical_sources, self.values):
            grouped_values.setdefault(source, []).append(value)
        return [statistics.median(values) for values in grouped_values.values()]

    @property
    def independent_source_count(self) -> int:
        values = self._independent_values()
        return len(values) if values is not None else 0

    @property
    def has_metric_unit_compatibility(self) -> bool:
        """Reject missing or internally contradictory metric/unit metadata."""
        if not all(str(value or "").strip() for value in (self.key, self.label, self.unit)):
            return False

        # Catch obvious key/label contradictions without requiring a breaking
        # change to the legacy API, whose keys and labels use mixed languages.
        families = {
            "revenue": {"revenue", "sales", "营收", "收入", "营业收入"},
            "profit": {"profit", "netprofit", "np", "净利润", "归母净利润"},
            "eps": {"eps", "每股收益", "每股盈利"},
            "margin": {"margin", "grossmargin", "毛利率", "净利率"},
            "assets": {"assets", "资产"},
            "cashflow": {"cashflow", "经营现金流", "自由现金流", "ocf", "fcf"},
        }

        def family(value: str) -> Optional[str]:
            normalized = self._normalize_source_name(value)
            for name, aliases in families.items():
                for alias in aliases:
                    token = self._normalize_source_name(alias)
                    if token and (normalized == token or token in normalized):
                        return name
            return None

        key_family, label_family = family(self.key), family(self.label)
        if key_family and label_family and key_family != label_family:
            return False

        if self.source_metrics:
            if len(self.source_metrics) != len(self.values):
                return False
            metrics = [self._normalize_source_name(x) for x in self.source_metrics]
            if not all(metrics) or len(set(metrics)) != 1:
                return False
        if self.source_units:
            if len(self.source_units) != len(self.values):
                return False
            units = [self._normalize_source_name(x) for x in self.source_units]
            if not all(units) or len(set(units)) != 1:
                return False
        return True

    @property
    def status(self) -> VerifyStatus:
        if self.is_estimate:
            return VerifyStatus.ESTIMATE
        if not self.values:
            return VerifyStatus.UNAVAILABLE

        independent_values = self._independent_values()
        if (
            independent_values is None
            or len(independent_values) < 2
            or not self.has_metric_unit_compatibility
        ):
            return VerifyStatus.SINGLE_SRC

        median = statistics.median(independent_values)
        scale = abs(median)
        if scale == 0:
            return (VerifyStatus.VERIFIED
                    if max(independent_values) == min(independent_values) == 0
                    else VerifyStatus.CONFLICTING)
        relative_spread = (max(independent_values) - min(independent_values)) / scale
        if relative_spread <= 0.02:
            return VerifyStatus.VERIFIED
        return VerifyStatus.CONFLICTING

    @property
    def consensus_value(self) -> Optional[float]:
        """Return median of verified values, None if unavailable."""
        if not self.values:
            return None
        return statistics.median(self.values)

    @property
    def value_str(self) -> str:
        if not self.values:
            return "N/A"
        if self.status == VerifyStatus.CONFLICTING:
            lo, hi = min(self.values), max(self.values)
            return f"{lo}-{hi} {self.unit} ⚠"
        v = self.consensus_value
        # Format nicely
        if abs(v) >= 100:
            return f"{v:.1f} {self.unit}"
        elif abs(v) >= 10:
            return f"{v:.2f} {self.unit}"
        else:
            return f"{v:.3f} {self.unit}"


class DataVerifier:
    """
    Collects data points, classifies them, and generates a verification report.
    Designed to run as a mandatory pre-step before writing any research report.
    """

    BANNER_WIDTH = 72

    def __init__(self, company_name: str, ticker: str = ""):
        self.company = company_name
        self.ticker  = ticker
        self.points: dict[str, DataPoint] = {}

    def add(
        self,
        key:          str,
        label:        str,
        values:       List[float],
        unit:         str          = "",
        sources:      List[str]    = None,
        is_estimate:  bool         = False,
        note:         str          = "",
        source_aliases: Dict[str, str] = None,
        source_metrics: List[str] = None,
        source_units:   List[str] = None,
    ) -> "DataVerifier":
        """Register a data point; source_aliases maps known aliases to one source ID."""
        self.points[key] = DataPoint(
            key=key, label=label, values=values, unit=unit,
            sources=sources or [], is_estimate=is_estimate, note=note,
            source_aliases=source_aliases or {},
            source_metrics=source_metrics or [], source_units=source_units or [],
        )
        return self

    def get(self, key: str) -> Optional[float]:
        """Return the consensus value for a verified data point."""
        dp = self.points.get(key)
        if dp is None:
            raise KeyError(f"Data point '{key}' not registered in verifier")
        if dp.status in (VerifyStatus.UNAVAILABLE, VerifyStatus.CONFLICTING):
            return None
        return dp.consensus_value

    def status(self, key: str) -> VerifyStatus:
        dp = self.points.get(key)
        if dp is None:
            return VerifyStatus.UNAVAILABLE
        return dp.status

    # ──────────────── reporting ────────────────

    def summary_table(self, width: int = None) -> str:
        """Generate a plain-text verification summary table."""
        W = width or self.BANNER_WIDTH
        lines = []
        lines.append("═" * W)
        lines.append(f"  DATA VERIFICATION — {self.company} {self.ticker}")
        lines.append("═" * W)
        col = f"  {'Data Point':<30} {'Value':<20} {'Status':<22} {'Src':<4} {'Notes'}"
        lines.append(col)
        lines.append("─" * W)

        counts = {s: 0 for s in VerifyStatus}
        for dp in self.points.values():
            s = dp.status
            counts[s] += 1
            src_n  = str(dp.independent_source_count)
            note   = dp.note or (", ".join(dp.sources) if len(dp.sources) <= 2 else
                                  f"{dp.sources[0]}, ... +{len(dp.sources)-1}")
            lines.append(
                f"  {dp.label:<30} {dp.value_str:<20} {s.value:<22} {src_n:<4} {note}"
            )

        lines.append("─" * W)
        total = len(self.points)
        verified  = counts[VerifyStatus.VERIFIED]
        conflicts = counts[VerifyStatus.CONFLICTING]
        single    = counts[VerifyStatus.SINGLE_SRC]
        estimates = counts[VerifyStatus.ESTIMATE]
        unavail   = counts[VerifyStatus.UNAVAILABLE]

        lines.append(f"  Total: {total}  ✅ {verified}  ⚠️ {single}  ❌ {conflicts}"
                     f"  [E] {estimates}  🚫 {unavail}")
        lines.append("═" * W)
        return "\n".join(lines)

    def conflicts(self) -> List[DataPoint]:
        return [dp for dp in self.points.values()
                if dp.status == VerifyStatus.CONFLICTING]

    def single_source_items(self) -> List[DataPoint]:
        return [dp for dp in self.points.values()
                if dp.status == VerifyStatus.SINGLE_SRC]

    def assert_no_conflicts(self):
        """
        Raise ValueError listing all ❌ Conflicting items.
        Call this before report generation to enforce data integrity.
        """
        bad = self.conflicts()
        if bad:
            msg = "DATA CONFLICTS detected — resolve before writing report:\n"
            for dp in bad:
                msg += f"  • {dp.label}: values {dp.values} {dp.unit}\n"
                msg += f"    Sources: {dp.sources}\n"
            raise ValueError(msg)

    def report_block(self) -> str:
        """
        Return a formatted block suitable for embedding in a research report
        as a data-integrity footnote or appendix.
        """
        lines = [
            "【数据核查说明】",
            f"本报告数据来源经多源交叉核验，核查标准：",
            "  ✅ 已验证 = ≥2个独立、同口径来源数值差异≤2%",
            "  ⚠️  单一来源 = 仅1个来源，需谨慎参考",
            "  ❌ 数据冲突 = 同口径多源差异>2%，已在正文注明",
            "  [E] = 分析师预估/预测，非实际已披露数据",
            "",
        ]
        for dp in self.points.values():
            if dp.status != VerifyStatus.VERIFIED:
                lines.append(f"  {dp.status.value} | {dp.label}: {dp.value_str}"
                              + (f" — {dp.note}" if dp.note else ""))
        return "\n".join(lines)


# ──────────────── CLI convenience ────────────────

def demo():
    """Quick demo showing how to use DataVerifier."""
    dv = DataVerifier("卓越商企服务", "06989.HK")

    # Revenue — 3 consistent sources → ✅
    dv.add("revenue_2024", "2024年营收", [42.32, 42.3, 42.32], "亿元",
           sources=["港交所年报2024", "新浪财经", "观点网"])

    # Net profit — 2 sources, slightly different rounding → ✅
    dv.add("np_2024", "2024归母净利润", [3.12, 3.12], "亿元",
           sources=["港交所年报2024", "智通财经"])

    # DPS — 2 sources agree → ✅
    dv.add("dps_2024", "2024每股派息", [0.1394, 0.139], "HKD",
           sources=["年报公告", "investing.com"])

    # Operating cash flow — 2 sources conflict → ❌
    dv.add("ocf_2024", "2024经营现金流", [-5.55, -4.80], "亿元",
           sources=["观点网", "东方财富"],
           note="需回归年报原文核实")

    # Stock 52W high — single source → ⚠️
    dv.add("high_52w", "52周高点", [1.98], "HKD",
           sources=["Yahoo Finance 2025-04"],
           note="需补充第二来源确认")

    # Q1 2025 forecast — estimate → [E]
    dv.add("rev_q1_2025", "2025Q1营收预测", [19.5], "亿元",
           sources=["兴业证券2025-03"],
           is_estimate=True)

    print(dv.summary_table())
    print()
    print(dv.report_block())

    # Example: how to safely get a value in report code
    rev = dv.get("revenue_2024")
    print(f"\n→ 报告中使用的2024营收: {rev}亿元 (status: {dv.status('revenue_2024').value})")

    # Show what happens when conflicts exist
    try:
        dv.assert_no_conflicts()
    except ValueError as e:
        print(f"\n→ 报告生成被阻止:\n{e}")


def self_test() -> int:
    """Offline, anonymized regression checks for source-independence rules."""
    cases = {
        "independent sources": (
            DataPoint("metric_a", "Metric A", [100.0, 100.0], "unit",
                      ["Provider Alpha", "Provider Beta"]),
            VerifyStatus.VERIFIED,
        ),
        "duplicate source": (
            DataPoint("metric_a", "Metric A", [100.0, 100.0], "unit",
                      ["Provider Alpha", "Provider Alpha"]),
            VerifyStatus.SINGLE_SRC,
        ),
        "source aliases": (
            DataPoint("metric_a", "Metric A", [100.0, 100.0], "unit",
                      ["Provider Alpha", "Alpha Data"],
                      source_aliases={
                          "Provider Alpha": "provider-alpha",
                          "Alpha Data": "provider-alpha",
                      }),
            VerifyStatus.SINGLE_SRC,
        ),
        "value/source count mismatch": (
            DataPoint("metric_a", "Metric A", [100.0, 100.0], "unit",
                      ["Provider Alpha"]),
            VerifyStatus.SINGLE_SRC,
        ),
        "same caliber within two percent": (
            DataPoint("metric_a", "Metric A", [100.0, 101.9], "unit",
                      ["Provider Alpha", "Provider Beta"]),
            VerifyStatus.VERIFIED,
        ),
        "missing source": (
            DataPoint("metric_a", "Metric A", [100.0, 100.0], "unit", ["", ""]),
            VerifyStatus.SINGLE_SRC,
        ),
        "missing unit compatibility": (
            DataPoint("metric_a", "Metric A", [100.0, 100.0], "",
                      ["Provider Alpha", "Provider Beta"]),
            VerifyStatus.SINGLE_SRC,
        ),
        "contradictory metric labels": (
            DataPoint("revenue", "EPS", [100.0, 100.0], "unit",
                      ["Provider Alpha", "Provider Beta"]),
            VerifyStatus.SINGLE_SRC,
        ),
        "contradictory decorated metric labels": (
            DataPoint("revenue_2024", "2024 EPS", [100.0, 100.0], "unit",
                      ["Provider Alpha", "Provider Beta"]),
            VerifyStatus.SINGLE_SRC,
        ),
        "source metric mismatch": (
            DataPoint("metric_a", "Metric A", [100.0, 100.0], "unit",
                      ["Provider Alpha", "Provider Beta"],
                      source_metrics=["revenue", "eps"]),
            VerifyStatus.SINGLE_SRC,
        ),
    }

    failures = []
    for name, (point, expected) in cases.items():
        actual = point.status
        if actual is not expected:
            failures.append(f"{name}: expected {expected.name}, got {actual.name}")

    if failures:
        print("self-test failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print(f"self-test passed: {len(cases)} cases")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    demo()
