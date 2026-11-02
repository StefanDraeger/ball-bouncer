
from machine import Pin, SPI
import framebuf
import gc

from gc9a01 import LCD_1inch28


class LCDPartial(framebuf.FrameBuffer):
    """
    Speicherarme Variante fuer das CrowPanel 1.28" (GC9A01).

    Statt eines 240x240-RGB565-Framebuffers (115200 Byte)
    wird nur ein 240x80-Framebuffer (38400 Byte) reserviert.

    Die Initialisierung und SPI-Hilfsfunktionen werden aus dem
    funktionierenden Elecrow-Treiber gc9a01.py uebernommen.
    """

    WIDTH = 240
    BAND_HEIGHT = 80

    # Bewaehrte Methoden aus Elecrows Treiber wiederverwenden
    write_cmd = LCD_1inch28.write_cmd
    write_data = LCD_1inch28.write_data
    init_display = LCD_1inch28.init_display
    setWindows = LCD_1inch28.setWindows
    write_text = LCD_1inch28.write_text

    def __init__(self):
        self.width = self.WIDTH
        self.height = self.BAND_HEIGHT

        self.cs = Pin(10, Pin.OUT)
        self.cs(1)

        self.spi = SPI(
            1,
            60_000_000,
            polarity=0,
            phase=0,
            bits=8,
            sck=Pin(6),
            mosi=Pin(7),
        )

        self.dc = Pin(2, Pin.OUT)
        self.dc(1)

        gc.collect()

        self.buffer = bytearray(self.width * self.height * 2)

        super().__init__(
            self.buffer,
            self.width,
            self.height,
            framebuf.RGB565,
        )

        # Originale Elecrow-Initialisierung
        self.init_display()

        # Farbcodierung des Elecrow-Treibers (BGR/RGB565)
        self.red = 0x07E0
        self.green = 0x001F
        self.blue = 0xF800
        self.white = 0xFFFF
        self.black = 0x0000
        self.brown = 0x8430

    def show_at(self, y):
        """
        Den 240x80-Framebuffer an die Y-Position y schreiben.
        Gueltige Positionen fuer dieses Projekt: 0, 80, 160.
        """
        if y < 0 or y + self.height > 240:
            raise ValueError("ungueltige Y-Position fuer Display-Band")

        self.setWindows(
            0,
            y,
            self.width,
            y + self.height,
        )

        self.cs(1)
        self.dc(1)
        self.cs(0)
        self.spi.write(self.buffer)
        self.cs(1)

    def clear_screen(self):
        """
        Gesamtes 240x240-Display mit drei 80-Pixel-Baendern loeschen.
        """
        self.fill(self.black)

        self.show_at(0)
        self.show_at(80)
        self.show_at(160)
