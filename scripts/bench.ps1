param([switch]$Court, [switch]$Rapport, [string]$Seulement)
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$py = Join-Path $root '.venv\Scripts\python.exe'
$a = @((Join-Path $PSScriptRoot 'bench.py'))
if ($Court) { $a += '--court' }
if ($Rapport) { $a += '--rapport' }
if ($Seulement) { $a += @('--seulement', $Seulement) }
$env:PYTHONUTF8 = '1'
& $py @a
exit $LASTEXITCODE
