param([switch]$Court)
$ErrorActionPreference = 'Continue'
$key = [Environment]::GetEnvironmentVariable('LITELLM_MASTER_KEY', 'User')
$h = @{ Authorization = "Bearer $key" }
$dataDir = Join-Path $env:LOCALAPPDATA 'opencode-free-router'
$jsonl = Join-Path $dataDir 'requetes.jsonl'

try { $null = Invoke-RestMethod 'http://127.0.0.1:4000/health/liveliness' -TimeoutSec 3; Write-Host 'Routeur : actif' -ForegroundColor Green }
catch { Write-Host 'Routeur : ARRETE' -ForegroundColor Red; exit 1 }

# Auto-reglage (V4) : dernier banc court, par fournisseur (OK / LENT / EPUISE / SANS CLE / KO / PETIT).
$auto = Join-Path $dataDir 'autoreglage.json'
if (Test-Path $auto) {
    $a = Get-Content $auto -Raw -Encoding UTF8 | ConvertFrom-Json
    Write-Host "Auto-reglage (banc du $($a.heure)) :"
    foreach ($p in $a.fournisseurs.PSObject.Properties) {
        $e = $p.Value.etat
        $lib = switch ($e) { 'EPUISE' { 'EPUISE' } 'SANS CLE' { 'SANS CLE' } default { $e } }
        $col = switch ($e) { 'OK' { 'Green' } 'PETIT' { 'Yellow' } 'SANS CLE' { 'DarkGray' } default { 'Red' } }
        $d = if ($p.Value.delai_30k_s) { "30K: $($p.Value.delai_30k_s) s" } elseif ($p.Value.delai_1k_s) { "1K: $($p.Value.delai_1k_s) s" } else { '' }
        Write-Host ('  {0,-9} {1,-24} {2}' -f $lib, $p.Name, $d) -ForegroundColor $col
    }
}

if ($Court) {
    # Etat rapide (aucun appel aux fournisseurs, aucun quota consomme) : cles presentes,
    # resultat des 20 dernieres requetes par fournisseur, Ollama en ligne ou non.
    $rec = @()
    if (Test-Path $jsonl) { $rec = @(Get-Content $jsonl -Tail 20 -Encoding UTF8 | ForEach-Object { $_ | ConvertFrom-Json }) }
    $four = @(
        @{ N = 'Gemini'; Cle = 'GEMINI_API_KEY'; Motif = 'gemini' },
        @{ N = 'Groq';   Cle = 'GROQ_API_KEY';   Motif = 'groq|gpt-oss' },
        @{ N = 'NVIDIA'; Cle = 'NVIDIA_API_KEY'; Motif = 'nvidia|glm|deepseek' }
    )
    Write-Host 'Fournisseurs :'
    foreach ($f in $four) {
        $cle = [Environment]::GetEnvironmentVariable($f.Cle, 'User')
        if ($f.N -eq 'NVIDIA') { Write-Host ('  --  {0,-8} retire de la chaine active (reactivable)' -f $f.N) -ForegroundColor DarkGray; continue }
        if (-not $cle) { Write-Host ('  KO  {0,-8} cle absente ({1})' -f $f.N, $f.Cle) -ForegroundColor Red; continue }
        $r = @($rec | Where-Object { ($_.fournisseur + ' ' + $_.groupe) -match $f.Motif })
        $ok = @($r | Where-Object { $_.ok }).Count; $ko = $r.Count - $ok
        if ($r.Count -eq 0) { Write-Host ('  OK  {0,-8} cle presente, pas de requete recente' -f $f.N) -ForegroundColor Green }
        elseif ($ko -eq 0) { Write-Host ('  OK  {0,-8} {1} requete(s) reussie(s)' -f $f.N, $ok) -ForegroundColor Green }
        else { Write-Host ('  !!  {0,-8} {1} echec(s) sur {2} (quota epuise ou saturation : le routeur bascule seul)' -f $f.N, $ko, $r.Count) -ForegroundColor Yellow }
    }
    try { $null = Invoke-RestMethod 'http://localhost:11434/api/tags' -TimeoutSec 3; Write-Host '  OK  Ollama   local, en ligne' -ForegroundColor Green }
    catch { Write-Host '  KO  Ollama   hors ligne (ollama serve)' -ForegroundColor Red }
    $v = Join-Path $dataDir 'ollama-vitesse.txt'
    if (Test-Path $v) { Write-Host "  Ollama : $((Get-Content $v -Raw).Trim())" -ForegroundColor DarkGray }
    exit 0
}

Write-Host "`nFournisseurs (healthy / unhealthy) :"
try {
    $s = Invoke-RestMethod 'http://127.0.0.1:4000/health' -Headers $h -TimeoutSec 120
    foreach ($e in $s.healthy_endpoints)   { Write-Host ("  OK  {0}" -f $e.model) -ForegroundColor Green }
    foreach ($e in $s.unhealthy_endpoints) { Write-Host ("  KO  {0}" -f $e.model) -ForegroundColor Red }
} catch { Write-Host "  /health indisponible : $($_.Exception.Message)" -ForegroundColor Yellow }

$v = Join-Path $dataDir 'ollama-vitesse.txt'
if (Test-Path $v) { Write-Host "`nOllama : $((Get-Content $v -Raw).Trim())" }

Write-Host "`n20 dernieres requetes (fournisseur reel) :"
if (Test-Path $jsonl) {
    $rows = @(Get-Content $jsonl -Tail 20 -Encoding UTF8 | ForEach-Object { $_ | ConvertFrom-Json })
    foreach ($r in $rows) {
        '  {0}  {1,-10} {2,-6} {3,5}s  {4}' -f $r.heure, $r.groupe, $(if ($r.ok) {'OK'} else {'ECHEC'}), $r.duree_s, $r.fournisseur
    }
    $ech = @($rows | Where-Object { -not $_.ok }).Count
    Write-Host ("`nBilan : {0} echec(s) sur {1} ; fournisseurs ayant repondu : {2}" -f $ech, $rows.Count, ((@($rows | Where-Object { $_.ok } | ForEach-Object { $_.fournisseur } | Sort-Object -Unique)) -join ', '))
} else { Write-Host '  aucune requete enregistree depuis ce demarrage' -ForegroundColor Yellow }
