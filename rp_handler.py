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
import threading
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional
from botocore.exceptions import ClientError

COMFY_PORT = int(os.getenv("COMFY_PORT", 8188))
COMFY_HOST = os.getenv("COMFY_HOST", "127.0.0.1")
COMFY_URL = f"http://{COMFY_HOST}:{COMFY_PORT}"  # Base URL for ComfyUI API
OUTPUT_BASE = Path(os.getenv("RUNPOD_OUTPUT_DIR", os.getenv("RUNPOD_VOLUME_PATH", "/runpod-volume")))

# S3 Configuration
S3_BUCKET = os.getenv("S3_BUCKET")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL")  # For R2/Backblaze etc.
S3_REGION = os.getenv("S3_REGION", "auto")
S3_PUBLIC_URL = os.getenv("S3_PUBLIC_URL")  # Optional: Custom public URL (e.g. CDN)
S3_SIGNED_URL_EXPIRY = int(os.getenv("S3_SIGNED_URL_EXPIRY", 3600))  # Seconds (default: 1h)
S3_UPLOAD_ENABLED = bool(S3_BUCKET and S3_ACCESS_KEY and S3_SECRET_KEY)

_VOLUME_READY = False


class S3ClientManager:
    """Thread-safe singleton manager for S3 client to avoid global variable issues in serverless environments."""
    _instance = None
    _client = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                # Double-checked locking pattern
                if cls._instance is None:
                    cls._instance = super(S3ClientManager, cls).__new__(cls)
        return cls._instance
    
    def get_client(self):
        """Get or create S3 client."""
        if self._client is None and S3_UPLOAD_ENABLED:
            with self._lock:
                # Double-checked locking for thread safety
                if self._client is None:
                    print(f"🔧 Initializing S3 Client (Region: {S3_REGION})")
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
                        print(f"✅ S3 Bucket is accessible")
                    except ClientError as e:
                        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
                        # Log detailed error internally but don't expose sensitive info
                        print(f"❌ S3 Bucket access failed: {error_code}")
                        if error_code == '404':
                            print(f"❌ Bucket does not exist!")
                        elif error_code == '403':
                            print(f"❌ No permission for bucket!")
                        self._client = None  # Reset client to prevent usage
                        raise RuntimeError("S3 Storage is not available. Please check configuration.")
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
        raise RuntimeError("S3 Upload is not configured. Please set S3_BUCKET, S3_ACCESS_KEY and S3_SECRET_KEY.")
    
    # S3ClientManager().get_client() will raise RuntimeError if client cannot be initialized
    s3_client = S3ClientManager().get_client()
    
    # S3 Key generation strategy:
    # - Format: {job_id}/{timestamp}_{unique_id}_{filename} if job_id present, else {timestamp}_{unique_id}_{filename}
    # - timestamp: YYYYMMDD_HHMMSS_ffffff (UTC with microseconds, %f always produces 6 zero-padded digits)
    # - unique_id: 8-char hex UUID to prevent collisions in high-concurrency scenarios
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    unique_id = uuid.uuid4().hex[:8]
    if job_id:
        s3_key = f"{job_id}/{timestamp}_{unique_id}_{file_path.name}"
    else:
        s3_key = f"{timestamp}_{unique_id}_{file_path.name}"
    
    print(f"☁️ Uploading {file_path.name} to S3: s3://{S3_BUCKET}/{s3_key}")
    
    # Determine Content-Type
    suffix = file_path.suffix.lower()
    content_type = "image/png"
    if suffix == ".jpg" or suffix == ".jpeg":
        content_type = "image/jpeg"
    elif suffix == ".webp":
        content_type = "image/webp"
    elif suffix == ".mp4":
        content_type = "video/mp4"
    elif suffix == ".gif":
        content_type = "image/gif"
    
    try:
        # Set content type for the uploaded object; this will be returned when accessed, including via signed URLs
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
        print(f"✅ Upload successful! ({file_size} bytes)")
        
        # Generate URL
        if S3_PUBLIC_URL:
            # Custom public URL (e.g. CDN)
            url = f"{S3_PUBLIC_URL.rstrip('/')}/{s3_key}"
            print(f"🌐 Public URL: {url}")
        else:
            # Generate signed URL
            url = s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': S3_BUCKET, 'Key': s3_key},
                ExpiresIn=S3_SIGNED_URL_EXPIRY
            )
            expiry_minutes = S3_SIGNED_URL_EXPIRY // 60
            print(f"🔐 Signed URL generated (valid for {expiry_minutes} minutes)")
        
        return url
        
    except ClientError as e:
        print(f"❌ S3 Upload failed: {e}")
        raise
    except Exception as e:
        print(f"❌ Unexpected error during S3 upload: {e}")
        raise


def _sanitize_job_id(job_id: Optional[str]) -> Optional[str]:
    if not job_id:
        return None
    sanitized = re.sub(r"[^a-zA-Z0-9_.-]", "_", str(job_id))
    return sanitized.strip("._") or None

# ----------------------------------------------------------------------------
# Helper Functions
# ----------------------------------------------------------------------------

def _is_comfy_running() -> bool:
    """Check if ComfyUI responds on the designated port."""
    try:
        r = requests.get(f"{COMFY_URL}/system_stats", timeout=2)
        return r.status_code == 200
    except requests.RequestException:
        return False


def _start_comfy():
    """Start ComfyUI in background if not already running."""
    if _is_comfy_running():
        print("✅ ComfyUI is already running.")
        return

    print("🚀 Starting ComfyUI in background…")
    log_path = "/workspace/comfy.log"
    
    # Less aggressive memory parameters for container environment
    cmd = [
        "python", "/workspace/ComfyUI/main.py",
        "--listen", COMFY_HOST,
        "--port", str(COMFY_PORT),
        "--normalvram",  # Instead of --highvram for better container compatibility
        "--preview-method", "auto",
        "--verbose",  # For debug logs
    ]
    
    print(f"🎯 ComfyUI Start Command: {' '.join(cmd)}")
    
    with open(log_path, "a") as log_file:
        subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT, cwd="/workspace/ComfyUI")

    # Wait until API is reachable
    for _ in range(30):
        if _is_comfy_running():
            print("✅ ComfyUI is running.")
            return
        time.sleep(2)
    raise RuntimeError("ComfyUI could not be started.")


def _normalize_workflow(workflow_input):
    """Accept workflow input in multiple formats and always return a dict."""
    # Already a dict – nothing to do.
    if isinstance(workflow_input, dict):
        return workflow_input

    # Stringified JSON – attempt to decode recursively.
    if isinstance(workflow_input, str):
        stripped = workflow_input.strip()
        if not stripped:
            raise ValueError("workflow provided as empty string")
        try:
            decoded = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"workflow JSON konnte nicht geparsed werden: {exc}") from exc
        normalized = _normalize_workflow(decoded)
        if normalized is None:
            raise ValueError("workflow JSON enthält keine gültige Struktur")
        return normalized

    # Potential wrapper object with workflow key.
    if isinstance(workflow_input, (list, tuple)):
        raise TypeError("workflow muss ein Objekt (dict) sein, keine Liste")

    raise TypeError(f"workflow Typ wird nicht unterstützt: {type(workflow_input).__name__}")


def _run_workflow(workflow: dict):
    """Send workflow to Comfy and wait for result."""
    if not isinstance(workflow, dict):
        raise TypeError("workflow muss ein dict sein")
    # ComfyUI API expects {"prompt": workflow, "client_id": uuid} format
    client_id = str(uuid.uuid4())
    payload = {"prompt": workflow, "client_id": client_id}
    
    print(f"📤 Sending Workflow to ComfyUI API...")
    print(f"🔗 URL: {COMFY_URL}/prompt")
    print(f"🆔 Client ID: {client_id}")
    print(f"📋 Workflow Node Count: {len(workflow)}")
    print(f"🔍 Workflow Nodes: {list(workflow.keys())}")
    
    # DEBUG: Test available API Endpoints
    try:
        print("🔄 Testing ComfyUI System Stats...")
        test_r = requests.get(f"{COMFY_URL}/system_stats", timeout=5)
        print(f"✅ System Stats: {test_r.status_code}")
        
        print("🔄 Testing available Models...")
        models_r = requests.get(f"{COMFY_URL}/object_info", timeout=5)
        if models_r.status_code == 200:
            object_info = models_r.json()
            checkpoints = object_info.get("CheckpointLoaderSimple", {}).get("input", {}).get("required", {}).get("ckpt_name", [[]])
            if len(checkpoints) > 0 and len(checkpoints[0]) > 0:
                print(f"📦 Available Checkpoints: {checkpoints[0][:3]}..." if len(checkpoints[0]) > 3 else checkpoints[0])
            else:
                print("⚠️ No Checkpoints found!")
        else:
            print(f"⚠️ Object Info not reachable: {models_r.status_code}")
    except Exception as e:
        print(f"❌ API Tests failed: {e}")
        # Not fatal - continue anyway
    
    # DEBUG: Check Output directory for SaveImage Node
    output_dir = Path("/workspace/ComfyUI/output")
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"📁 Output Dir: {output_dir}, exists: {output_dir.exists()}, writable: {os.access(output_dir, os.W_OK)}")
    
    # DEBUG: Validate Workflow structure
    save_image_nodes = [
        node_id
        for node_id, node in workflow.items()
        if isinstance(node, dict) and node.get("class_type") == "SaveImage"
    ]
    print(f"💾 SaveImage Nodes found: {len(save_image_nodes)}")
    
    try:
        print(f"🚀 Sending Workflow with client_id...")
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
            print(f"❌ No prompt_id in Response: {response_data}")
            raise ValueError(f"ComfyUI Response invalid: {response_data}")
            
        print(f"✅ Workflow sent! Prompt ID: {prompt_id}")
        return prompt_id
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Request Exception: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"📄 Error Response: {e.response.text}")
        raise

def _wait_for_completion(prompt_id: str):
    """Wait for workflow completion and return result."""
    print(f"⏳ Waiting for completion of prompt {prompt_id}…")
    
    for attempt in range(60):  # Max 3 minutes wait
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
                        print("✅ Workflow successfully completed!")
                        return result
                    elif status_str == "error" or "error" in status:
                        error_msg = status.get("error", status)
                        print(f"❌ ComfyUI Workflow Error: {error_msg}")
                        raise RuntimeError(f"ComfyUI Workflow failed: {error_msg}")
                else:
                    print(f"⏳ Prompt {prompt_id} not yet in History...")
        except Exception as e:
            print(f"⚠️ Status check error (attempt {attempt+1}): {e}")
        
        time.sleep(3)
    
    raise TimeoutError("Workflow Timeout after 3 minutes")


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

    Expected event["input"] with:
      - workflow: dict  (ComfyUI Workflow JSON)
    """
    inp = event.get("input", {})
    workflow_raw = inp.get("workflow")
    if workflow_raw is None:
        raise ValueError("workflow missing in input")

    workflow = _normalize_workflow(workflow_raw)
    if not isinstance(workflow, dict) or not workflow:
        raise ValueError("workflow ist leer oder hat kein gültiges Format (dict erwartet)")

    raw_job_id = event.get("id") or event.get("requestId") or inp.get("jobId")
    job_id = _sanitize_job_id(raw_job_id)
    if raw_job_id and not job_id:
        print(f"⚠️ Received job ID '{raw_job_id}' but sanitization removed all characters")
    print(f"🆔 Runpod Job ID: {job_id}")

    print("🚀 Handler started - ComfyUI Workflow is being processed...")
    print(f"📦 S3 Upload: {'✅ Enabled' if S3_UPLOAD_ENABLED else '❌ Disabled'}")
    print(f"📦 Volume Storage: {'✅ Enabled' if not S3_UPLOAD_ENABLED else '⚠️ Fallback'}")
    
    _start_comfy()

    # Volume readiness check - always ensure volume is ready for fallback
    # even when S3 is enabled, in case S3 upload fails
    volume_ready = _ensure_volume_ready()
    if not volume_ready:
        if S3_UPLOAD_ENABLED:
            print("⚠️ Volume not available - S3 Upload will be used, but no fallback possible")
        else:
            raise RuntimeError(
                f"Network volume could not be mounted and S3 is not configured. "
                f"Either set S3 environment variables or ensure volume is mounted at {OUTPUT_BASE}."
            )

    prompt_id = _run_workflow(workflow)
    result = _wait_for_completion(prompt_id)
    
    # ComfyUI History API structure: result["outputs"] contains node outputs
    links = []
    local_paths = []
    outputs = result.get("outputs", {})
    
    print(f"📁 Searching for generated files in outputs...")
    for node_id, node_output in outputs.items():
        if "images" in node_output:
            for img_data in node_output["images"]:
                # ComfyUI stores images by default in /workspace/ComfyUI/output/
                filename = img_data.get("filename")
                subfolder = img_data.get("subfolder", "")
                
                if filename:
                    # Full path to image
                    if subfolder:
                        img_path = Path(f"/workspace/ComfyUI/output/{subfolder}/{filename}")
                    else:
                        img_path = Path(f"/workspace/ComfyUI/output/{filename}")
                    
                    print(f"🖼️ Found image: {img_path}")
                    if img_path.exists():
                        # Upload to S3 when enabled
                        if S3_UPLOAD_ENABLED:
                            try:
                                s3_url = _upload_to_s3(img_path, job_id=job_id)
                                links.append(s3_url)
                                local_paths.append(str(img_path))
                                print(f"✅ Successfully uploaded to S3: {s3_url}")
                            except Exception as e:
                                print(f"⚠️ S3 Upload failed: {e}")
                                # Fallback to Volume when available
                                if _volume_ready():
                                    print(f"⚠️ Using fallback to Network Volume...")
                                    try:
                                        network_file_path = _save_to_network_volume(img_path, job_id=job_id)
                                        links.append(network_file_path)
                                        local_paths.append(str(img_path))
                                        print(f"✅ Successfully saved to volume: {network_file_path}")
                                    except Exception as vol_err:
                                        print(f"❌ Volume save failed: {vol_err}")
                                        raise RuntimeError(
                                            f"S3 upload failed and volume fallback unavailable for {img_path.name}"
                                        )
                                else:
                                    print(f"❌ No volume fallback available for {img_path.name}")
                                    raise RuntimeError(f"S3 upload failed and no volume fallback available")
                        else:
                            # Only use volume
                            print(f"💾 Saving to Network Volume: {img_path}")
                            network_file_path = _save_to_network_volume(img_path, job_id=job_id)
                            links.append(network_file_path)
                            # Store original local path for consistency with S3 mode
                            local_paths.append(str(img_path))
                            print(f"✅ Successfully saved: {network_file_path}")
                    else:
                        print(f"⚠️ File not found: {img_path}")

    if not links:
        print("❌ No images found in ComfyUI outputs")
        # Fallback: search all images in output directory
        output_dir = Path("/workspace/ComfyUI/output")
        if output_dir.exists():
            for img_file in output_dir.glob("*.png"):
                print(f"💾 Fallback save: {img_file}")
                if S3_UPLOAD_ENABLED:
                    try:
                        s3_url = _upload_to_s3(img_file, job_id=job_id)
                        links.append(s3_url)
                        local_paths.append(str(img_file))
                    except Exception as e:
                        print(f"⚠️ S3 Upload failed for {img_file.name}: {e}")
                        if _volume_ready():
                            print(f"⚠️ Using fallback to Network Volume...")
                            try:
                                network_file_path = _save_to_network_volume(img_file, job_id=job_id)
                                links.append(network_file_path)
                                local_paths.append(str(img_file))
                                print(f"✅ Successfully saved to volume: {network_file_path}")
                            except Exception as vol_err:
                                print(f"❌ Volume save failed for {img_file.name}: {vol_err}")
                        else:
                            print(f"❌ No volume fallback available for {img_file.name}")
                else:
                    network_file_path = _save_to_network_volume(img_file, job_id=job_id)
                    links.append(network_file_path)
                    # Store original local path for consistency with S3 mode
                    local_paths.append(str(img_file))
    response = {
        "links": links,
        "total_images": len(links),
        "job_id": job_id,
        "storage_type": "s3" if S3_UPLOAD_ENABLED else "volume",
    }
    
    # Optional additional info
    if S3_UPLOAD_ENABLED:
        response["s3_bucket"] = S3_BUCKET
        response["local_paths"] = local_paths
    else:
        response["output_base"] = str(OUTPUT_BASE)
        response["saved_paths"] = links
    
    return response


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
