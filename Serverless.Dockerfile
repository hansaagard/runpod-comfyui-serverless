FROM runpod/pytorch:2.8.0-py3.11-cuda12.8.1-cudnn-devel-ubuntu22.04

# ------------------------------------------------------------
# Metadata
# ------------------------------------------------------------
LABEL maintainer="Sebastian" \
      description="ComfyUI – Runpod Serverless Worker"

# ------------------------------------------------------------
# System Packages
# ------------------------------------------------------------
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && \
    apt-get install -y git wget curl unzip && \
    apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# ------------------------------------------------------------
# Python Dependencies
# ------------------------------------------------------------
RUN pip uninstall -y torch torchvision torchaudio xformers || true && \
    pip install --no-cache-dir torch==2.8.0 torchvision==0.23.0 torchaudio==2.8.0 \
        --index-url https://download.pytorch.org/whl/cu128 && \
    pip install --no-cache-dir ninja flash-attn --no-build-isolation && \
    pip install --no-cache-dir tensorrt nvidia-tensorrt accelerate transformers diffusers scipy opencv-python Pillow numpy && \
    pip install --no-cache-dir runpod requests pathlib

# ------------------------------------------------------------
# ComfyUI Checkout (headless)
# ------------------------------------------------------------
WORKDIR /workspace
RUN git clone https://github.com/comfyanonymous/ComfyUI.git && \
    cd ComfyUI && git checkout v0.3.57 && \
    pip install --no-cache-dir $(grep -v -E "^torch([^a-z]|$)|torchvision|torchaudio" requirements.txt | grep -v "^#" | grep -v "^$" | tr '\n' ' ') && \
    pip install --no-cache-dir librosa soundfile av moviepy

# Download default SD 1.5 model für default-api.json workflow
RUN cd /workspace/ComfyUI/models/checkpoints && \
    wget -O v1-5-pruned-emaonly-fp16.safetensors \
    "https://huggingface.co/runwayml/stable-diffusion-v1-5/resolve/main/v1-5-pruned-emaonly.safetensors"

# ------------------------------------------------------------
# Copy Worker Handler
# ------------------------------------------------------------
COPY rp_handler.py /workspace/rp_handler.py

# ------------------------------------------------------------
# Runtime Env Vars
# ------------------------------------------------------------
ENV PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:1024,expandable_segments:True \
    TORCH_ALLOW_TF32_CUBLAS_OVERRIDE=1

# ------------------------------------------------------------
# Start the Runpod Serverless Worker
# ------------------------------------------------------------
CMD ["python3", "-u", "/workspace/rp_handler.py"]
