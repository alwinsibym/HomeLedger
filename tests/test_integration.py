"""Starts the real program as a separate process: concurrency, hard kill (power cut), corrupt-file recovery, safety headers."""
import json, os, signal, subprocess, sys, tempfile, threading, time, unittest, urllib.request, urllib.error, sqlite3
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
PORT = 8790


def call(path, body=None, headers=None, timeout=15):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", method="POST" if body is not None else "GET",
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"X-HomeLedger": "1", "Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try: return e.code, json.loads(raw or b"null")
        except ValueError: return e.code, raw.decode("utf-8", "replace")


class Proc:
    def __init__(self, data):
        env = dict(os.environ, HOMELEDGER_DATA=str(data), HOMELEDGER_PORT=str(PORT))
        self.p = subprocess.Popen([sys.executable, "-I", str(ROOT / "HomeLedger.pyw"), "--no-window"], env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        for _ in range(100):
            try:
                if call("/api/ping")[0] == 200: return
            except Exception: time.sleep(0.1)
        raise RuntimeError("server did not start: " + (self.p.stdout.read(2000).decode() if self.p.poll() is not None else ""))

    def kill9(self):
        self.p.kill(); self.p.wait()          # hard kill on every OS (TerminateProcess on Windows, SIGKILL elsewhere)

    def stop(self):
        try: call("/api/quit", {})
        except Exception: pass
        try: self.p.wait(timeout=15)
        except Exception: self.p.kill()


def ledger_ids():
    m = call("/api/masters")[1]
    return {l["name"]: l["id"] for l in m["ledgers"]}


def pay(L, amt, d="2026-11-10"):
    return call("/api/voucher/save", {"vtype": "Payment", "date": d, "lines": [
        {"ledger_id": L["Water Bill"], "side": "Dr", "amount": amt}, {"ledger_id": L["Cash"], "side": "Cr", "amount": amt}]})


class TestServer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True); self.data = Path(self.tmp.name)
        self.pr = Proc(self.data)

    def tearDown(self):
        self.pr.stop(); self.tmp.cleanup()

    def test_security_and_errors(self):
        self.assertEqual(call("/api/voucher/save", {}, headers={"X-HomeLedger": "0"})[0], 403)        # other websites cannot post
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}/api/masters", headers={"Host": "evil.example"})
        with self.assertRaises(urllib.error.HTTPError) as cm: urllib.request.urlopen(req)
        self.assertEqual(cm.exception.code, 403)                                                         # DNS-rebinding guard
        self.assertEqual(call("/../../etc/passwd")[0], 404)
        s, r = call("/api/voucher/save", {"vtype": "Payment", "date": "2026-11-10", "lines": "junk"})
        self.assertEqual(s, 400); self.assertIn("error", r)
        self.assertEqual(call("/api/nope")[0], 404)
        s, r = call("/api/voucher/save", {"vtype": "Payment"}, timeout=5); self.assertEqual(s, 400)
        self.assertEqual(call("/api/dashboard?from=2026-04-01&to=2027-03-31")[0], 200)                  # empty books must not crash anything
        for path in ("/api/tb", "/api/pnl", "/api/bs", "/api/activities", "/api/commodities", "/api/daybook", "/api/search"):
            self.assertEqual(call(f"{path}?from=2026-04-01&to=2027-03-31")[0], 200, path)

    def test_concurrent_writes_unique_numbers(self):
        L = ledger_ids(); out = []
        def work(i):
            for _ in range(15):
                out.append(pay(L, "10.00")[0])
        ts = [threading.Thread(target=work, args=(i,)) for i in range(8)]
        [t.start() for t in ts]; [t.join() for t in ts]
        self.assertEqual(set(out), {200})
        rows = call("/api/daybook?from=2026-04-01&to=2027-03-31")[1]["rows"]
        nums = sorted(r["number"] for r in rows)
        self.assertEqual(nums, list(range(1, 121)))

    def test_hard_kill_then_restart_is_consistent(self):
        L = ledger_ids(); stop = threading.Event(); n = [0]
        def work():
            while not stop.is_set():
                try:
                    if pay(L, "25.50")[0] == 200: n[0] += 1
                except Exception: return
        t = threading.Thread(target=work); t.start(); time.sleep(1.5)
        self.pr.kill9(); stop.set(); t.join()
        self.assertGreater(n[0], 5)
        self.pr = Proc(self.data)
        h = call("/api/health")[1]
        self.assertTrue(h["all_ok"], h)
        rows = call("/api/daybook?from=2026-04-01&to=2027-03-31")[1]["rows"]
        self.assertGreaterEqual(len(rows), n[0]); self.assertLessEqual(len(rows), n[0] + 1)             # every acknowledged save survived
        tb = call("/api/tb?from=2026-04-01&to=2027-03-31")[1]
        self.assertEqual(tb["closing_dr"], tb["closing_cr"])

    def test_corrupt_database_restored_from_backup(self):
        L = ledger_ids()
        for i in range(5): self.assertEqual(pay(L, "100")[0], 200)
        self.assertEqual(call("/api/backup/create", {})[0], 200)
        self.pr.stop()
        db = self.data / "homeledger.db"
        for ext in ("-wal", "-shm"): (self.data / ("homeledger.db" + ext)).unlink(missing_ok=True)
        raw = bytearray(db.read_bytes()); raw[4096 * 2: 4096 * 2 + 8000] = os.urandom(8000); db.write_bytes(bytes(raw))
        self.pr = Proc(self.data)
        st = call("/api/status")[1]
        self.assertIn("restored", (st["notice"] or "").lower())
        self.assertEqual(len(call("/api/daybook?from=2026-04-01&to=2027-03-31")[1]["rows"]), 5)
        self.assertTrue(list(self.data.glob("homeledger-damaged-*.db")))                               # the bad file is kept, not deleted

    def test_garbage_file_without_backup_starts_fresh(self):
        self.pr.stop(); shutil_rm = [p.unlink() for p in (self.data / "backups").glob("*")]
        (self.data / "homeledger.db").write_bytes(b"this is not a database" * 400)
        for ext in ("-wal", "-shm"): (self.data / ("homeledger.db" + ext)).unlink(missing_ok=True)
        self.pr = Proc(self.data)
        self.assertIn("new", (call("/api/status")[1]["notice"] or "").lower())
        self.assertEqual(call("/api/health")[1]["all_ok"], True)

    def test_backup_restore_roundtrip_over_api(self):
        L = ledger_ids(); pay(L, "100"); b = call("/api/backup/create", {})[1]["name"]
        pay(L, "200"); pay(L, "300")
        self.assertEqual(call("/api/backup/restore", {"name": b})[0], 200)
        self.assertEqual(len(call("/api/daybook?from=2026-04-01&to=2027-03-31")[1]["rows"]), 1)
        self.assertEqual(call("/api/backup/restore", {"name": "../../x.db"})[0], 400)
        self.assertTrue(any(x["reason"] == "pre-restore" for x in call("/api/backups")[1]["rows"]))     # undo copy exists

    def test_second_instance_does_not_start_second_server(self):
        env = dict(os.environ, HOMELEDGER_DATA=str(self.data), HOMELEDGER_PORT=str(PORT))
        r = subprocess.run([sys.executable, "-I", str(ROOT / "HomeLedger.pyw"), "--no-window"], env=env, timeout=20)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(call("/api/ping")[0], 200)

    def test_exits_quickly_when_window_says_closing_and_survives_reload(self):
        self.pr.stop()
        env = dict(os.environ, HOMELEDGER_DATA=str(self.data), HOMELEDGER_PORT=str(PORT))
        code = "import homeledger.server as s; s.CLOSE_SECONDS=3; from homeledger.main import run; run(['--no-window'])"
        p = subprocess.Popen([sys.executable, "-I", "-c", f"import sys; sys.path.insert(0, {str(ROOT)!r}); {code}"], env=env)
        for _ in range(50):
            try:
                if call("/api/ping")[0] == 200: break
            except Exception: time.sleep(0.1)
        call("/api/closing", {}); time.sleep(0.5); call("/api/ping")            # a reload: closing then a new ping
        time.sleep(4); self.assertIsNone(p.poll())                               # still running
        call("/api/closing", {})                                                 # really closed
        p.wait(timeout=15); self.assertEqual(p.returncode, 0)
        self.pr = Proc(self.data)

    def test_exits_when_window_closed(self):
        self.pr.stop()
        env = dict(os.environ, HOMELEDGER_DATA=str(self.data), HOMELEDGER_PORT=str(PORT))
        code = "import homeledger.server as s; s.GRACE_SECONDS=4; s.CLOSE_SECONDS=2; s.FIRST_PING_SECONDS=30; from homeledger.main import run; run(['--no-window'])"
        p = subprocess.Popen([sys.executable, "-I", "-c", f"import sys; sys.path.insert(0, {str(ROOT)!r}); {code}"], env=env)
        for _ in range(50):
            try:
                if call("/api/ping")[0] == 200: break
            except Exception: time.sleep(0.1)
        self.assertIsNone(p.poll())
        p.wait(timeout=20)                                      # no further pings -> must exit by itself
        self.assertEqual(p.returncode, 0)
        self.assertTrue(any((self.data / "backups").glob("*.db")))
        self.pr = Proc(self.data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
