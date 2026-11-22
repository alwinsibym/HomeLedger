# HomeLedger

HOMELEDGER  -  household and farm accounts, in the style of Tally ERP 9
=====================================================================
Works completely offline on one Windows PC. Nothing is sent anywhere.
Your data: %LOCALAPPDATA%\HomeLedger   (homeledger.db + backups folder + logs)

1. INSTALL (first time)
-----------------------
A) Computer that has Python 3:   double-click  Install_HomeLedger.bat
B) Computer without Python:      on a computer WITH Python run build_exe.bat once; copy the folder
                                 dist\HomeLedger to the other PC; run Create_Desktop_Icon.bat inside it.
Either way you get a "HomeLedger" icon on the Desktop and in the Start menu. Double-click it.
HomeLedger opens in its own window (it uses Microsoft Edge or Chrome, which are already on Windows).
When the window is closed the program finishes by itself and makes a backup.

2. FIRST-TIME SETUP (10 minutes)
--------------------------------
 - Gateway > Company Info (F3): type the name and the date the books begin (start of the oldest notebook year).
 - Gateway > Opening Balances (O): enter cash in hand, bank balance, land, loans, money lent/borrowed.
   The Difference line must say "Balanced". Put any remainder on "Capital Account" as Cr.
 - Utilities > Backup: choose a SECOND COPY folder on a pen drive / external disk / OneDrive.
 - Then enter entries daily. Copying old notebooks: tick "Date is approximate" when the exact date is unknown,
   and write the notebook page in Reference.

3. KEYS (same habit as Tally)
-----------------------------
 Gateway: arrow keys + Enter, or press the highlighted letter.      Esc = go back
 F4 Contra   F5 Payment   F6 Receipt   F7 Journal   F8 Sales   F9 Purchase
 Enter = next box.   Ctrl+A = Accept (save).   F2 (in a voucher) = change the date.
 In an account box: type a few letters, arrows, Enter.  Last choice "+ Create ledger" adds a new account on the spot.
 Ctrl+F = search anywhere.   Alt+F1 = Dashboard.   Alt+C = create (in Masters).
 After the last amount in a voucher press Enter to add another line; Enter on the empty line goes to Narration.

 Which voucher?
   Spent money (cash or bank)      -> Payment (F5)
   Received money                  -> Receipt (F6)
   Cash <-> Bank (withdraw/deposit)-> Contra (F4)
   Bill not paid yet / adjustments -> Journal (F7) (cannot touch Cash or Bank)

4. WHAT YOU GET
---------------
 Dashboard      cash, bank, net worth, this month vs last month, income vs spending, household vs farm,
                where money went, top items, plain-language "what stands out"
 Day Book       every entry by day, filter by type or words;  Enter opens an entry to correct it
 Search         by words, amount, date, account, activity, item  (Ctrl+F)
 Ledger / Cash-Bank Book / Trial Balance / Profit & Loss / Balance Sheet   (Tally-style, click any line to drill down)
 Activities     income, spending and surplus for Rubber, Cattle, Goats, Coffee ... and Household; tag any line
 Commodities    every item you typed (Urea, Milk, Rubber sheet): totals, average price paid / received
 Export         everything to Excel (CSV) from Utilities

 Tip: in a voucher line fill Item (+ Qty and Unit) when you buy or sell something worth tracking.
 The "Activity" box tags the line to Rubber / Cattle / Household ... it is filled in automatically for most accounts.

5. KEEPING IT SAFE
------------------
 - Every entry is saved the moment you press Accept, with all-or-nothing safety against power cuts.
 - Automatic backups: at start, about hourly while working, and when the window closes. Old ones are thinned out.
 - A second copy of each backup goes to your pen-drive/cloud folder (Utilities > Backup). Set this up!
 - Entries are never deleted: "Cancel voucher" strikes them out; the Audit Trail lists every change.
 - If the data file is ever damaged, HomeLedger restores the latest good backup by itself and tells you.
 - Utilities > Health Check verifies the books at any time.
 - To move to a new PC: install HomeLedger there, then Utilities > Backup > or copy the folder
   %LOCALAPPDATA%\HomeLedger from the old PC.

6. NOTES
--------
 - No internet needed. No account. Nothing to pay.
 - The program only listens inside this computer (127.0.0.1), never on the network.
 - Text too small? Utilities > Settings > Text size.
 - Run_Tests.bat runs the built-in self-tests (for whoever maintains it).
 - If something ever fails to start, give the file  %LOCALAPPDATA%\HomeLedger\logs\homeledger.log  to the person who set it up.


SIGN-IN AND BACKUP PASSWORD (new in 1.2)
----------------------------------
Utilities > Security: turn on a user name + password (or a short PIN). It asks every time HomeLedger opens,
locks itself when idle (Ctrl+L locks at once), and allows 'view only' users. Write down the RECOVERY KEY shown once:
it is the only way back in if the password is forgotten.
Utilities > Backup & Restore: you can password-protect the second copy (use this for Google Drive / OneDrive folders).
KEEP THAT PASSWORD SAFE. Protected copies end in .hlbk and are restored from the same screen.
The bar at the bottom shows: Saved, Last backup, Second copy, Offline.


LOOK, GO TO AND INSTALLER (new in 1.3)
-------------------------------------
Alt+G opens Go To: type a few letters of any report, ledger, voucher or activity and press Enter.
The menu bar (Go To, Company, Data, Export, Print, Lock, F1 Help) works with the mouse or Alt+letter.
Utilities > Settings > Look switches between TallyPrime style (default) and Classic (Tally ERP 9 style).
HomeLedger-Setup-x.y.z.exe (built on GitHub, see installer\ and .github\) installs without Python and adds an
uninstaller in Windows Settings > Apps. Uninstalling asks before touching your accounts; the default is to keep them.

## User guide

A step-by-step guide with screenshots and a shortcut map is in [docs/USER_GUIDE.md](docs/USER_GUIDE.md) (printable PDF: [docs/HomeLedger_Guide.pdf](docs/HomeLedger_Guide.pdf)). Inside the app: Gateway, G (Guide and Help), or Shift+F1.
