import os
import re
import shutil
import subprocess
import time
import requests
import json
import runpod
import uuid
from pathlib import Path

COMFY_PORT = int(os.getenv("COMFY_PORT", 8188))
COMFY_HOST = os.getenv("COMFY_HOST", "127.0.0.1")
COMFY_URL = f"http://{COMFY_HOST}:{COMFY_PORT}"  # Base URL für ComfyUI API
OUTPUT_BASE = Path(os.getenv("RUNPOD_OUTPUT_DIR", os.getenv("RUNPOD_VOLUME_PATH", "/runpod-volume")))

_VOLUME_READY = False


def _check_volume_once() -> bool:
    """Check if network volume is mounted and writable."""
    try:
        OUTPUT_BASE.mkdir(parents=True, exist_ok=True)
    except Exception as mkdir_err:
        print(f"⚠️ Cannot create output base directory {OUTPUT_BASE}: {mkdir_err}")
        return False

    if not OUTPUT_BASE.exists():
        print(f"⚠️ Output base {OUTPUT_BASE} exists? {OUTPUT_BASE.exists()}")
        return False

    test_file = OUTPUT_BASE / ".volume-test"
    try:
        with open(test_file, "w", encoding="utf-8") as tmp:
            tmp.write("ok")
        if not test_file.exists():
            print(f"⚠️ Volume test file not found after write: {test_file}")
            return False
        os.remove(test_file)
        return True
    except Exception as test_err:
        print(f"⚠️ Volume not writable yet: {test_err}")
        try:
            if test_file.exists():
                os.remove(test_file)
        except OSError:
            pass
        return False


def _ensure_volume_ready(max_wait_seconds: float = 45.0) -> bool:
    """Wait until volume is mounted and writable."""
    global _VOLUME_READY
    if _VOLUME_READY and OUTPUT_BASE.exists():
        return True

    deadline = time.time() + max_wait_seconds
    attempt = 0
    while time.time() <= deadline:
        attempt += 1
        if _check_volume_once():
            _VOLUME_READY = True
            print(f"✅ Network volume ready (attempt {attempt}) at {OUTPUT_BASE}")
            return True
        print(f"⏳ Volume not ready yet (attempt {attempt}), retrying…")
        time.sleep(2)

    print("❌ Network volume failed to become ready within timeout")
    return False


def _volume_ready() -> bool:
    return _VOLUME_READY and OUTPUT_BASE.exists()


def _sanitize_job_id(job_id: str | None) -> str | None:
    if not job_id:
        return None
    sanitized = re.sub(r"[^a-zA-Z0-9_.-]", "_", str(job_id))
    return sanitized.strip("._") or None


def _sanitize_job_id(job_id: str | None) -> str | None:
    if not job_id:
        return None
    sanitized = re.sub(r"[^a-zA-Z0-9_.-]", "_", str(job_id))
    return sanitized.strip("._") or None

# ----------------------------------------------------------------------------
# Helferfunktionen
# ----------------------------------------------------------------------------

def _is_comfy_running() -> bool:
    """Prüfen, ob ComfyUI auf dem vorgesehenen Port reagiert."""
    try:
        r = requests.get(f"{COMFY_URL}/system_stats", timeout=2)
        return r.status_code == 200
    except requests.RequestException:
        return False


def _start_comfy():
    """ComfyUI im Hintergrund starten, falls noch nicht läuft."""
    if _is_comfy_running():
        print("✅ ComfyUI läuft bereits.")
        return

    print("🚀 Starte ComfyUI im Hintergrund…")
    log_path = "/workspace/comfy.log"
    
    # Weniger aggressive Memory-Parameter für Container-Umgebung
    cmd = [
        "python", "/workspace/ComfyUI/main.py",
        "--listen", COMFY_HOST,
        "--port", str(COMFY_PORT),
        "--normalvram",  # Statt --highvram für bessere Container-Kompatibilität
        "--preview-method", "auto",
        "--verbose",  # Für Debug-Logs
    ]
    
    print(f"🎯 ComfyUI Start-Command: {' '.join(cmd)}")
    
    with open(log_path, "a") as log_file:
        subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT, cwd="/workspace/ComfyUI")

    # Warten bis API erreichbar
    for _ in range(30):
        if _is_comfy_running():
            print("✅ ComfyUI läuft.")
            return
        time.sleep(2)
    raise RuntimeError("ComfyUI konnte nicht gestartet werden.")


def _run_workflow(workflow: dict):
    """Workflow an Comfy senden und auf Ergebnis warten."""
    # ComfyUI API erwartet {"prompt": workflow, "client_id": uuid} Format
    client_id = str(uuid.uuid4())
    payload = {"prompt": workflow, "client_id": client_id}
    
    print(f"📤 Sende Workflow an ComfyUI API...")
    print(f"🔗 URL: {COMFY_URL}/prompt")
    print(f"🆔 Client ID: {client_id}")
    print(f"📋 Workflow Node Count: {len(workflow)}")
    print(f"🔍 Workflow Nodes: {list(workflow.keys())}")
    
    # DEBUG: Teste verfügbare API Endpoints
    try:
        print("🔄 Teste ComfyUI System Stats...")
        test_r = requests.get(f"{COMFY_URL}/system_stats", timeout=5)
        print(f"✅ System Stats: {test_r.status_code}")
        
        print("🔄 Teste verfügbare Models...")
        models_r = requests.get(f"{COMFY_URL}/object_info", timeout=5)
        if models_r.status_code == 200:
            object_info = models_r.json()
            checkpoints = object_info.get("CheckpointLoaderSimple", {}).get("input", {}).get("required", {}).get("ckpt_name", [[]])
            if len(checkpoints) > 0 and len(checkpoints[0]) > 0:
                print(f"📦 Verfügbare Checkpoints: {checkpoints[0][:3]}..." if len(checkpoints[0]) > 3 else checkpoints[0])
            else:
                print("⚠️ Keine Checkpoints gefunden!")
        else:
            print(f"⚠️ Object Info nicht erreichbar: {models_r.status_code}")
    except Exception as e:
        print(f"❌ API Tests fehlgeschlagen: {e}")
        # Nicht fatal - trotzdem weitermachen
    
    # DEBUG: Überprüfe Output-Verzeichnis für SaveImage Node
    output_dir = Path("/workspace/ComfyUI/output")
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"📁 Output Dir: {output_dir}, existiert: {output_dir.exists()}, beschreibbar: {os.access(output_dir, os.W_OK)}")
    
    # DEBUG: Validiere Workflow-Struktur
    save_image_nodes = [node_id for node_id, node in workflow.items() if node.get("class_type") == "SaveImage"]
    print(f"💾 SaveImage Nodes gefunden: {len(save_image_nodes)}")
    
    try:
        print(f"🚀 Sende Workflow mit client_id...")
        r = requests.post(f"{COMFY_URL}/prompt", json=payload, timeout=15)
        print(f"📤 Response Status: {r.status_code}")
        print(f"📤 Response Headers: {dict(r.headers)}")
        print(f"📜 Response Body: {r.text[:500]}...")
        
        if r.status_code != 200:
            print(f"❌ ComfyUI API Error: {r.status_code}")
            print(f"📄 Full Response: {r.text}")
            r.raise_for_status()
        
        response_data = r.json()
        prompt_id = response_data.get("prompt_id")
        
        if not prompt_id:
            print(f"❌ Keine prompt_id in Response: {response_data}")
            raise ValueError(f"ComfyUI Response invalid: {response_data}")
            
        print(f"✅ Workflow gesendet! Prompt ID: {prompt_id}")
        return prompt_id
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Request Exception: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"📄 Error Response: {e.response.text}")
        raise

def _wait_for_completion(prompt_id: str):
    """Warte auf Workflow-Completion und return result."""
    print(f"⏳ Warte auf Fertigstellung von prompt {prompt_id}…")
    
    for attempt in range(60):  # Max 3 Minuten warten
        try:
            history_r = requests.get(f"{COMFY_URL}/history/{prompt_id}")
            if history_r.status_code == 200:
                history_data = history_r.json()
                if prompt_id in history_data:
                    result = history_data[prompt_id]
                    status = result.get("status", {})
                    status_str = status.get("status_str")
                    
                    print(f"🔄 Status Check {attempt+1}: {status_str}")
                    
                    if status_str == "success":
                        print("✅ Workflow erfolgreich abgeschlossen!")
                        return result
                    elif status_str == "error" or "error" in status:
                        error_msg = status.get("error", status)
                        print(f"❌ ComfyUI Workflow Fehler: {error_msg}")
                        raise RuntimeError(f"ComfyUI Workflow failed: {error_msg}")
                else:
                    print(f"⏳ Prompt {prompt_id} noch nicht in History...")
        except Exception as e:
            print(f"⚠️ Status check error (attempt {attempt+1}): {e}")
        
        time.sleep(3)
    
    raise TimeoutError("Workflow Timeout nach 3 Minuten")


def _save_to_network_volume(file_path: Path, job_id: str | None = None, retry_copy: bool = True) -> str:
    """Copy file to network volume instead of uploading."""
    if not _volume_ready():
        raise RuntimeError("Volume mount not ready")

    target_dir = OUTPUT_BASE
    network_filename = file_path.name
    if job_id:
        target_dir = target_dir / job_id
        network_filename = f"{job_id}-{file_path.name}" if job_id not in file_path.name else file_path.name

    target_dir.mkdir(parents=True, exist_ok=True)
    network_path = target_dir / network_filename

    print(f"💾 Copying {file_path} to network volume: {network_path}")

    try:
        shutil.copy2(file_path, network_path)
    except FileNotFoundError:
        if retry_copy:
            print("⚠️ Source file disappeared during copy, retrying once…")
            time.sleep(0.5)
            if file_path.exists():
                return _save_to_network_volume(file_path, job_id, retry_copy=False)
        raise

    if network_path.exists() and network_path.stat().st_size == file_path.stat().st_size:
        print(f"✅ File saved to network volume: {network_path} ({network_path.stat().st_size} bytes)")
        return str(network_path)
    else:
        raise RuntimeError(f"Failed to save file to network volume: {network_path}")


# ----------------------------------------------------------------------------
# Runpod Handler
# ----------------------------------------------------------------------------

def handler(event):
    """Runpod Handler.

    Erwartet event["input"] mit:
      - workflow: dict  (ComfyUI Workflow JSON)
    """
    inp = event.get("input", {})
    workflow = inp.get("workflow")
    if not workflow:
        raise ValueError("workflow fehlt im Input")

    raw_job_id = event.get("id") or event.get("requestId") or inp.get("jobId")
    job_id = _sanitize_job_id(raw_job_id)
    if raw_job_id and not job_id:
        print(f"⚠️ Received job ID '{raw_job_id}' but sanitization removed all characters")
    print(f"🆔 Runpod Job ID: {job_id}")

    print("🚀 Handler gestartet - ComfyUI Workflow wird verarbeitet...")
    _start_comfy()

    if not _ensure_volume_ready():
        raise RuntimeError(
            f"Network volume am Pfad {OUTPUT_BASE} wurde nicht innerhalb des Timeouts bereitgestellt"
        )

    prompt_id = _run_workflow(workflow)
    result = _wait_for_completion(prompt_id)
    
    # ComfyUI History API Struktur: result["outputs"] enthält node outputs
    links = []
    outputs = result.get("outputs", {})
    
    print(f"📁 Suche nach generierten Dateien in outputs...")
    for node_id, node_output in outputs.items():
        if "images" in node_output:
            for img_data in node_output["images"]:
                # ComfyUI speichert Bilder standardmäßig in /workspace/ComfyUI/output/
                filename = img_data.get("filename")
                subfolder = img_data.get("subfolder", "")
                
                if filename:
                    # Vollständiger Pfad zum Bild
                    if subfolder:
                        img_path = Path(f"/workspace/ComfyUI/output/{subfolder}/{filename}")
                    else:
                        img_path = Path(f"/workspace/ComfyUI/output/{filename}")
                    
                    print(f"🖼️ Gefundenes Bild: {img_path}")
                    if img_path.exists():
                        print(f"💾 Speichere auf Network Volume: {img_path}")
                        network_file_path = _save_to_network_volume(img_path, job_id=job_id)
                        links.append(network_file_path)
                        print(f"✅ Erfolgreich gespeichert: {network_file_path}")
                    else:
                        print(f"⚠️ Datei nicht gefunden: {img_path}")

    if not links:
        print("❌ Keine Bilder gefunden in ComfyUI outputs")
        # Fallback: suche alle Bilder im output Verzeichnis
        output_dir = Path("/workspace/ComfyUI/output")
        if output_dir.exists():
            for img_file in output_dir.glob("*.png"):
                print(f"💾 Fallback Speicherung: {img_file}")
                network_file_path = _save_to_network_volume(img_file, job_id=job_id)
                links.append(network_file_path)

    return {
        "links": links,
        "total_images": len(links),
        "comfy_result": result,
        "output_base": str(OUTPUT_BASE),
        "job_id": job_id,
        "saved_paths": links,
    }


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
