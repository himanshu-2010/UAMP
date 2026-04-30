"""
UAMP - Settings & Persistence
Stores user preferences across the session.
"""

class AppSettings:
    def __init__(self):
        self.charset_key = 'standard'
        self.color_mode = False
        self.braille_mode = False
        self.density = 1 # 1: Standard, 2: High, 3: Ultra
        self.zoom = 1.0
        self.fps = 10.0

    def toggle_color(self):
        self.color_mode = not self.color_mode

    def toggle_braille(self):
        self.braille_mode = not self.braille_mode

    def cycle_density(self):
        self.density = (self.density % 3) + 1

    def set_charset(self, key):
        self.charset_key = key
