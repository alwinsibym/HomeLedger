r"""Send HomeLedger's source code to GitHub in small, meaningful commits (one push per batch).

Usage:   py tools\push_in_batches.py [https://github.com/YOU/REPO.git]
The address is needed only the first time; it is remembered afterwards.
Safe to run again whenever you change something: only changed groups are committed.
GitHub gets the PROGRAM only. Your accounting data (.db files, backups) is never uploaded.
"""
import subprocess, sys, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BATCHES = [  # (commit message, paths)
    ("Add project housekeeping: ignore rules and readme", [".gitignore", "README.txt"]),
    ("Add core: errors, configuration and money handling", ["homeledger/__init__.py", "homeledger/errors.py", "homeledger/config.py", "homeledger/money.py"]),
    ("Add database layer: schema, safe transactions, audit log", ["homeledger/db.py", "homeledger/auth.py"]),
    ("Add accounting engine: vouchers, ledgers, activities", ["homeledger/service.py"]),
    ("Add reports: trial balance, P&L, balance sheet, dashboard, search", ["homeledger/reports.py"]),
    ("Add backup, rotation, restore and damaged-file recovery", ["homeledger/backup.py"]),
    ("Add local server, start-up and window handling", ["homeledger/server.py", "homeledger/main.py", "HomeLedger.pyw"]),
    ("Add screen foundations: page, styles, helpers, charts", ["homeledger/static/index.html", "homeledger/static/style.css", "homeledger/static/core.js", "homeledger/static/charts.js", "homeledger/static/auth.js", "homeledger/static/goto.js"]),
    ("Add gateway, dashboard, voucher entry and day book screens", ["homeledger/static/screens_a.js"]),
    ("Add ledger, reports, activities, commodities and search screens", ["homeledger/static/screens_b.js"]),
    ("Add masters, openings, company and utilities screens", ["homeledger/static/screens_c.js", "homeledger/static/app.js"]),
    ("Add logo, icons and branding files", ["homeledger/static/icon.png", "homeledger/static/icon-192.png", "homeledger/static/icon-512.png", "homeledger/static/logo.png", "homeledger/static/favicon.ico", "homeledger/static/manifest.webmanifest", "homeledger.ico", "branding"]),
    ("Add Windows installer (Setup.exe, uninstaller) and automatic build on GitHub", ["installer", ".github"]),
    ("Add automated tests", ["tests"]),
    ("Add Windows install, build and test scripts", ["Install_HomeLedger.bat", "build_exe.bat", "make_shortcut.ps1", "Run_Tests.bat", "Push_To_GitHub.bat"]),
    ("Add tools: demo data and this upload script", ["tools"]),
]

def git(*a, check=True, capture=True):
    r = subprocess.run(["git", *a], cwd=ROOT, text=True, capture_output=capture)
    if check and r.returncode:
        sys.exit("\nGit said:\n" + (r.stdout + r.stderr).strip())
    return r

def main():
    try: git("--version")
    except FileNotFoundError: sys.exit("Git is not installed. Get it from https://git-scm.com/download/win and run this again.")
    if not (ROOT / ".git").exists():
        git("init", "-b", "main"); print("Started a new local history.")
    if git("config", "user.name", check=False).stdout.strip() == "" or git("config", "user.email", check=False).stdout.strip() == "":
        sys.exit('Tell Git who you are once, then run again:\n  git config --global user.name "Your Name"\n  git config --global user.email "you@example.com"')
    if len(sys.argv) > 1:
        if git("remote", check=False).stdout.split().count("origin"): git("remote", "set-url", "origin", sys.argv[1])
        else: git("remote", "add", "origin", sys.argv[1])
    if "origin" not in git("remote").stdout.split():
        print("Paste the address of your GitHub repository and press Enter.")
        print("Example: https://github.com/yourname/HomeLedger.git")
        url = input("Repository address: ").strip()
        if not url.startswith(("https://", "git@")): sys.exit("That does not look like a repository address. Run again.")
        git("remote", "add", "origin", url)
    branch = git("branch", "--show-current").stdout.strip() or "main"
    listed = set()
    sent = 0
    def commit_paths(msg, paths):
        nonlocal sent
        existing = [p for p in paths if (ROOT / p).exists()]
        if not existing: return
        git("add", "--", *existing)
        if git("diff", "--cached", "--quiet", check=False).returncode == 0: return
        git("commit", "-q", "-m", msg)
        print("Committed:", msg); print("  pushing ...", end=" ", flush=True)
        r = git("push", "-u", "origin", branch, check=False)
        if r.returncode: sys.exit("\nPush failed (your work is safe locally; run again to retry):\n" + (r.stdout + r.stderr).strip())
        print("done"); sent += 1
    for msg, paths in BATCHES:
        commit_paths(msg, paths); listed.update(paths)
    # anything new that is not in a group above goes in its own batch, per top-level folder/file
    out = git("ls-files", "--others", "--exclude-standard").stdout.split("\n")
    groups = {}
    for f in filter(None, out):
        if any(f == p or f.startswith(p.rstrip("/") + "/") for p in listed): continue
        groups.setdefault(f.split("/")[0], []).append(f)
    for top, files in sorted(groups.items()):
        commit_paths("Add " + top, files)
    # changed files that were already tracked are committed per folder too
    changed = [l[3:] for l in git("status", "--porcelain").stdout.split("\n") if l.strip()]
    per = {}
    for f in changed: per.setdefault(f.split("/")[0], []).append(f)
    for top, files in sorted(per.items()):
        commit_paths("Update " + top, files)
    print("\nAll up to date." if not sent else "\n%d batch(es) uploaded. Your accounting data was NOT uploaded." % sent)

main()
