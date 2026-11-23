HOMELEDGER  -  accounts for the home and small business, in the style of Tally
=====================================================================
Works completely offline on one Windows PC. Nothing is sent anywhere.
Your data: %LOCALAPPDATA%\HomeLedger   (homeledger.db + backups folder + logs)

START HERE
----------
 - Open HomeLedger. A one-minute tour appears the first time.
 - Gateway > G (Guide and Help) has a step-by-step guide with pictures, a shortcut map and answers to common questions.
 - Shift+F1 shows the key list at any time.

FIRST TEN MINUTES
-----------------
 1. F3 Company Info: type the name and the date the books begin.
 2. Gateway > M (Masters) > O (Opening Balances): cash, bank, loans, money others owe you. Once only.
 3. Utilities > Backup: choose a SECOND COPY folder on a pen drive or external disk.
 4. F5 = Payment, F6 = Receipt. Enter moves to the next box, Ctrl+A saves.

MAIN KEYS
---------
 F4 Contra   F5 Payment   F6 Receipt   F7 Journal   F8 Sales   F9 Purchase
 Alt+G Go To (type any screen or ledger)   Ctrl+F Search   Alt+F1 Dashboard   F1 Companies   Esc Back
 Ctrl+P Print or Save as PDF   Save as Excel button on every report

KEEPING IT SAFE
---------------
 - Every entry is saved the moment you press Accept, safe against power cuts.
 - Automatic backups at start, about hourly while working, and on close. Set the second copy folder!
 - Entries are cancelled, never deleted; the Audit Trail lists every change.
 - Utilities > Health Check verifies the books; Data Repair fixes common problems (it copies first).
 - To move to a new PC: install HomeLedger there and restore a backup, or copy %LOCALAPPDATA%\HomeLedger.
 - Utilities > Security turns on a password and roles (Owner, Accountant, Data entry, Viewer).
   Write down the recovery key shown once.

NOTES
-----
 - No internet needed. No account. Nothing to pay. The program listens only inside this computer (127.0.0.1).
 - GST, TDS and payroll are first versions: have an accountant check the rates before filing anything.
 - Text too small? Utilities > Settings > Text size.
 - If something fails to start, give the file %LOCALAPPDATA%\HomeLedger\logs\homeledger.log to whoever set it up.
 - Full guide: docs\USER_GUIDE.md and docs\HomeLedger_Guide.pdf in the project on GitHub.
 - Malayalam guide: docs\USER_GUIDE_ML.md and docs\HomeLedger_Guide_Malayalam.pdf. In the app, use the EN / Malayalam switch in the Guide.
