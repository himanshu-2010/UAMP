#!/usr/bin/env python3
"""
UAMP - Universal ASCII Media Player
Entry point with dependency verification.

Usage:
    python main.py                  # Open file browser in home directory
    python main.py /path/to/dir     # Open browser at specific directory
    python main.py /path/to/video   # Open file directly
"""

import sys
import subprocess
import shutil


# ─── Dependency checker ───────────────────────────────────────────────────────

def check_dependencies() -> list[str]:
    issues = []

    # ffmpeg / ffprobe
    for tool in ('ffmpeg', 'ffprobe'):
        if shutil.which(tool) is None:
            issues.append(f"  ✗  '{tool}' not found in PATH")

    # Python packages
    try:
        import numpy
    except ImportError:
        issues.append("  ✗  Python package 'numpy' is not installed  →  pip install numpy")

    try:
        import curses
    except ImportError:
        issues.append("  ✗  Python 'curses' module unavailable (Windows?)")

    return issues


def print_banner():
    print("""
╔══════════════════════════════════════════════╗
║   UAMP  –  Universal ASCII Media Player      ║
║   v0.1.0 MVP                                 ║
╚══════════════════════════════════════════════╝
""")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    issues = check_dependencies()
    if issues:
        print_banner()
        print("ERROR: Missing dependencies:\n")
        for issue in issues:
            print(issue)
        print()
        print("Install guide:")
        print("  Ubuntu/Debian:  sudo apt install ffmpeg && pip install numpy")
        print("  Arch Linux:     sudo pacman -S ffmpeg python-numpy")
        print("  Fedora:         sudo dnf install ffmpeg && pip install numpy")
        sys.exit(1)

    import argparse
    parser = argparse.ArgumentParser(
        prog='uamp',
        description='Universal ASCII Media Player — play video/images as ASCII art in your terminal.',
    )
    parser.add_argument(
        'path', nargs='?', default=None,
        help='File or directory to open (default: home directory)'
    )
    parser.add_argument('--version', action='version', version='UAMP 0.1.0-mvp')
    args = parser.parse_args()

    from .tui import UAMP
    app = UAMP(start_path=args.path)
    try:
        app.run()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
