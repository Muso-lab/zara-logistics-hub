<# :
@echo off
REM ==============================================================================
REM INSTALLATORE 1-CLICK SERVIZIO AUTOMATICO DI SINCRONIZZAZIONE XML TMS (TRICK A)
REM Zero Porte Firewall in Ingresso - Zero Whitelist IP - Polling HTTPS ogni 60s
REM ==============================================================================
title Installazione Sync Automatico XML TMS (Zero Firewall)
echo ==============================================================================
echo    INSTALLAZIONE SYNC AUTOMATICO XML TMS DA GOOGLE CLOUD STORAGE
echo    (Connessione HTTPS in uscita - Nessuna Whitelist Firewall richiesta)
echo ==============================================================================
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-Expression ([System.IO.File]::ReadAllText('%~f0'))"
echo.
echo ==============================================================================
echo Premi un tasto per chiudere questa finestra...
echo ==============================================================================
pause
exit /b
#>

$BucketName = "lacchi-tms-zara"
$RemotePrefix = "IMPORT_SGA/RICEZIONE_ORDINI/ZARA"
$LocalDir = "C:\IMPORT_SGA\RICEZIONE_ORDINI\ZARA"
$ParentDir = Split-Path -Path $LocalDir -Parent
if (-not $ParentDir) { $ParentDir = "C:\IMPORT_SGA\RICEZIONE_ORDINI" }
$SystemDir = Join-Path $ParentDir "_sync_system_zara"
$WorkerScriptPath = Join-Path $SystemDir "sync_worker_tms.ps1"
$TaskName = "Zara_TMS_XML_AutoSync"

if (-not (Test-Path -Path $LocalDir)) {
    New-Item -ItemType Directory -Path $LocalDir -Force | Out-Null
}
if (-not (Test-Path -Path $SystemDir)) {
    New-Item -ItemType Directory -Path $SystemDir -Force | Out-Null
}

$WorkerCode = @'
param(
    [switch]$Force
)

$BucketName = "__BUCKET__"
$RemotePrefix = "__PREFIX__"
$LocalDir = "__LOCALDIR__"
$SystemDir = "__SYSDIR__"
$StateFile = Join-Path $SystemDir "last_batch_signature.txt"
$LogFile = Join-Path $SystemDir "sync_tms.log"

function Write-SyncLog($msg) {
    $ts = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    $line = "[$ts] $msg"
    try {
        Add-Content -Path $LogFile -Value $line -Encoding UTF8 -ErrorAction SilentlyContinue
    } catch {}
    if ($Force) {
        Write-Host $line -ForegroundColor Cyan
    }
}

if (-not (Test-Path -Path $LocalDir)) {
    New-Item -ItemType Directory -Path $LocalDir -Force | Out-Null
}

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$apiUrl = "https://storage.googleapis.com/storage/v1/b/$BucketName/o?prefix=$RemotePrefix"

try {
    $response = Invoke-RestMethod -Uri $apiUrl -Method Get -TimeoutSec 15
    if (-not $response.items) {
        if ($Force) {
            Write-SyncLog "Nessun file XML presente nel bucket gs://$BucketName/$RemotePrefix"
        }
        exit 0
    }

    $xmlItems = @($response.items | Where-Object { $_.name -like "*.xml" } | Sort-Object name)
    if ($xmlItems.Count -eq 0) {
        exit 0
    }

    # Calcola impronta univoca del lotto (nome + generation ID di Google Cloud Storage)
    $sigParts = @()
    foreach ($it in $xmlItems) {
        $sigParts += "$($it.name):$($it.generation):$($it.size)"
    }
    $rawSig = $sigParts -join "|"
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $hashBytes = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($rawSig))
    $currentSignature = ($hashBytes | ForEach-Object { $_.ToString("x2") }) -join ""

    $lastSignature = ""
    if (Test-Path -Path $StateFile) {
        $lastSignature = (Get-Content -Path $StateFile -Raw -ErrorAction SilentlyContinue).Trim()
    }

    if ((-not $Force) -and ($currentSignature -eq $lastSignature)) {
        # Questo lotto operativo e' gia' stato scaricato in precedenza: non riscarica!
        exit 0
    }

    Write-SyncLog "Rilevato nuovo lotto operativo su GCS ($($xmlItems.Count) file XML). Avvio download in $LocalDir..."

    # Rimuove eventuali vecchi XML residui prima di depositare il nuovo lotto
    $oldXmls = Get-ChildItem -Path $LocalDir -Filter "*.xml" -File -ErrorAction SilentlyContinue
    if ($oldXmls) {
        $oldXmls | Remove-Item -Force -ErrorAction SilentlyContinue
    }

    $downloadedCount = 0
    foreach ($item in $xmlItems) {
        $blobName = $item.name
        $fileName = Split-Path $blobName -Leaf
        if ($fileName -like "*.xml") {
            $tmpPath = Join-Path $SystemDir "$fileName.part"
            $destPath = Join-Path $LocalDir $fileName
            $downloadUrl = "https://storage.googleapis.com/$BucketName/$blobName"
            Invoke-WebRequest -Uri $downloadUrl -OutFile $tmpPath -UseBasicParsing -TimeoutSec 20
            Move-Item -Path $tmpPath -Destination $destPath -Force
            $downloadedCount++
        }
    }

    if ($downloadedCount -eq $xmlItems.Count) {
        Set-Content -Path $StateFile -Value $currentSignature -Encoding UTF8
        Write-SyncLog "SUCCESSO: Scaricati $downloadedCount nuovi file XML in $LocalDir"
    } else {
        Write-SyncLog "ATTENZIONE: Scaricati $downloadedCount su $($xmlItems.Count) file XML."
    }
} catch {
    Write-SyncLog "ERRORE durante il controllo GCS: $_"
}
'@

$WorkerCode = $WorkerCode.Replace("__BUCKET__", $BucketName).Replace("__PREFIX__", $RemotePrefix).Replace("__LOCALDIR__", $LocalDir).Replace("__SYSDIR__", $SystemDir)
Set-Content -Path $WorkerScriptPath -Value $WorkerCode -Encoding UTF8

Write-Host "[1/3] Script worker installato in: $WorkerScriptPath" -ForegroundColor Green
Write-Host "[2/3] Registrazione attivita pianificata Windows '$TaskName' (ogni 1 minuto in background)..." -ForegroundColor Yellow

$taskCmd = "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$WorkerScriptPath`""
& schtasks.exe /Create /F /SC MINUTE /MO 1 /TN "$TaskName" /TR "$taskCmd" | Out-Null

if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Attivita pianificata '$TaskName' attiva (controllo silenzioso ogni 60 secondi)!" -ForegroundColor Green
} else {
    Write-Host "[AVVISO] Impossibile registrare schtasks automaticamente (prova ad eseguire come Amministratore)." -ForegroundColor Yellow
}

Write-Host "[3/3] Esecuzione immediata del primo test di sincronizzazione..." -ForegroundColor Yellow
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$WorkerScriptPath" -Force

Write-Host ""
Write-Host "==============================================================================" -ForegroundColor Green
Write-Host " TUTTO PRONTO! Da questo momento non serve alcun FTP o apertura firewall:" -ForegroundColor Green
Write-Host " Ogni volta che generi un'operativa sul portale web, entro 60 secondi i" -ForegroundColor White
Write-Host " nuovi file XML compariranno da soli in: $LocalDir" -ForegroundColor Cyan
Write-Host " Log operazioni salvato in: $SystemDir\sync_tms.log" -ForegroundColor DarkGray
Write-Host "==============================================================================" -ForegroundColor Green
