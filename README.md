# RunPod ComfyUI Serverless Handler

Ein hochperformanter Serverless Handler für die Ausführung von ComfyUI Workflows auf RunPod's Serverless GPU Infrastructure.

## 🚀 Features

- **Serverless GPU Computing**: Nutzt RunPod's Serverless Platform für skalierbare GPU-Berechnungen
- **ComfyUI Integration**: Nahtlose Integration mit ComfyUI für AI-Bildgenerierung
- **RunPod Network-Volume-Support**: Automatisches Speichern der generierten Bilder auf dem RunPod Network-Volume
- **Workflow Flexibilität**: Unterstützt sowohl vordefinierte als auch dynamische Workflows
- **Error Handling**: Robuste Fehlerbehandlung und detailliertes Logging
- **Test Suite**: Umfangreiches Test-Script für lokale und Remote-Tests

## 📋 Voraussetzungen

- RunPod Account mit API Key
- RunPod Network Volume (für persistente Speicherung)
- Docker (für Image Build)
- Python 3.11+

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

Der Handler unterstützt folgende Umgebungsvariablen:

- `COMFY_PORT`: ComfyUI Port (default: 8188)
- `COMFY_HOST`: ComfyUI Host (default: 127.0.0.1)
- `RUNPOD_VOLUME_PATH`: Pfad zum Network Volume (default: /runpod-volume)
- `RUNPOD_OUTPUT_DIR`: Alternatives Output-Verzeichnis (optional)

### Workflow Konfiguration

Workflows werden als JSON direkt im Request übergeben. Der Handler erwartet das ComfyUI Workflow-Format.

## 📝 Verwendung

### Request Format

```json
{
  "input": {
    "workflow": {
      // ComfyUI Workflow JSON
      // Beispiel: SD 1.5 Text-to-Image
      "3": {
        "inputs": {
          "seed": 42,
          "steps": 20,
          "cfg": 7.0,
          "sampler_name": "euler",
          "scheduler": "normal",
          "denoise": 1.0,
          "model": ["4", 0],
          "positive": ["6", 0],
          "negative": ["7", 0],
          "latent_image": ["5", 0]
        },
        "class_type": "KSampler"
      }
      // ... weitere Nodes
    }
  }
}
```

### Response Format

```json
{
  "links": [
    "/runpod-volume/job-id/output_image.png"
  ],
  "total_images": 1,
  "job_id": "abc123",
  "saved_paths": [
    "/runpod-volume/job-id/output_image.png"
  ],
  "output_base": "/runpod-volume",
  "comfy_result": {
    // ComfyUI execution result
  }
}
```

## 🧪 Testing

Test-Skripte sind nicht im Repository enthalten (siehe `.gitignore`). Erstelle dein eigenes Test-Script:

```bash
#!/bin/bash
ENDPOINT_ID="your-endpoint-id"
API_KEY="your-runpod-api-key"
API_URL="https://api.runpod.ai/v2/${ENDPOINT_ID}/runsync"

curl -X POST "$API_URL" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "workflow": { /* dein ComfyUI-Workflow */ }
    }
  }'
```

## 🏗️ Architektur

```
├── rp_handler.py          # Haupt-Handler für RunPod
├── Serverless.Dockerfile  # Docker Image Definition
├── .gitignore            # Git ignore rules
└── README.md             # Diese Datei
```

### Handler Komponenten

- **handler()**: Hauptfunktion für Job-Verarbeitung
- **_start_comfy()**: ComfyUI Server Management
- **_run_workflow()**: Workflow Execution über ComfyUI API
- **_wait_for_completion()**: Monitoring der Workflow-Ausführung
- **_save_to_network_volume()**: Speicherung auf RunPod Network Volume
- **_ensure_volume_ready()**: Volume Mount Validation

## 🚀 Deployment

1. **Docker Image bauen und pushen**
   ```bash
   docker build -t ecomtree/comfyui-serverless:latest -f Serverless.Dockerfile .
   docker push ecomtree/comfyui-serverless:latest
   ```

2. **RunPod Serverless Endpoint erstellen**
   - Gehe zu [RunPod Dashboard](https://runpod.io/console/serverless)
   - Erstelle neuen Serverless Endpoint
   - Docker Image: `ecomtree/comfyui-serverless:latest`
   - Container Disk: mindestens 15GB
   - GPU: mindestens RTX 3090 oder besser
   - **Wichtig**: Network Volume mit ausreichend Speicher verbinden

3. **Endpoint konfigurieren**
   - Setze Umgebungsvariablen falls nötig
   - Konfiguriere Max Workers und Idle Timeout
   - Notiere Endpoint ID und API Key

## 📊 Performance

- **Cold Start**: ~15-30 Sekunden (ComfyUI + Model Loading)
- **Warm Start**: ~2-5 Sekunden
- **Workflow Execution**: Abhängig von Komplexität und Modell (5-120 Sekunden)
- **Volume Save**: <1 Sekunde pro Bild

## 💡 Technische Details

- **Base Image**: `runpod/pytorch:2.8.0-py3.11-cuda12.8.1-cudnn-devel-ubuntu22.04`
- **ComfyUI Version**: v0.3.57
- **PyTorch**: 2.8.0 mit CUDA 12.8
- **Vorinstallierte Modelle**: Stable Diffusion 1.5 (v1-5-pruned-emaonly)
- **GPU Memory**: Optimiert mit `--normalvram` Flag

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
