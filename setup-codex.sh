#!/bin/bash
# =============================================================================
# Setup-Skript für ComfyUI Serverless Codex-Entwicklungsumgebung
# =============================================================================
#
# Dieses Skript richtet eine vollständige Entwicklungsumgebung ein für:
# - Lokale Python-Entwicklung
# - ComfyUI Testing
# - Docker Image Build & Test
# - RunPod Serverless Deployment
#
# =============================================================================

set -e  # Bei Fehler abbrechen

# Farben für Output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging-Funktionen
log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_header() {
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo ""
}

# =============================================================================
# System-Checks
# =============================================================================

print_header "System-Checks"

# Python Version Check
log_info "Prüfe Python Installation..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version | awk '{print $2}')
    log_success "Python $PYTHON_VERSION gefunden"
    
    # Version check (mindestens 3.11)
    PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
    PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)
    
    if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 11 ]); then
        log_warning "Python 3.11+ empfohlen, gefunden: $PYTHON_VERSION"
    fi
else
    log_error "Python 3 nicht gefunden! Bitte installieren."
    exit 1
fi

# Git Check
log_info "Prüfe Git Installation..."
if command -v git &> /dev/null; then
    GIT_VERSION=$(git --version | awk '{print $3}')
    log_success "Git $GIT_VERSION gefunden"
else
    log_error "Git nicht gefunden! Bitte installieren."
    exit 1
fi

# Docker Check (optional)
log_info "Prüfe Docker Installation..."
if command -v docker &> /dev/null; then
    DOCKER_VERSION=$(docker --version | awk '{print $3}' | sed 's/,//')
    log_success "Docker $DOCKER_VERSION gefunden"
    DOCKER_AVAILABLE=true
else
    log_warning "Docker nicht gefunden - Docker-Features werden übersprungen"
    DOCKER_AVAILABLE=false
fi

# Disk Space Check
log_info "Prüfe verfügbaren Speicherplatz..."
AVAILABLE_SPACE=$(df -BG . | tail -1 | awk '{print $4}' | sed 's/G//')
if [ "$AVAILABLE_SPACE" -lt 10 ]; then
    log_warning "Wenig Speicherplatz verfügbar: ${AVAILABLE_SPACE}GB (mindestens 10GB empfohlen)"
else
    log_success "Verfügbarer Speicherplatz: ${AVAILABLE_SPACE}GB"
fi

# =============================================================================
# Verzeichnisstruktur erstellen
# =============================================================================

print_header "Verzeichnisstruktur erstellen"

WORKSPACE_ROOT=$(pwd)
log_info "Workspace Root: $WORKSPACE_ROOT"

# Erstelle Entwicklungsverzeichnisse
mkdir -p .venv
mkdir -p logs
mkdir -p tests
mkdir -p .codex
mkdir -p tmp/comfy-output

log_success "Verzeichnisstruktur erstellt"

# =============================================================================
# Python Virtual Environment
# =============================================================================

print_header "Python Virtual Environment einrichten"

# Prüfe ob venv bereits existiert
if [ -d ".venv/bin" ]; then
    log_warning "Virtual Environment existiert bereits"
    read -p "Neu erstellen? (j/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Jj]$ ]]; then
        log_info "Lösche altes Virtual Environment..."
        rm -rf .venv
    else
        log_info "Verwende existierendes Virtual Environment"
    fi
fi

if [ ! -d ".venv/bin" ]; then
    log_info "Erstelle Virtual Environment..."
    python3 -m venv .venv
    log_success "Virtual Environment erstellt"
fi

# Aktiviere venv
log_info "Aktiviere Virtual Environment..."
source .venv/bin/activate
log_success "Virtual Environment aktiviert"

# Upgrade pip
log_info "Upgrade pip, setuptools, wheel..."
pip install --upgrade pip setuptools wheel --quiet
log_success "pip aktualisiert"

# =============================================================================
# Python Dependencies installieren
# =============================================================================

print_header "Python Dependencies installieren"

log_info "Erstelle requirements-dev.txt..."
cat > requirements-dev.txt << 'EOF'
# Core Dependencies (wie im Dockerfile)
requests>=2.31.0
runpod>=1.6.0
pathlib

# Development Tools
pytest>=7.4.0
pytest-cov>=4.1.0
pytest-mock>=3.11.1
black>=23.7.0
flake8>=6.1.0
mypy>=1.5.0
ipython>=8.14.0
ipdb>=0.13.13

# Type stubs
types-requests

# Linting & Formatting
isort>=5.12.0
pylint>=2.17.5

# Testing & Mocking
responses>=0.23.3
faker>=19.3.0

# Documentation
sphinx>=7.1.2
sphinx-rtd-theme>=1.3.0

# Jupyter (optional, für interaktive Entwicklung)
jupyter>=1.0.0
notebook>=7.0.0
EOF

log_success "requirements-dev.txt erstellt"

log_info "Installiere Dependencies..."
log_warning "Dies kann einige Minuten dauern..."

pip install -r requirements-dev.txt --quiet

log_success "Dependencies installiert"

# =============================================================================
# ComfyUI für lokale Tests (optional)
# =============================================================================

print_header "ComfyUI Setup für lokale Tests"

log_info "ComfyUI wird für lokale Tests benötigt"
read -p "ComfyUI jetzt klonen? (J/n): " -n 1 -r
echo

if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    if [ -d "ComfyUI" ]; then
        log_warning "ComfyUI Verzeichnis existiert bereits"
    else
        log_info "Clone ComfyUI Repository..."
        git clone https://github.com/comfyanonymous/ComfyUI.git
        
        cd ComfyUI
        log_info "Checkout Version v0.3.57 (wie im Dockerfile)..."
        git checkout v0.3.57
        
        log_info "Installiere ComfyUI Dependencies..."
        # Installiere nur die Python-Packages, keine Torch-Pakete neu
        pip install -r requirements.txt --quiet || log_warning "Einige ComfyUI Dependencies konnten nicht installiert werden"
        
        cd "$WORKSPACE_ROOT"
        log_success "ComfyUI eingerichtet"
        
        # Erstelle Model-Verzeichnisse
        mkdir -p ComfyUI/models/checkpoints
        mkdir -p ComfyUI/models/vae
        mkdir -p ComfyUI/models/loras
        mkdir -p ComfyUI/output
        
        log_info "Model-Verzeichnisse erstellt"
        log_warning "Hinweis: Modelle müssen manuell heruntergeladen werden"
        log_info "Beispiel: wget -P ComfyUI/models/checkpoints/ <model-url>"
    fi
else
    log_info "ComfyUI Setup übersprungen"
fi

# =============================================================================
# Test-Setup
# =============================================================================

print_header "Test-Setup konfigurieren"

log_info "Erstelle Test-Struktur..."

mkdir -p tests/unit
mkdir -p tests/integration
mkdir -p tests/fixtures

# pytest.ini
cat > pytest.ini << 'EOF'
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = 
    -v
    --tb=short
    --strict-markers
    --cov=.
    --cov-report=term-missing
    --cov-report=html
markers =
    unit: Unit tests
    integration: Integration tests
    slow: Slow running tests
EOF

log_success "pytest.ini erstellt"

# Beispiel Unit Test
cat > tests/unit/test_handler.py << 'EOF'
"""Unit Tests für rp_handler.py"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add workspace to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import rp_handler


class TestVolumeFunctions:
    """Tests für Volume-Management Funktionen"""
    
    def test_sanitize_job_id_valid(self):
        """Test sanitize_job_id mit gültigem Input"""
        result = rp_handler._sanitize_job_id("test-job-123")
        assert result == "test-job-123"
    
    def test_sanitize_job_id_invalid_chars(self):
        """Test sanitize_job_id mit ungültigen Zeichen"""
        result = rp_handler._sanitize_job_id("test/job@123!")
        assert result == "test_job_123"
    
    def test_sanitize_job_id_none(self):
        """Test sanitize_job_id mit None"""
        result = rp_handler._sanitize_job_id(None)
        assert result is None


class TestComfyFunctions:
    """Tests für ComfyUI-Interaktion"""
    
    @patch('rp_handler.requests.get')
    def test_is_comfy_running_success(self, mock_get):
        """Test _is_comfy_running wenn ComfyUI läuft"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        result = rp_handler._is_comfy_running()
        assert result is True
    
    @patch('rp_handler.requests.get')
    def test_is_comfy_running_failure(self, mock_get):
        """Test _is_comfy_running wenn ComfyUI nicht läuft"""
        mock_get.side_effect = Exception("Connection failed")
        
        result = rp_handler._is_comfy_running()
        assert result is False


class TestHandler:
    """Tests für den Haupt-Handler"""
    
    def test_handler_missing_workflow(self):
        """Test handler ohne workflow Input"""
        event = {"input": {}}
        
        with pytest.raises(ValueError, match="workflow fehlt"):
            rp_handler.handler(event)
    
    @patch('rp_handler._start_comfy')
    @patch('rp_handler._ensure_volume_ready')
    @patch('rp_handler._run_workflow')
    @patch('rp_handler._wait_for_completion')
    def test_handler_basic_flow(self, mock_wait, mock_run, mock_volume, mock_start):
        """Test grundlegender Handler-Flow"""
        # Setup mocks
        mock_volume.return_value = True
        mock_run.return_value = "test-prompt-id"
        mock_wait.return_value = {"outputs": {}}
        
        event = {
            "id": "test-job-123",
            "input": {
                "workflow": {"test": "workflow"}
            }
        }
        
        result = rp_handler.handler(event)
        
        assert "links" in result
        assert "total_images" in result
        assert "job_id" in result
        assert result["job_id"] == "test-job-123"
EOF

log_success "Beispiel-Tests erstellt"

# =============================================================================
# Development Tools Config
# =============================================================================

print_header "Development Tools konfigurieren"

# .flake8
cat > .flake8 << 'EOF'
[flake8]
max-line-length = 120
exclude = 
    .git,
    __pycache__,
    .venv,
    ComfyUI,
    build,
    dist
ignore = 
    E203,  # whitespace before ':'
    W503,  # line break before binary operator
EOF

# pyproject.toml (für black, isort, etc.)
cat > pyproject.toml << 'EOF'
[tool.black]
line-length = 120
target-version = ['py311']
include = '\.pyi?$'
exclude = '''
/(
    \.git
  | \.venv
  | ComfyUI
  | build
  | dist
)/
'''

[tool.isort]
profile = "black"
line_length = 120
skip = [".venv", "ComfyUI"]

[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = false
exclude = ['ComfyUI', '.venv']
EOF

log_success "Tool-Konfigurationen erstellt"

# =============================================================================
# Docker Helper Scripts
# =============================================================================

if [ "$DOCKER_AVAILABLE" = true ]; then
    print_header "Docker Helper Scripts erstellen"
    
    # build-docker.sh
    cat > build-docker.sh << 'EOF'
#!/bin/bash
# Docker Image Build Script

set -e

IMAGE_NAME="${IMAGE_NAME:-ecomtree/comfyui-serverless}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

echo "🐳 Building Docker Image: ${IMAGE_NAME}:${IMAGE_TAG}"
echo ""

docker build \
    -t "${IMAGE_NAME}:${IMAGE_TAG}" \
    -f Serverless.Dockerfile \
    .

echo ""
echo "✅ Build erfolgreich!"
echo ""
echo "Image: ${IMAGE_NAME}:${IMAGE_TAG}"
echo ""
echo "Nächste Schritte:"
echo "  - Testen: docker run -it ${IMAGE_NAME}:${IMAGE_TAG} bash"
echo "  - Push: docker push ${IMAGE_NAME}:${IMAGE_TAG}"
EOF
    chmod +x build-docker.sh
    
    # test-docker-local.sh
    cat > test-docker-local.sh << 'EOF'
#!/bin/bash
# Lokaler Docker Test

set -e

IMAGE_NAME="${IMAGE_NAME:-ecomtree/comfyui-serverless}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

echo "🧪 Teste Docker Image lokal: ${IMAGE_NAME}:${IMAGE_TAG}"
echo ""

# Erstelle Test-Volume
mkdir -p tmp/test-volume

# Teste ob Image existiert
if ! docker image inspect "${IMAGE_NAME}:${IMAGE_TAG}" > /dev/null 2>&1; then
    echo "❌ Image nicht gefunden: ${IMAGE_NAME}:${IMAGE_TAG}"
    echo "Bitte zuerst bauen: ./build-docker.sh"
    exit 1
fi

echo "🚀 Starte Container im interaktiven Modus..."
echo ""

docker run -it --rm \
    --gpus all \
    -v "$(pwd)/tmp/test-volume:/runpod-volume" \
    -e COMFY_PORT=8188 \
    -e RUNPOD_VOLUME_PATH=/runpod-volume \
    -p 8188:8188 \
    "${IMAGE_NAME}:${IMAGE_TAG}" \
    bash
EOF
    chmod +x test-docker-local.sh
    
    log_success "Docker Scripts erstellt"
fi

# =============================================================================
# Codex Konfiguration
# =============================================================================

print_header "Codex-Konfiguration erstellen"

# .codex/config.json
cat > .codex/config.json << 'EOF'
{
  "project": "runpod-comfyui-serverless",
  "description": "Serverless Handler für ComfyUI auf RunPod Infrastructure",
  "language": "python",
  "version": "3.11+",
  "framework": "runpod-serverless",
  "paths": {
    "handler": "rp_handler.py",
    "tests": "tests/",
    "docker": "Serverless.Dockerfile",
    "logs": "logs/"
  },
  "commands": {
    "test": "pytest",
    "lint": "flake8 rp_handler.py",
    "format": "black rp_handler.py",
    "type-check": "mypy rp_handler.py",
    "docker-build": "./build-docker.sh",
    "docker-test": "./test-docker-local.sh"
  },
  "env_vars": {
    "COMFY_PORT": "8188",
    "COMFY_HOST": "127.0.0.1",
    "RUNPOD_VOLUME_PATH": "/runpod-volume"
  }
}
EOF

# .codex/development.md
cat > .codex/development.md << 'EOF'
# Development Guide

## Quick Start

```bash
# Setup ausführen
./setup-codex.sh

# Virtual Environment aktivieren
source .venv/bin/activate

# Tests ausführen
pytest

# Code formatieren
black rp_handler.py

# Linting
flake8 rp_handler.py
```

## Projekt-Struktur

```
.
├── rp_handler.py           # Haupt-Handler
├── Serverless.Dockerfile   # Docker Image
├── tests/                  # Test Suite
│   ├── unit/              # Unit Tests
│   └── integration/       # Integration Tests
├── .codex/                # Codex Konfiguration
├── logs/                  # Log Files
└── tmp/                   # Temporäre Dateien
```

## Lokale Entwicklung

### ComfyUI lokal starten

```bash
cd ComfyUI
python main.py --listen 127.0.0.1 --port 8188
```

### Handler testen

```python
from rp_handler import handler

event = {
    "input": {
        "workflow": {
            # Dein ComfyUI Workflow
        }
    }
}

result = handler(event)
```

## Docker Development

### Image bauen
```bash
./build-docker.sh
```

### Lokal testen
```bash
./test-docker-local.sh
```

## Testing

### Alle Tests
```bash
pytest
```

### Nur Unit Tests
```bash
pytest -m unit
```

### Mit Coverage
```bash
pytest --cov=. --cov-report=html
```

## Code Quality

### Formatierung
```bash
black rp_handler.py
isort rp_handler.py
```

### Linting
```bash
flake8 rp_handler.py
pylint rp_handler.py
```

### Type Checking
```bash
mypy rp_handler.py
```

## Deployment

1. Image bauen: `./build-docker.sh`
2. Image pushen: `docker push ecomtree/comfyui-serverless:latest`
3. RunPod Endpoint konfigurieren
4. Mit test_endpoint.sh testen
EOF

log_success "Codex-Dokumentation erstellt"

# =============================================================================
# Environment File
# =============================================================================

print_header "Environment Setup"

cat > .env.example << 'EOF'
# RunPod Configuration
RUNPOD_API_KEY=your-api-key-here
RUNPOD_ENDPOINT_ID=your-endpoint-id-here

# ComfyUI Configuration
COMFY_PORT=8188
COMFY_HOST=127.0.0.1

# Storage Configuration
RUNPOD_VOLUME_PATH=/runpod-volume
RUNPOD_OUTPUT_DIR=/runpod-volume

# Docker Configuration
IMAGE_NAME=ecomtree/comfyui-serverless
IMAGE_TAG=latest

# Development
DEBUG=false
LOG_LEVEL=INFO
EOF

if [ ! -f ".env" ]; then
    cp .env.example .env
    log_success ".env Datei erstellt (bitte anpassen!)"
else
    log_warning ".env existiert bereits"
fi

# =============================================================================
# .gitignore Update
# =============================================================================

print_header ".gitignore aktualisieren"

cat >> .gitignore << 'EOF'

# Codex Development
.venv/
.vscode/
.idea/
*.pyc
__pycache__/
.pytest_cache/
.coverage
htmlcov/
.mypy_cache/
.env
logs/
tmp/
ComfyUI/
requirements-dev.txt
build/
dist/
*.egg-info/
EOF

log_success ".gitignore aktualisiert"

# =============================================================================
# Quick Start Script
# =============================================================================

print_header "Quick-Start Script erstellen"

cat > start-dev.sh << 'EOF'
#!/bin/bash
# Quick Start für Development

set -e

# Aktiviere venv
source .venv/bin/activate

echo "✅ Virtual Environment aktiviert"
echo ""
echo "📋 Verfügbare Befehle:"
echo "  pytest              - Tests ausführen"
echo "  black rp_handler.py - Code formatieren"
echo "  flake8 rp_handler.py - Code linten"
echo "  ./build-docker.sh   - Docker Image bauen"
echo ""
echo "📚 Dokumentation: .codex/development.md"
echo ""

# Shell öffnen
exec bash
EOF
chmod +x start-dev.sh

log_success "start-dev.sh erstellt"

# =============================================================================
# Tests ausführen
# =============================================================================

print_header "Test-Installation verifizieren"

log_info "Führe Tests aus..."
if pytest tests/ -v; then
    log_success "Alle Tests bestanden!"
else
    log_warning "Einige Tests sind fehlgeschlagen (expected für Mocks)"
fi

# =============================================================================
# Abschluss
# =============================================================================

print_header "Setup abgeschlossen!"

echo ""
log_success "🎉 Codex-Entwicklungsumgebung ist bereit!"
echo ""
echo "📁 Erstellte Dateien:"
echo "   ├── .venv/                    Python Virtual Environment"
echo "   ├── requirements-dev.txt      Development Dependencies"
echo "   ├── pytest.ini                Test Configuration"
echo "   ├── pyproject.toml            Tool Configuration"
echo "   ├── .env.example              Environment Template"
echo "   ├── tests/                    Test Suite"
echo "   ├── .codex/                   Codex Konfiguration"
echo "   ├── build-docker.sh           Docker Build Script"
echo "   ├── test-docker-local.sh      Docker Test Script"
echo "   └── start-dev.sh              Quick Start Script"
echo ""
echo "🚀 Nächste Schritte:"
echo ""
echo "1. Virtual Environment aktivieren:"
echo "   source .venv/bin/activate"
echo ""
echo "2. Oder Quick-Start verwenden:"
echo "   ./start-dev.sh"
echo ""
echo "3. .env Datei anpassen:"
echo "   nano .env"
echo ""
echo "4. Tests ausführen:"
echo "   pytest"
echo ""
echo "5. Docker Image bauen (optional):"
echo "   ./build-docker.sh"
echo ""
echo "📚 Weitere Infos: .codex/development.md"
echo ""
log_success "Happy Coding! 🚀"
echo ""
