"""Startpunkt. Das Display muss als ERSTES alloziert werden: der Framebuffer
braucht 115 KB am Stueck, und der ESP32-C3 hat wenig Heap."""
import gc
import time
from machine import Pin, I2C

gc.collect()
from pi4ioe5v6408ztaex import PI4IOE5V6408

i2c = I2C(0, sda=Pin(4), scl=Pin(5), freq=400_000)
io = PI4IOE5V6408(i2c)
io.write_pin(4, True)   # wie im Hersteller-Beispiel LCD.py
time.sleep_ms(300)
io.write_pin(2, True)
time.sleep_ms(300)
# Der Touch-Controller (0x15) erscheint erst am Bus, wenn alle Expander-Pins
# high sind (ermittelt mit probe_touch.py); welcher Pin es ist, ist egal.
# Pin 0 ist der Vibrationsmotor und wird aktiv ausgeschaltet: der Expander
# behaelt seinen Ausgangszustand ueber einen Soft-Reboot hinweg.
for pin in range(1, 8):
    io.write_pin(pin, True)
io.write_pin(0, False)
time.sleep_ms(300)

gc.collect()
from display_partial import LCDPartial
lcd = LCDPartial()
lcd.clear_screen()
gc.collect()
print("Heap frei nach LCD:", gc.mem_free())

import game
game.lcd = lcd
game.io = io
gc.collect()
print("Heap frei vor Spielstart:", gc.mem_free())
game.main()
