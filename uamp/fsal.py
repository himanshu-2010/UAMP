"""
UAMP - File System Abstraction Layer
Handles directory navigation, file listing, and type detection.
"""

import subprocess
import json
from pathlib import Path
from datetime import datetime

# Supported file extensions
VIDEO_EXTS = {'.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv', '.m4v', '.ts'}
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif'}
AUDIO_EXTS = {'.mp3', '.wav', '.ogg', '.flac', '.m4a', '.aac', '.opus', '.wma'}
MEDIA_EXTS = VIDEO_EXTS | IMAGE_EXTS | AUDIO_EXTS

FILE_ICONS = {
    'dir':   '📂',
    'video': '🎬',
    'image': '🖼 ',
    'audio': '🎵',
    'file':  '   ',
    'up':    '↩ ',
}


def get_file_type(path: Path) -> str:
    if path.is_dir():
        return 'dir'
    ext = path.suffix.lower()
    if ext in VIDEO_EXTS:
        return 'video'
    if ext in IMAGE_EXTS:
        return 'image'
    if ext in AUDIO_EXTS:
        return 'audio'
    return 'file'


def get_metadata(path: Path) -> dict:
    """Extract metadata for a file."""
    meta = {
        'Size': 'Unknown',
        'Modified': 'Unknown',
        'Type': get_file_type(path),
    }
    
    try:
        stat = path.stat()
        size = stat.st_size
        if size < 1024:
            meta['Size'] = f"{size} B"
        elif size < 1024 * 1024:
            meta['Size'] = f"{size/1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            meta['Size'] = f"{size/(1024*1024):.1f} MB"
        else:
            meta['Size'] = f"{size/(1024*1024*1024):.1f} GB"
        
        meta['Modified'] = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M')
    except: pass

    if meta['Type'] in ('video', 'audio', 'image'):
        try:
            cmd = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_format', '-show_streams', str(path)
            ]
            res = subprocess.check_output(cmd)
            data = json.loads(res)
            
            fmt = data.get('format', {})
            if 'duration' in fmt:
                d = float(fmt['duration'])
                meta['Duration'] = f"{int(d//60):02}:{int(d%60):02}"
            
            if 'bit_rate' in fmt:
                meta['Bitrate'] = f"{int(fmt['bit_rate'])/1000:.0f} kbps"

            for stream in data.get('streams', []):
                if stream.get('codec_type') == 'video':
                    meta['Resolution'] = f"{stream.get('width')}x{stream.get('height')}"
                    meta['Codec'] = stream.get('codec_name')
                elif stream.get('codec_type') == 'audio' and 'Codec' not in meta:
                    meta['Codec'] = stream.get('codec_name')
        except: pass
        
    return meta


class FileManager:
    def __init__(self, start_path: str = None):
        if start_path:
            p = Path(start_path).expanduser().resolve()
            self.current_path = p if p.is_dir() else p.parent
        else:
            self.current_path = Path.home()

        self.entries: list[Path] = []
        self.selected_idx: int = 0
        self.scroll_offset: int = 0
        self.show_hidden: bool = False
        self.refresh()

    # ─── Navigation ──────────────────────────────────────────────────────────

    def refresh(self):
        """Re-read the current directory."""
        try:
            raw = list(self.current_path.iterdir())
        except:
            raw = []

        if not self.show_hidden:
            raw = [e for e in raw if not e.name.startswith('.')]

        dirs  = sorted([e for e in raw if e.is_dir()],  key=lambda x: x.name.lower())
        files = sorted([e for e in raw if e.is_file()], key=lambda x: x.name.lower())

        self.entries = dirs + files
        self.selected_idx = min(self.selected_idx, max(0, len(self.entries) - 1))

    def move_up(self):
        if self.selected_idx > 0:
            self.selected_idx -= 1

    def move_down(self):
        if self.selected_idx < len(self.entries) - 1:
            self.selected_idx += 1

    def go_parent(self):
        parent = self.current_path.parent
        if parent != self.current_path:
            self.current_path = parent
            self.selected_idx = 0
            self.scroll_offset = 0
            self.refresh()

    def open_selected(self) -> Path | None:
        if not self.entries:
            return None
        entry = self.entries[self.selected_idx]
        if entry.is_dir():
            self.current_path = entry
            self.selected_idx = 0
            self.scroll_offset = 0
            self.refresh()
            return None
        return entry

    def toggle_hidden(self):
        self.show_hidden = not self.show_hidden
        self.selected_idx = 0
        self.scroll_offset = 0
        self.refresh()

    # ─── Display helpers ─────────────────────────────────────────────────────

    def update_scroll(self, visible_rows: int):
        if self.selected_idx >= self.scroll_offset + visible_rows:
            self.scroll_offset = self.selected_idx - visible_rows + 1
        elif self.selected_idx < self.scroll_offset:
            self.scroll_offset = self.selected_idx

    def get_display_entry(self, entry: Path) -> tuple[str, str]:
        ftype = get_file_type(entry)
        icon  = FILE_ICONS[ftype]
        name  = entry.name + ('/' if ftype == 'dir' else '')
        return icon, name

    @property
    def selected_entry(self) -> Path | None:
        return self.entries[self.selected_idx] if self.entries else None

    def get_playlist(self, dir_path: Path) -> list[Path]:
        try:
            raw = list(dir_path.iterdir())
            if not self.show_hidden:
                raw = [e for e in raw if not e.name.startswith('.')]
            return sorted([e for e in raw if e.is_file() and e.suffix.lower() in MEDIA_EXTS],
                          key=lambda x: x.name.lower())
        except:
            return []

    def get_next_prev(self, current: Path):
        """Find next/prev file relative to the current file's directory."""
        playlist = self.get_playlist(current.parent)
        if not playlist:
            return None, None
        
        # Ensure 'current' is compared fairly (resolved paths)
        try:
            current_res = current.resolve()
            playlist_res = [p.resolve() for p in playlist]
            if current_res not in playlist_res:
                return None, None
            idx = playlist_res.index(current_res)
        except:
            if current not in playlist: return None, None
            idx = playlist.index(current)

        nxt = playlist[(idx + 1) % len(playlist)]
        prv = playlist[(idx - 1) % len(playlist)]
        return nxt, prv
