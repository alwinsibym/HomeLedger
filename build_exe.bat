@echo off
setlocal
cd /d "%~dp0"
title Build HomeLedger.exe
echo.
echo  Building a stand-alone HomeLedger (no Python needed on the computer that will use it)...
echo  This needs internet once, on THIS computer, to download the packaging tool.
echo.
py -3 -m pip install --upgrade pyinstaller
if errorlevel 1 goto failed
py -3 -m PyInstaller --noconfirm --clean --windowed --name HomeLedger --icon homeledger.ico --add-data "homeledger\static;homeledger\static" HomeLedger.pyw
if errorlevel 1 goto failed
copy /y homeledger.ico "dist\HomeLedger\homeledger.ico" >nul
copy /y make_shortcut.ps1 "dist\HomeLedger\make_shortcut.ps1" >nul
(
echo @echo off
echo cd /d "%%~dp0"
echo powershell -NoProfile -ExecutionPolicy Bypass -File "%%~dp0make_shortcut.ps1" -Target "%%~dp0HomeLedger.exe"
echo echo.
echo echo  Done. Double-click the HomeLedger icon on the Desktop.
echo pause
) > "dist\HomeLedger\Create_Desktop_Icon.bat"
echo.
echo  Finished. Copy the whole folder  dist\HomeLedger  to the other computer (for example on a pen drive),
echo  then double-click Create_Desktop_Icon.bat inside it. Existing accounts are not touched.
echo.
pause
exit /b 0

:failed
echo.
echo  The build failed. Make sure Python 3 is installed and this computer is online, then try again.
pause
exit /b 1
