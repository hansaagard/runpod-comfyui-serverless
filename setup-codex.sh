#!/bin/bash
#
# Codex Setup Script für RunPod Serverless Environment
# Dieses Skript richtet die Codex-Umgebung für das ComfyUI Serverless Repo ein
#

set -e  # Exit on error

# Farben für bessere Lesbarkeit
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

echo_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

echo_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

echo_error() {
    echo -e "${RED}❌ $1${NC}"
}

echo_info "🚀 Starte Codex Umgebungs-Setup für RunPod ComfyUI Serverless..."

# ============================================================
# 1. Workspace-Verzeichnis erstellen
# ============================================================
echo_info "📁 Erstelle Workspace-Struktur..."
mkdir -p /workspace
cd /workspace
echo_success "Workspace bereit: $(pwd)"

# ============================================================
# 2. Repository klonen (falls nicht vorhanden)
# ============================================================
if [ ! -d "/workspace/runpod-comfyui-serverless" ]; then
    echo_info "📦 Klone Repository..."
    git clone https://github.com/EcomTree/runpod-comfyui-serverless.git
    cd runpod-comfyui-serverless
    echo_success "Repository geklont"
else
    echo_warning "Repository existiert bereits, überspringe Klonen"
    cd runpod-comfyui-serverless
fi

# ============================================================
# 3. Python Environment Setup
# ============================================================
echo_info "🐍 Richte Python-Umgebung ein..."

# Python Version prüfen (sollte bereits 3.12 sein laut Screenshot)
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo_info "Python Version: $PYTHON_VERSION"

# Pip upgrade (wichtig für neueste Pakete)
python3 -m pip install --upgrade pip setuptools wheel

# Python Dependencies für das Projekt installieren
echo_info "📦 Installiere Python-Abhängigkeiten..."
python3 -m pip install --no-cache-dir \
    runpod \
    requests \
    boto3 \
    Pillow \
    numpy \
    pathlib

echo_success "Python-Abhängigkeiten installiert"

# ============================================================
# 4. System-Tools (falls noch nicht vorhanden)
# ============================================================
echo_info "🔧 Prüfe System-Tools..."

# jq für JSON-Verarbeitung (nützlich für Debugging)
if ! command -v jq &> /dev/null; then
    echo_info "Installiere jq..."
    apt-get update -qq
    apt-get install -y jq
    echo_success "jq installiert"
else
    echo_success "jq bereits vorhanden"
fi

# curl für API-Tests
if ! command -v curl &> /dev/null; then
    echo_info "Installiere curl..."
    apt-get update -qq
    apt-get install -y curl
    echo_success "curl installiert"
else
    echo_success "curl bereits vorhanden"
fi

# ============================================================
# 5. Umgebungsvariablen Setup
# ============================================================
echo_info "🌍 Konfiguriere Umgebungsvariablen..."

# Erstelle .env Template falls nicht vorhanden
if [ ! -f ".env.example" ]; then
    cat > .env.example << 'EOF'
# ComfyUI Konfiguration
COMFY_PORT=8188
COMFY_HOST=127.0.0.1

# Storage Konfiguration - S3 (Empfohlen)
S3_BUCKET=
S3_ACCESS_KEY=
S3_SECRET_KEY=
S3_ENDPOINT_URL=
S3_REGION=auto
S3_PUBLIC_URL=
S3_SIGNED_URL_EXPIRY=3600

# Network Volume (Fallback)
RUNPOD_VOLUME_PATH=/runpod-volume
RUNPOD_OUTPUT_DIR=
EOF
    echo_success ".env.example erstellt"
fi

# ============================================================
# 6. Verzeichnisstruktur für Outputs
# ============================================================
echo_info "📂 Erstelle Output-Verzeichnisse..."
mkdir -p /workspace/outputs
mkdir -p /workspace/logs
mkdir -p /runpod-volume || echo_warning "Network Volume nicht verfügbar (normal in Codex)"
echo_success "Verzeichnisstruktur erstellt"

# ============================================================
# 7. Test-Skript vorbereiten
# ============================================================
echo_info "🧪 Bereite Test-Umgebung vor..."

# Mache test_endpoint.sh ausführbar
if [ -f "test_endpoint.sh" ]; then
    chmod +x test_endpoint.sh
    echo_success "Test-Skript ausführbar gemacht"
fi

# ============================================================
# 8. Git Konfiguration (für Codex)
# ============================================================
echo_info "🔧 Konfiguriere Git..."
git config --global user.email "codex@ecomtree.dev" || true
git config --global user.name "Codex Environment" || true
git config --global init.defaultBranch main || true
echo_success "Git konfiguriert"

# ============================================================
# 9. Validierung & Zusammenfassung
# ============================================================
echo ""
echo_success "✨ Setup erfolgreich abgeschlossen!"
echo ""
echo_info "📋 Zusammenfassung der installierten Komponenten:"
echo "   ├─ Python: $(python3 --version | awk '{print $2}')"
echo "   ├─ pip: $(pip3 --version | awk '{print $2}')"
echo "   ├─ Node.js: $(node --version 2>/dev/null || echo 'nicht verfügbar')"
echo "   ├─ jq: $(jq --version 2>/dev/null || echo 'nicht verfügbar')"
echo "   ├─ curl: $(curl --version | head -n1 | awk '{print $2}')"
echo "   └─ git: $(git --version | awk '{print $3}')"
echo ""
echo_info "📁 Workspace: $(pwd)"
echo_info "📂 Logs: /workspace/logs"
echo_info "📂 Outputs: /workspace/outputs"
echo ""
echo_info "📝 Nächste Schritte:"
echo "   1. Kopiere .env.example zu .env und fülle die Werte aus"
echo "   2. Teste den Handler mit: python3 rp_handler.py (lokal)"
echo "   3. Oder baue das Docker Image: docker build -f Serverless.Dockerfile ."
echo ""
echo_success "🎉 Codex Environment ist bereit!"
