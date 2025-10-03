#!/bin/bash
#
# Codex Setup Script for RunPod Serverless Environment
# This script sets up the Codex environment for the ComfyUI Serverless repo
#

set -e  # Exit on error

# Colors for better readability
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

echo_info "🚀 Starting Codex environment setup for RunPod ComfyUI Serverless..."

# ============================================================
# 1. Create Workspace Directory
# ============================================================
echo_info "📁 Creating workspace structure..."
mkdir -p /workspace
cd /workspace
echo_success "Workspace ready: $(pwd)"

# ============================================================
# 2. Clone Repository (if not present)
# ============================================================
if [ ! -d "/workspace/runpod-comfyui-serverless" ]; then
    echo_info "📦 Cloning repository..."
    git clone https://github.com/EcomTree/runpod-comfyui-serverless.git
    cd runpod-comfyui-serverless
    echo_success "Repository cloned"
else
    echo_warning "Repository already exists, skipping clone"
    cd runpod-comfyui-serverless
fi

echo_info "🌿 Ensuring repository is on main branch..."
if git fetch origin main --tags; then
    if git show-ref --verify --quiet refs/heads/main; then
        if ! git checkout main; then
            echo_warning "Lokaler Branch main defekt – neu aus origin/main erstellen"
            git checkout -B main origin/main
        fi
    else
        git checkout -B main origin/main
    fi

    if git status --short --porcelain | grep -q ""; then
        echo_warning "Lokale Änderungen vorhanden – git pull wird übersprungen"
    else
        if git pull --ff-only origin main; then
            echo_success "Branch main erfolgreich aktualisiert"
        else
            echo_warning "Konnte main nicht aktualisieren – bitte manuell prüfen"
        fi
    fi
else
    echo_warning "Fetch von origin/main fehlgeschlagen – arbeite mit vorhandener Kopie"
fi

# ============================================================
# 3. Python Environment Setup
# ============================================================
echo_info "🐍 Setting up Python environment..."

# Check Python version (should be 3.12 according to screenshot)
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo_info "Python Version: $PYTHON_VERSION"

# Pip upgrade (important for latest packages)
python3 -m pip install --upgrade pip setuptools wheel

# Install Python dependencies for the project
echo_info "📦 Installing Python dependencies..."
python3 -m pip install --no-cache-dir \
    runpod \
    requests \
    boto3 \
    Pillow \
    numpy

echo_success "Python dependencies installed"

# ============================================================
# 4. System Tools (if not already present)
# ============================================================
echo_info "🔧 Checking system tools..."

# jq for JSON processing (useful for debugging)
if ! command -v jq &> /dev/null; then
    echo_info "Installing jq..."
    apt-get update -qq
    apt-get install -y jq
    echo_success "jq installed"
else
    echo_success "jq already available"
fi

# curl for API tests
if ! command -v curl &> /dev/null; then
    echo_info "Installing curl..."
    apt-get update -qq
    apt-get install -y curl
    echo_success "curl installed"
else
    echo_success "curl already available"
fi

# ============================================================
# 5. Environment Variables Setup
# ============================================================
echo_info "🌍 Configuring environment variables..."

# Create .env template if not present
if [ ! -f ".env.example" ]; then
    cat > .env.example << 'EOF'
# ComfyUI Configuration
COMFY_PORT=8188
COMFY_HOST=127.0.0.1

# Storage Configuration - S3 (Recommended)
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
    echo_success ".env.example created"
fi

# ============================================================
# 6. Output Directory Structure
# ============================================================
echo_info "📂 Creating output directories..."
mkdir -p /workspace/outputs
mkdir -p /workspace/logs
mkdir -p /runpod-volume || echo_warning "Network Volume not available (normal in Codex)"
echo_success "Directory structure created"

# ============================================================
# 7. Prepare Test Script
# ============================================================
echo_info "🧪 Preparing test environment..."

# Make test_endpoint.sh executable
if [ -f "test_endpoint.sh" ]; then
    chmod +x test_endpoint.sh
    echo_success "Test script made executable"
fi

# ============================================================
# 8. Git Configuration (optional, can be customized)
# ============================================================
echo_info "🔧 Configuring Git..."

# Only set git config if not already set
if [ -z "$(git config --global user.email)" ]; then
    git config --global user.email "${GIT_USER_EMAIL:-codex@example.com}" || true
fi

if [ -z "$(git config --global user.name)" ]; then
    git config --global user.name "${GIT_USER_NAME:-Codex User}" || true
fi

git config --global init.defaultBranch main || true
echo_success "Git configured"

# ============================================================
# 9. Validation & Summary
# ============================================================
echo ""
echo_success "✨ Setup completed successfully!"
echo ""
echo_info "📋 Summary of installed components:"
echo "   ├─ Python: $(python3 --version | awk '{print $2}')"
echo "   ├─ pip: $(pip3 --version | awk '{print $2}')"
echo "   ├─ Node.js: $(node --version 2>/dev/null || echo 'not available')"
echo "   ├─ jq: $(jq --version 2>/dev/null || echo 'not available')"
echo "   ├─ curl: $(curl --version | head -n1 | awk '{print $2}')"
echo "   └─ git: $(git --version | awk '{print $3}')"
echo ""
echo_info "📁 Workspace: $(pwd)"
echo_info "📂 Logs: /workspace/logs"
echo_info "📂 Outputs: /workspace/outputs"
echo ""
echo_info "📝 Next steps:"
echo "   1. Copy .env.example to .env and fill in the values"
echo "   2. Test the handler with: python3 rp_handler.py (locally)"
echo "   3. Or build the Docker image: docker build -f Serverless.Dockerfile ."
echo ""
echo_success "🎉 Codex Environment is ready!"
