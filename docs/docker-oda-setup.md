# Docker ODA FileConverter Setup

## Why Docker?

The macOS version of ODA FileConverter is GUI-only and cannot run headless. The Linux version supports proper command-line usage, so we use Docker to run it.

## Setup Steps

### 1. Download ODA FileConverter for Linux

1. Go to: https://www.opendesign.com/guestfiles/oda_file_converter
2. **Sign in** or create a free account
3. Download: **ODAFileConverter_QT6_lnxX64_8.3dll_25.12.tar.gz** (Linux x64)

### 2. Extract to Project

```bash
cd /Users/robenhai/aga

# Create directory for ODA files
mkdir -p oda_linux

# Extract the downloaded tar.gz
tar -xzf ~/Downloads/ODAFileConverter_QT6_lnxX64_8.3dll_25.12.tar.gz

# Move contents to oda_linux folder
mv ODAFileConverter_QT6_lnxX64_8.3dll_25.12/* oda_linux/
rmdir ODAFileConverter_QT6_lnxX64_8.3dll_25.12
```

### 3. Build Docker Image

```bash
cd /Users/robenhai/aga
docker build -t oda-converter -f Dockerfile.oda .
```

### 4. Test It

```bash
# Create test directories
mkdir -p /tmp/test_oda/input /tmp/test_oda/output

# Copy a DWF file to input folder
cp "path/to/your/file.dwf" /tmp/test_oda/input/

# Run conversion
docker run --rm \
  -v /tmp/test_oda:/data \
  oda-converter \
  /data/input \
  /data/output \
  ACAD2018 \
  DWG \
  0 \
  1 \
  "*.DWF"

# Check output
ls /tmp/test_oda/output/
```

## How It Works

1. **DWF Upload**: User uploads DWF file via web UI
2. **Docker Conversion**: Backend runs ODA FileConverter in Linux container
   - DwfImporter reads DWF format
   - Converts to DWG (AutoCAD 2018 format)
3. **PNG Rendering**: Backend uses ezdxf + matplotlib
   - TD_Rasterizer equivalent via Python
   - Renders DWG geometry to high-res PNG
4. **GPT Analysis**: PNG sent to GPT-5.1 for segmentation

## Troubleshooting

### "No such file or directory: oda_linux"

You need to download and extract ODA FileConverter first (steps 1-2 above).

### "Docker is not running"

Start Docker Desktop:
```bash
open -a Docker
```

### "Permission denied"

Make sure the ODA executable has execute permissions:
```bash
chmod +x oda_linux/ODAFileConverter
```

## Alternative: Manual Conversion

If Docker setup is too complex, users can convert manually:

1. Open ODA FileConverter GUI (macOS)
2. Convert DWF → DWG
3. Open DWG in FreeCAD
4. Export as PNG
5. Upload PNG directly (skip DWF upload)
