# ==============================================================================
# Deploy Script (PowerShell): Deploy Zara Logistics Hub to Google Cloud Run
# ==============================================================================
$ErrorActionPreference = "Stop"

$ProjectId = (gcloud config get-value project 2>$null)
$Region = "europe-west8" # Milano (oppure europe-west12 Torino o europe-west1 Belgio)
$ServiceName = "zara-logistics-hub"
$RepoName = "zara-hub"
$ImageTag = "$Region-docker.pkg.dev/$ProjectId/$RepoName/${ServiceName}:latest"

if (-not $ProjectId) {
    Write-Error "Nessun progetto GCP selezionato. Esegui: gcloud config set project <ID_PROGETTO>"
    exit 1
}

Write-Host "🚀 Avvio procedura di deploy su Google Cloud Platform" -ForegroundColor Cyan
Write-Host "📌 Progetto: $ProjectId"
Write-Host "📌 Regione:  $Region"
Write-Host "📌 Servizio: $ServiceName`n"

# 1. Abilitazione API
Write-Host "⏳ Abilitazione API Google Cloud..." -ForegroundColor Yellow
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com --project=$ProjectId

# 2. Creazione Artifact Registry se non presente
Write-Host "⏳ Verifica repository Artifact Registry..." -ForegroundColor Yellow
$repoExists = gcloud artifacts repositories describe $RepoName --location=$Region --project=$ProjectId 2>$null
if (-not $repoExists) {
    Write-Host "📦 Creazione del repository Docker '$RepoName'..."
    gcloud artifacts repositories create $RepoName --repository-format=docker --location=$Region --description="Docker repo per Zara Logistics Hub" --project=$ProjectId
}

# 3. Auth Docker
Write-Host "🔑 Autenticazione Docker..." -ForegroundColor Yellow
gcloud auth configure-docker "$Region-docker.pkg.dev" --quiet

# 4. Build Docker
Write-Host "🔨 Compilazione immagine Docker..." -ForegroundColor Yellow
docker build -t $ImageTag .

# 5. Push Docker
Write-Host "⬆️ Push immagine su Google Artifact Registry..." -ForegroundColor Yellow
docker push $ImageTag

# 6. Deploy Cloud Run
Write-Host "🚀 Deploy su Google Cloud Run..." -ForegroundColor Yellow
gcloud run deploy $ServiceName `
    --image=$ImageTag `
    --region=$Region `
    --platform=managed `
    --allow-unauthenticated `
    --port=8080 `
    --memory=1Gi `
    --cpu=1 `
    --min-instances=0 `
    --max-instances=3 `
    --timeout=3600 `
    --session-affinity `
    --set-env-vars="ENV=production,ZARA_ADMIN_PASS=zara2026,ZARA_UFFICIO_PASS=traffico2026,ZARA_MAGAZZINO_PASS=banchina2026" `
    --project=$ProjectId

$ServiceUrl = (gcloud run services describe $ServiceName --platform=managed --region=$Region --format="value(status.url)" --project=$ProjectId)

Write-Host "`n==============================================================================" -ForegroundColor Green
Write-Host "🎉 DEPLOY COMPLETATO CON SUCCESSO!" -ForegroundColor Green
Write-Host "🌐 URL Applicazione: $ServiceUrl" -ForegroundColor Green
Write-Host "==============================================================================" -ForegroundColor Green
