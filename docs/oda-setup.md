# ODA File Converter Setup

## What is ODA File Converter?

The **Open Design Alliance (ODA) File Converter** is a free command-line tool that converts DWF/DWFX files to DWG without watermarks. It's industry-standard and widely used.

## Download & Installation

### 1. Download ODA File Converter

Visit: https://www.opendesign.com/guestfiles/oda_file_converter

Choose your platform:
- **macOS**: Download the macOS version
- **Linux**: Download the Linux version
- **Windows**: Download the Windows version

### 2. Install

#### macOS
```bash
# Extract the downloaded file
unzip ODAFileConverter_*.zip

# Move to /usr/local/bin (or another directory in your PATH)
sudo mv ODAFileConverter /usr/local/bin/

# Make executable
sudo chmod +x /usr/local/bin/ODAFileConverter
```

#### Linux
```bash
# Extract
tar -xzf ODAFileConverter_*.tar.gz

# Move to /usr/local/bin
sudo mv ODAFileConverter /usr/local/bin/

# Make executable
sudo chmod +x /usr/local/bin/ODAFileConverter
```

#### Windows
1. Extract the ZIP file
2. Place `ODAFileConverter.exe` in a directory (e.g., `C:\Program Files\ODA\`)
3. Add that directory to your PATH environment variable

### 3. Configure in .env

Add the path to your `.env` file:

```bash
# ODA File Converter path (for DWF → PNG conversion)
ODA_FILE_CONVERTER_PATH=/usr/local/bin/ODAFileConverter
```

Or for Windows:
```bash
ODA_FILE_CONVERTER_PATH=C:\Program Files\ODA\ODAFileConverter.exe
```

### 4. Install Python Dependencies

```bash
pip install ezdxf==1.3.0 matplotlib==3.8.2
```

These are required to render the converted DWG files to PNG.

## Test the Installation

```bash
# Test ODA FileConverter
/usr/local/bin/ODAFileConverter --help

# Test Python
python -c "import ezdxf; import matplotlib; print('✅ Dependencies installed')"
```

## How It Works

1. **DWF → DWG**: ODA FileConverter converts DWF/DWFX to DWG
2. **DWG → PNG**: ezdxf + matplotlib renders the DWG to a PNG image
3. **Analysis**: GPT-5.1 analyzes the clean PNG (no watermarks!)

## Troubleshooting

### ODA FileConverter not found
- Make sure the path in `.env` is correct
- Check if the file is executable: `ls -la /usr/local/bin/ODAFileConverter`
- Try running it manually to see error messages

### ezdxf import errors
```bash
pip install --upgrade ezdxf matplotlib
```

### Conversion fails
- Check that the DWF file is valid
- Try converting manually with ODA FileConverter GUI first
- Check logs for detailed error messages

## Alternative: Manual Conversion

If ODA FileConverter is not available, users can still convert DWF files manually using:

1. **Autodesk Design Review** (free) - https://www.autodesk.com/products/design-review
2. **DWG TrueView** (free) - https://www.autodesk.com/products/dwg/viewers
3. **LibreCAD** (open source) - https://librecad.org

Then upload the converted PNG/PDF file directly.

## License

ODA File Converter is provided free by the Open Design Alliance. No license key required.
