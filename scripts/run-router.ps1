$ErrorActionPreference = 'Stop'

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$venvPython = Join-Path $root '.venv\Scripts\python.exe'
$litellmExe = Join-Path $root '.venv\Scripts\litellm.exe'
$dataDir = Join-Path $env:LOCALAPPDATA 'opencode-free-router'
$log = Join-Path $dataDir 'routeur.log'

New-Item -ItemType Directory -Path $dataDir -Force | Out-Null

function Write-RouteurLog {
    param([string]$Message)
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message"
    Add-Content -LiteralPath $log -Value $line -Encoding UTF8
}

if (Test-Path -LiteralPath $log) {
    $taille = (Get-Item -LiteralPath $log).Length
    if ($taille -gt 10MB) {
        Move-Item -LiteralPath $log -Destination "$log.1" -Force
    }
}

try {
    $null = Invoke-RestMethod -Uri 'http://127.0.0.1:4000/health/liveliness' -TimeoutSec 2
    Write-RouteurLog 'Routeur deja actif, aucun demarrage.'
    exit 0
} catch {
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-RouteurLog "ERREUR: venv absent: $venvPython"
    exit 1
}

$env:OLLAMA_API_BASE = 'http://localhost:11434'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

if ([string]::IsNullOrWhiteSpace($env:LITELLM_MASTER_KEY)) {
    $env:LITELLM_MASTER_KEY = [Environment]::GetEnvironmentVariable('LITELLM_MASTER_KEY', 'User')
}
if ([string]::IsNullOrWhiteSpace($env:LITELLM_MASTER_KEY)) {
    Write-RouteurLog 'ERREUR: LITELLM_MASTER_KEY absente. Relancer scripts/installer.ps1.'
    exit 1
}

& $venvPython (Join-Path $root 'scripts\render-config.py') *>> $log
if ($LASTEXITCODE -ne 0) {
    Write-RouteurLog 'ERREUR: rendu de la configuration impossible.'
    exit 1
}

$config = Join-Path $dataDir 'litellm-config.yaml'
if (-not (Test-Path -LiteralPath $config)) {
    Write-RouteurLog "ERREUR: configuration absente: $config"
    exit 1
}

# Prechauffage Ollama (num_ctx 32768, keep_alive 30m) et mesure de vitesse.
try {
    $body = @{ model = 'qwen2.5-coder:7b'; prompt = 'Reponds OK.'; stream = $false; keep_alive = '30m'
               options = @{ num_ctx = 32768; num_predict = 40 } } | ConvertTo-Json -Depth 4
    $r = Invoke-RestMethod -Uri 'http://localhost:11434/api/generate' -Method Post -Body $body -ContentType 'application/json' -TimeoutSec 180
    $tps = if ($r.eval_duration -gt 0) { [math]::Round($r.eval_count / ($r.eval_duration / 1e9), 1) } else { 0 }
    $etat = if ($tps -lt 10) { 'secours lent' } else { 'secours rapide' }
    Write-RouteurLog "Ollama precharge: $tps tokens/s ($etat)."
    Set-Content -LiteralPath (Join-Path $dataDir 'ollama-vitesse.txt') -Value "$tps;$etat" -Encoding UTF8
    if ($tps -lt 10) { Write-Host "Ollama : secours lent ($tps tokens/s)" -ForegroundColor Yellow }
} catch {
    Write-RouteurLog "Ollama indisponible au prechauffage: $($_.Exception.Message)"
}

# Serveur du message "quotas epuises" sur 127.0.0.1:4010, si pas deja lance.
try {
    $null = Invoke-RestMethod -Uri 'http://127.0.0.1:4010/health' -TimeoutSec 2
} catch {
    Start-Process -FilePath $venvPython -ArgumentList (Join-Path $PSScriptRoot 'epuise.py') -WindowStyle Hidden
}

# Auto-reglage (V4) : banc court au demarrage puis toutes les 2 h, en tache de fond.
$autoreg = Join-Path $PSScriptRoot 'autoreglage.py'
Start-Job -ScriptBlock {
    param($py, $script)
    Start-Sleep -Seconds 45
    while ($true) {
        & $py $script
        Start-Sleep -Seconds 7200
    }
} -ArgumentList $venvPython, $autoreg | Out-Null

$flag = Join-Path $dataDir 'redemarrer.flag'
$previous = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
do {
    Remove-Item -LiteralPath $flag -ErrorAction SilentlyContinue
    & $venvPython (Join-Path $root 'scripts\render-config.py') *>> $log
    Write-RouteurLog 'Demarrage de LiteLLM sur 127.0.0.1:4000.'
    if (Test-Path -LiteralPath $litellmExe) {
        & $litellmExe --config $config --host 127.0.0.1 --port 4000 *>> $log
    } else {
        & $venvPython -m litellm --config $config --host 127.0.0.1 --port 4000 *>> $log
    }
    $code = $LASTEXITCODE
    Write-RouteurLog "LiteLLM arrete (code $code)."
    $relance = Test-Path -LiteralPath $flag
    if ($relance) { Write-RouteurLog 'Redemarrage demande par l auto-reglage.' }
} while ($relance)
$ErrorActionPreference = $previous
exit $code
