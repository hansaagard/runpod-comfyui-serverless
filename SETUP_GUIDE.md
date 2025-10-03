# Codex Setup Guide

## 🚀 Schnellstart

Dieses Setup-Skript richtet eine vollständige Entwicklungsumgebung für das RunPod ComfyUI Serverless Projekt ein.

### Installation

```bash
# Setup ausführen
./setup-codex.sh

# Danach: Virtual Environment aktivieren
source .venv/bin/activate
```

**Oder mit Quick-Start:**

```bash
# Alles in einem
./setup-codex.sh && ./start-dev.sh
```

## 📦 Was wird eingerichtet?

Das Setup-Skript erstellt automatisch:

### 1. **Python Virtual Environment**
- `.venv/` - Isolierte Python-Umgebung
- Alle Development Dependencies installiert
- Python 3.11+ kompatibel

### 2. **Development Tools**
- **pytest** - Test Framework
- **black** - Code Formatter
- **flake8** - Linter
- **mypy** - Type Checker
- **ipython** - Interaktive Shell
- **jupyter** - Notebook Support

### 3. **Test-Infrastruktur**
- `tests/unit/` - Unit Tests
- `tests/integration/` - Integration Tests
- `pytest.ini` - Test Configuration
- Beispiel-Tests für Handler

### 4. **Code Quality Tools**
- `.flake8` - Linter Configuration
- `pyproject.toml` - black, isort, mypy Config
- Pre-configured für das Projekt

### 5. **Docker Development**
- `build-docker.sh` - Build Docker Image
- `test-docker-local.sh` - Test Image lokal
- GPU-Support für lokale Tests

### 6. **Codex Configuration**
- `.codex/config.json` - Projekt-Metadaten
- `.codex/development.md` - Development Guide
- Kommandos und Best Practices

### 7. **Optional: ComfyUI**
- Lokales ComfyUI für Tests
- Version v0.3.57 (wie im Docker Image)
- Model-Verzeichnisse vorbereitet

## 🛠️ Voraussetzungen

### Minimal
- **Python 3.11+**
- **Git**
- **10GB+ freier Speicher**

### Optional
- **Docker** (für Image-Build und Tests)
- **NVIDIA GPU** (für lokales ComfyUI Testing)

## 📋 Verwendung

### Development starten

```bash
# Virtual Environment aktivieren
source .venv/bin/activate

# Oder Quick-Start
./start-dev.sh
```

### Tests ausführen

```bash
# Alle Tests
pytest

# Nur Unit Tests
pytest -m unit

# Mit Coverage Report
pytest --cov=. --cov-report=html
```

### Code Quality

```bash
# Code formatieren
black rp_handler.py

# Linting
flake8 rp_handler.py

# Type Checking
mypy rp_handler.py
```

### Docker Development

```bash
# Image bauen
./build-docker.sh

# Lokal testen (mit GPU)
./test-docker-local.sh
```

## 🔧 Konfiguration

### Environment Variables

Kopiere `.env.example` zu `.env` und passe an:

```bash
cp .env.example .env
nano .env
```

Wichtige Variablen:
- `RUNPOD_API_KEY` - Dein RunPod API Key
- `RUNPOD_ENDPOINT_ID` - Dein Endpoint
- `COMFY_PORT` - ComfyUI Port (default: 8188)

### ComfyUI Modelle

Wenn du ComfyUI lokal nutzen möchtest:

```bash
# Beispiel: Stable Diffusion 1.5
wget -P ComfyUI/models/checkpoints/ \
  "https://huggingface.co/runwayml/stable-diffusion-v1-5/resolve/main/v1-5-pruned-emaonly.safetensors"
```

## 📚 Dokumentation

Nach dem Setup findest du:

- **Development Guide**: `.codex/development.md`
- **Test Examples**: `tests/unit/test_handler.py`
- **Docker Scripts**: `build-docker.sh`, `test-docker-local.sh`

## 🐛 Troubleshooting

### Python Version zu alt

```bash
# Installiere Python 3.11+
sudo apt-get update
sudo apt-get install python3.11 python3.11-venv
```

### Disk Space Issues

```bash
# Prüfe Speicherplatz
df -h

# Cleanup Docker (falls vorhanden)
docker system prune -a
```

### ComfyUI Installation fehlgeschlagen

Das ist optional - du kannst das Projekt auch ohne lokales ComfyUI entwickeln:

```bash
# Setup erneut ausführen und ComfyUI-Installation überspringen
./setup-codex.sh
```

### Tests schlagen fehl

Das ist normal beim ersten Setup - einige Tests sind Mocks und benötigen angepasste Configuration:

```bash
# Einzelnen Test ausführen
pytest tests/unit/test_handler.py::TestVolumeFunctions::test_sanitize_job_id_valid -v
```

## 🚢 Deployment Workflow

1. **Lokal entwickeln**
   ```bash
   source .venv/bin/activate
   # Code ändern in rp_handler.py
   pytest  # Tests ausführen
   ```

2. **Docker Image bauen**
   ```bash
   ./build-docker.sh
   ```

3. **Image pushen**
   ```bash
   docker push ecomtree/comfyui-serverless:latest
   ```

4. **RunPod Endpoint updaten**
   - Gehe zu RunPod Dashboard
   - Update Endpoint mit neuem Image

5. **Testen**
   ```bash
   ./test_endpoint.sh
   ```

## 💡 Best Practices

### 1. Virtual Environment immer aktivieren

```bash
# Am Anfang jeder Session
source .venv/bin/activate
```

### 2. Code formatieren vor Commit

```bash
black rp_handler.py
flake8 rp_handler.py
```

### 3. Tests schreiben

Für jede neue Funktion einen Test in `tests/unit/` erstellen.

### 4. Environment Variables nicht committen

`.env` ist in `.gitignore` - Secrets gehören NICHT ins Repository!

### 5. Docker Image testen vor Push

```bash
./test-docker-local.sh
```

## 🤝 Contribution Workflow

1. Feature Branch erstellen
2. Code entwickeln + Tests schreiben
3. `pytest` + `black` + `flake8` ausführen
4. Docker Image bauen und testen
5. Pull Request erstellen

## 📞 Support

Bei Fragen oder Problemen:

1. Prüfe die Logs: `logs/`
2. Lese die Dokumentation: `.codex/development.md`
3. Teste mit `pytest -v`

## 🎉 Los geht's!

```bash
# Setup ausführen
./setup-codex.sh

# Development starten
./start-dev.sh

# Happy Coding! 🚀
```

---

**Erstellt für RunPod ComfyUI Serverless Handler**  
*Entwicklungsumgebung für AI-Bildgenerierung auf Serverless GPU Infrastructure*
