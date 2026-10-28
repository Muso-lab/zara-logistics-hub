#!/bin/bash
# ==============================================================================
# Deploy Script: Deploy Zara Logistics Hub to Google Cloud Run (Serverless)
# ==============================================================================
set -e

# Configurable variables
PROJECT_ID=$(gcloud config get-value project 2>/dev/null || echo "")
REGION="europe-west8" # Milan, Italy (or europe-west1 Belgium / europe-west12 Turin)
SERVICE_NAME="zara-logistics-hub"
REPO_NAME="zara-hub"
IMAGE_TAG="europe-west8-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${SERVICE_NAME}:latest"

if [ -z "$PROJECT_ID" ]; then
    echo "❌ Errore: Nessun progetto GCP configurato in gcloud CLI."
    echo "Esegui prima: gcloud config set project <ID_PROGETTO>"
    exit 1
fi

echo "🚀 Avvio procedura di deploy su Google Cloud Platform"
echo "📌 Progetto: ${PROJECT_ID}"
echo "📌 Regione:  ${REGION}"
echo "📌 Servizio: ${SERVICE_NAME}"
echo ""

# 1. Abilitazione delle API GCP necessarie
echo "⏳ Abilitazione API Cloud Run, Artifact Registry e Cloud Build..."
gcloud services enable \
    run.googleapis.com \
    artifactregistry.googleapis.com \
    cloudbuild.googleapis.com \
    secretmanager.googleapis.com \
    --project="${PROJECT_ID}"

# 2. Creazione del repository in Artifact Registry se non presente
echo "⏳ Verifica Artifact Registry..."
if ! gcloud artifacts repositories describe "${REPO_NAME}" --location="${REGION}" --project="${PROJECT_ID}" &>/dev/null; then
    echo "📦 Creazione del repository Docker '${REPO_NAME}'..."
    gcloud artifacts repositories create "${REPO_NAME}" \
        --repository-format=docker \
        --location="${REGION}" \
        --description="Docker repository per Zara Logistics Hub" \
        --project="${PROJECT_ID}"
fi

# 3. Autenticazione Docker con Artifact Registry
echo "🔑 Configurazione autenticazione Docker..."
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

# 4. Build dell'immagine Docker
echo "🔨 Compilazione immagine container Docker..."
docker build -t "${IMAGE_TAG}" .

# 5. Push dell'immagine su Artifact Registry
echo "⬆️ Upload immagine su Google Artifact Registry..."
docker push "${IMAGE_TAG}"

# 6. Deploy su Cloud Run con parametri ottimizzati per Streamlit
echo "🚀 Rilascio su Cloud Run..."
gcloud run deploy "${SERVICE_NAME}" \
    --image="${IMAGE_TAG}" \
    --region="${REGION}" \
    --platform=managed \
    --allow-unauthenticated \
    --port=8080 \
    --memory=1Gi \
    --cpu=1 \
    --min-instances=0 \
    --max-instances=3 \
    --timeout=3600 \
    --session-affinity \
    --set-env-vars="ENV=production,ZARA_ADMIN_PASS=zara2026,ZARA_UFFICIO_PASS=traffico2026,ZARA_MAGAZZINO_PASS=banchina2026" \
    --project="${PROJECT_ID}"

# 7. Recupero URL pubblico del servizio
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" --platform=managed --region="${REGION}" --format="value(status.url)" --project="${PROJECT_ID}")

echo ""
echo "=============================================================================="
echo "🎉 DEPLOY COMPLETATO CON SUCCESSO!"
echo "🌐 URL Applicazione: ${SERVICE_URL}"
echo "=============================================================================="
