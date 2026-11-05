#!/usr/bin/env python3
"""stock-data 批量数据湖模块（v5.8.0, 2026-09-29）。

三块能力，均由 stock_data_cli.py 的子命令调用（bulk / thsdump / ths / lake）：

1) bulk    baostock 批量下载 5 分钟线 / 日线(+复权因子)，逐只落 parquet，可断点续传。
2) thsdump 同花顺(fuyao) Market Dumps：全市场 10 年日K(未复权)、近 10 日增量、复权事件。
3) ths     同花顺(fuyao) REST 只读透传（GET，固定 host，key 从文件读，永不回显）。
4) lake    数据湖盘点：已下载多少、缺多少、日期范围。

数据湖根目录：环境变量 STOCK_DATA_LAKE，默认 ~/quant_data。布局：
  raw/bs_5m/<code>.parquet        5分钟线（不复权，字段 date,code,open,high,low,close,volume,amount,dt）
  raw/bs_daily/<code>.parquet     日线（不复权，含 turn/tradestatus/isST/peTTM 等）
  raw/bs_daily/<code>_adj.parquet baostock 复权因子
  raw/ths/<kind>_<yyyymmdd>.parquet 同花顺全市场 dump
  meta/universe_union_2020_2026.csv 下载名单（code,name,indices,first_in,last_out,current）
  logs/bs_<kind>_progress.csv     下载进度日志
价格一律存**不复权**原价，复权因子另存，回测时自行复权（避免前复权价随新分红漂移）。

依赖：baostock, pandas, pyarrow, requests（见 requirements-runtime.txt）。
"""

from __future__ import annotations

import contextlib
import io
import json
import multiprocessing as mp
import os
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------- 路径与常量

LAKE = Path(os.environ.get("STOCK_DATA_LAKE", "~/quant_data")).expanduser()
UNIVERSE_DEFAULT = LAKE / "meta" / "universe_union_2020_2026.csv"

# baostock 5 分钟线实测最早 2020-01-02（文档称 2015 起，不成立）；1 分钟线不支持
BS_MIN_START = {"5m": "2020-01-02", "daily": "2018-01-01", "daily_pre": "2010-01-01", "daily_gap": "2018-01-01"}
BS_PRE_END = date(2017, 12, 31)  # daily_pre：补 2010~2017 日线（不含复权因子，daily 的 _adj 已从 2010 年起）
BS_FIELDS = {
    "5m": "date,time,code,open,high,low,close,volume,amount",
    "daily": ("date,code,open,high,low,close,preclose,volume,amount,turn,tradestatus,"
              "pctChg,peTTM,pbMRQ,psTTM,pcfNcfTTM,isST"),
}
BS_FIELDS["daily_pre"] = BS_FIELDS["daily_gap"] = BS_FIELDS["daily"]
BS_NUM_COLS = {
    "5m": ["open", "high", "low", "close", "volume", "amount"],
    "daily": ["open", "high", "low", "close", "preclose", "volume", "amount", "turn",
              "tradestatus", "pctChg", "peTTM", "pbMRQ", "psTTM", "pcfNcfTTM", "isST"],
}
BS_NUM_COLS["daily_pre"] = BS_NUM_COLS["daily_gap"] = BS_NUM_COLS["daily"]
BS_RETRIES = 4
REQUEST_PAUSE = 0.5   # 秒；每只股票开始前停顿
MAX_CONSEC_ERRORS = 5  # 连续出错达到此数即熔断，停止全部下载

THS_BASE = "https://fuyao.aicubes.cn"
THS_KEY_ENV = "HITHINK_FINANCE_API_KEY"
THS_KEY_FILE = Path("~/.config/quant/fuyao.env").expanduser()
THS_DUMP_KINDS = ("daily-k", "daily-k-10d", "adjustment-factors")
THS_RETRY_CODES = {4001, 5001, 5002, 5003}


# ---------------------------------------------------------------- baostock 批量

def bs_code(code: str) -> str:
    """6 位代码 -> baostock 代码；北交所不支持。"""
    code = str(code).zfill(6)
    if code[:2] in ("60", "68", "90"):
        return f"sh.{code}"
    if code[:2] in ("00", "30", "20"):
        return f"sz.{code}"
    raise ValueError(f"baostock 不支持北交所或未知号段: {code}")


def download_window(first_in: str, last_out: str, current: bool, kind: str,
                    today: date | None = None) -> tuple[date, date]:
    """某只股票需要下载的 [start, end]：成员期前推 365 天做特征预热；
    已剔除者只下到 last_out+90 天；现成分下到今天。"""
    import pandas as pd
    today = today or date.today()
    floor = pd.Timestamp(BS_MIN_START[kind]).date()
    # 纳入日缺失/非法/晚于今天（如占位符 9999）时，退回下限：宁可多下，不可漏下
    try:
        fi = pd.Timestamp(first_in).date()
        if fi > today:
            fi = None
    except (ValueError, TypeError, OverflowError, pd.errors.OutOfBoundsDatetime):
        fi = None
    start = floor if fi is None else max(floor, (pd.Timestamp(fi) - pd.Timedelta(days=365)).date())
    if current:
        end = today
    else:
        try:
            end = min(today, (pd.Timestamp(last_out) + pd.Timedelta(days=90)).date())
        except (ValueError, TypeError, OverflowError, pd.errors.OutOfBoundsDatetime):
            end = today
    return start, end


# ---------------------------------------------------------------- baostock 客户端加固
SOCKET_TIMEOUT = 30       # 秒：每次 connect/recv 的超时
RESPONSE_DEADLINE = 300   # 秒：单次请求总时限（含大响应）


class ServiceDownError(RuntimeError):
    """baostock 服务不响应（登录/查询在超时内无返回，或连接被对端关闭）。重试无益，应熔断。"""


def install_baostock_guards() -> None:
    """给 baostock 客户端加超时与断连检测（幂等）。

    baostock 0.9.x 的 send_msg 没有超时，且对端关闭连接时 recv 返回空字节、循环条件永不满足，
    进程 100% CPU 空转（第三方 issue HKUDS/Vibe-Trading#1492 亦有记录）。这里替换为：
    每次 recv 有超时、收到空字节即视为断连、单次请求有总时限；任何异常返回 None
    （调用方会把 None 处理成错误码 10002007「网络接收错误」）。
    """
    import socket
    import zlib
    import baostock.common.contants as cons
    import baostock.common.context as ctx
    import baostock.util.socketutil as su
    if getattr(su, "_stock_data_guarded", False):
        return
    socket.setdefaulttimeout(SOCKET_TIMEOUT)  # 之后新建的 socket（含 connect）都带超时

    def safe_send_msg(msg):
        try:
            sock = getattr(ctx, "default_socket", None)
            if sock is None:
                return None
            sock.settimeout(SOCKET_TIMEOUT)
            sock.send(bytes(msg + "\n", encoding="utf-8"))
            receive, t0 = b"", time.time()
            while True:
                chunk = sock.recv(8192)
                if not chunk:
                    raise ConnectionError("peer closed")
                receive += chunk
                if receive[-13:] == b"<![CDATA[]]>\n":
                    break
                if time.time() - t0 > RESPONSE_DEADLINE:
                    raise TimeoutError("response deadline exceeded")
            head_str = bytes.decode(receive[0:cons.MESSAGE_HEADER_LENGTH])
            head_arr = head_str.split(cons.MESSAGE_SPLIT)
            if head_arr[1] in cons.COMPRESSED_MESSAGE_TYPE_TUPLE:
                n = int(head_arr[2])
                body = bytes.decode(zlib.decompress(
                    receive[cons.MESSAGE_HEADER_LENGTH:cons.MESSAGE_HEADER_LENGTH + n]))
                return head_str + body
            return bytes.decode(receive)
        except Exception:  # noqa: BLE001
            return None

    su.send_msg = safe_send_msg
    su._stock_data_guarded = True


def probe_baostock() -> dict[str, Any]:
    """安全探测：一次登录 + 一次极小查询，全程带超时，不会挂死；用于封禁/故障后判断能否恢复。"""
    import baostock as bs
    install_baostock_guards()
    t0 = time.time()
    with contextlib.redirect_stdout(io.StringIO()):
        lg = bs.login()
    out: dict[str, Any] = {"login": f"{lg.error_code}:{lg.error_msg}", "login_secs": round(time.time() - t0, 1)}
    if lg.error_code == "0":
        t1 = time.time()
        rs = bs.query_history_k_data_plus("sh.600000", "date,close", start_date="2026-09-21",
                                          end_date="2026-09-28", frequency="d", adjustflag="3")
        n = 0
        while rs.error_code == "0" and rs.next():
            rs.get_row_data()  # baostock 的游标只在 get_row_data() 里前进；只调 next() 会死循环
            n += 1
            if n > 10_000:
                break
        out.update({"query": f"{rs.error_code}:{rs.error_msg}", "rows": n, "query_secs": round(time.time() - t1, 1)})
    with contextlib.redirect_stdout(io.StringIO()), contextlib.suppress(Exception):
        bs.logout()
    out["healthy"] = out["login"].startswith("0:") and out.get("query", "").startswith("0:") and out.get("rows", 0) > 0
    return out


class BlacklistError(RuntimeError):
    """baostock 10001011：IP 被列入黑名单。继续重试只会加重，必须立刻停止全部下载。"""


_LOGIN_ERR = ""  # 最近一次登录的错误码；"" 表示登录成功


def _bs_login() -> None:
    global _LOGIN_ERR
    import baostock as bs
    install_baostock_guards()
    with contextlib.redirect_stdout(io.StringIO()):
        lg = bs.login()
    _LOGIN_ERR = "" if lg.error_code == "0" else str(lg.error_code)


def _bs_logout() -> None:
    import baostock as bs
    with contextlib.redirect_stdout(io.StringIO()), contextlib.suppress(Exception):
        bs.logout()


def _bs_fetch(query, *args, **kw):
    """带重试 + 断线重登的 baostock 查询，返回 DataFrame。"""
    import pandas as pd
    last = ""
    for i in range(BS_RETRIES):
        try:
            rs = query(*args, **kw)
            if rs.error_code != "0":
                last = f"{rs.error_code}:{rs.error_msg}"
                if rs.error_code == "10001011":
                    raise BlacklistError(last)
                raise RuntimeError(last)
            rows = []
            while rs.next():
                rows.append(rs.get_row_data())
            return pd.DataFrame(rows, columns=rs.fields)
        except (BlacklistError, ServiceDownError):
            raise
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
            _bs_logout()
            time.sleep(2 * (i + 1))
            _bs_login()
            if _LOGIN_ERR == "10001011":
                raise BlacklistError(f"login: {_LOGIN_ERR}")
            if _LOGIN_ERR == "10002007":
                raise ServiceDownError(f"login: {_LOGIN_ERR} 网络接收错误(服务无响应)")
    raise RuntimeError(f"baostock failed after {BS_RETRIES} retries: {last}")


def _atomic_write(df, path: str) -> None:
    tmp = path + ".tmp"
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def bs_work(task: tuple[str, date, date, str]) -> tuple[str, str, int, float, str]:
    """下载单只股票一个 kind；已存在则跳过（断点续传）。返回 (code,status,rows,secs,note)。"""
    import baostock as bs
    import pandas as pd
    code, start, end, kind = task
    t0 = time.time()
    outdir = LAKE / "raw" / f"bs_{kind}"
    path = str(outdir / f"{code}.parquet")
    if os.path.exists(path):
        return code, "skip", 0, 0.0, ""
    if _LOGIN_ERR == "10001011":
        return code, "blacklisted", 0, 0.0, "login 10001011"
    time.sleep(REQUEST_PAUSE)  # 节流：每只股票开始前的固定停顿
    try:
        df = _bs_fetch(bs.query_history_k_data_plus, bs_code(code), BS_FIELDS[kind],
                       start_date=str(start), end_date=str(end),
                       frequency="5" if kind == "5m" else "d", adjustflag="3")
        if df.empty:
            _atomic_write(df, path)
            return code, "empty", 0, time.time() - t0, "no rows"
        for col in BS_NUM_COLS[kind]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        if kind == "5m":
            df["dt"] = pd.to_datetime(df["time"].str[:14], format="%Y%m%d%H%M%S")
            df = df.drop(columns=["time"])
            per_day = df.groupby("date").size()
            note = f"days={len(per_day)} off48={int((per_day != 48).sum())}"
        elif kind == "daily":
            adj = _bs_fetch(bs.query_adjust_factor, bs_code(code),
                            start_date="2010-01-01", end_date=str(end))
            _atomic_write(adj, str(outdir / f"{code}_adj.parquet"))
            note = f"adj_rows={len(adj)}"
        else:
            note = f"{kind} rows={len(df)}"
        _atomic_write(df, path)
        return code, "ok", len(df), time.time() - t0, note
    except BlacklistError as exc:
        return code, "blacklisted", 0, time.time() - t0, str(exc)[:120]
    except ServiceDownError as exc:
        return code, "service_down", 0, time.time() - t0, str(exc)[:120]
    except Exception as exc:  # noqa: BLE001
        return code, "error", 0, time.time() - t0, str(exc)[:120]


def build_bulk_tasks(kind: str, universe: Path = UNIVERSE_DEFAULT, limit: int = 0):
    import pandas as pd
    uni = pd.read_csv(universe, dtype={"code": str}).fillna({"last_out": ""})
    uni = uni.sort_values(["current", "code"], ascending=[False, True])  # 现成分优先
    tasks = []
    if kind == "daily_gap":  # 补齐 2018-01 至各股现有日线起点之间的空档（窗口按成员期前推 365 天造成的）
        import pandas as pd
        floor = date.fromisoformat(BS_MIN_START[kind])
        for r in uni.itertuples():
            try:
                bs_code(r.code)
            except ValueError:
                continue
            fp = LAKE / "raw" / "bs_daily" / f"{r.code}.parquet"
            if not fp.exists():
                continue
            first = pd.read_parquet(fp, columns=["date"])["date"]
            if first.empty:
                continue
            first_d = pd.Timestamp(first.min()).date()
            if (first_d - floor).days > 14:  # 起点晚于 2018 年初两周以上才视为有空档
                tasks.append((r.code, floor, first_d - timedelta(days=1), kind))
        return tasks[:limit] if limit else tasks
    if kind == "daily_pre":  # 与成员期无关：名单内每只股票补 2010~2017 日线（无数据者写空文件）
        for r in uni.itertuples():
            try:
                bs_code(r.code)
            except ValueError:
                continue
            tasks.append((r.code, date.fromisoformat(BS_MIN_START[kind]), BS_PRE_END, kind))
        return tasks[:limit] if limit else tasks
    for r in uni.itertuples():
        try:
            bs_code(r.code)
        except ValueError:
            continue
        s, e = download_window(r.first_in, r.last_out, bool(r.current), kind)
        if e > s:
            tasks.append((r.code, s, e, kind))
    return tasks[:limit] if limit else tasks


def run_bulk(kind: str, workers: int = 4, limit: int = 0,
             universe: Path = UNIVERSE_DEFAULT) -> dict[str, Any]:
    """并行批量下载；前台阻塞运行，进度打印到 stderr 并写日志 CSV。"""
    import signal
    import sys
    acquire_bulk_lock()

    def _on_term(signum, frame):  # noqa: ARG001  让 `with Pool` 的 __exit__ 终止全部工作进程
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _on_term)
    try:
        return _run_bulk(kind, workers, limit, universe)
    finally:
        release_bulk_lock()


def _run_bulk(kind: str, workers: int, limit: int, universe: Path) -> dict[str, Any]:
    import sys
    tasks = build_bulk_tasks(kind, universe, limit)
    (LAKE / "raw" / f"bs_{kind}").mkdir(parents=True, exist_ok=True)
    (LAKE / "logs").mkdir(parents=True, exist_ok=True)
    log = LAKE / "logs" / f"bs_{kind}_progress.csv"
    new = not log.exists()
    print(f"{datetime.now():%F %T} kind={kind} tasks={len(tasks)} workers={workers}",
          file=sys.stderr, flush=True)
    counts: dict[str, int] = {}
    aborted = ""
    rows_total, t_start = 0, time.time()
    with open(log, "a") as lf, mp.Pool(workers, initializer=_bs_login, maxtasksperchild=40) as pool:
        if new:
            lf.write("ts,code,status,rows,secs,note\n")
        consec = 0
        for i, (code, status, n, secs, note) in enumerate(pool.imap_unordered(bs_work, tasks), 1):
            counts[status] = counts.get(status, 0) + 1
            rows_total += n
            consec = consec + 1 if status in ("error", "blacklisted", "service_down") else (0 if status != "skip" else consec)
            if status in ("blacklisted", "service_down") or consec >= MAX_CONSEC_ERRORS:
                aborted = ("baostock 黑名单(10001011)：已停止全部下载，勿重试；等待解除后再降速续传"
                           if status == "blacklisted" else
                           "baostock 服务无响应(超时/断连)：已停止全部下载；先 `bulk --probe` 确认恢复再续传"
                           if status == "service_down" else f"连续 {consec} 次出错，已熔断")
                lf.write(f"{datetime.now():%F %T},{code},{status},0,{secs:.1f},ABORT {aborted}\n")
                lf.flush()
                pool.terminate()
                break
            lf.write(f"{datetime.now():%F %T},{code},{status},{n},{secs:.1f},{note}\n")
            lf.flush()
            if i % 20 == 0 or status == "error":
                el = time.time() - t_start
                print(f"{datetime.now():%T} {i}/{len(tasks)} last={code}:{status} rows={rows_total} "
                      f"elapsed={el/60:.1f}min eta={(el/i)*(len(tasks)-i)/60:.0f}min",
                      file=sys.stderr, flush=True)
    return {"kind": kind, "tasks": len(tasks), "status_counts": counts, "rows": rows_total,
            "elapsed_min": round((time.time() - t_start) / 60, 1), "lake": str(LAKE),
            "aborted": aborted or None}


# ---------------------------------------------------------------- 单实例锁与停止
def _pidfile() -> Path:
    return LAKE / "logs" / "bulk.pid"


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def acquire_bulk_lock() -> None:
    """全局只允许一个 bulk 在跑（2026-09-29 并发 7 会话触发 baostock 黑名单的教训）。"""
    pf = _pidfile()
    pf.parent.mkdir(parents=True, exist_ok=True)
    if pf.exists():
        try:
            other = int(pf.read_text().split()[0])
        except (ValueError, IndexError):
            other = 0
        if other and other != os.getpid() and _pid_alive(other):
            raise RuntimeError(f"已有 bulk 在运行(pid {other})；同一时间只允许一个。先运行 `bulk --stop`")
    pf.write_text(f"{os.getpid()} {datetime.now():%F %T}\n")


def release_bulk_lock() -> None:
    with contextlib.suppress(OSError):
        pf = _pidfile()
        if pf.exists() and pf.read_text().split()[0] == str(os.getpid()):
            pf.unlink()


def stop_bulk(grace: float = 10.0) -> dict[str, Any]:
    """向运行中的 bulk 发 SIGTERM（其处理函数会终止工作进程池），超时再 SIGKILL。"""
    import signal
    pf = _pidfile()
    if not pf.exists():
        return {"stopped": False, "reason": "无 pid 文件（没有运行中的 bulk）"}
    try:
        pid = int(pf.read_text().split()[0])
    except (ValueError, IndexError):
        pf.unlink(missing_ok=True)
        return {"stopped": False, "reason": "pid 文件损坏，已清除"}
    if not _pid_alive(pid):
        pf.unlink(missing_ok=True)
        return {"stopped": False, "reason": f"pid {pid} 已不存在，已清除 pid 文件"}
    os.kill(pid, signal.SIGTERM)
    deadline = time.time() + grace
    while time.time() < deadline and _pid_alive(pid):
        time.sleep(0.5)
    killed = False
    if _pid_alive(pid):
        os.kill(pid, signal.SIGKILL)
        killed = True
    pf.unlink(missing_ok=True)
    return {"stopped": True, "pid": pid, "sigkill_needed": killed}


# ---------------------------------------------------------------- 同花顺 fuyao

def load_ths_key() -> str:
    """key 只从环境变量或 ~/.config/quant/fuyao.env 读取；永不打印、永不写入日志。"""
    key = os.environ.get(THS_KEY_ENV, "").strip()
    if not key and THS_KEY_FILE.exists():
        for line in THS_KEY_FILE.read_text(encoding="utf-8").splitlines():
            m = re.match(rf"\s*{THS_KEY_ENV}\s*=\s*(.+?)\s*$", line)
            if m:
                key = m.group(1).strip().strip("'\"")
                break
    if not key:
        raise RuntimeError(f"未找到同花顺 API key：设置环境变量 {THS_KEY_ENV}，"
                           f"或写入 {THS_KEY_FILE}（权限 600）")
    return key


def ths_get(path: str, params: dict[str, Any] | None = None, retries: int = 3) -> Any:
    """GET https://fuyao.aicubes.cn<path>；path 必须以 /api/ 开头（固定 host，防止 key 外发）。
    返回信封里的 data；code != 0 抛 RuntimeError（带 request_id，不含 key）。"""
    import requests
    if not path.startswith("/api/"):
        raise ValueError("path 必须以 /api/ 开头")
    headers = {"X-api-key": load_ths_key()}
    last = ""
    for i in range(retries):
        try:
            resp = requests.get(THS_BASE + path, params=params or {}, headers=headers, timeout=30)
            body = resp.json()
        except Exception as exc:  # noqa: BLE001  网络/解析错误可重试
            last = f"{type(exc).__name__}"
            time.sleep(2 ** i)
            continue
        code = body.get("code")
        if code == 0:
            return body.get("data")
        last = f"code={code} message={body.get('message')} request_id={body.get('request_id')}"
        if code in THS_RETRY_CODES:
            time.sleep(2 ** i)
            continue
        break  # 1xxx/2xxx/3xxx 调用方错误，不重试
    raise RuntimeError(f"fuyao API failed: {path} {last}")


def ths_dump(kind: str, confirm_download: bool = False) -> dict[str, Any]:
    """同花顺 Market Dump。默认只签出并查询文件大小（--confirm-download 才真正下载）。
    预签名 URL 约 5 分钟有效，只在进程内使用，不打印、不落盘。"""
    import requests
    if kind not in THS_DUMP_KINDS:
        raise ValueError(f"kind 必须是 {THS_DUMP_KINDS}")
    data = ths_get(f"/api/dump/market-dumps/{kind}/download-url")
    url = (data or {}).get("presigned_url")
    if not url:
        raise RuntimeError(f"未取得下载链接：kind={kind}")
    head = requests.get(url, headers={"Range": "bytes=0-0"}, timeout=30, stream=True)
    total = None
    cr = head.headers.get("Content-Range", "")
    if "/" in cr:
        total = int(cr.split("/")[-1])
    elif head.headers.get("Content-Length"):
        total = int(head.headers["Content-Length"])
    head.close()
    out = LAKE / "raw" / "ths" / f"{kind}_{date.today():%Y%m%d}.parquet"
    info: dict[str, Any] = {"kind": kind, "size_bytes": total,
                            "size_mb": round(total / 1e6, 1) if total else None,
                            "expires_at": (data or {}).get("presigned_url_expires_at"),
                            "target": str(out), "downloaded": False}
    if not confirm_download:
        info["note"] = "未下载；确认大小后加 --confirm-download"
        return info
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(out) + ".tmp"
    with requests.get(url, stream=True, timeout=120) as r, open(tmp, "wb") as f:
        r.raise_for_status()
        for chunk in r.iter_content(1 << 20):
            f.write(chunk)
    import pyarrow.parquet as pq
    meta = pq.ParquetFile(tmp).metadata  # 校验是合法 parquet
    os.replace(tmp, out)
    info.update({"downloaded": True, "rows": meta.num_rows, "columns": meta.num_columns})
    return info


# ---------------------------------------------------------------- 数据湖盘点

def lake_status(sample: int = 5) -> dict[str, Any]:
    """盘点数据湖：文件数、行数(读 parquet 元数据)、体积、缺口、日期范围(抽样)。"""
    import pyarrow.parquet as pq
    import pandas as pd
    out: dict[str, Any] = {"lake": str(LAKE), "exists": LAKE.exists()}
    if not LAKE.exists():
        return out
    uni_codes: list[str] = []
    if UNIVERSE_DEFAULT.exists():
        uni = pd.read_csv(UNIVERSE_DEFAULT, dtype={"code": str})
        uni_codes = uni["code"].tolist()
        out["universe_size"] = len(uni_codes)
    for kind in ("5m", "daily"):
        d = LAKE / "raw" / f"bs_{kind}"
        if not d.exists():
            continue
        files = sorted(p for p in d.glob("*.parquet") if not p.stem.endswith("_adj"))
        rows = sum(pq.ParquetFile(p).metadata.num_rows for p in files)
        info: dict[str, Any] = {"files": len(files), "rows": rows,
                                "size_mb": round(sum(p.stat().st_size for p in files) / 1e6, 1)}
        if uni_codes:
            have = {p.stem for p in files}
            info["missing_vs_universe"] = len(set(uni_codes) - have)
        dates = []
        for p in files[:: max(1, len(files) // sample)][:sample]:
            col = pd.read_parquet(p, columns=["date"])["date"]
            if len(col):
                dates.append((col.min(), col.max()))
        if dates:
            info["date_range_sampled"] = [min(a for a, _ in dates), max(b for _, b in dates)]
        log = LAKE / "logs" / f"bs_{kind}_progress.csv"
        if log.exists():
            lg = pd.read_csv(log)
            info["log_status"] = lg["status"].value_counts().to_dict()
        out[f"bs_{kind}"] = info
    ths_dir = LAKE / "raw" / "ths"
    if ths_dir.exists():
        out["ths"] = {p.name: round(p.stat().st_size / 1e6, 1) for p in sorted(ths_dir.glob("*.parquet"))}
    return out


if __name__ == "__main__":  # 便于单独调试
    print(json.dumps(lake_status(), ensure_ascii=False, indent=2, default=str))
