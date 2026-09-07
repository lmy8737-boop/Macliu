"""
状态机路由 - 模块三核心（v4.6 增强版：含反偷懒路由逻辑）
LangGraph 简化版：基于状态码 PASS/REJECT 的强制路由

工作流：
  1/2/3/4 号产出 → 5号审核 → STATUS:PASS|REJECT
  REJECT → 自动回炉到对应节点（带5号意见）→ 重做
  连续 2 次 REJECT → 强行通过但打 [高风险未决] 标签 → 走到 6号

v4.6 新增：
  - REJECT_TYPE 解析（SHALLOW/UNVERIFIED/PERFUNCTORY_REWORK/COPYING）
  - 返工语义差异要求（rework_prompt 中嵌入 diff 要求）
  - 偷懒类型统计 + 月度熔断
  - 独立性违规的双节点回炉

外部接口：
  - run_review_pipeline(role, artifact_path) → 返回 final_status
  - parse_review_status(review_text) → ('PASS'|'REJECT', reason, reject_type)
"""
import json
import os
import re
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional

# 数据库路径优先读环境变量 INVESTMENT_TEAM_DB，fallback 到当前工作目录
DB_PATH = Path(os.environ.get(
    "INVESTMENT_TEAM_DB",
    Path.cwd() / "engine" / "data" / "trading.db"
))

MAX_RETRIES = 2  # 死循环熔断阈值
STATUS_PATTERN = re.compile(r"STATUS:\s*(PASS|REJECT)", re.IGNORECASE)
REJECT_TYPE_PATTERN = re.compile(
    r"REJECT_TYPE:\s*(SHALLOW|UNVERIFIED|PERFUNCTORY_REWORK|COPYING)",
    re.IGNORECASE,
)

# 反偷懒：月度 FORCED_PASS(偷懒类) 阈值 → 触发 Prompt 重写告警
MONTHLY_LAZINESS_THRESHOLD = 3


def parse_review_status(review_text: str):
    """
    严格提取 5号审核报告的状态码 + 偷懒类型
    返回 (status, reject_reason, reject_type)
    - reject_type: SHALLOW|UNVERIFIED|PERFUNCTORY_REWORK|COPYING|None
    """
    m = STATUS_PATTERN.search(review_text)
    if not m:
        # 没有状态码 = 视为 REJECT（5号违规未输出状态码）
        return ("REJECT", "5号未按规范输出 STATUS: PASS|REJECT 状态码", None)

    status = m.group(1).upper()
    if status == "PASS":
        return ("PASS", None, None)

    # 提取 REJECT_TYPE（v4.6 新增）
    reject_type = None
    rt_match = REJECT_TYPE_PATTERN.search(review_text)
    if rt_match:
        reject_type = rt_match.group(1).upper()

    # 提取打回意见（REJECT 后面的内容直到 ## 或文末）
    after = review_text[m.end():]
    reason_match = re.search(r"REASON:\s*(.+?)(?:\n##|\n---|$)", after, re.DOTALL)
    if reason_match:
        reason = reason_match.group(1).strip()
    else:
        # 简单截取后面 500 字
        reason = after.strip()[:500]

    return ("REJECT", reason, reject_type)


def log_review(role: str, artifact: str, status: str, reason: str = None,
               retry_count: int = 0, final_status: str = None,
               reject_type: str = None):
    """记录到 review_log（v4.6：新增 reject_type 字段）"""
    conn = sqlite3.connect(DB_PATH)
    # 确保表有 reject_type 列（兼容旧 schema）
    try:
        conn.execute("ALTER TABLE review_log ADD COLUMN reject_type TEXT")
    except sqlite3.OperationalError:
        pass  # 列已存在
    conn.execute("""
        INSERT INTO review_log (review_date, target_role, target_artifact,
                                status, reject_reason, retry_count,
                                final_status, reject_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (date.today().isoformat(), role, artifact, status, reason,
          retry_count, final_status, reject_type))
    conn.commit()
    conn.close()


def build_rework_prompt(original_artifact: str, reject_reason: str, role: str,
                        reject_type: Optional[str] = None,
                        retry_count: int = 0, remaining: int = 1):
    """
    构建回炉提示 - v4.6 增强版：按 reject_type 注入不同的强制要求
    """
    role_names = {
        "1": "1号宏观研究员",
        "2": "2号行业研究员",
        "3": "3号数据收集员",
        "4": "4号交易员",
    }

    # 基础模板
    base = f"""
[强制回炉指令 - 来自系统状态机路由]

你（{role_names.get(role, role)}）的产出 `{original_artifact}` 被 5号监工打回。

【5号打回意见】
{reject_reason}

【系统约束】
- 你已经被打回 {retry_count} 次
- 剩余重试次数：{remaining}
- 若再次 REJECT，系统将强制通过但加 [高风险未决] 标签上报老板
"""

    # v4.6：按偷懒类型注入额外强制要求
    type_requirements = _get_type_specific_requirements(reject_type, role)

    # v4.6：语义差异要求（返工稿必须明确标注修改点）
    diff_requirement = """
【v4.6 返工质量要求 — 违反将被判定"返工敷衍"再次REJECT】
1. 你必须在产出末尾添加「修改对照表」：
   | 原始意见 | 修改内容 | 修改位置 |
   |---------|---------|---------|
   | [逐条列出5号每条意见] | [你做了什么修改] | [第X段/标的XX] |
2. 每条意见必须有实质性修改（非换词/换序/加disclaimer）
3. 5号将用"首次提交标准"审核你的返工稿 — 不会因为你改了就放水
4. 禁止最小改动策略：仅修改被指出的部分是不够的，同类问题必须全部修正
"""

    return base + type_requirements + diff_requirement


def _get_type_specific_requirements(reject_type: Optional[str], role: str) -> str:
    """按 REJECT_TYPE 生成针对性强制要求"""
    if reject_type == "SHALLOW":
        return """
【反浅析强制要求】
- 所有定性判断必须附带具体数据（数值+来源+日期）
- 禁止使用以下词汇（除非紧跟具体数据）：
  "市场情绪改善"、"有望受益于"、"政策利好"、"估值合理"、
  "存在上行空间"、"近期"、"受多重因素影响"
- 必须补充至少1个逆向观点/反面论据
- 如果是1号：补充数据点至≥5个（带日期）+ 添加≥1个矛盾信号
- 如果是2号：补充个股独立催化剂 + 量化下行风险
- 如果是4号：展示从 structures.json 字段到信号的完整推导链
"""
    elif reject_type == "UNVERIFIED":
        return """
【数据核实强制要求】
- 被标记为未验证的数据项：必须标注精确来源（API名称/文件路径/URL）
- 所有数值必须附带：数据来源 + 采集日期 + 原始值
- 若数据来自3号产出：标注具体文件名和字段路径
- 若数据来自外部：标注 API 调用参数或网页 URL
- 禁止"据了解"/"据悉"/"市场传闻"等无来源表述
- 数据时效：所有引用数据距今不得超过7个交易日（历史对比除外，需标注）
"""
    elif reject_type == "PERFUNCTORY_REWORK":
        return """
【⚠️ 返工敷衍警告 — 你上次的修改被判定为敷衍】
- 你的上次修改被5号判定为"非实质性修改"
- 以下行为将再次触发"返工敷衍"判定：
  ❌ 仅增删修饰词（"较为"→"非常"）
  ❌ 仅调换段落顺序
  ❌ 仅添加 disclaimer 但不解决实质问题
  ❌ 用同样模糊的表达替换原模糊表达
- 必须做到：
  ✅ 每条意见有对应的新增数据/新增分析/新增计算
  ✅ 修改前后的具体差异可被第三方验证
  ✅ 同类问题全部修正（非仅修改被指出的单个点）
"""
    elif reject_type == "COPYING":
        independence_req = {
            "2": """
【反抄袭强制要求 — 2号必须展示独立研判】
- 你的产出被判定为"抄袭1号宏观结论"
- 必须满足以下独立性要求：
  ✅ 至少1只候选标的不在1号推荐的行业中（证明全市场扫描能力）
  ✅ 至少1个你自己发现的催化剂（非1号已提到的宏观逻辑）
  ✅ 提供1号报告中没有的新数据/新逻辑来支撑你的行业选择
  ✅ 如果行业选择与1号相同，必须有独立的微观证据（如订单/产能/客户数据）
- 禁止：直接将1号"建议超配XX行业"作为你选择该行业的唯一理由
""",
            "4": """
【反橡皮图章强制要求 — 4号必须展示独立技术分析】
- 你的产出被判定为"橡皮图章式确认2号结论"
- 必须满足以下独立性要求：
  ✅ 至少1只标的给出"观望/放弃/降级"判断（不能全部同方向确认）
  ✅ 引用 structures.json 中至少2个具体字段值（笔序号、背驰能量比、中枢区间等）
  ✅ 展示独立的技术面推导过程（不能仅复述基本面逻辑）
  ✅ 如方向与2号一致，必须用技术面证据独立验证（不能仅因为2号推荐就确认）
- 禁止：对2号 Watchlist 全部给出同方向信号
""",
        }
        return independence_req.get(role, "\n【必须展示独立分析过程，不能复制上游结论】\n")
    else:
        return ""


class ReviewRouter:
    """状态机路由器（v4.6 增强版）"""

    def __init__(self, max_retries=MAX_RETRIES):
        self.max_retries = max_retries

    def route(self, role: str, artifact_path: str, review_text: str,
              retry_count: int = 0):
        """
        路由决策核心函数（v4.6：支持 reject_type 差异化路由）
        返回:
            {
                "action": "PASS" | "REWORK" | "FORCED_PASS",
                "next_node": "secretary" | "<role>" | "secretary_with_warning",
                "rework_prompt": str | None,
                "warning_label": str | None,
                "reject_type": str | None,   # v4.6 新增
                "audit_trail": dict | None,  # v4.6 新增：审计追踪
            }
        """
        status, reason, reject_type = parse_review_status(review_text)

        if status == "PASS":
            log_review(role, artifact_path, "PASS", None, retry_count, "PASS")
            return {
                "action": "PASS",
                "next_node": "secretary",
                "rework_prompt": None,
                "warning_label": None,
                "reject_type": None,
                "audit_trail": {
                    "check": "review_pass",
                    "retry_count": retry_count,
                    "timestamp": datetime.now().isoformat(),
                },
            }

        # status == REJECT
        if retry_count < self.max_retries:
            # 还有重试机会
            new_count = retry_count + 1
            remaining = self.max_retries - new_count

            # v4.6：PERFUNCTORY_REWORK 类型消耗双倍重试（加速熔断）
            effective_count = new_count
            if reject_type == "PERFUNCTORY_REWORK" and new_count < self.max_retries:
                # 敷衍返工惩罚：如果是第1次返工就敷衍，直接视为第2次
                effective_count = min(new_count + 1, self.max_retries)
                remaining = self.max_retries - effective_count

            log_review(role, artifact_path, "REJECT", reason,
                       effective_count, None, reject_type)

            prompt = build_rework_prompt(
                artifact_path, reason, role,
                reject_type=reject_type,
                retry_count=effective_count,
                remaining=remaining,
            )

            # v4.6：COPYING 类型可能需要回炉多个节点
            next_nodes = self._determine_rework_targets(role, reject_type)

            return {
                "action": "REWORK",
                "next_node": next_nodes[0],  # 主回炉目标
                "additional_nodes": next_nodes[1:] if len(next_nodes) > 1 else [],
                "rework_prompt": prompt,
                "retry_count": effective_count,
                "warning_label": None,
                "reject_type": reject_type,
                "audit_trail": {
                    "check": "review_reject",
                    "reject_type": reject_type,
                    "retry_count": effective_count,
                    "remaining": remaining,
                    "reason_summary": reason[:200],
                    "timestamp": datetime.now().isoformat(),
                },
            }
        else:
            # 超过最大重试 - 强制熔断
            laziness_label = ""
            if reject_type:
                laziness_label = f"+{reject_type}"

            log_review(role, artifact_path, "REJECT", reason,
                       retry_count, "FORCED_PASS", reject_type)

            # v4.6：检查是否触发月度偷懒阈值
            monthly_alert = self._check_monthly_laziness(role)

            warning = (
                f"[高风险未决{laziness_label}] "
                f"{role}号产出经{self.max_retries}次打回仍未达标，"
                f"原因：{reason[:100]}"
            )
            if monthly_alert:
                warning += f" | ⚠️ 月度偷懒熔断累计{monthly_alert}次，建议重写Prompt"

            return {
                "action": "FORCED_PASS",
                "next_node": "secretary_with_warning",
                "rework_prompt": None,
                "warning_label": warning,
                "reject_type": reject_type,
                "audit_trail": {
                    "check": "forced_pass",
                    "reject_type": reject_type,
                    "total_retries": retry_count,
                    "monthly_laziness_count": monthly_alert,
                    "reason_summary": reason[:200],
                    "timestamp": datetime.now().isoformat(),
                },
            }

    def _determine_rework_targets(self, role: str, reject_type: Optional[str]) -> list:
        """
        v4.6：根据 reject_type 决定回炉目标节点
        - UNVERIFIED: 可能需要3号也重新采集数据
        - COPYING: 只回炉下游角色（要求独立分析）
        - 其他: 仅回炉当前角色
        """
        if reject_type == "UNVERIFIED" and role in ("1", "2", "4"):
            # 数据未核实：主回炉当前角色，附带通知3号补充数据
            return [role, "3"]
        elif reject_type == "COPYING":
            # 抄袭：只回炉抄袭方（下游角色）
            return [role]
        else:
            return [role]

    def _check_monthly_laziness(self, role: str) -> Optional[int]:
        """
        v4.6：检查该角色本月 FORCED_PASS 中偷懒类型的累计次数
        返回次数（如超阈值）或 None
        """
        try:
            conn = sqlite3.connect(DB_PATH)
            month_start = date.today().replace(day=1).isoformat()
            row = conn.execute("""
                SELECT COUNT(*) FROM review_log
                WHERE target_role = ?
                  AND review_date >= ?
                  AND final_status = 'FORCED_PASS'
                  AND reject_type IS NOT NULL
            """, (role, month_start)).fetchone()
            conn.close()
            count = row[0] if row else 0
            return count if count >= MONTHLY_LAZINESS_THRESHOLD else None
        except Exception:
            return None

    def get_review_summary(self, target_date=None):
        """查看打回率统计 - 给 6号秘书的进化报告用（v4.6 增强：含偷懒类型分布）"""
        target_date = target_date or date.today().isoformat()
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        rows = conn.execute("""
            SELECT target_role,
                   COUNT(*) as total,
                   SUM(CASE WHEN status='REJECT' THEN 1 ELSE 0 END) as rejects,
                   SUM(CASE WHEN final_status='FORCED_PASS' THEN 1 ELSE 0 END) as forced,
                   SUM(CASE WHEN reject_type='SHALLOW' THEN 1 ELSE 0 END) as shallow,
                   SUM(CASE WHEN reject_type='UNVERIFIED' THEN 1 ELSE 0 END) as unverified,
                   SUM(CASE WHEN reject_type='PERFUNCTORY_REWORK' THEN 1 ELSE 0 END) as perfunctory,
                   SUM(CASE WHEN reject_type='COPYING' THEN 1 ELSE 0 END) as copying
            FROM review_log
            WHERE review_date >= ?
            GROUP BY target_role
        """, (target_date,)).fetchall()
        conn.close()

        return [dict(r) for r in rows]

    def get_laziness_report(self, month: str = None):
        """
        v4.6 → v4.7 升级：月度偷懒报告
        month 格式: "2026-05"
        v4.7：JOIN audit_log 聚合 5 类偷懒（4 reject_type + supervisor_lazy）
        """
        if not month:
            month = date.today().strftime("%Y-%m")
        month_start = f"{month}-01"

        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row

            # v4.6 原有：reject_type 分布（含 SUPERVISOR_LAZY 通过 LIKE 匹配）
            review_rows = conn.execute("""
                SELECT target_role,
                       reject_type,
                       COUNT(*) as count,
                       GROUP_CONCAT(reject_reason, ' | ') as reasons
                FROM review_log
                WHERE review_date >= ?
                  AND reject_type IS NOT NULL
                GROUP BY target_role, reject_type
                ORDER BY target_role, count DESC
            """, (month_start,)).fetchall()

            # v4.7 新增：audit_log 维度聚合
            audit_rows = []
            try:
                audit_rows = conn.execute("""
                    SELECT target_role,
                           script_name,
                           verdict,
                           COUNT(*) as count
                    FROM audit_log
                    WHERE audit_date >= ?
                      AND verdict IN ('FAIL', 'SOFT_FAIL')
                    GROUP BY target_role, script_name, verdict
                    ORDER BY target_role, count DESC
                """, (month_start,)).fetchall()
            except sqlite3.OperationalError:
                pass  # audit_log 表不存在（旧库）

            # v4.7 新增：supervisor_lazy 计数（5 号漏检）
            supervisor_lazy_count = 0
            try:
                row = conn.execute("""
                    SELECT COUNT(*)
                    FROM audit_log
                    WHERE audit_date >= ?
                      AND script_name = 'supervisor_self_check'
                      AND verdict = 'FAIL'
                """, (month_start,)).fetchone()
                supervisor_lazy_count = row[0] if row else 0
            except sqlite3.OperationalError:
                pass

            conn.close()

            return {
                "month": month,
                "review_log_breakdown": [dict(r) for r in review_rows],
                "audit_log_breakdown": [dict(r) for r in audit_rows],
                "supervisor_lazy_count": supervisor_lazy_count,
                "trigger_prompt_rewrite": self._compute_rewrite_triggers(
                    [dict(r) for r in review_rows], supervisor_lazy_count
                ),
            }
        except Exception as e:
            return {"month": month, "error": str(e)}

    def _compute_rewrite_triggers(self, review_breakdown: list,
                                  supervisor_lazy_count: int) -> list:
        """计算哪些角色月度累计偷懒 ≥3 次 → 触发 Prompt 重写工单"""
        role_totals = {}
        for r in review_breakdown:
            role = r["target_role"]
            role_totals[role] = role_totals.get(role, 0) + r["count"]

        triggers = []
        for role, total in role_totals.items():
            if total >= MONTHLY_LAZINESS_THRESHOLD:
                triggers.append({
                    "role": role,
                    "lazy_count": total,
                    "action": "rewrite_prompt",
                })

        if supervisor_lazy_count >= MONTHLY_LAZINESS_THRESHOLD:
            triggers.append({
                "role": "5",
                "lazy_count": supervisor_lazy_count,
                "action": "rewrite_supervisor_prompt",
                "severity": "CRITICAL",
                "note": "5 号漏检偷懒最严重，必须立即重写",
            })

        return triggers


# ---------- CLI 测试 + v4.7 子命令 ----------
def _run_demo():
    """v4.6 原有的 demo 测试模式（保留向后兼容）"""
    router = ReviewRouter()

    # 测试 1: 通过
    review_pass = """
    ## 5号审核报告

    数据准确，逻辑链完整，独立验证一致。

    STATUS: PASS
    """
    print("=== 测试1：PASS ===")
    print(json.dumps(router.route("4", "/output/trading/2026-05-20.md", review_pass),
                     ensure_ascii=False, indent=2))

    # 测试 2: 浅析打回
    review_shallow = """
    ## 5号审核报告

    2号产出模糊废话过多，"市场情绪改善"x2 + "有望受益于"x1 + "政策利好"x1 = 4处模糊词。
    深度卡片缺少个股独立催化剂，仅引用行业共性逻辑。

    ## 🔍 反偷懒审计
    ### 浅析检测
    | 角色 | 模糊词命中 | 深度达标 | 判定 |
    | 2号 | 4处 | ❌ 无个股催化剂 | FAIL |

    STATUS: REJECT
    REJECT_TYPE: SHALLOW
    REASON: 2号深度卡片"中际旭创"缺少个股独立催化剂（仅引用"CPO行业高景气"），
    必须补充：1)该公司独有的订单/客户/产能数据 2)量化下行风险冲击幅度
    """
    print("\n=== 测试2：SHALLOW REJECT ===")
    result = router.route("2", "/output/industry/2026-05-28.md", review_shallow, retry_count=0)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # 测试 3: 返工敷衍
    review_perfunctory = """
    ## 5号审核报告

    2号返工稿对照原始意见：
    | 原始意见 | 修改状态 | 实质性 |
    | 补充个股催化剂 | 仅添加"订单情况良好" | 否 - 仍无具体数据 |
    | 量化下行风险 | 添加"注意风险" | 否 - 无量化 |

    返工稿未达到首次提交标准，判定为返工敷衍。

    STATUS: REJECT
    REJECT_TYPE: PERFUNCTORY_REWORK
    REASON: 返工敷衍。两条意见均未实质性修改：1)"订单情况良好"无具体金额/增速/来源
    2)"注意风险"未量化冲击幅度。必须提供具体数据。
    """
    print("\n=== 测试3：PERFUNCTORY_REWORK（首次返工即敷衍 → 加速熔断）===")
    result = router.route("2", "/output/industry/2026-05-28.md", review_perfunctory, retry_count=1)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # 测试 4: 抄袭打回
    review_copying = """
    ## 5号审核报告

    独立性验证失败：
    - 2号 Top 3 行业（光通信、AI算力、机器人）与1号"建议超配"行业100%重合
    - 2号未提供任何1号报告中不存在的新增数据或逻辑
    - 2号推荐理由直接引用1号原文"AI算力需求持续增长"

    STATUS: REJECT
    REJECT_TYPE: COPYING
    REASON: 2号未展示独立行业研判，Top 3行业100%复制1号结论，且无增量微观数据。
    必须：1)至少1只候选标的不在1号推荐行业中 2)提供独立的产业链调研证据
    """
    print("\n=== 测试4：COPYING REJECT ===")
    result = router.route("2", "/output/industry/2026-05-28.md", review_copying, retry_count=0)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # 测试 5: 数据未核实
    review_unverified = """
    ## 5号审核报告

    数据核实抽查发现2项红旗：
    1. 2号声称"中际旭创Q1营收同比+62%"但未标注来源，westock-data 查无此数
    2. 4号引用"日线第7笔完成"但 structures.json 显示日线仅到第5笔

    STATUS: REJECT
    REJECT_TYPE: UNVERIFIED
    REASON: 数据红旗2处：1)中际旭创营收数据无来源且可能虚构 2)缠论结构引用与JSON不一致。
    必须标注数据来源或更正数值。
    """
    print("\n=== 测试5：UNVERIFIED REJECT（双节点回炉）===")
    result = router.route("2", "/output/industry/2026-05-28.md", review_unverified, retry_count=0)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"  → 附加通知节点: {result.get('additional_nodes', [])}")

    # 打回率汇总
    print("\n=== 打回率汇总（今日，含偷懒类型分布）===")
    print(json.dumps(router.get_review_summary(), ensure_ascii=False, indent=2))


def _cli_monthly_report(month: str = None):
    """v4.7：月度偷懒报告"""
    router = ReviewRouter()
    report = router.get_laziness_report(month)
    print(f"📊 月度偷懒报告 [{report.get('month', month)}]")
    print(json.dumps(report, ensure_ascii=False, indent=2))

    triggers = report.get("trigger_prompt_rewrite", [])
    if triggers:
        print("\n🚨 Prompt 重写触发：")
        for t in triggers:
            print(f"   - 角色 {t['role']}: 累计偷懒 {t['lazy_count']} 次 → {t['action']}")
    else:
        print("\n✅ 本月无角色触发 Prompt 重写阈值")


def _cli_summary(target_date: str = None):
    """v4.7：当日打回率汇总"""
    router = ReviewRouter()
    summary = router.get_review_summary(target_date)
    print(f"📋 打回率汇总 [{target_date or 'today'}]")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def _cli_laziness_rank():
    """v4.7：偷懒排行榜（本月）"""
    router = ReviewRouter()
    report = router.get_laziness_report()
    breakdown = report.get("review_log_breakdown", [])
    audit_breakdown = report.get("audit_log_breakdown", [])

    # 按角色聚合总偷懒次数
    role_totals = {}
    for r in breakdown:
        role = r["target_role"]
        role_totals[role] = role_totals.get(role, 0) + r["count"]
    if report.get("supervisor_lazy_count", 0) > 0:
        role_totals["5"] = report["supervisor_lazy_count"]

    ranked = sorted(role_totals.items(), key=lambda x: -x[1])
    print(f"🏆 偷懒排行榜 [{report['month']}]")
    print(f"{'排名':<6}{'角色':<8}{'偷懒次数':<12}{'是否触发重写':<15}")
    for i, (role, count) in enumerate(ranked, 1):
        triggered = "🚨 是" if count >= MONTHLY_LAZINESS_THRESHOLD else "—"
        print(f"{i:<6}{role:<8}{count:<12}{triggered:<15}")

    print("\n详细分类：")
    print(json.dumps({
        "by_reject_type": breakdown,
        "by_audit_script": audit_breakdown,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    # v4.7：argparse-style 子命令路由（保留 v4.6 demo 作为默认）
    args = sys.argv[1:]
    if not args:
        _run_demo()
    elif args[0] == "--monthly-report":
        month = args[1] if len(args) > 1 else None
        _cli_monthly_report(month)
    elif args[0] == "--summary":
        target_date = args[1] if len(args) > 1 else None
        _cli_summary(target_date)
    elif args[0] == "--laziness-rank":
        _cli_laziness_rank()
    elif args[0] in ("--help", "-h"):
        print("""review_router.py — 5 号路由器 + v4.7 偷懒月报 CLI

用法:
  python review_router.py                          # 跑 demo 测试
  python review_router.py --monthly-report 2026-05 # 月度偷懒报告（不传月份默认本月）
  python review_router.py --summary [date]         # 当日打回率汇总
  python review_router.py --laziness-rank          # 偷懒排行榜
""")
    else:
        print(f"⚠️  未知命令: {args[0]}，跑 --help 查看用法")
        sys.exit(1)
