"""
UAMP - Advanced Media Engine
Supports 256-color, Braille, and Virtual Resolution.
"""

import subprocess
import threading
import json
import time
import numpy as np
import os
import signal
from pathlib import Path

# All character sets MUST be tuples to be hashable for caching
ASCII_SETS = {
    'simple':   (' ', '.', '+', '*', '@'),
    'standard': (' ', '.', ':', '-', '=', '+', '*', '#', '%', '@'),
    'detailed': tuple(' `.-\'_,^=;><+!rc*/z?sLTv)J7(|Fi{C}fI31tlu[neoZ5Yxjya]2ESwqkP6h9d4VpOGbUAKXHm8RD#$Bg0MNWQ%&@'),
    'blocks':   (' ', '░', '▒', '▓', '█'),
}

CHARSET_NAMES = list(ASCII_SETS.keys())

LUM_R, LUM_G, LUM_B = 0.299, 0.587, 0.114

def get_color_index(r, g, b):
    """Convert RGB to xterm 256-color code index (0-255)."""
    return 16 + (36 * int(r / 256 * 6)) + (6 * int(g / 256 * 6)) + int(b / 256 * 6)

class Frame:
    __slots__ = ('lum', 'rgb', '_cache')

    def __init__(self, lum: np.ndarray, rgb: np.ndarray):
        self.lum = lum 
        self.rgb = rgb 
        self._cache = {}

    def render(self, mode, charset, color_mode, zoom, density, term_w, term_h):
        key = (mode, charset, color_mode, zoom, density, term_w, term_h)
        if key in self._cache: return self._cache[key]

        lum_data = self.lum
        rgb_data = self.rgb
        sh, sw = lum_data.shape
        
        # 1. Apply Zoom
        if zoom > 1.0:
            nh, nw = int(sh / zoom), int(sw / zoom)
            sy, sx = (sh - nh) // 2, (sw - nw) // 2
            lum_data = lum_data[sy:sy+nh, sx:sx+nw]
            rgb_data = rgb_data[sy:sy+nh, sx:sx+nw]

        # 2. Render
        if mode == 'braille':
            # Braille ignore density for now as it's already high-res
            target_h, target_w = term_h * 4, term_w * 2
            row_idx = (np.arange(target_h) * lum_data.shape[0] / target_h).astype(np.int32)
            col_idx = (np.arange(target_w) * lum_data.shape[1] / target_w).astype(np.int32)
            lum_data = lum_data[np.ix_(row_idx, col_idx)]
            rgb_data = rgb_data[np.ix_(row_idx, col_idx)]
            lines = self._render_braille(lum_data, rgb_data, color_mode)
        else:
            # ASCII respects density (1x, 2x, 3x)
            target_h, target_w = term_h, term_w * density
            row_idx = (np.arange(target_h) * lum_data.shape[0] / target_h).astype(np.int32)
            col_idx = (np.arange(target_w) * lum_data.shape[1] / target_w).astype(np.int32)
            lum_data = lum_data[np.ix_(row_idx, col_idx)]
            rgb_data = rgb_data[np.ix_(row_idx, col_idx)]
            lines = self._render_ascii(lum_data, rgb_data, charset, color_mode, density)
        
        self._cache[key] = lines
        return lines

    def _render_braille(self, lum, rgb, color_mode):
        h, w = lum.shape
        bh, bw = (h // 4) * 4, (w // 2) * 2
        data = (lum[:bh, :bw] > 0.5)
        lines = []
        for y in range(0, bh, 4):
            line_segments = []
            for x in range(0, bw, 2):
                v = (data[y,x]*1 + data[y+1,x]*2 + data[y+2,x]*4 + 
                     data[y,x+1]*8 + data[y+1,x+1]*16 + data[y+2,x+1]*32 + 
                     data[y+3,x]*64 + data[y+3,x+1]*128)
                char = chr(0x2800 + v)
                color_idx = get_color_index(rgb[y,x,0], rgb[y,x,1], rgb[y,x,2]) if color_mode else None
                line_segments.append((char, color_idx))
            lines.append(line_segments)
        return lines

    def _render_ascii(self, lum, rgb, charset, color_mode, density):
        h, w = lum.shape
        chars = np.array(list(charset))
        indices = (lum * (len(chars)-1)).astype(np.int32)
        lines = []
        for y in range(h):
            line_segments = []
            for x in range(w):
                char = chars[indices[y, x]]
                color_idx = get_color_index(rgb[y,x,0], rgb[y,x,1], rgb[y,x,2]) if color_mode else None
                line_segments.append((char, color_idx))
            lines.append(line_segments)
        return lines

class MediaEngine:
    def __init__(self, filepath: Path, term_w, term_h, settings):
        self.filepath = filepath
        self.term_w = term_w
        self.term_h = term_h
        self.settings = settings
        
        self.frames = []
        self.loaded = False
        self._stop = threading.Event()
        self._audio = None

    def start_loading(self):
        t = threading.Thread(target=self._decode, daemon=True)
        t.start()
        self._start_audio()

    def _start_audio(self):
        try:
            self._audio = subprocess.Popen(
                ['ffplay', '-nodisp', '-autoexit', '-loglevel', 'quiet', str(self.filepath)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid
            )
        except: pass

    def stop(self):
        self._stop.set()
        if self._audio:
            try:
                os.killpg(os.getpgid(self._audio.pid), signal.SIGTERM)
            except:
                try: self._audio.terminate()
                except: pass

    def _decode(self):
        from uamp.fsal import IMAGE_EXTS
        # High-res master sampling to support density/zoom
        sw, sh = self.term_w * 6, self.term_h * 4 # Max density (3) * width + Braille height
        
        ext = self.filepath.suffix.lower()
        is_animated_format = ext in {'.gif', '.webp'}
        is_static = (ext in IMAGE_EXTS) and not is_animated_format
        decode_fps = self.settings.fps if not is_static else 1
        
        cmd = [
            'ffmpeg', '-i', str(self.filepath),
            '-vf', f'scale={sw}:{sh},fps={decode_fps}:round=up',
            '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1'
        ]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            chunk_size = sw * sh * 3
            while not self._stop.is_set():
                raw = proc.stdout.read(chunk_size)
                if not raw or len(raw) < chunk_size: break
                rgb = np.frombuffer(raw, dtype=np.uint8).reshape((sh, sw, 3))
                lum = (rgb[:,:,0]*LUM_R + rgb[:,:,1]*LUM_G + rgb[:,:,2]*LUM_B) / 255.0
                lo, hi = np.percentile(lum, 2), np.percentile(lum, 98)
                if hi > lo: lum = np.clip((lum - lo) / (hi - lo), 0, 1)
                else: lum = np.clip(lum, 0, 1)
                self.frames.append(Frame(lum, rgb.copy()))
                if is_static: break
            proc.terminate()
        except: pass
        self.loaded = True

    def get_frame(self, idx, w, h):
        if not self.frames: return None
        f = self.frames[idx % len(self.frames)]
        s = self.settings
        return f.render(
            'braille' if s.braille_mode else 'ascii',
            ASCII_SETS[s.charset_key], 
            s.color_mode, 
            s.zoom, 
            s.density,
            w, h
        )
