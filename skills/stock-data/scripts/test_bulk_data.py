"""bulk_data 离线单元测试（不联网、不写真实数据湖）。"""
from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock


def _load():
    spec = importlib.util.spec_from_file_location("bulk_data_under_test", Path(__file__).with_name("bulk_data.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bd = _load()


class BsCodeTests(unittest.TestCase):
    def test_exchange_mapping(self):
        self.assertEqual(bd.bs_code("600519"), "sh.600519")
        self.assertEqual(bd.bs_code("688981"), "sh.688981")
        self.assertEqual(bd.bs_code("000001"), "sz.000001")
        self.assertEqual(bd.bs_code("300750"), "sz.300750")
        self.assertEqual(bd.bs_code("1"), "sz.000001")  # zfill

    def test_beijing_rejected(self):
        for code in ("830799", "430047", "920001"):
            with self.assertRaises(ValueError):
                bd.bs_code(code)


class WindowTests(unittest.TestCase):
    today = date(2026, 9, 29)

    def test_current_member_runs_to_today_with_warmup(self):
        s, e = bd.download_window("2021-06-15", "", True, "5m", today=self.today)
        self.assertEqual(s, date(2020, 6, 15))
        self.assertEqual(e, self.today)

    def test_5m_floor_is_2020(self):
        s, _ = bd.download_window("2015-01-01", "", True, "5m", today=self.today)
        self.assertEqual(s, date(2020, 1, 2))

    def test_daily_floor_is_2018(self):
        s, _ = bd.download_window("2005-01-01", "", True, "daily", today=self.today)
        self.assertEqual(s, date(2018, 1, 1))

    def test_removed_stock_stops_after_last_out_plus_90d(self):
        _, e = bd.download_window("2021-01-01", "2022-03-01", False, "5m", today=self.today)
        self.assertEqual(e, date(2022, 5, 30))

    def test_placeholder_first_in_falls_back_to_floor_not_empty_window(self):
        # 回归：first_in='9999' 曾导致 518 只现成分股下载窗口为空而被静默跳过
        for bad in ("9999", "", "not-a-date", "9999-12-31"):
            s, e = bd.download_window(bad, "", True, "5m", today=self.today)
            self.assertEqual(s, date(2020, 1, 2), bad)
            self.assertTrue(e > s, bad)

    def test_removed_never_beyond_today(self):
        _, e = bd.download_window("2021-01-01", "2026-09-01", False, "5m", today=self.today)
        self.assertEqual(e, self.today)


class DailyPreTests(unittest.TestCase):
    def test_daily_pre_tasks_cover_every_code_2010_to_2017_and_skip_bj(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "u.csv"
            f.write_text("code,name,indices,first_in,last_out,current\n"
                         "600519,a,x,2015-01-01,,1\n000001,b,x,9999,,1\n830799,bj,x,2015-01-01,,1\n")
            tasks = bd.build_bulk_tasks("daily_pre", f)
        self.assertEqual([t[0] for t in tasks], ["000001", "600519"])  # 北交所被跳过；第一列是 code
        for _, s, e, kind in tasks:
            self.assertEqual((s, e, kind), (date(2010, 1, 1), date(2017, 12, 31), "daily_pre"))


class DailyGapTests(unittest.TestCase):
    def test_gap_tasks_only_for_late_starts_and_end_day_before_first(self):
        import pandas as pd
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "raw" / "bs_daily").mkdir(parents=True)
            for code, first in (("600519", "2018-01-02"), ("000001", "2019-03-05"), ("300750", "2018-01-10")):
                pd.DataFrame({"date": [first, "2026-01-05"]}).to_parquet(root / "raw" / "bs_daily" / f"{code}.parquet")
            uni = root / "u.csv"
            uni.write_text("code,name,indices,first_in,last_out,current\n"
                           "600519,a,x,2015-01-01,,1\n000001,b,x,2015-01-01,,1\n300750,c,x,2015-01-01,,1\n000002,d,x,2015-01-01,,1\n")
            with mock.patch.object(bd, "LAKE", root):
                tasks = bd.build_bulk_tasks("daily_gap", uni)
        # 600519 起点 2018-01-02、300750 起点 2018-01-10（均在两周内）不算空档；000002 无日线文件被跳过
        self.assertEqual([(t[0], t[1], t[2]) for t in tasks], [("000001", date(2018, 1, 1), date(2019, 3, 4))])


class BlacklistTests(unittest.TestCase):
    """回归：2026-09-29 baostock 返回 10001011(IP 黑名单)后，旧版每只股票重试 4 次并继续下一只，
    3 个下载进程连续重试约 1.7 小时（约 1190 次失败），可能加重封禁。"""

    class FakeRS:
        error_code = "10001011"
        error_msg = "黑名单用户，请与管理员联系"
        fields: list = []

    def test_fetch_raises_blacklist_immediately_without_retry(self):
        calls, sleeps = [], []

        def query(*a, **k):
            calls.append(1)
            return self.FakeRS()

        with mock.patch("time.sleep", lambda s: sleeps.append(s)):
            with self.assertRaises(bd.BlacklistError):
                bd._bs_fetch(query)
        self.assertEqual(len(calls), 1)  # 不重试
        self.assertEqual(sleeps, [])  # 不退避重登

    def test_work_returns_blacklisted_status_not_error(self):
        with tempfile.TemporaryDirectory() as d, \
             mock.patch.object(bd, "LAKE", Path(d)), \
             mock.patch.object(bd, "REQUEST_PAUSE", 0), \
             mock.patch("baostock.query_history_k_data_plus", lambda *a, **k: self.FakeRS()):
            (Path(d) / "raw" / "bs_5m").mkdir(parents=True)
            r = bd.bs_work(("600519", date(2020, 1, 2), date(2026, 9, 28), "5m"))
        self.assertEqual(r[1], "blacklisted")

    def test_work_short_circuits_when_login_already_blacklisted(self):
        with tempfile.TemporaryDirectory() as d, \
             mock.patch.object(bd, "LAKE", Path(d)), \
             mock.patch.object(bd, "_LOGIN_ERR", "10001011"):
            (Path(d) / "raw" / "bs_5m").mkdir(parents=True)
            r = bd.bs_work(("600519", date(2020, 1, 2), date(2026, 9, 28), "5m"))
        self.assertEqual(r[1], "blacklisted")


class BaostockGuardTests(unittest.TestCase):
    """回归：baostock 自带 send_msg 无超时，对端关闭连接时 recv 返回空字节，循环永不结束（100% CPU）。"""

    def _install_fresh(self):
        import baostock.util.socketutil as su
        import baostock.common.context as ctx
        su._stock_data_guarded = False
        bd.install_baostock_guards()
        return su, ctx

    def test_peer_closed_returns_none_instead_of_spinning(self):
        su, ctx = self._install_fresh()

        class ClosedSock:
            def settimeout(self, t): pass
            def send(self, b): return len(b)
            def recv(self, n): return b""  # 对端已关闭

        with mock.patch.object(ctx, "default_socket", ClosedSock(), create=True):
            self.assertIsNone(su.send_msg("x"))  # 若仍是原实现，这里会死循环

    def test_recv_timeout_returns_none(self):
        import socket
        su, ctx = self._install_fresh()

        class SilentSock:
            def settimeout(self, t): pass
            def send(self, b): return len(b)
            def recv(self, n): raise socket.timeout("timed out")

        with mock.patch.object(ctx, "default_socket", SilentSock(), create=True):
            self.assertIsNone(su.send_msg("x"))

    def test_install_is_idempotent_and_sets_default_timeout(self):
        import socket
        su, _ = self._install_fresh()
        first = su.send_msg
        bd.install_baostock_guards()
        self.assertIs(su.send_msg, first)
        self.assertEqual(socket.getdefaulttimeout(), bd.SOCKET_TIMEOUT)
        socket.setdefaulttimeout(None)  # 还原，避免影响其它测试


class ProbeTests(unittest.TestCase):
    """回归：probe_baostock 曾只调用 rs.next() 而不调用 get_row_data()，游标不前进，登录成功后仍无限循环
    （2026-09-30，baostock 已恢复，探测却挂了 10 分钟）。"""

    def test_probe_terminates_and_counts_rows_via_get_row_data(self):
        class RS:
            error_code, error_msg, fields = "0", "success", ["date", "close"]

            def __init__(self):
                self.i, self.rows = 0, [["2026-09-21", "9.0"], ["2026-09-22", "9.1"]]

            def next(self):
                return self.i < len(self.rows)

            def get_row_data(self):
                r = self.rows[self.i]
                self.i += 1
                return r

        class LG:
            error_code, error_msg = "0", "success"

        with mock.patch("baostock.login", lambda *a, **k: LG()), \
             mock.patch("baostock.logout", lambda *a, **k: None), \
             mock.patch("baostock.query_history_k_data_plus", lambda *a, **k: RS()):
            r = bd.probe_baostock()
        self.assertEqual(r["rows"], 2)
        self.assertTrue(r["healthy"])


class BulkLockTests(unittest.TestCase):
    def test_lock_blocks_second_instance_and_replaces_stale(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(bd, "LAKE", Path(d)):
            (Path(d) / "logs").mkdir()
            pf = Path(d) / "logs" / "bulk.pid"
            # 另一个存活进程持有锁（用父进程 pid 模拟）
            pf.write_text(f"{os.getppid()} 2026-01-01 00:00:00\n")
            with self.assertRaises(RuntimeError):
                bd.acquire_bulk_lock()
            # 陈旧 pid（不存在）会被接管
            pf.write_text("999999 2026-01-01 00:00:00\n")
            bd.acquire_bulk_lock()
            self.assertTrue(pf.read_text().startswith(str(os.getpid())))
            bd.release_bulk_lock()
            self.assertFalse(pf.exists())

    def test_stop_without_pidfile_or_with_dead_pid(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(bd, "LAKE", Path(d)):
            (Path(d) / "logs").mkdir()
            self.assertFalse(bd.stop_bulk()["stopped"])
            (Path(d) / "logs" / "bulk.pid").write_text("999999 x\n")
            r = bd.stop_bulk()
            self.assertFalse(r["stopped"])
            self.assertFalse((Path(d) / "logs" / "bulk.pid").exists())


class ThsKeyTests(unittest.TestCase):
    def test_env_takes_precedence(self):
        with mock.patch.dict(os.environ, {bd.THS_KEY_ENV: "envkey"}):
            self.assertEqual(bd.load_ths_key(), "envkey")

    def test_reads_env_file_and_strips_quotes(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "fuyao.env"
            f.write_text(f'# c\n{bd.THS_KEY_ENV}="filekey"\n')
            with mock.patch.object(bd, "THS_KEY_FILE", f):
                os.environ.pop(bd.THS_KEY_ENV, None)
                self.assertEqual(bd.load_ths_key(), "filekey")

    def test_missing_key_message_names_variable_only(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(bd, "THS_KEY_FILE", Path(d) / "none.env"):
                os.environ.pop(bd.THS_KEY_ENV, None)
                with self.assertRaises(RuntimeError) as cm:
                    bd.load_ths_key()
                self.assertIn(bd.THS_KEY_ENV, str(cm.exception))


class ThsGetTests(unittest.TestCase):
    def test_path_guard_blocks_non_api(self):
        with self.assertRaises(ValueError):
            bd.ths_get("https://evil.example/steal")
        with self.assertRaises(ValueError):
            bd.ths_get("/other/path")

    def test_error_code_not_retried_and_no_key_leak(self):
        calls = []

        class R:
            def json(self):
                return {"code": 1002, "message": "bad param", "request_id": "rid1", "data": None}

        def fake_get(*a, **k):
            calls.append(1)
            return R()

        with mock.patch.dict(os.environ, {bd.THS_KEY_ENV: "SECRETKEY"}), \
             mock.patch("requests.get", fake_get):
            with self.assertRaises(RuntimeError) as cm:
                bd.ths_get("/api/x", {"a": "1"})
        self.assertEqual(len(calls), 1)  # 1xxx 不重试
        self.assertNotIn("SECRETKEY", str(cm.exception))
        self.assertIn("rid1", str(cm.exception))

    def test_rate_limit_retried_then_succeeds(self):
        seq = [{"code": 4001, "message": "rl", "request_id": "r", "data": None},
               {"code": 0, "message": "", "request_id": "r", "data": {"ok": 1}}]

        class R:
            def __init__(self, body):
                self.body = body

            def json(self):
                return self.body

        it = iter(seq)
        with mock.patch.dict(os.environ, {bd.THS_KEY_ENV: "k"}), \
             mock.patch("requests.get", lambda *a, **k: R(next(it))), \
             mock.patch("time.sleep"):
            self.assertEqual(bd.ths_get("/api/x"), {"ok": 1})

    def test_dump_kind_validated(self):
        with self.assertRaises(ValueError):
            bd.ths_dump("weekly-k")


if __name__ == "__main__":
    unittest.main()
