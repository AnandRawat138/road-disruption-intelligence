# Process helpers for start.bat / stop.bat.
# Identifies ONLY the backend started from this project folder: the command line must contain
# "rdi.server" and the process (or its parent launcher) must be this project's .venv python.
param(
  [Parameter(Mandatory = $true)][ValidateSet('find', 'verify', 'alive')][string]$Action,
  [int]$ProcId = 0,
  [Parameter(Mandatory = $true)][string]$Root
)
$ErrorActionPreference = 'SilentlyContinue'
$venv = [System.IO.Path]::GetFullPath((Join-Path $Root '.venv\Scripts\python.exe'))

function Test-Ours($p) {
  if (-not $p) { return $false }
  if ($p.CommandLine -notlike '*rdi.server*') { return $false }
  if ($p.ExecutablePath -and ([System.IO.Path]::GetFullPath($p.ExecutablePath) -ieq $venv)) { return $true }
  $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($p.ParentProcessId)"
  return ($parent -and $parent.ExecutablePath -and ([System.IO.Path]::GetFullPath($parent.ExecutablePath) -ieq $venv))
}

switch ($Action) {
  'verify' {
    $p = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcId"
    if (Test-Ours $p) { exit 0 } else { exit 1 }
  }
  'alive' {
    if (Get-Process -Id $ProcId) { exit 0 } else { exit 1 }
  }
  'find' {
    $ours = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { Test-Ours $_ }
    # Prefer the venv launcher (killing its tree stops the interpreter too).
    $launcher = $ours | Where-Object { $_.ExecutablePath -and ([System.IO.Path]::GetFullPath($_.ExecutablePath) -ieq $venv) } | Select-Object -First 1
    $pick = if ($launcher) { $launcher } else { $ours | Select-Object -First 1 }
    if ($pick) { Write-Output $pick.ProcessId; exit 0 } else { exit 1 }
  }
}
