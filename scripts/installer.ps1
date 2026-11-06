$ErrorActionPreference = 'Stop'

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$venv = Join-Path $root '.venv'
$venvPython = Join-Path $venv 'Scripts\python.exe'
$dataDir = Join-Path $env:LOCALAPPDATA 'opencode-free-router'
$log = Join-Path $dataDir 'routeur.log'
$taskName = 'OpenCode-Free-Router'

function Write-Step {
    param([string]$Message)
    Write-Host "==> $Message"
}

function Write-Ok {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "[ATTENTION] $Message" -ForegroundColor Yellow
}

function Write-Err {
    param([string]$Message)
    Write-Host "[ERREUR] $Message" -ForegroundColor Red
}

function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = "$machine;$user"
}

function Invoke-Native {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $FilePath @Arguments 2>&1 | Out-Host
    $code = $LASTEXITCODE
    $ErrorActionPreference = $previous
    return $code
}

function Find-Python312 {
    $directs = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
        (Join-Path $env:ProgramFiles 'Python312\python.exe')
    )
    foreach ($candidate in $directs) {
        if (Test-Path -LiteralPath $candidate) {
            return @{ Exe = $candidate; Args = @() }
        }
    }
    $cmd = Get-Command python3.12 -ErrorAction SilentlyContinue
    if ($cmd) {
        return @{ Exe = $cmd.Source; Args = @() }
    }
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        $code = Invoke-Native -FilePath 'cmd.exe' -Arguments @('/c', 'py -3.12 --version >nul 2>&1')
        if ($code -eq 0) {
            return @{ Exe = 'py'; Args = @('-3.12') }
        }
    }
    return $null
}

function Get-OllamaTags {
    try {
        return Invoke-RestMethod -Uri 'http://localhost:11434/api/tags' -TimeoutSec 5
    } catch {
        return $null
    }
}

function Test-Key {
    param([string]$Name)
    $value = [Environment]::GetEnvironmentVariable($Name, 'User')
    if ([string]::IsNullOrWhiteSpace($value)) {
        $value = [Environment]::GetEnvironmentVariable($Name, 'Process')
    }
    return -not [string]::IsNullOrWhiteSpace($value)
}

Write-Step 'Verification de Python 3.12.'
$python = Find-Python312
if (-not $python) {
    Write-Warn 'Python 3.12 absent, installation via winget.'
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        Write-Err 'winget introuvable. WAITING FOR THE OWNER: installer Python 3.12 manuellement.'
        exit 2
    }
    $code = Invoke-Native -FilePath 'winget' -Arguments @('install', '--id', 'Python.Python.3.12', '-e', '--scope', 'user', '--accept-source-agreements', '--accept-package-agreements', '--silent')
    if ($code -ne 0) {
        Write-Warn 'Installation utilisateur refusee, nouvel essai sans --scope user.'
        $code = Invoke-Native -FilePath 'winget' -Arguments @('install', '--id', 'Python.Python.3.12', '-e', '--accept-source-agreements', '--accept-package-agreements', '--silent')
    }
    Refresh-Path
    Start-Sleep -Seconds 3
    $python = Find-Python312
}
if (-not $python) {
    Write-Err 'Python 3.12 introuvable apres installation. WAITING FOR THE OWNER.'
    exit 2
}
Write-Ok "Python 3.12: $($python.Exe) $($python.Args -join ' ')"

Write-Step 'Creation du venv dedie.'
if (-not (Test-Path -LiteralPath $venvPython)) {
    $venvArgs = @($python.Args) + @('-m', 'venv', $venv)
    $code = Invoke-Native -FilePath $python.Exe -Arguments $venvArgs
    if ($code -ne 0) {
        Write-Err "Creation du venv impossible (code $code)."
        exit 1
    }
}
if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Err "Creation du venv impossible: $venvPython"
    exit 1
}
Write-Ok "Venv: $venv"

Write-Step 'Installation de LiteLLM Proxy.'
$code = Invoke-Native -FilePath $venvPython -Arguments @('-m', 'pip', 'install', '--upgrade', 'pip')
if ($code -ne 0) {
    Write-Err 'Mise a jour de pip impossible.'
    exit 1
}
$code = Invoke-Native -FilePath $venvPython -Arguments @('-m', 'pip', 'install', '-r', (Join-Path $root 'requirements.txt'))
if ($code -ne 0) {
    Write-Err 'Installation de LiteLLM impossible.'
    exit 1
}
Write-Ok 'LiteLLM installe.'

Write-Step 'Verification d''Ollama et du modele qwen2.5-coder:7b.'
$tags = Get-OllamaTags
if (-not $tags) {
    $ollama = Get-Command ollama -ErrorAction SilentlyContinue
    if ($ollama) {
        Start-Process -FilePath $ollama.Source -ArgumentList 'serve' -WindowStyle Hidden
        Start-Sleep -Seconds 4
        $tags = Get-OllamaTags
    }
}
if (-not $tags) {
    Write-Warn 'Ollama non joignable. Le routeur demarrera quand meme, mais le secours local sera indisponible.'
} else {
    $names = @($tags.models | ForEach-Object { $_.name })
    if ($names -notcontains 'qwen2.5-coder:7b') {
        Write-Warn 'Modele qwen2.5-coder:7b absent, telechargement.'
        $code = Invoke-Native -FilePath 'ollama' -Arguments @('pull', 'qwen2.5-coder:7b')
        if ($code -ne 0) {
            Write-Warn 'Telechargement du modele Ollama echoue.'
        }
    } else {
        Write-Ok 'Ollama et qwen2.5-coder:7b disponibles.'
    }
}

Write-Step 'Preparation du dossier de travail et de la configuration effective.'
New-Item -ItemType Directory -Path $dataDir -Force | Out-Null
$code = Invoke-Native -FilePath $venvPython -Arguments @((Join-Path $root 'scripts\render-config.py'))
if ($code -ne 0) {
    Write-Err 'Rendu de la configuration impossible.'
    exit 1
}

Write-Step 'Verification de la cle locale du routeur.'
$masterKey = [Environment]::GetEnvironmentVariable('LITELLM_MASTER_KEY', 'User')
if ([string]::IsNullOrWhiteSpace($masterKey)) {
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($bytes)
    $rng.Dispose()
    $masterKey = 'sk-free-' + (([BitConverter]::ToString($bytes)) -replace '-', '').ToLowerInvariant()
    [Environment]::SetEnvironmentVariable('LITELLM_MASTER_KEY', $masterKey, 'User')
    Write-Ok 'Cle locale generee et stockee dans l''environnement utilisateur (valeur non affichee).'
} else {
    Write-Ok 'Cle locale LITELLM_MASTER_KEY presente.'
}
$env:LITELLM_MASTER_KEY = $masterKey

Write-Step 'Enregistrement de la tache planifiee au logon.'
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$root\scripts\run-router.ps1`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
Start-ScheduledTask -TaskName $taskName
Write-Ok "Tache $taskName enregistree et demarree."

Write-Step 'Verification de /health.'
$vivant = $false
for ($i = 0; $i -lt 45; $i++) {
    try {
        $null = Invoke-RestMethod -Uri 'http://127.0.0.1:4000/health/liveliness' -TimeoutSec 2
        $vivant = $true
        break
    } catch {
        Start-Sleep -Seconds 2
    }
}
if (-not $vivant) {
    Write-Err 'Routeur non joignable sur 127.0.0.1:4000.'
    if (Test-Path -LiteralPath $log) {
        Get-Content -LiteralPath $log -Tail 30
    }
    exit 1
}
Write-Ok 'Routeur en ligne sur http://127.0.0.1:4000.'
try {
    $health = Invoke-RestMethod -Uri 'http://127.0.0.1:4000/health' -TimeoutSec 10
    $health | ConvertTo-Json -Depth 6
} catch {
    Write-Warn 'Le detail /health est indisponible pour le moment (cles absentes ou fournisseurs en erreur).'
}

Write-Step 'Etat des cles.'
$manquantes = @()
foreach ($name in @('GEMINI_API_KEY', 'NVIDIA_API_KEY', 'GROQ_API_KEY')) {
    if (Test-Key -Name $name) {
        Write-Ok "$name presente."
    } else {
        Write-Warn "$name absente."
        $manquantes += $name
    }
}
if ($manquantes.Count -gt 0) {
    Write-Warn 'WAITING FOR THE OWNER: definir les cles avec setx, puis relancer ce script.'
    Write-Host '  setx GEMINI_API_KEY "<cle Google AI Studio>"'
    Write-Host '  setx NVIDIA_API_KEY "<cle NVIDIA NIM>"'
    Write-Host '  setx GROQ_API_KEY "<cle Groq>"'
    Write-Host 'Ne jamais coller une cle dans un fichier du depot.'
}

Write-Ok 'Installation terminee.'
Write-Host "Log: $log"
Write-Host 'Test: Invoke-RestMethod http://127.0.0.1:4000/health'
