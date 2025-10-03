# Setup Scripts Übersicht

Dieses Repository enthält **zwei** Setup-Skripte für unterschiedliche Anwendungsfälle:

## 🌐 setup-codex.sh - Für Codex Web UI

**Verwendung:** Wenn du das Projekt in der **Codex Web UI** verwendest

### Eigenschaften:
- ✅ **Schlank & schnell** (~30 Sekunden)
- ✅ Keine Virtual Environment (nicht nötig in Codex)
- ✅ Nur essenzielle Pakete (runpod, requests, boto3, etc.)
- ✅ Optimiert für vorinstallierte Umgebung (Python 3.12, Node.js 20, etc.)
- ✅ Erstellt `.env.example` für Konfiguration

### In Codex verwenden:

**Option A - Direkt vom Repo:**
```bash
curl -fsSL https://raw.githubusercontent.com/EcomTree/runpod-comfyui-serverless/main/setup-codex.sh | bash
```

**Option B - Nach dem Clone:**
```bash
git clone https://github.com/EcomTree/runpod-comfyui-serverless.git /workspace/runpod-comfyui-serverless
cd /workspace/runpod-comfyui-serverless
chmod +x setup-codex.sh
./setup-codex.sh
```

### In Codex Web UI eintragen:

Unter **"Setup-Skript"** → **"Manuell"**:
```bash
git clone https://github.com/EcomTree/runpod-comfyui-serverless.git /workspace/runpod-comfyui-serverless && cd /workspace/runpod-comfyui-serverless && chmod +x setup-codex.sh && ./setup-codex.sh
```

📖 **Vollständige Anleitung:** Siehe `CODEX_SETUP.md`

---

## 💻 setup-dev.sh - Für lokale Entwicklung

**Verwendung:** Wenn du das Projekt **lokal auf deinem Mac/PC** entwickelst

### Eigenschaften:
- 🔧 **Vollständige Dev-Umgebung** (~5-10 Minuten)
- 🔧 Erstellt Python Virtual Environment
- 🔧 Installiert Dev-Tools (pytest, black, flake8, mypy, etc.)
- 🔧 Optional: ComfyUI Clone für lokales Testing
- 🔧 Docker Helper Scripts
- 🔧 Test Suite mit Beispiel-Tests
- 🔧 Code Quality Tools (Linting, Formatting)

### Lokal verwenden:

```bash
# Repository klonen
git clone https://github.com/EcomTree/runpod-comfyui-serverless.git
cd runpod-comfyui-serverless

# Setup ausführen (interaktiv)
chmod +x setup-dev.sh
./setup-dev.sh

# Danach: Virtual Environment aktivieren
source .venv/bin/activate
```

### Was wird erstellt:
```
.
├── .venv/                    # Python Virtual Environment
├── requirements-dev.txt      # Development Dependencies
├── pytest.ini                # Test Konfiguration
├── pyproject.toml            # Tool Konfiguration (black, isort, mypy)
├── .flake8                   # Linter Config
├── tests/                    # Test Suite
│   ├── unit/                 # Unit Tests
│   └── integration/          # Integration Tests
├── .codex/                   # Codex Konfiguration & Doku
│   ├── config.json
│   └── development.md
├── build-docker.sh           # Docker Build Helper
├── test-docker-local.sh      # Docker Test Helper
├── start-dev.sh              # Quick-Start für Dev
└── ComfyUI/                  # Optional: Lokale ComfyUI Installation
```

---

## 🤔 Welches Skript soll ich verwenden?

| Szenario | Skript | Grund |
|----------|--------|-------|
| 🌐 Codex Web UI | `setup-codex.sh` | Schnell, schlank, für Cloud-Umgebung optimiert |
| 💻 Lokale Entwicklung auf Mac/PC | `setup-dev.sh` | Vollständige Dev-Tools, Virtual Environment |
| 🐳 Nur Docker Build | Keins nötig | Dockerfile hat alles |
| 🚀 RunPod Serverless Deployment | Keins nötig | Container wird direkt deployed |

---

## 📝 Weitere Dokumente

- **CODEX_SETUP.md** - Detaillierte Anleitung für Codex Web UI
- **SETUP_GUIDE.md** - Allgemeine Setup-Anleitung
- **README.md** - Projekt-Übersicht

---

## 🆘 Troubleshooting

### Codex: "setup-codex.sh not found"
```bash
# Stelle sicher dass du im richtigen Verzeichnis bist:
cd /workspace/runpod-comfyui-serverless
ls -la setup-codex.sh

# Falls nicht vorhanden, neu klonen:
git clone https://github.com/EcomTree/runpod-comfyui-serverless.git
```

### Lokal: "setup-dev.sh: Permission denied"
```bash
chmod +x setup-dev.sh
./setup-dev.sh
```

### "Python version too old"
- **Codex:** Sollte Python 3.12 haben (automatisch)
- **Lokal:** Installiere Python 3.11+ von [python.org](https://python.org)

---

**Tipp:** Beide Skripte sind idempotent - du kannst sie mehrfach ausführen ohne Probleme! ✅
