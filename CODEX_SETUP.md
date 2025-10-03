# Codex Environment Setup Guide

## 🎯 Übersicht

Dieses Dokument beschreibt, wie du das RunPod ComfyUI Serverless Repo in der Codex-Umgebung einrichtest.

## 🚀 Schnellstart

### In Codex Web UI:

1. **Setup-Skript einfügen:**
   - Gehe zu Codex → "Setup-Skript"
   - Wähle "Manuell"
   - Füge folgenden Befehl ein:

```bash
# Codex Setup for RunPod ComfyUI Serverless
curl -fsSL https://raw.githubusercontent.com/EcomTree/runpod-comfyui-serverless/main/setup-codex.sh | bash
```

ODER (falls du den Branch testen willst):

```bash
# Setup Script ausführen
git clone https://github.com/EcomTree/runpod-comfyui-serverless.git /workspace/runpod-comfyui-serverless
cd /workspace/runpod-comfyui-serverless
chmod +x setup-codex.sh
./setup-codex.sh
```

2. **Umgebungsvariablen setzen (Optional):**
   - Klicke auf "Umgebungsvariablen" → "Hinzufügen"
   - Füge folgende Variablen hinzu, falls du S3 nutzen willst:

   | Variable | Wert | Beschreibung |
   |----------|------|--------------|
   | `S3_BUCKET` | `dein-bucket-name` | S3 Bucket für Bilder |
   | `S3_ACCESS_KEY` | `xxx` | S3 Access Key ID |
   | `S3_SECRET_KEY` | `xxx` | S3 Secret Key |
   | `S3_ENDPOINT_URL` | `https://...` | Endpoint (für R2/B2) |
   | `S3_REGION` | `auto` oder `us-east-1` | S3 Region |

3. **Container starten:**
   - Klicke auf "Ein" beim Container-Caching
   - Starte die Umgebung

## 📦 Was wird installiert?

Das Setup-Skript installiert automatisch:

### Python Pakete:
- ✅ `runpod` - RunPod SDK
- ✅ `requests` - HTTP Client
- ✅ `boto3` - AWS S3 SDK
- ✅ `Pillow` - Bildverarbeitung
- ✅ `numpy` - Numerische Berechnungen

### System-Tools:
- ✅ `jq` - JSON Parser (für Debugging)
- ✅ `curl` - HTTP Client

### Bereits vorinstalliert (laut Codex):
- ✅ Python 3.12
- ✅ Node.js 20
- ✅ Ruby 3.4.4
- ✅ Rust 1.89.0
- ✅ Go 1.24.3
- ✅ Bun 1.2.14
- ✅ PHP 8.4
- ✅ Java 21
- ✅ Swift 6.1

## 🔧 Konfiguration

### Option 1: S3 Storage (Empfohlen für Codex)

S3 ist ideal für Codex, da die generierten Bilder direkt über HTTP-URLs erreichbar sind:

```bash
# Cloudflare R2 (Kostenlos bis 10GB)
S3_BUCKET=comfyui-outputs
S3_ACCESS_KEY=dein-access-key
S3_SECRET_KEY=dein-secret-key
S3_ENDPOINT_URL=https://account-id.r2.cloudflarestorage.com
S3_REGION=auto
```

### Option 2: Network Volume (nur in RunPod Serverless)

Network Volumes funktionieren nur in der RunPod Serverless Umgebung, **nicht in Codex**:

```bash
RUNPOD_VOLUME_PATH=/runpod-volume
```

## 🧪 Testing in Codex

Nach dem Setup kannst du in Codex folgendes testen:

```bash
# In Codex Terminal:
cd /workspace/runpod-comfyui-serverless

# Python Handler testen (Syntax-Check)
python3 -m py_compile rp_handler.py

# Dependencies prüfen
python3 -c "import runpod, requests, boto3; print('✅ Alle Dependencies verfügbar')"

# Test-Skript vorbereiten
chmod +x test_endpoint.sh
```

## 📝 Wartungsskript

Das Setup-Skript wird auch im Dockerfile als "Wartungsskript" referenziert.

**Für RunPod Serverless Container:**

```dockerfile
# Im Serverless.Dockerfile könntest du optional hinzufügen:
COPY setup-codex.sh /workspace/setup-codex.sh
RUN chmod +x /workspace/setup-codex.sh && /workspace/setup-codex.sh
```

## 🐛 Troubleshooting

### "Connection Error" in Codex Terminal

Das ist normal beim ersten Start. Das Setup-Skript erstellt die notwendige Struktur automatisch.

### "Volume not ready"

In Codex gibt es keine RunPod Network Volumes. Nutze stattdessen S3 Storage.

### Python Module nicht gefunden

```bash
# Führe Setup erneut aus:
cd /workspace/runpod-comfyui-serverless
./setup-codex.sh
```

## 🎯 Nächste Schritte

Nach erfolgreichem Setup:

1. **Lokales Testing:**
   ```bash
   # Teste den Handler (ohne ComfyUI)
   python3 -c "from rp_handler import handler; print('✅ Handler importierbar')"
   ```

2. **Docker Build (für Deployment):**
   ```bash
   docker build -t ecomtree/comfyui-serverless:latest -f Serverless.Dockerfile .
   ```

3. **RunPod Deployment:**
   - Push das Image zu Docker Hub
   - Erstelle Serverless Endpoint in RunPod
   - Konfiguriere Umgebungsvariablen

## 💡 Tipps

- ✅ **S3 nutzen** für einfachen HTTP-Zugriff auf generierte Bilder
- ✅ **Cloudflare R2** ist kostenlos bis 10GB (perfekt für Tests)
- ✅ **Container-Caching aktivieren** in Codex für schnellere Starts
- ✅ **Setup-Skript** kann beliebig oft ausgeführt werden (idempotent)

## 🆘 Support

Bei Fragen oder Problemen:
- Check die Logs: `cat /workspace/logs/*.log`
- GitHub Issues: https://github.com/EcomTree/runpod-comfyui-serverless/issues
- RunPod Docs: https://docs.runpod.io/

---

**Erstellt für Codex Environment Setup** 🚀
