# Codex Setup Guide

## 🚀 Quick Start

This setup script configures a complete development environment for the RunPod ComfyUI Serverless project.

### Installation

```bash
# Run setup
./setup-codex.sh

# Then: Activate Virtual Environment
source .venv/bin/activate
```

**Or with Quick-Start:**

```bash
# All in one
./setup-codex.sh && ./start-dev.sh
```

## 📦 What Gets Installed?

The setup script automatically creates:

### 1. **Python Virtual Environment**
- `.venv/` - Isolated Python environment
- All development dependencies installed
- Python 3.11+ compatible

### 2. **Development Tools**
- **pytest** - Test Framework
- **black** - Code Formatter
- **flake8** - Linter
- **mypy** - Type Checker
- **ipython** - Interactive Shell
- **jupyter** - Notebook Support

### 3. **Test Infrastructure**
- `tests/unit/` - Unit Tests
- `tests/integration/` - Integration Tests
- `pytest.ini` - Test Configuration
- Example tests for handler

### 4. **Code Quality Tools**
- `.flake8` - Linter Configuration
- `pyproject.toml` - black, isort, mypy Config
- Pre-configured for the project

### 5. **Docker Development**
- `build-docker.sh` - Build Docker Image
- `test-docker-local.sh` - Test Image locally
- GPU support for local tests

### 6. **Codex Configuration**
- `.codex/config.json` - Project metadata
- `.codex/development.md` - Development Guide
- Commands and best practices

### 7. **Optional: ComfyUI**
- Local ComfyUI for testing
- Version v0.3.57 (as in Docker image)
- Model directories prepared

## 🛠️ Requirements

### Minimum
- **Python 3.11+**
- **Git**
- **10GB+ free disk space**

### Optional
- **Docker** (for image build and tests)
- **NVIDIA GPU** (for local ComfyUI testing)

## 📋 Usage

### Starting Development

```bash
# Activate Virtual Environment
source .venv/bin/activate

# Or Quick-Start
./start-dev.sh
```

### Running Tests

```bash
# All tests
pytest

# Only Unit Tests
pytest -m unit

# With Coverage Report
pytest --cov=. --cov-report=html
```

### Code Quality

```bash
# Format code
black rp_handler.py

# Linting
flake8 rp_handler.py

# Type Checking
mypy rp_handler.py
```

### Docker Development

```bash
# Build image
./build-docker.sh

# Test locally (with GPU)
./test-docker-local.sh
```

## 🔧 Configuration

### Environment Variables

Copy `.env.example` to `.env` and customize:

```bash
cp .env.example .env
nano .env
```

Important variables:
- `RUNPOD_API_KEY` - Your RunPod API Key
- `RUNPOD_ENDPOINT_ID` - Your Endpoint
- `COMFY_PORT` - ComfyUI Port (default: 8188)

### ComfyUI Models

If you want to use ComfyUI locally:

```bash
# Example: Stable Diffusion 1.5
wget -P ComfyUI/models/checkpoints/ \
  "https://huggingface.co/runwayml/stable-diffusion-v1-5/resolve/main/v1-5-pruned-emaonly.safetensors"
```

## 📚 Documentation

After setup you'll find:

- **Development Guide**: `.codex/development.md`
- **Test Examples**: `tests/unit/test_handler.py`
- **Docker Scripts**: `build-docker.sh`, `test-docker-local.sh`

## 🐛 Troubleshooting

### Python Version Too Old

```bash
# Install Python 3.11+
sudo apt-get update
sudo apt-get install python3.11 python3.11-venv
```

### Disk Space Issues

```bash
# Check disk space
df -h

# Cleanup Docker (if available)
docker system prune -a
```

### ComfyUI Installation Failed

This is optional - you can develop the project without local ComfyUI:

```bash
# Run setup again and skip ComfyUI installation
./setup-codex.sh
```

### Tests Failing

This is normal on first setup - some tests are mocks and need adjusted configuration:

```bash
# Run single test
pytest tests/unit/test_handler.py::TestVolumeFunctions::test_sanitize_job_id_valid -v
```

## 🚢 Deployment Workflow

1. **Develop locally**
   ```bash
   source .venv/bin/activate
   # Change code in rp_handler.py
   pytest  # Run tests
   ```

2. **Build Docker image**
   ```bash
   ./build-docker.sh
   ```

3. **Push image**
   ```bash
   docker push ecomtree/comfyui-serverless:latest
   ```

4. **Update RunPod Endpoint**
   - Go to RunPod Dashboard
   - Update Endpoint with new image

5. **Test**
   ```bash
   ./test_endpoint.sh
   ```

## 💡 Best Practices

### 1. Always activate Virtual Environment

```bash
# At the beginning of each session
source .venv/bin/activate
```

### 2. Format code before commit

```bash
black rp_handler.py
flake8 rp_handler.py
```

### 3. Write tests

Create a test in `tests/unit/` for every new function.

### 4. Don't commit Environment Variables

`.env` is in `.gitignore` - Secrets do NOT belong in the repository!

### 5. Test Docker image before push

```bash
./test-docker-local.sh
```

## 🤝 Contribution Workflow

1. Create feature branch
2. Develop code + write tests
3. Run `pytest` + `black` + `flake8`
4. Build and test Docker image
5. Create Pull Request

## 📞 Support

If you have questions or problems:

1. Check the logs: `logs/`
2. Read the documentation: `.codex/development.md`
3. Test with `pytest -v`

## 🎉 Let's Go!

```bash
# Run setup
./setup-codex.sh

# Start development
./start-dev.sh

# Happy Coding! 🚀
```

---

**Created for RunPod ComfyUI Serverless Handler**  
*Development environment for AI image generation on Serverless GPU Infrastructure*
