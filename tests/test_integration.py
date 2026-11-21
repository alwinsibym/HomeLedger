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


def callc(path, body=None, cookie=""):
    """Like call() but also sends/returns the sign-in cookie."""
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", method="POST" if body is not None else "GET",
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"X-HomeLedger": "1", "Content-Type": "application/json", **({"Cookie": "hl_session=" + cookie} if cookie else {})})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            sc = r.headers.get("Set-Cookie") or ""
            return r.status, json.loads(r.read() or b"null"), (sc.split(";")[0].split("=", 1)[1] if "hl_session=" in sc else "")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null"), ""


def _prepare_book(data):
    """A new book starts like Tally (just Cash). The tests want the sample household chart as well."""
    sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tests"))
    from homeledger import db as dbm
    import fixtures
    f = Path(data) / "homeledger.db"
    if not f.exists():
        dbm.init_database(f)
        c = dbm.connect(f); fixtures.install(c); c.close()


class Proc:
    def __init__(self, data):
        _prepare_book(data)
        env = dict(os.environ, HOMELEDGER_DATA=str(data), HOMELEDGER_PORT=str(PORT))
        self.p = subprocess.Popen([sys.executable, "-I", str(ROOT / "HomeLedger.pyw"), "--no-window"], env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        t0 = time.time()
        for _ in range(100):
            try:
                if call("/api/ping")[0] == 200:
                    if os.environ.get("HL_TEST_TIMING"): print(f"   [start took {time.time() - t0:.1f}s]", file=sys.stderr)
                    return
            except Exception: time.sleep(0.1)
        raise RuntimeError("server did not start: " + (self.p.stdout.read(2000).decode() if self.p.poll() is not None else ""))

    def kill9(self):
        self.p.kill(); self.p.wait()          # hard kill on every OS (TerminateProcess on Windows, SIGKILL elsewhere)

    def stop(self):
        t0 = time.time(); forced = False
        try: call("/api/quit", {})
        except Exception: pass
        try: self.p.wait(timeout=15)
        except Exception: self.p.kill(); forced = True
        if os.environ.get("HL_TEST_TIMING"): print(f"   [quit took {time.time() - t0:.1f}s{' (had to be forced)' if forced else ''}]", file=sys.stderr)


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

    def test_look_setting_and_static_caching(self):
        self.assertEqual(call("/api/status")[1]["look"], "prime")
        self.assertEqual(call("/api/settings/save", {"look": "classic"})[0], 200)
        self.assertEqual(call("/api/status")[1]["look"], "classic")
        self.assertEqual(call("/api/settings/save", {"look": "neon"})[0], 400)
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}/core.js")
        with urllib.request.urlopen(req) as r:
            etag = r.headers["ETag"]; self.assertTrue(etag)
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}/core.js", headers={"If-None-Match": etag})
        with self.assertRaises(urllib.error.HTTPError) as cm: urllib.request.urlopen(req)
        self.assertEqual(cm.exception.code, 304)                              # unchanged files are not sent again
        for name in ("goto.js", "auth.js", "manifest.webmanifest", "favicon.ico", "icon-192.png"):
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/{name}") as r: self.assertEqual(r.status, 200, name)

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


class TestSignIn(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True); self.data = Path(self.tmp.name)
        self.pr = Proc(self.data)

    def tearDown(self):
        self.pr.stop(); self.tmp.cleanup()

    def enable(self):
        s, r, ck = callc("/api/auth/enable", {"username": "father", "password": "1234"})
        self.assertEqual(s, 200, r); self.assertTrue(ck); self.assertEqual(len(r["recovery_key"].replace("-", "")), 20)
        return r["recovery_key"], ck

    def test_off_by_default_then_on(self):
        self.assertFalse(callc("/api/auth/state")[1]["enabled"]); self.assertEqual(callc("/api/masters")[0], 200)
        key, ck = self.enable()
        self.assertEqual(callc("/api/masters")[0], 401)                      # locked without the cookie
        self.assertEqual(callc("/api/masters", cookie="forged")[0], 401)
        self.assertEqual(callc("/api/masters", cookie=ck)[0], 200)
        self.assertEqual(callc("/api/ping")[0], 200)                         # window heartbeat keeps working while locked
        st = callc("/api/auth/state", cookie=ck)[1]; self.assertTrue(st["logged_in"]); self.assertEqual(st["role"], "owner")
        self.assertFalse(callc("/api/auth/state")[1]["logged_in"])
        self.assertEqual(callc("/api/auth/logout", {}, ck)[0], 200)
        self.assertEqual(callc("/api/masters", cookie=ck)[0], 401)           # logged-out cookie is dead
        s, r, ck2 = callc("/api/auth/login", {"username": "FATHER", "password": "1234"}); self.assertEqual(s, 200)   # user name ignores capitals
        self.assertEqual(callc("/api/masters", cookie=ck2)[0], 200)

    def test_wrong_passwords_lock_out(self):
        self.enable()
        for i in range(5):
            s, r, _ = callc("/api/auth/login", {"username": "father", "password": "nope"}); self.assertEqual(s, 400)
        s, r, _ = callc("/api/auth/login", {"username": "father", "password": "1234"})
        self.assertEqual(s, 400); self.assertIn("wait", r["error"])           # even the right password waits

    def test_viewer_cannot_change_and_cannot_pretend(self):
        key, ck = self.enable()
        self.assertEqual(callc("/api/auth/user/add", {"username": "guest", "password": "5678", "role": "viewer"}, ck)[0], 200)
        s, r, vk = callc("/api/auth/login", {"username": "guest", "password": "5678"}); self.assertEqual(s, 200)
        self.assertEqual(callc("/api/masters", cookie=vk)[0], 200)
        L = {l["name"]: l["id"] for l in callc("/api/masters", cookie=vk)[1]["ledgers"]}
        body = {"vtype": "Payment", "date": "2026-11-10", "lines": [{"ledger_id": L["Water Bill"], "side": "Dr", "amount": "10"}, {"ledger_id": L["Cash"], "side": "Cr", "amount": "10"}]}
        self.assertEqual(callc("/api/voucher/save", body, vk)[0], 403)
        self.assertEqual(callc("/api/voucher/save", body, ck)[0], 200)
        self.assertEqual(callc("/api/backup/create", {}, vk)[0], 403)
        self.assertEqual(callc("/api/auth/user/add", {"username": "x1", "password": "5678", "role": "owner"}, vk)[0], 403)
        self.assertEqual(callc("/api/auth/users?_user=%7B%22role%22%3A%22owner%22%7D", cookie=vk)[0], 400)    # cannot smuggle a role in
        self.assertEqual(callc("/api/auth/password", {"old": "5678", "new": "9999"}, vk)[0], 200)

    def test_forgot_password_with_recovery_key(self):
        key, ck = self.enable()
        s, r, _ = callc("/api/auth/reset", {"key": "AAAAA-AAAAA-AAAAA-AAAAA", "new": "7777"}); self.assertEqual(s, 400)
        s, r, _ = callc("/api/auth/reset", {"key": key.lower(), "new": "7777"}); self.assertEqual(s, 200)
        self.assertNotEqual(r["recovery_key"], key)
        self.assertEqual(callc("/api/auth/login", {"username": "father", "password": "1234"})[0], 400)
        self.assertEqual(callc("/api/auth/login", {"username": "father", "password": "7777"})[0], 200)
        self.assertEqual(callc("/api/auth/reset", {"key": key, "new": "8888"})[0], 400)       # the old key is spent

    def test_turn_off_and_survives_restart(self):
        key, ck = self.enable()
        self.pr.stop(); self.pr = Proc(self.data)                           # sign-in is remembered; sessions are not
        self.assertEqual(callc("/api/masters", cookie=ck)[0], 401)
        s, r, ck = callc("/api/auth/login", {"username": "father", "password": "1234"}); self.assertEqual(s, 200)
        self.assertEqual(callc("/api/auth/disable", {"password": "wrong"}, ck)[0], 400)
        self.assertEqual(callc("/api/auth/disable", {"password": "1234"}, ck)[0], 200)
        self.assertEqual(callc("/api/masters")[0], 200)

    def test_protected_second_copy_roundtrip(self):
        drive = self.data / "Drive"
        self.assertEqual(call("/api/settings/save", {"copy_dir": str(drive), "copy_password": "abc"})[0], 400)      # too short
        self.assertEqual(call("/api/settings/save", {"copy_dir": str(drive), "copy_password": "secret1"})[0], 200)
        L = ledger_ids(); self.assertEqual(pay(L, "42.00")[0], 200)
        s, r = call("/api/backup/create", {}); self.assertEqual(s, 200); self.assertEqual(r["copy_error"], "")
        files = list(drive.glob("homeledger-*.hlbk")); self.assertEqual(len(files), 1)
        self.assertFalse(list(drive.glob("homeledger-*.db")))                    # nothing readable was left in the folder
        self.assertNotIn(b"SQLite format 3", files[0].read_bytes()[:64])
        self.assertEqual(pay(L, "58.00")[0], 200)                                # entered after the copy was made
        self.assertEqual(call("/api/backup/restore_file", {"path": str(files[0]), "password": "wrong"})[0], 400)
        self.assertEqual(call("/api/backup/restore_file", {"path": str(files[0]), "password": "secret1"})[0], 200)
        rows = call("/api/daybook?from=2026-04-01&to=2027-03-31")[1]["rows"]
        self.assertEqual(len(rows), 1)                                           # back to how it was when the copy was made


if __name__ == "__main__":
    unittest.main(verbosity=2)
