"""
UAMP - Advanced TUI
Full media player with color, high-res, and playlist support.
"""

import curses
import time
from pathlib import Path
from uamp.fsal import FileManager, get_file_type, get_metadata
from uamp.media_engine import MediaEngine, ASCII_SETS
from uamp.settings import AppSettings

HELP_PLAYER = [
    "┌──────── Player Controls ──────────┐",
    "│ Space: Pause/Resume   H: Help     │",
    "│ N/P: Next/Prev File   Q: Back     │",
    "│ C: Color Toggle       B: Braille  │",
    "│ V: HQ (Plain) Mode    D: Cycle Den│",
    "│ 1-4: Charset          Z/X: Zoom   │",
    "│ +-: Speed             Left/Right:Seek",
    "└───────────────────────────────────┘",
]

HELP_BROWSER = [
    "┌────────── Browser ────────────┐",
    "│ ↑↓: Nav       Enter: Play     │",
    "│ Esc/⌫: Parent .: Hidden       │",
    "│ H: Help       Q: Quit         │",
    "└───────────────────────────────┘",
]

COLOR_OFFSET = 16

def _safe_addstr(stdscr, y, x, text, attr=0):
    try:
        h, w = stdscr.getmaxyx()
        if y < 0 or y >= h or x < 0 or x >= w: return
        display_text = text[:w - x]
        if y == h - 1 and x + len(display_text) >= w:
            display_text = display_text[:w - x - 1]
        stdscr.addstr(y, x, display_text, attr)
    except: pass

class BrowserView:
    def __init__(self, fm: FileManager, settings: AppSettings):
        self.fm = fm
        self.settings = settings
        self.show_help = False
        self.preview_cache = {}
        self.meta_cache = {}
        
        # Performance & Animation
        self._last_idx = -1
        self._preview_requested = False
        self._scroll_pos = 0.0 # For smooth scrolling
        self._target_scroll = 0.0

    def _get_preview(self, filepath: Path, w, h):
        cache_key = (filepath, w, h)
        if cache_key in self.preview_cache:
            return self.preview_cache[cache_key]
        
        if get_file_type(filepath) in ('video', 'image'):
            try:
                engine = MediaEngine(filepath, w, h, self.settings)
                engine._decode_sync(limit=1)
                if engine.frames:
                    frame = engine.frames[0].render('ascii', ASCII_SETS['detailed'], True, 1.0, 1, w, h)
                    self.preview_cache[cache_key] = frame
                    return frame
            except: pass
        return None

    def _get_meta(self, filepath: Path):
        if filepath in self.meta_cache:
            return self.meta_cache[filepath]
        meta = get_metadata(filepath)
        self.meta_cache[filepath] = meta
        return meta

    def draw(self, stdscr):
        h, w = stdscr.getmaxyx()
        stdscr.erase()
        _safe_addstr(stdscr, 0, 0, " UAMP [MANUAL-P] Universal ASCII Media Player ".ljust(w), curses.A_REVERSE | curses.A_BOLD)
        _safe_addstr(stdscr, 1, 0, f" {self.fm.current_path}".ljust(w), curses.A_DIM)
        
        list_w = int(w * 0.50)
        preview_w = w - list_w - 4
        
        visible = h - 4
        self.fm.update_scroll(visible)
        entries = self.fm.entries

        # Smooth Scroll Update
        self._target_scroll = self.fm.scroll_offset
        self._scroll_pos += (self._target_scroll - self._scroll_pos) * 0.4
        if abs(self._scroll_pos - self._target_scroll) < 0.05:
            self._scroll_pos = self._target_scroll

        # Draw List
        for i in range(visible):
            idx = i + int(self._scroll_pos)
            if idx >= len(entries): break
            entry = entries[idx]
            icon, name = self.fm.get_display_entry(entry)
            line = f" {icon} {name}"
            is_sel = (idx == self.fm.selected_idx)
            attr = curses.A_REVERSE if is_sel else 0
            _safe_addstr(stdscr, 2+i, 0, line.ljust(list_w), attr)

        # Vertical Separator
        for i in range(2, h-1):
            _safe_addstr(stdscr, i, list_w + 1, "│")

        # Handle Selection Change (Reset preview state)
        if self.fm.selected_idx != self._last_idx:
            self._last_idx = self.fm.selected_idx
            self._preview_requested = False

        # Draw Preview/Metadata (only if manually requested)
        selected = self.fm.selected_entry
        if selected and selected.is_file():
            if self._preview_requested:
                meta = self._get_meta(selected)
                start_y = 2
                
                # ASCII Thumbnail
                thumb_h = min(18, h // 2 - 2)
                thumb = self._get_preview(selected, preview_w, thumb_h)
                if thumb:
                    for row_i, line_segments in enumerate(thumb):
                        x = list_w + 3
                        for char, color_idx in line_segments:
                            attr = curses.color_pair(color_idx + COLOR_OFFSET) if color_idx is not None else 0
                            _safe_addstr(stdscr, start_y + row_i, x, char, attr)
                            x += 1
                    start_y += thumb_h + 1

                # Metadata text
                name_text = f"Name: {selected.name}"
                if len(name_text) > preview_w: name_text = name_text[:preview_w-3] + "..."
                _safe_addstr(stdscr, start_y, list_w + 3, name_text, curses.A_BOLD)
                start_y += 1
                for k, v in meta.items():
                    if start_y >= h - 2: break
                    _safe_addstr(stdscr, start_y, list_w + 3, f"{k}: {v}")
                    start_y += 1
            else:
                _safe_addstr(stdscr, h//2, list_w + 5, "[ Press 'P' for Preview ]", curses.A_DIM)

        _safe_addstr(stdscr, h-1, 0, " ↑↓:Nav  Enter:Open  P:Preview  Esc/⌫:Parent  H:Help  Q:Quit ".ljust(w), curses.A_DIM)
        if self.show_help:
            for i, line in enumerate(HELP_BROWSER):
                _safe_addstr(stdscr, h//2 - 2 + i, w//2 - 15, line, curses.A_BOLD)
        stdscr.refresh()

    def handle_key(self, key):
        # Reset preview on any navigation
        if key in (curses.KEY_UP, curses.KEY_DOWN, curses.KEY_BACKSPACE, 127, 27):
            self._preview_requested = False

        if key in (ord('q'), ord('Q')): return 'quit'
        elif key == curses.KEY_UP: self.fm.move_up()
        elif key == curses.KEY_DOWN: self.fm.move_down()
        elif key in (ord('p'), ord('P')): self._preview_requested = True
        elif key in (curses.KEY_BACKSPACE, 127, 27): self.fm.go_parent()
        elif key in (ord('\n'), ord('\r')):
            res = self.fm.open_selected()
            if res: return f'play:{res}'
        elif key == ord('.'): 
            self.fm.toggle_hidden()
            self._preview_requested = False
        elif key in (ord('h'), ord('H')): self.show_help = not self.show_help
        return None

class PlayerView:
    def __init__(self, filepath: Path, fm: FileManager, settings: AppSettings):
        self.filepath = filepath
        self.fm = fm
        self.settings = settings
        self.engine = None
        self.playing = True
        self.cur_idx = 0
        self.show_help = False
        self._last_t = 0

    def start(self, w, h):
        self.w, self.h = w, h
        if self.engine: self.engine.stop()
        self.engine = MediaEngine(self.filepath, w, h - 3, self.settings)
        self.engine.start()
        self._last_t = time.monotonic()

    def stop(self):
        if self.engine: self.engine.stop()

    def _seek_relative(self, seconds):
        if not self.engine: return
        # Calculate current time and add offset
        cur_time = self.cur_idx / self.settings.fps
        new_time = max(0, cur_time + seconds)
        
        self.engine.stop()
        self.engine = MediaEngine(self.filepath, self.w, self.h - 3, self.settings)
        self.engine.start(new_time)
        self.cur_idx = 0
        self._last_t = time.monotonic()

    def tick(self):
        if not self.playing or not self.engine: return
        now = time.monotonic()
        if now - self._last_t >= 1.0 / self.settings.fps:
            cnt = len(self.engine.frames)
            if cnt > 0: self.cur_idx = (self.cur_idx + 1) % cnt
            self._last_t = now

    def draw(self, stdscr):
        h, w = stdscr.getmaxyx()
        stdscr.erase()
        
        if not self.engine or (not self.engine.frames and not self.engine.loaded):
            _safe_addstr(stdscr, h//2, w//2 - 5, "Loading...", curses.A_BOLD)
        else:
            # Note: engine uses self.settings internally
            lines = self.engine.get_frame(self.cur_idx, w, h - 3)
            if lines:
                for row_i, line_segments in enumerate(lines[:h-3]):
                    x = 0
                    current_text = ""
                    current_color = None
                    for char, color_idx in line_segments:
                        if color_idx == current_color:
                            current_text += char
                        else:
                            if current_text:
                                attr = curses.color_pair(current_color + COLOR_OFFSET) if current_color is not None else 0
                                _safe_addstr(stdscr, row_i, x, current_text, attr)
                                x += len(current_text)
                            current_text = char
                            current_color = color_idx
                    if current_text:
                        attr = curses.color_pair(current_color + COLOR_OFFSET) if current_color is not None else 0
                        _safe_addstr(stdscr, row_i, x, current_text, attr)

        # Seek Bar
        cnt = len(self.engine.frames) if self.engine and self.engine.frames else 1
        pct = self.cur_idx / max(1, cnt - 1)
        bar_w = max(10, w - 30)
        filled = int(pct * bar_w)
        bar = "█" * filled + "░" * (bar_w - filled)
        _safe_addstr(stdscr, h-3, 2, f"[{bar}] {int(pct*100)}%", curses.color_pair(6))

        # Status
        s = self.settings
        mode = "COLOR" if s.color_mode else "B&W"
        if s.braille_mode: fmt = "BRAILLE"
        elif s.hq_mode: fmt = "HQ-PLAIN"
        else: fmt = f"CHAR:{s.charset_key}"
        
        dens = f"D:{s.density}"
        status = f" {self.filepath.name} │ {mode} │ {fmt} │ {dens} │ Zoom:{s.zoom:.1f}x │ {s.fps} FPS "
        _safe_addstr(stdscr, h-2, 0, status.ljust(w), curses.A_REVERSE)
        _safe_addstr(stdscr, h-1, 0, " N:Next  P:Prev  D:Density  V:HQ  C:Color  B:Braille  H:Help ".ljust(w))

        if self.show_help:
            for i, line in enumerate(HELP_PLAYER):
                _safe_addstr(stdscr, h//2 - 3 + i, w//2 - 18, line, curses.A_BOLD)
        stdscr.refresh()

    def handle_key(self, key):
        s = self.settings
        if key in (ord('q'), ord('Q'), 27): return 'back'
        elif key == ord(' '): self.playing = not self.playing
        elif key in (ord('h'), ord('H')): self.show_help = not self.show_help
        elif key in (ord('c'), ord('C')): s.toggle_color()
        elif key in (ord('b'), ord('B')): s.toggle_braille()
        elif key in (ord('v'), ord('V')): s.toggle_hq()
        elif key in (ord('d'), ord('D')): s.cycle_density()
        elif key in (ord('n'), ord('N')): return 'next'
        elif key in (ord('p'), ord('P')): return 'prev'
        elif key in (ord('z'), ord('Z')): s.zoom = min(10.0, s.zoom + 0.2)
        elif key in (ord('x'), ord('X')): s.zoom = max(1.0, s.zoom - 0.2)
        elif key == ord('1'): s.set_charset('simple')
        elif key == ord('2'): s.set_charset('standard')
        elif key == ord('3'): s.set_charset('detailed')
        elif key == ord('4'): s.set_charset('blocks')
        elif key == ord('+'): s.fps = min(60, s.fps + 1)
        elif key == ord('-'): s.fps = max(1, s.fps - 1)
        elif key == curses.KEY_RIGHT:
            self._seek_relative(15)
        elif key == curses.KEY_LEFT:
            self._seek_relative(-15)
        return None

class UAMP:
    def __init__(self, start_path=None):
        self.fm = FileManager(start_path)
        self.settings = AppSettings()
        self.player = None
        self.mode = 'browser'

    def run(self):
        import os
        os.environ.setdefault('ESCDELAY', '25')
        try:
            curses.wrapper(self._main)
        finally:
            if self.player: self.player.stop()
            # Explicitly restore terminal state
            try:
                curses.endwin()
                # Force reset common terminal modes just in case
                import subprocess
                subprocess.run(['stty', 'sane'], check=False)
            except: pass

    def _main(self, stdscr):
        curses.start_color()
        curses.use_default_colors()
        for i in range(min(256, curses.COLORS)):
            curses.init_pair(i + COLOR_OFFSET, i, -1)
        curses.init_pair(6, curses.COLOR_YELLOW, -1)
        curses.curs_set(0)
        stdscr.timeout(50)
        browser = BrowserView(self.fm, self.settings)

        while True:
            h, w = stdscr.getmaxyx()
            if self.mode == 'browser':
                browser.draw(stdscr)
                res = browser.handle_key(stdscr.getch())
                if res == 'quit': break
                elif res and res.startswith('play:'):
                    self.player = PlayerView(Path(res[5:]), self.fm, self.settings)
                    self.player.start(w, h)
                    self.mode = 'player'
            else:
                self.player.tick()
                self.player.draw(stdscr)
                res = self.player.handle_key(stdscr.getch())
                if res == 'back':
                    self.player.stop()
                    self.mode = 'browser'
                elif res in ('next', 'prev'):
                    nxt, prv = self.fm.get_next_prev(self.player.filepath)
                    target = nxt if res == 'next' else prv
                    if target:
                        self.player.stop()
                        self.player = PlayerView(target, self.fm, self.settings)
                        self.player.start(w, h)
