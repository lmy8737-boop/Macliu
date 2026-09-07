"""
supervisor_self_check.py — v4.7 Meta 反偷懒（5 号自身一致性校验）

设计哲学（与原始方案 X 的关键改进）：
  - 否决"8 号 LLM 监工 5 号"递归路线（LLM 监 LLM = 递归偷懒，无 ground truth）
  - 替代为"5 号决策 vs audit script verdict 的硬性一致性校验"
  - 删掉伪硬门槛（审核字数 ≥800、数据点引用 ≥3）— 这些与"是否漏检"没有因果链

核心规则（不可绕过）：
  1. 任一 audit script verdict=FAIL **但** 5 号 STATUS=PASS
     → 自动改写 final_status=FORCED_REJECT
     → 在 audit_log 写一行 supervisor_self_check / verdict=FAIL 记录
     → review_log 的 reject_type 写为 SUPERVISOR_LAZY（用于 accountability 扣 5 分）

  2. 任一 audit FAIL 但 5 号 STATUS=REJECT 但 reject_type 不匹配
     → 视为部分捕获，仅警告（不强制改写）

  3. 反向（脚本 PASS 但 5 号 REJECT）→ 允许通过，保留 LLM 高阶判断空间
     这是"5 号否决权"的合法行使（如发现脚本未覆盖的逻辑漏洞）

CLI:
  python supervisor_self_check.py \
      --supervisor outputs/05_supervisor/05_审核.md \
      --review-id <review_log_id>
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

STATUS_PATTERN = re.compile(r"STATUS:\s*(PASS|REJECT)", re.IGNORECASE)
REJECT_TYPE_PATTERN = re.compile(
    r"REJECT_TYPE:\s*(SHALLOW|UNVERIFIED|PERFUNCTORY_REWORK|COPYING)",
    re.IGNORECASE,
)

# audit script_name → 期望的 reject_type 映射
SCRIPT_TO_REJECT_TYPE = {
    "buzzword": "SHALLOW",
    "data_verify": "UNVERIFIED",
    "independence": "COPYING",
    "semantic_diff": "PERFUNCTORY_REWORK",
}


def parse_supervisor_status(text: str):
    """从 5 号产出提取 STATUS + REJECT_TYPE"""
    m = STATUS_PATTERN.search(text)
    if not m:
        return ("MISSING", None)
    status = m.group(1).upper()
    if status == "PASS":
        return ("PASS", None)
    rt_match = REJECT_TYPE_PATTERN.search(text)
    reject_type = rt_match.group(1).upper() if rt_match else None
    return ("REJECT", reject_type)


def fetch_audit_results(review_id: int) -> list:
    """从 audit_log 拉取该 review 的所有 audit 结果"""
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT script_name, target_role, target_artifact, verdict, detail_json
        FROM audit_log
        WHERE review_id = ?
          AND script_name != 'supervisor_self_check'
        ORDER BY created_at
    """, (review_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def evaluate(supervisor_status: str, supervisor_reject_type: str,
             audit_results: list) -> dict:
    """评估一致性"""
    fail_audits = [a for a in audit_results if a["verdict"] == "FAIL"]
    soft_fail_audits = [a for a in audit_results if a["verdict"] == "SOFT_FAIL"]

    case = None
    overridden = False
    final_status = None
    laziness_label = None
    warnings = []

    if supervisor_status == "MISSING":
        # 5 号没输出状态码 → 视同最严重偷懒
        case = "missing_status"
        overridden = True
        final_status = "FORCED_REJECT"
        laziness_label = "supervisor_lazy"
        warnings.append("5 号未按规范输出 STATUS 码 → 自动判定为 supervisor_lazy")

    elif supervisor_status == "PASS" and fail_audits:
        # 关键场景：脚本红旗但 5 号放水
        case = "supervisor_pass_audit_fail"
        overridden = True
        final_status = "FORCED_REJECT"
        laziness_label = "supervisor_lazy"
        scripts = [a["script_name"] for a in fail_audits]
        warnings.append(
            f"5 号偷懒漏检：audit FAIL ({scripts}) 但 5 号给 PASS → "
            f"强制改写 FORCED_REJECT，accountability -5"
        )

    elif supervisor_status == "REJECT" and fail_audits:
        # 5 号 REJECT 了，检查 reject_type 是否匹配 audit 类型
        expected_types = {SCRIPT_TO_REJECT_TYPE.get(a["script_name"]) for a in fail_audits}
        expected_types.discard(None)
        if supervisor_reject_type and supervisor_reject_type in expected_types:
            case = "supervisor_reject_aligned"
            warnings.append(f"5 号 REJECT 与 audit FAIL 一致（{supervisor_reject_type}）")
        else:
            case = "supervisor_reject_mismatch"
            warnings.append(
                f"5 号 REJECT 但 reject_type='{supervisor_reject_type}' 与 audit FAIL "
                f"类型集 {sorted(expected_types)} 不匹配 → 部分捕获，仅警告不强制改写"
            )

    elif supervisor_status == "REJECT" and not fail_audits:
        # 脚本全 PASS 但 5 号 REJECT → 合法行使 LLM 否决权
        case = "supervisor_reject_independent"
        warnings.append(
            "5 号 REJECT 但所有 audit PASS → 合法 LLM 否决权（保留高阶判断空间）"
        )

    elif supervisor_status == "PASS" and soft_fail_audits:
        # 仅 SOFT_FAIL 时 5 号 PASS：警告但不强制
        case = "supervisor_pass_soft_fail"
        warnings.append(
            f"audit SOFT_FAIL ({[a['script_name'] for a in soft_fail_audits]}) "
            f"但 5 号 PASS → 容忍（仅记录）"
        )

    else:  # supervisor_status == "PASS" and 全部 audit PASS
        case = "fully_aligned"
        warnings.append("5 号 PASS 与全部 audit PASS 一致")

    return {
        "case": case,
        "overridden": overridden,
        "final_status": final_status,
        "laziness_label": laziness_label,
        "warnings": warnings,
        "fail_audit_scripts": [a["script_name"] for a in fail_audits],
        "soft_fail_audit_scripts": [a["script_name"] for a in soft_fail_audits],
        "supervisor_status": supervisor_status,
        "supervisor_reject_type": supervisor_reject_type,
    }


def apply_override(review_id: int, eval_result: dict, supervisor_path: str):
    """如果 overridden=True，写 audit_log + 改 review_log final_status"""
    if not DB_PATH.exists():
        return
    conn = sqlite3.connect(DB_PATH)
    try:
        # 写 audit_log（记录 meta 检查本身的结果）
        verdict = "FAIL" if eval_result["overridden"] else "PASS"
        conn.execute("""
            INSERT INTO audit_log (review_id, script_name, target_role,
                                   target_artifact, verdict, detail_json,
                                   audit_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (review_id, "supervisor_self_check", "5", supervisor_path,
              verdict, json.dumps(eval_result, ensure_ascii=False),
              date.today().isoformat()))

        if eval_result["overridden"]:
            # 改写 review_log final_status + reject_type
            conn.execute("""
                UPDATE review_log
                SET final_status = ?,
                    reject_type = COALESCE(reject_type, '') || '|SUPERVISOR_LAZY'
                WHERE review_id = ?
            """, (eval_result["final_status"], review_id))

        conn.commit()
    except Exception as e:
        print(f"⚠️  override 写入失败: {e}", file=sys.stderr)
    finally:
        conn.close()


def parse_args():
    args = {"supervisor": None, "review_id": None}
    rest = sys.argv[1:]
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--supervisor":
            args["supervisor"] = rest[i + 1]; i += 2
        elif a == "--review-id":
            args["review_id"] = int(rest[i + 1]); i += 2
        else:
            i += 1
    return args


def main():
    args = parse_args()
    if not args["supervisor"] or args["review_id"] is None:
        print("用法: python supervisor_self_check.py --supervisor 05_审核.md --review-id N")
        sys.exit(1)

    sup_text = Path(args["supervisor"]).read_text(encoding="utf-8")
    sup_status, sup_reject_type = parse_supervisor_status(sup_text)
    audit_results = fetch_audit_results(args["review_id"])

    eval_result = evaluate(sup_status, sup_reject_type, audit_results)
    apply_override(args["review_id"], eval_result, args["supervisor"])

    emoji = "✅" if not eval_result["overridden"] else "🚨"
    print(f"{emoji} supervisor_self_check | review_id={args['review_id']}")
    print(f"   case: {eval_result['case']}")
    print(f"   5 号: STATUS={sup_status} REJECT_TYPE={sup_reject_type}")
    print(f"   audit FAIL: {eval_result['fail_audit_scripts']}")
    print(f"   audit SOFT_FAIL: {eval_result['soft_fail_audit_scripts']}")
    if eval_result["overridden"]:
        print(f"   🚨 OVERRIDDEN → final_status={eval_result['final_status']} "
              f"(label={eval_result['laziness_label']})")
    for w in eval_result["warnings"]:
        print(f"   - {w}")
    print(json.dumps(eval_result, ensure_ascii=False, indent=2))
    return 2 if eval_result["overridden"] else 0


if __name__ == "__main__":
    sys.exit(main())
