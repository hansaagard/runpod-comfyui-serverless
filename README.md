# RunPod ComfyUI Serverless Handler

Ein hochperformanter Serverless Handler für die Ausführung von ComfyUI Workflows auf RunPod's Serverless GPU Infrastructure.

## 🚀 Features

- **Serverless GPU Computing**: Nutzt RunPod's Serverless Platform für skalierbare GPU-Berechnungen
- **ComfyUI Integration**: Nahtlose Integration mit ComfyUI für AI-Bildgenerierung
- **AWS S3 Support**: Automatisches Hochladen der generierten Bilder zu AWS S3
- **Workflow Flexibilität**: Unterstützt sowohl vordefinierte als auch dynamische Workflows
- **Error Handling**: Robuste Fehlerbehandlung und detailliertes Logging
- **Test Suite**: Umfangreiches Test-Script für lokale und Remote-Tests

## 📋 Voraussetzungen

- RunPod Account mit API Key
- AWS Account mit S3 Bucket (optional)
- Docker (für lokale Tests)
- Python 3.8+

## 🛠️ Installation

1. **Repository klonen**
   ```bash
   git clone https://github.com/EcomTree/runpod-comfyui-serverless.git
   cd runpod-comfyui-serverless
   ```

2. **Docker Image bauen**
   ```bash
   docker build -t ecomtree/comfyui-serverless -f Serverless.Dockerfile .
   ```

3. **Image zu RunPod Registry pushen**
   ```bash
   docker tag ecomtree/comfyui-serverless:latest ecomtree/comfyui-serverless:latest
   docker push ecomtree/comfyui-serverless:latest
   ```

## 🔧 Konfiguration

### Umgebungsvariablen

Der Handler benötigt folgende Umgebungsvariablen:

- `RUNPOD_WEBHOOK_GET_WORK`: Webhook URL für Job-Abfrage
- `RUNPOD_AI_API_KEY`: RunPod API Key
- `COMFY_API_URL`: ComfyUI API Endpoint (default: http://127.0.0.1:8188)
- `AWS_ACCESS_KEY_ID`: AWS Access Key (optional)
- `AWS_SECRET_ACCESS_KEY`: AWS Secret Key (optional)
- `AWS_ENDPOINT_URL`: Custom S3 Endpoint URL (optional)
- `BUCKET_NAME`: S3 Bucket Name (optional)

### Workflow Konfiguration

Workflows können auf zwei Arten bereitgestellt werden:

1. **Vordefinierte Workflows**: Platziere `.json` Workflow-Dateien im `/comfyui/workflows/` Verzeichnis
2. **Dynamische Workflows**: Übergebe den Workflow direkt im Request

## 📝 Verwendung

### Request Format

```json
{
  "input": {
    "workflow": "workflow_name",  // oder komplettes workflow JSON
    "images": [
      {
        "name": "image1.png",
        "image": "base64_encoded_image_data"
      }
    ]
  }
}
```

### Response Format

```json
{
  "output": {
    "message": "Workflow completed successfully",
    "files": ["s3://bucket/path/to/output.png"]
  }
}
```

## 🧪 Testing

Das Repository enthält ein umfangreiches Test-Script (`test_endpoint.sh`) für verschiedene Szenarien:

```bash
# Lokaler Test
./test_endpoint.sh local

# RunPod Test
./test_endpoint.sh runpod

# Spezifische Test-Szenarien
./test_endpoint.sh test workflow_test
./test_endpoint.sh test image_upload_test
```

### Verfügbare Test-Szenarien

- `basic_health`: Health Check
- `workflow_test`: Test mit vordefiniertem Workflow
- `workflow_json_test`: Test mit JSON Workflow
- `image_upload_test`: Test mit Bild-Upload
- `batch_test`: Batch-Verarbeitung Test
- `error_test`: Error Handling Test
- `performance_test`: Performance Benchmark

## 🏗️ Architektur

```
├── rp_handler.py          # Haupt-Handler für RunPod
├── Serverless.Dockerfile  # Docker Image Definition
├── test_endpoint.sh       # Test Suite
└── README.md             # Diese Datei
```

### Handler Komponenten

- **RunPodHandler**: Hauptklasse für Job-Verarbeitung
- **upload_to_s3**: S3 Upload Funktionalität
- **test_handler**: Lokale Test-Funktion
- **Error Handling**: Umfassende Fehlerbehandlung

## 🚀 Deployment

1. **RunPod Serverless Endpoint erstellen**
   - Gehe zu RunPod Dashboard
   - Erstelle neuen Serverless Endpoint
   - Wähle dein Docker Image
   - Konfiguriere Umgebungsvariablen

2. **Endpoint testen**
   ```bash
   ./test_endpoint.sh runpod basic_health
   ```

## 📊 Performance

- **Cold Start**: ~10-15 Sekunden
- **Warm Start**: ~2-3 Sekunden
- **Workflow Execution**: Abhängig von Komplexität (5-60 Sekunden)
- **S3 Upload**: ~1-2 Sekunden pro Bild

## 🤝 Contributing

Contributions sind willkommen! Bitte erstelle einen Pull Request mit deinen Änderungen.

## 📄 Lizenz

Dieses Projekt ist unter der MIT Lizenz lizenziert.

## 🙏 Danksagung

- [RunPod](https://runpod.io) für die Serverless GPU Infrastructure
- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) für das geniale AI Workflow System
- Der Open Source Community für die kontinuierliche Unterstützung

---

Erstellt mit ❤️ für die AI Art Community
