"""
UAMP - Advanced TUI
Full media player with color, high-res, and playlist support.
"""

import curses
import time
from pathlib import Path
from uamp.fsal import FileManager, get_file_type
from uamp.media_engine import MediaEngine
from uamp.settings import AppSettings

HELP_PLAYER = [
    "┌──────── Player Controls ──────────┐",
    "│ Space: Pause/Resume   H: Help     │",
    "│ N/P: Next/Prev File   Q: Back     │",
    "│ C: Color Toggle       B: Braille  │",
    "│ D: Cycle Density      1-4: Charset│",
    "│ Z/X: Zoom In/Out      +-: Speed   │",
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
    def __init__(self, fm: FileManager):
        self.fm = fm
        self.show_help = False

    def draw(self, stdscr):
        h, w = stdscr.getmaxyx()
        stdscr.erase()
        _safe_addstr(stdscr, 0, 0, " UAMP  Universal ASCII Media Player ".ljust(w), curses.A_REVERSE | curses.A_BOLD)
        _safe_addstr(stdscr, 1, 0, f" {self.fm.current_path}".ljust(w), curses.A_DIM)
        
        visible = h - 4
        self.fm.update_scroll(visible)
        entries = self.fm.entries

        for i in range(visible):
            idx = i + self.fm.scroll_offset
            if idx >= len(entries): break
            entry = entries[idx]
            icon, name = self.fm.get_display_entry(entry)
            line = f" {icon} {name}"
            is_sel = (idx == self.fm.selected_idx)
            attr = curses.A_REVERSE if is_sel else 0
            _safe_addstr(stdscr, 2+i, 0, line.ljust(w-1), attr)

        _safe_addstr(stdscr, h-1, 0, " ↑↓:Nav  Enter:Open  Esc/⌫:Parent  H:Help  Q:Quit ".ljust(w), curses.A_DIM)
        if self.show_help:
            for i, line in enumerate(HELP_BROWSER):
                _safe_addstr(stdscr, h//2 - 2 + i, w//2 - 15, line, curses.A_BOLD)
        stdscr.refresh()

    def handle_key(self, key):
        if key in (ord('q'), ord('Q')): return 'quit'
        elif key == curses.KEY_UP: self.fm.move_up()
        elif key == curses.KEY_DOWN: self.fm.move_down()
        elif key in (curses.KEY_BACKSPACE, 127, 27): self.fm.go_parent()
        elif key in (ord('\n'), ord('\r')):
            res = self.fm.open_selected()
            if res: return f'play:{res}'
        elif key == ord('.'): self.fm.toggle_hidden()
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
        if self.engine: self.engine.stop()
        self.engine = MediaEngine(self.filepath, w, h - 3, self.settings)
        self.engine.start_loading()
        self._last_t = time.monotonic()

    def stop(self):
        if self.engine: self.engine.stop()

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
        fmt = "BRAILLE" if s.braille_mode else f"CHAR:{s.charset_key}"
        dens = f"D:{s.density}"
        status = f" {self.filepath.name} │ {mode} │ {fmt} │ {dens} │ Zoom:{s.zoom:.1f}x │ {s.fps} FPS "
        _safe_addstr(stdscr, h-2, 0, status.ljust(w), curses.A_REVERSE)
        _safe_addstr(stdscr, h-1, 0, " N:Next  P:Prev  D:Density  C:Color  B:Braille  H:Help ".ljust(w))

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
        elif key == curses.KEY_RIGHT and self.engine and self.engine.frames:
            self.cur_idx = (self.cur_idx + 10) % len(self.engine.frames)
        elif key == curses.KEY_LEFT and self.engine and self.engine.frames:
            self.cur_idx = (self.cur_idx - 10) % len(self.engine.frames)
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

    def _main(self, stdscr):
        curses.start_color()
        curses.use_default_colors()
        for i in range(min(256, curses.COLORS)):
            curses.init_pair(i + COLOR_OFFSET, i, -1)
        curses.init_pair(6, curses.COLOR_YELLOW, -1)
        curses.curs_set(0)
        stdscr.timeout(50)
        browser = BrowserView(self.fm)

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
