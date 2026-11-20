"""Start-up: single instance, data safety checks, server, app-style window."""
from __future__ import annotations

import json
import logging
import logging.handlers
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

from . import backup as bk
from . import config
from . import db as dbm
from .errors import CorruptDatabase
from .server import App, create_server


T0 = time.time()


def setup_logging():
    handler = logging.handlers.RotatingFileHandler(
        config.log_dir() / "homeledger.log", maxBytes=500_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def ping(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=1.5) as r:
            return json.loads(r.read()).get("app") == "HomeLedger"
    except Exception:
        return False


def message_box(title: str, text: str) -> None:
    """Plain pop-up so a non-technical person sees problems (Windows), else print."""
    try:
        if os.name == "nt":
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, text, title, 0x10)
            return
    except Exception:
        pass
    print(f"{title}: {text}", file=sys.stderr)


def find_browser():
    """An installed Chromium-based browser that can show the program as its own window (Edge ships with Windows)."""
    env = os.environ.get("HOMELEDGER_BROWSER")
    if env and Path(env).exists():
        return env
    cands = []
    if os.name == "nt":
        roots = [os.environ.get(k) for k in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
        for r in filter(None, roots):
            cands += [Path(r) / "Microsoft/Edge/Application/msedge.exe",
                      Path(r) / "Google/Chrome/Application/chrome.exe",
                      Path(r) / "BraveSoftware/Brave-Browser/Application/brave.exe"]
    else:
        for n in ("google-chrome", "chromium", "chromium-browser", "microsoft-edge", "brave-browser"):
            p = shutil.which(n)
            if p:
                cands.append(Path(p))
    for p in cands:
        if p.exists():
            return str(p)
    return None


def open_window(url: str) -> None:
    exe = find_browser()
    if exe:
        profile = config.data_dir() / "window-profile"  # own profile: own window, own size, no clash with their browser
        args = [exe, f"--app={url}", f"--user-data-dir={profile}", "--no-first-run",
                "--no-default-browser-check", "--disable-features=Translate", "--window-size=1366,820"]
        try:
            subprocess.Popen(args, close_fds=True)
            return
        except Exception:
            logging.exception("could not start app window")
    webbrowser.open(url)


def run(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    no_window = "--no-window" in argv
    setup_logging()
    log = logging.getLogger("homeledger")

    # already running? just bring up a window
    for port in range(config.DEFAULT_PORT, config.DEFAULT_PORT + config.PORT_RANGE):
        if ping(port):
            if not no_window:
                open_window(f"http://127.0.0.1:{port}/")
            return 0

    db_file = config.db_path()
    backups = config.backup_dir()
    notice = None
    try:
        try:
            dbm.init_database(db_file)
        except CorruptDatabase as e:
            log.error("database failed integrity check: %s", e)
            good = next((b for b in bk.list_backups(backups)
                         if not _bad(backups / b["name"])), None)
            stamp = time.strftime("%Y%m%d-%H%M%S")
            bad_copy = db_file.with_name(f"homeledger-damaged-{stamp}.db")
            shutil.move(str(db_file), str(bad_copy))
            for ext in ("-wal", "-shm"):
                Path(str(db_file) + ext).unlink(missing_ok=True)
            if good:
                shutil.copy2(backups / good["name"], db_file)
                dbm.init_database(db_file)
                notice = (f"The data file was damaged (probably by a sudden power cut), so HomeLedger restored the "
                          f"latest good backup from {good['when'][:16]}. Entries made after that time may need to "
                          f"be entered again. The damaged file was kept as {bad_copy.name}.")
            else:
                dbm.init_database(db_file)
                notice = ("The data file was damaged and no backup was available, so HomeLedger started with a new "
                          f"empty book. The damaged file was kept as {bad_copy.name} in {db_file.parent}.")
        app = App(db_file, backups)
        app.notice = notice
        httpd = None
        port = config.DEFAULT_PORT
        for port in range(config.DEFAULT_PORT, config.DEFAULT_PORT + config.PORT_RANGE):
            try:
                httpd = create_server(app, port)
                break
            except OSError:
                continue
        if httpd is None:
            raise RuntimeError("No free port for the local server")
    except Exception:
        log.exception("start-up failed")
        message_box("HomeLedger could not start",
                    f"HomeLedger could not start. Your data has not been changed.\n\nPlease tell the person who set "
                    f"this up and give them this file:\n{config.log_dir() / 'homeledger.log'}")
        return 1

    threading.Thread(target=app.watchdog, daemon=True).start()

    def startup_backup():       # in the background, so a slow pen drive or cloud folder never delays opening
        try:
            latest = bk.list_backups(backups)
            today = time.strftime("%Y-%m-%d")
            if not any(b["when"].startswith(today) and b["reason"] == "auto" for b in latest):
                with app.lock:
                    app.snapshot("auto")
        except Exception:
            log.exception("start-up backup failed")
    threading.Thread(target=startup_backup, daemon=True).start()
    url = f"http://127.0.0.1:{port}/"
    log.info("HomeLedger %s serving %s (data: %s) - ready %.2f s after start", config.VERSION, url, db_file,
             time.time() - T0)
    if not no_window:
        threading.Timer(0.6, open_window, args=(url,)).start()
    try:
        httpd.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        app.shutdown()
    finally:
        httpd.server_close()
    log.info("HomeLedger stopped")
    return 0


def _bad(path: Path) -> bool:
    try:
        bk.validate_backup(path)
        return False
    except Exception:
        return True
