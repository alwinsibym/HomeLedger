# Creates the HomeLedger icon on the Desktop and in the Start menu.
# Usage (done for you by Install_HomeLedger.bat):  powershell -File make_shortcut.ps1 -Target <exe or pythonw.exe> [-Arguments <script>]
param(
  [Parameter(Mandatory=$true)][string]$Target,
  [string]$Arguments = ""
)
$WorkDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$icon = Join-Path $WorkDir "homeledger.ico"
$shell = New-Object -ComObject WScript.Shell
$places = @([Environment]::GetFolderPath("Desktop"), (Join-Path ([Environment]::GetFolderPath("Programs")) ""))
foreach ($dir in $places) {
  if (-not (Test-Path $dir)) { continue }
  $lnk = $shell.CreateShortcut((Join-Path $dir "HomeLedger.lnk"))
  $lnk.TargetPath = $Target
  $lnk.Arguments = $Arguments
  $lnk.WorkingDirectory = $WorkDir
  $lnk.IconLocation = $icon
  $lnk.Description = "HomeLedger - household and farm accounts"
  $lnk.Save()
}
Write-Host "Icon created on the Desktop and in the Start menu."
