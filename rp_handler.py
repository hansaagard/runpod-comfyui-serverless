import os
import re
import shutil
import subprocess
import time
import requests
import json
import runpod
import uuid
import boto3
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
from botocore.exceptions import ClientError

COMFY_PORT = int(os.getenv("COMFY_PORT", 8188))
COMFY_HOST = os.getenv("COMFY_HOST", "127.0.0.1")
COMFY_URL = f"http://{COMFY_HOST}:{COMFY_PORT}"  # Base URL für ComfyUI API
OUTPUT_BASE = Path(os.getenv("RUNPOD_OUTPUT_DIR", os.getenv("RUNPOD_VOLUME_PATH", "/runpod-volume")))

# S3 Configuration
S3_BUCKET = os.getenv("S3_BUCKET")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL")  # Für R2/Backblaze etc.
S3_REGION = os.getenv("S3_REGION", "auto")
S3_PUBLIC_URL = os.getenv("S3_PUBLIC_URL")  # Optional: Custom public URL (z.B. CDN)
S3_SIGNED_URL_EXPIRY = int(os.getenv("S3_SIGNED_URL_EXPIRY", 3600))  # Sekunden (default: 1h)
S3_UPLOAD_ENABLED = bool(S3_BUCKET and S3_ACCESS_KEY and S3_SECRET_KEY)

_VOLUME_READY = False


class S3ClientManager:
    """Singleton manager for S3 client to avoid global variable issues in serverless environments."""
    _instance = None
    _client = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(S3ClientManager, cls).__new__(cls)
        return cls._instance
    
    def get_client(self):
        """Get or create S3 client."""
        if self._client is None and S3_UPLOAD_ENABLED:
            print(f"🔧 Initialisiere S3 Client (Bucket: {S3_BUCKET}, Region: {S3_REGION})")
            self._client = boto3.client(
                's3',
                aws_access_key_id=S3_ACCESS_KEY,
                aws_secret_access_key=S3_SECRET_KEY,
                endpoint_url=S3_ENDPOINT_URL,
                region_name=S3_REGION,
            )
            # Test connection
            try:
                self._client.head_bucket(Bucket=S3_BUCKET)
                print(f"✅ S3 Bucket '{S3_BUCKET}' ist erreichbar")
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', 'Unknown')
                if error_code == '404':
                    print(f"❌ Bucket '{S3_BUCKET}' existiert nicht!")
                elif error_code == '403':
                    print(f"❌ Keine Berechtigung für Bucket '{S3_BUCKET}'!")
                else:
                    print(f"❌ S3 Bucket '{S3_BUCKET}' ist nicht erreichbar: {error_code} - {e}")
                self._client = None  # Reset client to prevent usage
                raise RuntimeError(f"S3 Bucket '{S3_BUCKET}' ist nicht erreichbar: {error_code} - {e}")
        return self._client
    
    def reset_client(self):
        """Reset the S3 client (useful for testing or error recovery)."""
        self._client = None


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


def _get_s3_client():
    """Get or create S3 client using singleton manager."""
    s3_manager = S3ClientManager()
    return s3_manager.get_client()


def _upload_to_s3(file_path: Path, job_id: Optional[str] = None) -> str:
    """
    Upload a file to S3 and return a public or signed URL.

    Args:
        file_path: The path to the file to upload.
        job_id: Optional job identifier used as prefix in the S3 object key.

    Returns:
        The public or signed URL to access the uploaded file.

    Raises:
        RuntimeError: If S3 upload is not configured or the S3 client cannot be initialized.
        ClientError: If the upload to S3 fails.
    """
    if not S3_UPLOAD_ENABLED:
        raise RuntimeError("S3 Upload ist nicht konfiguriert. Bitte S3_BUCKET, S3_ACCESS_KEY und S3_SECRET_KEY setzen.")
    
    s3_client = _get_s3_client()
    if not s3_client:
        raise RuntimeError("S3 Client konnte nicht initialisiert werden")
    
    # S3 Key generieren (Pfad im Bucket)
    # Strategy: {job_id}/{timestamp}_{filename} wenn job_id vorhanden, sonst {timestamp}_{filename}
    # timestamp format: YYYYMMDD_HHMMSS (UTC)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    if job_id:
        s3_key = f"{job_id}/{timestamp}_{file_path.name}"
    else:
        s3_key = f"{timestamp}_{file_path.name}"
    
    print(f"☁️ Uploading {file_path.name} zu S3: s3://{S3_BUCKET}/{s3_key}")
    
    # Content-Type bestimmen
    content_type = "image/png"
    if file_path.suffix.lower() == ".jpg" or file_path.suffix.lower() == ".jpeg":
        content_type = "image/jpeg"
    elif file_path.suffix.lower() == ".webp":
        content_type = "image/webp"
    elif file_path.suffix.lower() == ".mp4":
        content_type = "video/mp4"
    elif file_path.suffix.lower() == ".gif":
        content_type = "image/gif"
    
    try:
        # Upload with content type - using signed URLs for security
        extra_args = {
            'ContentType': content_type,
        }
        
        s3_client.upload_file(
            str(file_path),
            S3_BUCKET,
            s3_key,
            ExtraArgs=extra_args
        )
        
        file_size = file_path.stat().st_size
        print(f"✅ Upload erfolgreich! ({file_size} bytes)")
        
        # URL generieren
        if S3_PUBLIC_URL:
            # Custom public URL (z.B. CDN)
            url = f"{S3_PUBLIC_URL.rstrip('/')}/{s3_key}"
            print(f"🌐 Public URL: {url}")
        else:
            # Signed URL generieren
            url = s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': S3_BUCKET, 'Key': s3_key},
                ExpiresIn=S3_SIGNED_URL_EXPIRY
            )
            expiry_minutes = S3_SIGNED_URL_EXPIRY // 60
            print(f"🔐 Signed URL generiert (gültig für {expiry_minutes} Minuten)")
        
        return url
        
    except ClientError as e:
        print(f"❌ S3 Upload fehlgeschlagen: {e}")
        raise
    except Exception as e:
        print(f"❌ Unerwarteter Fehler beim S3 Upload: {e}")
        raise


def _sanitize_job_id(job_id: Optional[str]) -> Optional[str]:
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


def _save_to_network_volume(file_path: Path, job_id: Optional[str] = None, retry_copy: bool = True) -> str:
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
    print(f"📦 S3 Upload: {'✅ Aktiviert' if S3_UPLOAD_ENABLED else '❌ Deaktiviert'}")
    print(f"📦 Volume Storage: {'✅ Aktiviert' if not S3_UPLOAD_ENABLED else '⚠️ Fallback'}")
    
    _start_comfy()

    # Volume readiness check - always ensure volume is ready for fallback
    # even when S3 is enabled, in case S3 upload fails
    volume_ready = _ensure_volume_ready()
    if not volume_ready:
        if S3_UPLOAD_ENABLED:
            print("⚠️ Volume nicht verfügbar - S3 Upload wird verwendet, aber kein Fallback möglich")
        else:
            raise RuntimeError(
                f"Weder S3 noch Network Volume sind konfiguriert! "
                f"Bitte S3 Umgebungsvariablen ODER Volume am Pfad {OUTPUT_BASE} bereitstellen."
            )

    prompt_id = _run_workflow(workflow)
    result = _wait_for_completion(prompt_id)
    
    # ComfyUI History API Struktur: result["outputs"] enthält node outputs
    links = []
    local_paths = []
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
                        # Upload zu S3 wenn aktiviert
                        if S3_UPLOAD_ENABLED:
                            try:
                                s3_url = _upload_to_s3(img_path, job_id=job_id)
                                links.append(s3_url)
                                local_paths.append(str(img_path))
                                print(f"✅ Erfolgreich zu S3 hochgeladen: {s3_url}")
                            except Exception as e:
                                print(f"❌ S3 Upload fehlgeschlagen: {e}")
                                # Fallback zu Volume wenn verfügbar
                                if _volume_ready():
                                    print(f"⚠️ Fallback: Speichere auf Network Volume...")
                                    network_file_path = _save_to_network_volume(img_path, job_id=job_id)
                                    links.append(network_file_path)
                                    local_paths.append(str(img_path))
                                    print(f"✅ Erfolgreich auf Volume gespeichert: {network_file_path}")
                                else:
                                    raise RuntimeError(f"Weder S3 noch Volume verfügbar! {e}")
                        else:
                            # Nur Volume verwenden
                            print(f"💾 Speichere auf Network Volume: {img_path}")
                            network_file_path = _save_to_network_volume(img_path, job_id=job_id)
                            links.append(network_file_path)
                            local_paths.append(network_file_path)
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
                if S3_UPLOAD_ENABLED:
                    try:
                        s3_url = _upload_to_s3(img_file, job_id=job_id)
                        links.append(s3_url)
                    except Exception as e:
                        print(f"❌ S3 Upload fehlgeschlagen für {img_file}: {e}")
                        if _volume_ready():
                            print(f"⚠️ Fallback: Speichere auf Network Volume...")
                            network_file_path = _save_to_network_volume(img_file, job_id=job_id)
                            links.append(network_file_path)
                            local_paths.append(network_file_path)
                            print(f"✅ Erfolgreich auf Volume gespeichert: {network_file_path}")
                        else:
                            print(f"❌ Weder S3 noch Volume verfügbar für {img_file}")
                else:
                    network_file_path = _save_to_network_volume(img_file, job_id=job_id)
                    links.append(network_file_path)
                    local_paths.append(network_file_path)
    response = {
        "links": links,
        "total_images": len(links),
        "job_id": job_id,
        "storage_type": "s3" if S3_UPLOAD_ENABLED else "volume",
    }
    
    # Optionale zusätzliche Infos
    if S3_UPLOAD_ENABLED:
        response["s3_bucket"] = S3_BUCKET
        response["local_paths"] = local_paths
    else:
        response["output_base"] = str(OUTPUT_BASE)
        response["saved_paths"] = links
    
    return response


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
