#!/bin/bash
# UAMP System-Wide Installer for Linux

echo "╔══════════════════════════════════════════════╗"
echo "║   UAMP - Universal ASCII Media Player        ║"
echo "║          Installer v0.1.0                    ║"
echo "╚══════════════════════════════════════════════╝"

# 1. Dependency Check
if ! command -v ffmpeg &> /dev/null; then
    echo "ERROR: ffmpeg not found. Please install it."
    exit 1
fi

# 2. Determine Install Mode
if [ "$EUID" -eq 0 ]; then
    echo "Running as root. Performing system-wide installation..."
    PIPCMD="pip install . --break-system-packages"
    BIN_DIR="/usr/local/bin"
    APPS_DIR="/usr/share/applications"
else
    echo "Running as user. Performing local installation..."
    PIPCMD="pip install --user . --break-system-packages"
    BIN_DIR="$HOME/.local/bin"
    APPS_DIR="$HOME/.local/share/applications"
    mkdir -p "$BIN_DIR"
fi

# 3. Install Python Package
echo "Installing UAMP Python package..."
$PIPCMD 2>/dev/null || pip install . 

# 4. Desktop Integration
echo "Setting up desktop integration..."
mkdir -p "$APPS_DIR"
cp uamp.desktop "$APPS_DIR/"

# 5. Path Verification & Final Message
echo "------------------------------------------------"
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo "WARNING: $BIN_DIR is not in your PATH."
    echo "Add this to your .bashrc or .zshrc:"
    echo "  export PATH=\$PATH:$BIN_DIR"
    echo "------------------------------------------------"
fi

echo "SUCCESS: UAMP has been installed!"
echo "Global Command: uamp"
echo "Example: uamp video.mp4"
