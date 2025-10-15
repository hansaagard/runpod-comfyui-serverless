#!/usr/bin/env python3

import runpod
import requests
import json
import time
import subprocess
import os
import sys
import uuid
import shutil
import datetime
import traceback
import mimetypes
import random
import copy
from pathlib import Path
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from botocore.config import Config
from urllib.parse import urlparse, urlunparse

# Constants
WORKSPACE_PATH = Path("/workspace")
RUNPOD_VOLUME_PATH = Path("/runpod-volume")
COMFYUI_PATH = WORKSPACE_PATH / "ComfyUI"
COMFYUI_MODELS_PATH = COMFYUI_PATH / "models"
COMFYUI_OUTPUT_PATH = COMFYUI_PATH / "output"
COMFYUI_LOGS_PATH = WORKSPACE_PATH / "logs"
COMFYUI_HOST = "127.0.0.1"
COMFYUI_PORT = 8188
COMFYUI_BASE_URL = f"http://{COMFYUI_HOST}:{COMFYUI_PORT}"
DEFAULT_WORKFLOW_DURATION_SECONDS = 60  # Default fallback for workflow start time
SUPPORTED_IMAGE_EXTENSIONS = ["*.png", "*.jpg", "*.jpeg", "*.webp", "*.gif"]
SUPPORTED_VIDEO_EXTENSIONS = ["*.mp4", "*.webm", "*.mov", "*.avi"]

# Global variable to track the ComfyUI process
_comfyui_process = None


def _parse_bool_env(key: str, default: str = "false") -> bool:
    """Safely parse environment variable as boolean."""

    value = os.getenv(key, default).lower()
    return value in {"1", "true", "yes", "on"}


def _get_s3_config() -> dict:
    """Get S3 configuration from environment variables."""
    return {
        "bucket": os.getenv("S3_BUCKET"),
        "access_key": os.getenv("S3_ACCESS_KEY"),
        "secret_key": os.getenv("S3_SECRET_KEY"),
        "endpoint_url": os.getenv("S3_ENDPOINT_URL"),
        "region": os.getenv("S3_REGION", "auto"),
        "public_url": os.getenv("S3_PUBLIC_URL"),
        "signed_url_expiry": int(os.getenv("S3_SIGNED_URL_EXPIRY", "3600")),
    }


def _is_s3_configured() -> bool:
    """Check if S3 is properly configured."""
    config = _get_s3_config()
    return all([config["bucket"], config["access_key"], config["secret_key"]])


def _get_s3_client():
    """Create and return S3 client."""
    config = _get_s3_config()
    
    # Allow configuration of S3 signature version and addressing style
    signature_version = os.getenv("S3_SIGNATURE_VERSION", "s3v4")
    addressing_style = os.getenv("S3_ADDRESSING_STYLE", "path")
    
    s3_config = Config(
        signature_version=signature_version,
        s3={'addressing_style': addressing_style}
    )
    
    client_kwargs = {
        "aws_access_key_id": config["access_key"],
        "aws_secret_access_key": config["secret_key"],
        "config": s3_config,
    }
    
    if config["endpoint_url"]:
        client_kwargs["endpoint_url"] = config["endpoint_url"]
    
    if config["region"]:
        client_kwargs["region_name"] = config["region"]
    
    return boto3.client("s3", **client_kwargs)


def _sanitize_url_for_logging(url: str) -> str:
    """
    Sanitize URL for safe logging by removing sensitive query parameters.
    
    For presigned URLs, this strips the query string containing authentication tokens
    (X-Amz-Signature, etc.) to prevent security leaks in logs.
    
    Args:
        url: Full URL (public or presigned)
        
    Returns:
        str: Sanitized URL safe for logging
    """
    try:
        parsed = urlparse(url)
        
        # Check if this is a presigned URL (has query parameters with AWS signature)
        if parsed.query and 'X-Amz-Signature' in parsed.query:
            # Strip all query parameters for presigned URLs
            sanitized = urlunparse((
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                '',  # params
                '',  # query (removed for security)
                ''   # fragment
            ))
            return f"{sanitized} [presigned - query params redacted for security]"
        else:
            # Public URL or CDN - safe to log in full
            return url
    except (ValueError, TypeError):
        # Fallback: return URL as-is if parsing fails
        return url


def _get_content_type(file_path: Path) -> str:
    """
    Determine MIME type based on file extension.
    
    Args:
        file_path: Path to the file
        
    Returns:
        str: MIME type string (e.g., 'image/png', 'video/mp4')
    """
    # Initialize mimetypes if not already done
    if not mimetypes.inited:
        mimetypes.init()
    
    # Get MIME type from file extension
    mime_type, _ = mimetypes.guess_type(str(file_path))
    
    # If mimetypes couldn't determine, fallback to common types for AI-generated content
    if mime_type is None:
        # Define a minimal fallback mapping for common AI output formats
        fallback_types = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.webp': 'image/webp',
            '.gif': 'image/gif',
            '.mp4': 'video/mp4',
            '.avi': 'video/x-msvideo',
            '.mov': 'video/quicktime',
            '.webm': 'video/webm',
        }
        ext = file_path.suffix.lower()
        mime_type = fallback_types.get(ext, 'application/octet-stream')
    
    return mime_type


def _upload_to_s3(file_path: Path, job_id: str) -> dict:
    """
    Upload file to S3.
    
    Returns:
        dict: {"success": bool, "url": str, "error": str}
    """
    print(f"☁️ Uploading to S3: {file_path.name}")
    
    try:
        config = _get_s3_config()
        s3_client = _get_s3_client()
        
        # Generate S3 key with job_id prefix and timestamp
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
        s3_key = f"{job_id}/{timestamp}_{file_path.name}"
        
        # Determine content type based on file extension
        content_type = _get_content_type(file_path)
        print(f"📋 Detected content type: {content_type}")
        
        # Get cache control setting from environment or use default (1 year)
        cache_control = os.getenv("S3_CACHE_CONTROL", "public, max-age=31536000")
        
        # Upload file
        print(f"📤 Uploading to bucket: {config['bucket']}, key: {s3_key}")
        with open(file_path, "rb") as f:
            s3_client.upload_fileobj(
                f,
                config["bucket"],
                s3_key,
                ExtraArgs={
                    "ContentType": content_type,
                    "CacheControl": cache_control,
                }
            )
        
        # Generate URL
        if config["public_url"]:
            # Use custom public URL (e.g., CDN)
            url = f"{config['public_url'].rstrip('/')}/{s3_key}"
        else:
            # Generate presigned URL
            url = s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": config["bucket"], "Key": s3_key},
                ExpiresIn=config["signed_url_expiry"],
            )
        
        print(f"✅ S3 Upload successful: {s3_key}")
        # Sanitize URL for logging to avoid exposing presigned URL tokens
        safe_url = _sanitize_url_for_logging(url)
        print(f"🔗 URL: {safe_url}")
        
        # Only log full URL with auth tokens if explicitly enabled (security risk)
        if _parse_bool_env("DEBUG_S3_URLS", "false"):
            print(f"🔍 DEBUG: Full URL with auth tokens: {url}")
            print("⚠️  WARNING: Full S3 URLs contain sensitive authentication tokens!")
        
        return {
            "success": True,
            "url": url,
            "s3_key": s3_key,
            "error": None
        }
        
    except NoCredentialsError:
        error_msg = "S3 credentials not found or invalid"
        print(f"❌ S3 Upload Error: {error_msg}")
        return {"success": False, "url": None, "error": error_msg}
    
    except ClientError as e:
        error_msg = f"S3 Client Error: {e}"
        print(f"❌ S3 Upload Error: {error_msg}")
        return {"success": False, "url": None, "error": error_msg}
    
    except Exception as e:
        error_msg = f"Unexpected S3 Error: {e}"
        print(f"❌ S3 Upload Error: {error_msg}")
        print(f"📋 Traceback: {traceback.format_exc()}")
        return {"success": False, "url": None, "error": error_msg}


def _cleanup_temp_files(file_paths: list[Path]) -> int:
    """
    Clean up temporary ComfyUI output files after successful upload.
    
    Args:
        file_paths: List of file paths to clean up
        
    Returns:
        int: Number of files successfully deleted
    """
    if not _parse_bool_env("CLEANUP_TEMP_FILES", "true"):
        print("📋 Cleanup disabled via CLEANUP_TEMP_FILES=false")
        return 0
    
    deleted_count = 0
    for file_path in file_paths:
        try:
            if file_path.exists():
                file_path.unlink()
                deleted_count += 1
        except Exception as e:
            print(f"⚠️ Could not delete temp file {file_path.name}: {e}")
    
    if deleted_count > 0:
        print(f"🧹 Cleaned up {deleted_count} temporary file(s)")
    
    return deleted_count


def _wait_for_path(path: Path, timeout: int = 20, poll_interval: float = 1.0) -> bool:
    """Wait until a path exists or timeout is reached."""

    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            return True
        time.sleep(poll_interval)

    return path.exists()


def _get_volume_base() -> Path:
    """Determine the base mount path for the Network Volume in Serverless/Pods."""
    timeout = int(os.getenv("NETWORK_VOLUME_TIMEOUT", "15"))

    if _wait_for_path(RUNPOD_VOLUME_PATH, timeout=timeout):
        print(f"📦 Detected Serverless Network Volume at {RUNPOD_VOLUME_PATH}")
        return RUNPOD_VOLUME_PATH
    print(f"📦 Using {WORKSPACE_PATH} as volume base (no {RUNPOD_VOLUME_PATH} detected)")
    return WORKSPACE_PATH

def _setup_volume_models():
    """Setup Volume Models with symlinks - the only solution that works in Serverless!"""
    print("📦 Setting up Volume Models with symlinks...")
    
    try:
        volume_base = _get_volume_base()
        print(f"🔍 Volume Base: {volume_base}")
        
        # Check the most common Volume Model structures
        possible_volume_model_dirs = [
            volume_base / "ComfyUI" / "models",     # /runpod-volume/ComfyUI/models
            volume_base / "models",                  # /runpod-volume/models  
            volume_base / "comfyui_models",         # /runpod-volume/comfyui_models
        ]
        
        volume_models_dir = None
        for path in possible_volume_model_dirs:
            if path.exists():
                print(f"✅ Volume Models Directory found: {path}")
                volume_models_dir = path
                break
        
        if not volume_models_dir:
            print(f"⚠️ No Volume Models found in: {[str(p) for p in possible_volume_model_dirs]}")
            return False
        
        # ComfyUI Models Directory - where ComfyUI expects the models
        comfy_models_dir = COMFYUI_MODELS_PATH
        comfy_models_parent = comfy_models_dir.parent
        comfy_models_parent.mkdir(parents=True, exist_ok=True)

        # Check for self-referential symlink: if volume base is WORKSPACE_PATH and volume_models_dir
        # would be the same as or contain comfy_models_dir, skip symlink creation
        try:
            volume_resolved = volume_models_dir.resolve()
            comfy_resolved = comfy_models_dir.resolve() if comfy_models_dir.exists() else comfy_models_dir
            
            if volume_resolved == comfy_resolved:
                print(f"✅ Volume models directory is already at the expected location: {comfy_models_dir}")
                print(f"⚠️ Skipping symlink creation (would be self-referential)")
                return True
            
            # Also check if both are under WORKSPACE_PATH (no real volume mounted)
            if volume_base == WORKSPACE_PATH:
                print(f"⚠️ No network volume detected (using {WORKSPACE_PATH} as fallback)")
                print(f"✅ Using local models directory: {comfy_models_dir}")
                # Ensure the directory exists
                comfy_models_dir.mkdir(parents=True, exist_ok=True)
                return True
        except (FileNotFoundError, OSError) as e:
            print(f"⚠️ Path resolution warning: {e}")

        symlink_needed = True
        
        if comfy_models_dir.is_symlink():
            try:
                current_target = comfy_models_dir.resolve()
                if current_target == volume_models_dir.resolve():
                    print("🔗 Symlink already exists and points to the volume.")
                    symlink_needed = False
                else:
                    print(f"🗑️ Removing existing symlink: {comfy_models_dir} → {current_target}")
                    comfy_models_dir.unlink()
            except (FileNotFoundError, OSError) as resolve_error:
                # Broken/malformed symlink - cannot be resolved
                print(f"🗑️ Removing broken symlink (resolve failed: {resolve_error})...")
                comfy_models_dir.unlink()
        elif comfy_models_dir.exists():
            print(f"🗑️ Removing local models directory: {comfy_models_dir}")
            shutil.rmtree(comfy_models_dir)
        
        # Create symlink only if needed
        if symlink_needed:
            print(f"🔗 Creating symlink: {comfy_models_dir} → {volume_models_dir}")
            try:
                comfy_models_dir.symlink_to(volume_models_dir, target_is_directory=True)
            except FileExistsError:
                # Edge case: Symlink was created by another process in the meantime
                print(f"⚠️ Symlink already exists (race condition)")
                # Verify that it is correct
                if comfy_models_dir.is_symlink():
                    try:
                        current_target = comfy_models_dir.resolve()
                        if current_target == volume_models_dir.resolve():
                            print("🔗 Symlink is correct")
                        else:
                            print(f"❌ Symlink points to wrong target: {current_target}")
                            return False
                    except (FileNotFoundError, OSError):
                        print("❌ Symlink is broken")
                        return False
                else:
                    print("❌ Path is blocked by file/directory")
                    return False
        
        # Verify the symlink
        if comfy_models_dir.is_symlink() and comfy_models_dir.exists():
            print(f"✅ Symlink successfully created and verified!")
            
            # Show available model types
            model_subdirs = ["checkpoints", "vae", "loras", "unet", "clip", "clip_vision", "text_encoders", "diffusion_models"]
            found_types = []
            
            for subdir in model_subdirs:
                subdir_path = comfy_models_dir / subdir
                if subdir_path.exists():
                    model_files = list(subdir_path.glob("*.safetensors")) + list(subdir_path.glob("*.ckpt"))
                    if model_files:
                        print(f"   📂 {subdir}: {len(model_files)} Models")
                        found_types.append(subdir)
                    else:
                        print(f"   📂 {subdir}: Directory exists, but empty")
            
            if found_types:
                print(f"🎯 Models available in: {', '.join(found_types)}")
                return True
            else:
                print(f"⚠️ Symlink created, but no models found!")
                return False
        else:
            print(f"❌ Symlink creation failed!")
            return False
            
    except Exception as e:
        print(f"❌ Volume Model Setup Error: {e}")
        print(f"📋 Traceback: {traceback.format_exc()}")
        return False

def _is_comfyui_running():
    """Check if ComfyUI is already running."""
    try:
        response = requests.get(f"{COMFYUI_BASE_URL}/system_stats", timeout=2)
        if response.status_code == 200:
            return True
    except requests.exceptions.RequestException:
        pass
    return False


def _wait_for_comfyui(max_retries=600, delay=2):
    """Wait until ComfyUI is ready. Default: 20 minutes (600 retries × 2 sec = 1200s)"""
    print(f"⏳ Waiting for ComfyUI to start (timeout: {max_retries * delay}s = {max_retries * delay / 60:.1f} min)...")
    
    for i in range(max_retries):
        try:
            response = requests.get(f"{COMFYUI_BASE_URL}/system_stats", timeout=5)
            if response.status_code == 200:
                elapsed = (i + 1) * delay
                print(f"✅ ComfyUI is running (started after ~{elapsed}s = {elapsed / 60:.1f} min)")
                return True
        except requests.exceptions.RequestException:
            pass
        
        if i < max_retries - 1:
            # Print every 10 seconds to avoid log spam
            if (i + 1) % 5 == 0:
                elapsed = (i + 1) * delay
                print(f"⏳ Still waiting for ComfyUI... ({elapsed}s / {max_retries * delay}s)")
            time.sleep(delay)
    
    print(f"❌ ComfyUI failed to start after {max_retries * delay}s ({max_retries * delay / 60:.1f} min)!")
    return False


def _direct_model_refresh() -> bool:
    """Trigger a direct model refresh via the object_info endpoint."""

    try:
        print("🔄 Alternative: Direct Model Scan...")
        refresh_response = requests.get(
            f"{COMFYUI_BASE_URL}/object_info/CheckpointLoaderSimple",
            params={"refresh": "true"},
            timeout=10,
        )
        print(f"📋 Direct Refresh Response: {refresh_response.status_code}")
        return refresh_response.status_code == 200
    except requests.exceptions.RequestException as error:
        print(f"⚠️ Direct refresh failed: {error}")
        return False


def _force_model_refresh() -> bool:
    """Attempt model refresh via manager endpoint, fallback to direct scan."""

    print("🔄 Force Model Refresh after symlink creation...")
    manager_root = f"{COMFYUI_BASE_URL}/manager"

    try:
        discovery_response = requests.get(manager_root, timeout=5)
        print(f"📋 Manager Discovery Status: {discovery_response.status_code}")
    except requests.exceptions.RequestException as discovery_error:
        print(f"⚠️ Manager Endpoint Discovery failed: {discovery_error}")
        return _direct_model_refresh()

    if discovery_response.status_code == 404:
        print("⚠️ Manager Plugin not available (404)")
        return _direct_model_refresh()

    if discovery_response.status_code >= 500:
        print(f"⚠️ Manager Discovery error code {discovery_response.status_code}, using fallback")
        return _direct_model_refresh()

    try:
        refresh_response = requests.post(f"{manager_root}/reboot", timeout=10)
        print(f"📋 Manager Refresh Status: {refresh_response.status_code}")
        if refresh_response.status_code == 200:
            # Wait briefly for restart
            time.sleep(3)
            if not _wait_for_comfyui():
                print("⚠️ ComfyUI restart after Model Refresh failed")
                return False
            print("✅ Model Refresh successful!")
            return True
        print("⚠️ Manager Refresh not successful, trying Direct Scan")
    except requests.exceptions.RequestException as refresh_error:
        print(f"⚠️ Manager Refresh failed: {refresh_error}")

    return _direct_model_refresh()


def _extract_checkpoint_names(object_info: dict) -> list:
    """Safely extract checkpoint names from ComfyUI object_info response."""
    try:
        # Navigate through the nested structure
        checkpoint_loader = object_info.get("CheckpointLoaderSimple", {})
        input_spec = checkpoint_loader.get("input", {})
        required_spec = input_spec.get("required", {})
        ckpt_name = required_spec.get("ckpt_name", [])
        
        # Handle nested list format [[model_names], {}]
        if isinstance(ckpt_name, list) and len(ckpt_name) > 0:
            if isinstance(ckpt_name[0], list):
                # Nested format: extract first list
                return ckpt_name[0] if len(ckpt_name[0]) > 0 else []
            else:
                # Simple list format
                return ckpt_name
        
        return []
    except (AttributeError, TypeError, KeyError, IndexError) as e:
        print(f"⚠️ Error extracting checkpoint names: {e}")
        return []


def _randomize_seeds(workflow: dict) -> dict:
    """
    Randomize all seed values in the workflow.
    
    This function walks through all nodes in the workflow and replaces any 'seed'
    parameters with random values (0 to 2^31-1). This ensures that each workflow 
    execution produces different results, even if the same workflow is sent multiple times.
    
    Uses recursive traversal to handle arbitrarily nested seed values in complex
    workflow structures. Creates a deep copy to avoid modifying the original workflow object.
    
    Args:
        workflow: ComfyUI workflow dictionary
        
    Returns:
        dict: Modified workflow with randomized seeds (deep copy)
    """
    # Check if seed randomization is disabled via env var
    if not _parse_bool_env("RANDOMIZE_SEEDS", "true"):
        print("🎲 Seed randomization disabled via RANDOMIZE_SEEDS=false")
        return workflow
    
    # Create deep copy to avoid in-place modification (only when randomization is enabled)
    workflow = copy.deepcopy(workflow)
    randomized_count = 0
    
    def _generate_random_seed():
        """
        Generate a random seed value using getrandbits for better performance.
        
        Uses getrandbits(31) to generate values in the range 0 to 2,147,483,647 (2^31-1).
        This range is safe for signed 32-bit integers used by ComfyUI nodes.
        getrandbits is more efficient than randint for generating random integers.
        """
        return random.getrandbits(31)
    
    def _randomize_seeds_in_obj(obj, node_id=None, path=""):
        """Recursively traverse and randomize all seed values in nested structures."""
        nonlocal randomized_count
        
        if isinstance(obj, dict):
            for key, value in obj.items():
                current_path = f"{path}.{key}" if path else key
                if key == "seed" and isinstance(value, (int, float)):
                    # Found a seed parameter - randomize it
                    old_seed = value
                    new_seed = _generate_random_seed()
                    obj[key] = new_seed
                    randomized_count += 1
                    
                    if node_id is not None:
                        print(f"🎲 Node {node_id}: Randomized seed at {current_path}: {old_seed} → {new_seed}")
                    else:
                        print(f"🎲 Randomized seed at {current_path}: {old_seed} → {new_seed}")
                else:
                    # Recursively process nested structures
                    _randomize_seeds_in_obj(value, node_id=node_id, path=current_path)
                    
        elif isinstance(obj, list):
            for idx, item in enumerate(obj):
                current_path = f"{path}[{idx}]" if path else f"[{idx}]"
                _randomize_seeds_in_obj(item, node_id=node_id, path=current_path)
        # For primitives (int, float, str, etc.), do nothing
    
    # Walk through all nodes in the workflow
    for node_id, node_data in workflow.items():
        if isinstance(node_data, dict) and "inputs" in node_data:
            inputs = node_data["inputs"]
            _randomize_seeds_in_obj(inputs, node_id=node_id, path="inputs")
    
    if randomized_count > 0:
        print(f"✅ Randomized {randomized_count} seed(s) in workflow")
    else:
        print("ℹ️ No seeds found in workflow to randomize")
    
    return workflow


def _run_workflow(workflow):
    """Execute ComfyUI workflow."""
    client_id = str(uuid.uuid4())
    workflow_start_time = time.time()  # Track when workflow execution starts
    
    try:
        print(f"📤 Sending workflow to ComfyUI API...")
        print(f"🔗 URL: {COMFYUI_BASE_URL}/prompt")
        print(f"🆔 Client ID: {client_id}")
        print(f"📋 Workflow Node Count: {len(workflow)}")
        print(f"🔍 Workflow Nodes: {list(workflow.keys())}")
        
        # Test system stats
        print(f"🔄 Testing ComfyUI System Stats...")
        stats_response = requests.get(f"{COMFYUI_BASE_URL}/system_stats", timeout=10)
        print(f"✅ System Stats: {stats_response.status_code}")
        
        # Test available models
        print(f"🔄 Testing available models...")
        models_response = requests.get(f"{COMFYUI_BASE_URL}/object_info", timeout=10)
        if models_response.status_code == 200:
            object_info = models_response.json()
            checkpoints = _extract_checkpoint_names(object_info)
            print(f"📋 Available Checkpoints: {checkpoints}")
            if not checkpoints:
                print("⚠️ No checkpoints found!")
        
        # Check output directory
        output_dir = COMFYUI_OUTPUT_PATH
        print(f"📁 Output Dir: {output_dir}, exists: {output_dir.exists()}, writable: {os.access(output_dir, os.W_OK) if output_dir.exists() else False}")
        
        # Count SaveImage nodes
        save_nodes = [k for k, v in workflow.items() if v.get("class_type") == "SaveImage"]
        print(f"💾 SaveImage Nodes found: {len(save_nodes)}")
        
        print(f"🚀 Sending workflow with client_id...")
        
        response = requests.post(
            f"{COMFYUI_BASE_URL}/prompt",
            json={"prompt": workflow, "client_id": client_id},
            timeout=30
        )
        
        print(f"📤 Response Status: {response.status_code}")
        print(f"📤 Response Headers: {dict(response.headers)}")
        
        if response.status_code != 200:
            print(f"📜 Response Body: {response.text}")
            return None
            
        result = response.json()
        prompt_id = result.get("prompt_id")
        
        if not prompt_id:
            print(f"❌ No prompt_id received: {result}")
            return None
            
        print(f"✅ Workflow sent. Prompt ID: {prompt_id}")
        
        # Wait for completion - long timeout for heavy video rendering
        max_wait = 3600  # 60 minutes for video rendering
        start_time = time.monotonic()
        poll_interval = 5  # seconds
        print(f"⏳ Workflow execution timeout: {max_wait}s ({max_wait / 60:.0f} min)")

        while True:
            elapsed = time.monotonic() - start_time
            
            try:
                history_response = requests.get(f"{COMFYUI_BASE_URL}/history/{prompt_id}", timeout=10)
                if history_response.status_code == 200:
                    history = history_response.json()
                    if prompt_id in history:
                        prompt_history = history[prompt_id]
                        status = prompt_history.get("status", {})
                        
                        if status.get("status_str") == "success":
                            print(f"✅ Workflow completed successfully!")
                            # Add workflow_start_time to the result for image filtering
                            prompt_history["_workflow_start_time"] = workflow_start_time
                            return prompt_history
                        elif status.get("status_str") == "error":
                            print(f"❌ Workflow Error: {status}")
                            return None
                
            except requests.exceptions.RequestException as e:
                print(f"⚠️ History API Error: {e}")
            
            # Check timeout after the attempt to allow full duration
            if elapsed >= max_wait:
                print(f"⏰ Workflow Timeout after {int(elapsed)}s (max: {max_wait}s)")
                return None
            
            # Sleep only if we haven't timed out
            remaining = max_wait - elapsed
            sleep_time = min(poll_interval, remaining)
            print(f"⏳ Workflow running... ({int(elapsed)}s / {max_wait}s)")
            time.sleep(sleep_time)
        
    except requests.exceptions.RequestException as e:
        print(f"❌ ComfyUI API Error: {e}")
        return None
    except Exception as e:
        print(f"❌ Workflow Error: {e}")
        return None

def _copy_to_volume_output(file_path: Path) -> dict:
    """
    Copy file to the volume output directory.
    
    Returns:
        dict: {"success": bool, "path": str, "error": str}
    """
    print(f"📁 Copying file to Volume Output: {file_path}")
    
    try:
        # Volume Output Directory (persistent volume, if available)
        volume_output_dir = _get_volume_base() / "comfyui" / "output"
        volume_output_dir.mkdir(parents=True, exist_ok=True)
        
        # Unique filename with timestamp and UUID for better collision resistance
        now = datetime.datetime.now(datetime.timezone.utc)
        timestamp_str = now.strftime("%Y%m%d_%H%M%S_%f")
        unique_id = str(uuid.uuid4())[:8]
        dest_filename = f"comfyui-{timestamp_str}-{unique_id}-{file_path.name}"
        dest_path = volume_output_dir / dest_filename
        
        # Copy file
        shutil.copy2(file_path, dest_path)
        
        print(f"✅ File successfully copied to: {dest_path}")
        print(f"📊 File size: {dest_path.stat().st_size / (1024*1024):.2f} MB")
        
        # Return success with path
        return {
            "success": True,
            "path": str(dest_path),
            "error": None
        }
        
    except Exception as e:
        error_msg = f"Error copying {file_path.name}: {e}"
        print(f"❌ Volume Copy Error: {error_msg}")
        print(f"📋 Traceback: {traceback.format_exc()}")
        return {
            "success": False,
            "path": None,
            "error": error_msg
        }

def _start_comfyui_if_needed():
    """Start ComfyUI if it's not already running."""
    global _comfyui_process
    
    # Check if ComfyUI is already running
    if _is_comfyui_running():
        print("✅ ComfyUI is already running, skipping startup")
        # Check if we have a process reference and it's still alive
        if _comfyui_process and _comfyui_process.poll() is None:
            print(f"📋 Using existing ComfyUI process (PID: {_comfyui_process.pid})")
        return True
    
    # If we have a stale process reference, clear it
    if _comfyui_process and _comfyui_process.poll() is not None:
        print("🔄 Clearing stale ComfyUI process reference")
        _comfyui_process = None
    
    print("🚀 Starting ComfyUI in background with optimal settings...")
    comfy_cmd = [
        "python", str(COMFYUI_PATH / "main.py"),
        "--listen", COMFYUI_HOST,
        "--port", str(COMFYUI_PORT),
        "--normalvram",
        "--preview-method", "auto",
        "--verbose",
        "--cache-lru", "3"  # Small LRU cache for better model detection after symlinks
    ]
    print(f"🎯 ComfyUI Start Command: {' '.join(comfy_cmd)}")
    
    # Create log files for debugging
    COMFYUI_LOGS_PATH.mkdir(exist_ok=True)
    stdout_log = COMFYUI_LOGS_PATH / "comfyui_stdout.log"
    stderr_log = COMFYUI_LOGS_PATH / "comfyui_stderr.log"
    
    # Open log files and start process
    try:
        stdout_file = open(stdout_log, "a")
        stderr_file = open(stderr_log, "a")
        
        _comfyui_process = subprocess.Popen(
            comfy_cmd,
            stdout=stdout_file,
            stderr=stderr_file,
            cwd=str(COMFYUI_PATH)
        )
        
        print(f"📋 ComfyUI process started (PID: {_comfyui_process.pid})")
        print(f"📝 Logs: stdout={stdout_log}, stderr={stderr_log}")
        
        # Wait until ComfyUI is ready
        if not _wait_for_comfyui():
            print("❌ ComfyUI failed to start, check logs for details")
            
            # Print last 50 lines of stderr for debugging
            try:
                with open(stderr_log, "r") as f:
                    lines = f.readlines()
                    last_lines = lines[-50:] if len(lines) > 50 else lines
                    print("=" * 60)
                    print("📋 Last 50 lines of ComfyUI stderr:")
                    print("=" * 60)
                    for line in last_lines:
                        print(line.rstrip())
                    print("=" * 60)
            except Exception as e:
                print(f"⚠️ Could not read stderr log: {e}")
            
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to start ComfyUI: {e}")
        print(f"📋 Traceback: {traceback.format_exc()}")
        return False


def handler(event):
    """
    Runpod handler for ComfyUI workflows.
    """
    print("🚀 Handler started - processing ComfyUI workflow...")
    print(f"📋 Event Type: {event.get('type', 'unknown')}")
    
    # Heartbeat for Runpod Serverless (prevents idle timeout during download)
    if event.get("type") == "heartbeat":
        print("💓 Heartbeat received - worker stays active")
        return {"status": "ok"}
    
    try:
        # Volume Models Setup - only on first run or if symlinks are missing
        comfy_models_dir = COMFYUI_MODELS_PATH
        just_setup_models = False  # Track if we just set up the models
        
        if not comfy_models_dir.is_symlink() or not comfy_models_dir.exists():
            print("📦 Setting up Volume Models...")
            volume_setup_success = _setup_volume_models()
            if not volume_setup_success:
                print("⚠️ Volume Models Setup failed - ComfyUI will start without Volume Models")
            else:
                print("✅ Volume Models Setup successful - ComfyUI will find models at startup!")
                # Short pause to ensure symlinks are ready
                time.sleep(2)
                print("🔗 Symlinks stabilized - ComfyUI can now start")
                just_setup_models = True  # We just set up the models
        else:
            print("✅ Volume Models symlink already exists, skipping setup")
            volume_setup_success = True
        
        # Start ComfyUI if not already running
        if not _start_comfyui_if_needed():
            return {"error": "ComfyUI could not be started"}
        
        # Model refresh only needed after initial setup
        if just_setup_models and _parse_bool_env("COMFYUI_REFRESH_MODELS", "true"):
            # Refresh models after we just set up the volume symlink
            print("⏳ Waiting for ComfyUI model scanning to initialize...")
            time.sleep(5)
            _force_model_refresh()
        
        # Extract workflow from input
        workflow = event.get("input", {}).get("workflow")
        if not workflow:
            return {"error": "No 'workflow' found in input"}
        
        # Randomize seeds before execution (if enabled)
        workflow = _randomize_seeds(workflow)
        
        # Execute workflow
        result = _run_workflow(workflow)
        if not result:
            return {"error": "Workflow could not be executed"}
        
        # Find generated images
        image_paths = []
        outputs = result.get("outputs", {})
        workflow_start_time = result.get("_workflow_start_time", time.time() - DEFAULT_WORKFLOW_DURATION_SECONDS)
        
        # Search all output nodes for images
        expected_files = []  # Track what ComfyUI said it would output
        for node_id, node_output in outputs.items():
            if "images" in node_output:
                for img_info in node_output["images"]:
                    filename = img_info.get("filename")
                    subfolder = img_info.get("subfolder", "")
                    if filename:
                        # Build path with subfolder if present
                        if subfolder:
                            full_path = COMFYUI_OUTPUT_PATH / subfolder / filename
                        else:
                            full_path = COMFYUI_OUTPUT_PATH / filename
                        
                        expected_files.append(full_path)
                        if full_path.exists():
                            image_paths.append(full_path)
                            print(f"🖼️ Found: {full_path.name}")
        
        # Log expected files that weren't found (debug info only, not an error)
        if expected_files and not image_paths:
            print(f"📋 ComfyUI reported {len(expected_files)} output file(s), but none found yet")
        elif expected_files and len(image_paths) < len(expected_files):
            missing_count = len(expected_files) - len(image_paths)
            print(f"📋 Found {len(image_paths)}/{len(expected_files)} expected files ({missing_count} temp/preview files not saved)")
        
        # Fallback: Search output directory recursively for new images created after workflow start
        if not image_paths:
            print("🔍 Fallback: Recursively searching output directory for images created after workflow start...")
            output_dir = COMFYUI_OUTPUT_PATH
            if output_dir.exists():
                # Use workflow_start_time for more accurate filtering
                cutoff_time = workflow_start_time
                # Use rglob for recursive search to find images in subfolders
                # Support multiple image formats
                for ext in SUPPORTED_IMAGE_EXTENSIONS:
                    for img_path in output_dir.rglob(ext):
                        # Only images modified strictly after workflow started (> not >=)
                        # to avoid including files from exactly the start time (previous workflows)
                        if img_path.stat().st_mtime > cutoff_time:
                            image_paths.append(img_path)
                            # Show relative path for clarity
                            rel_path = img_path.relative_to(output_dir)
                            print(f"🖼️ New image found: {rel_path} (mtime: {img_path.stat().st_mtime}, cutoff: {cutoff_time})")
                
                if not image_paths:
                    print(f"⚠️ No images found created after {cutoff_time} (workflow start time)")
                    # List recent files for debugging (recursively, all formats)
                    recent_files = []
                    for ext in SUPPORTED_IMAGE_EXTENSIONS:
                        recent_files.extend(output_dir.rglob(ext))
                    recent_files = sorted(
                        recent_files,
                        key=lambda p: p.stat().st_mtime,
                        reverse=True
                    )[:5]
                    if recent_files:
                        print(f"📋 Most recent images in output directory:")
                        for f in recent_files:
                            rel_path = f.relative_to(output_dir)
                            print(f"   - {rel_path} (mtime: {f.stat().st_mtime})")
        
        if not image_paths:
            return {"error": "No generated images found"}
        
        # Generate job_id for organizing uploads
        job_id = event.get("id", str(uuid.uuid4()))
        
        # Check if S3 is configured
        use_s3 = _is_s3_configured()
        
        if use_s3:
            print(f"☁️ S3 configured - uploading images to S3...")
        else:
            print(f"📦 S3 not configured - using Network Volume only")
        
        # Process images
        output_urls = []
        volume_paths = []
        failed_uploads = []
        s3_success_count = 0
        
        for img_path in image_paths:
            # Always save to volume as backup
            volume_result = _copy_to_volume_output(img_path)
            if volume_result["success"]:
                volume_paths.append(volume_result["path"])
            
            # Upload to S3 if configured
            if use_s3:
                s3_result = _upload_to_s3(img_path, job_id)
                if s3_result["success"]:
                    output_urls.append(s3_result["url"])
                    s3_success_count += 1
                else:
                    # S3 upload failed, fallback to volume path if available
                    failed_uploads.append({
                        "source": str(img_path),
                        "error": s3_result["error"]
                    })
                    if volume_result["success"]:
                        output_urls.append(volume_result["path"])
                        print(f"⚠️ S3 upload failed for {img_path.name}, using volume path as fallback")
            else:
                # No S3, use volume paths as URLs
                if volume_result["success"]:
                    output_urls.append(volume_result["path"])
        
        # Check if we have any output
        if not output_urls:
            if use_s3:
                error_details = "; ".join([f["error"] for f in failed_uploads])
                return {"error": f"Failed to upload all images to S3 and no volume paths available: {error_details}"}
            else:
                return {"error": "Failed to save all images to volume"}
        
        # Determine actual storage type based on what succeeded
        # If S3 was configured but all uploads failed, storage_type should be "volume"
        actual_storage_type = "s3" if (use_s3 and s3_success_count > 0) else "volume"
        
        # Build response
        response = {
            "links": output_urls,
            "total_images": len(output_urls),
            "job_id": job_id,
            "storage_type": actual_storage_type,
        }
        
        # Add S3-specific info only if S3 was actually used successfully
        if use_s3 and s3_success_count > 0:
            config = _get_s3_config()
            response["s3_bucket"] = config["bucket"]
            response["local_paths"] = [str(p) for p in image_paths]
        
        # Add volume paths
        if volume_paths:
            response["volume_paths"] = volume_paths
        
        # Include warnings about failed uploads if any
        if failed_uploads:
            response["warnings"] = {
                "failed_uploads": len(failed_uploads),
                "details": failed_uploads
            }
            print(f"⚠️ {len(failed_uploads)} image(s) failed to upload")
        
        print(f"✅ Handler successful! {len(output_urls)} images processed")
        if actual_storage_type == "s3":
            config = _get_s3_config()
            print(f"☁️ Images uploaded to S3: {config['bucket']}")
        
        if volume_paths:
            print(f"📦 Images saved to volume: {volume_paths}")
        
        return response
        
    except Exception as e:
        print(f"❌ Handler Error: {e}")
        print(f"📋 Traceback: {traceback.format_exc()}")
        return {"error": f"Handler Error: {str(e)}"}

if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
