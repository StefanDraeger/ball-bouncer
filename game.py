"""BallBouncer fuer das Elecrow CrowPanel 1.28" (ESP32-C3, GC9A01, CST816D).

Steuerung: auf den Touchscreen tippen -> Ball springt.
Der Displayrand ist tabu: beruehrt der Ball ihn oder eine Kugelkette, ist
Schluss. Die Luecke zwischen den Ketten schwingt auf und ab.
"""
import math
import time
import framebuf
from machine import Pin, PWM

from cst816d import Touch_CST816D

# ---------------------------------------------------------------- Hardware
lcd = None  # wird von main.py gesetzt (muss dort zuerst alloziert werden)
io = None    # IO-Expander, wird von main.py gesetzt (Pin 0 = Vibrationsmotor)
BAND_H = 80  # Hoehe des Framebuffers (LCDPartial)
oy = 0       # Y-Offset des Bandes, das gerade gezeichnet wird
bgt = 0.0    # Zeit fuer die Hintergrundanimation

touch = Touch_CST816D(mode=1)
if not hasattr(touch, "Flag"):
    raise RuntimeError("Touch-Controller nicht gefunden")
touch.Set_Mode(1)

SOUND = False
buzzer = PWM(Pin(3), freq=1000, duty_u16=0)
_beep_until = 0


def beep(freq, ms):
    global _beep_until
    if not SOUND:
        return
    buzzer.freq(freq)
    buzzer.duty_u16(32768)
    _beep_until = time.ticks_add(time.ticks_ms(), ms)


def beep_service(now):
    global _beep_until
    if _beep_until and time.ticks_diff(now, _beep_until) >= 0:
        buzzer.duty_u16(0)
        _beep_until = 0


_vib_until = 0


def vibrate(ms):
    global _vib_until
    if io is None:
        return
    io.write_pin(0, True)
    _vib_until = time.ticks_add(time.ticks_ms(), ms)


def vibrate_service(now):
    global _vib_until
    if _vib_until and time.ticks_diff(now, _vib_until) >= 0:
        io.write_pin(0, False)
        _vib_until = 0


# ---------------------------------------------------------------- Farben
def rgb(r, g, b):
    # framebuf speichert little-endian, der GC9A01 erwartet das hoeherwertige
    # Byte zuerst -> Standard-RGB565 mit vertauschten Bytes. (Passt zu den
    # Treiber-Konstanten red=0x07E0, green=0x001F, blue=0xF800.)
    c = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
    return ((c & 0xFF) << 8) | (c >> 8)


SKY = [rgb(90, 170, 250), rgb(115, 188, 252), rgb(140, 204, 254),
       rgb(165, 218, 255), rgb(190, 230, 255), rgb(210, 240, 255)]
C_SUN = rgb(255, 214, 60)
C_SUN_GLOW = rgb(255, 238, 150)
C_CLOUD = rgb(244, 250, 255)
C_HILL_FAR = rgb(110, 190, 150)
C_HILL_NEAR = rgb(70, 170, 90)
C_BALL = rgb(255, 196, 30)
C_SHINE = rgb(255, 250, 220)
C_ORB = rgb(52, 56, 64)
C_ORB_EDGE = rgb(88, 94, 106)
C_ORB_HI = rgb(150, 156, 170)
C_TEXT = rgb(255, 255, 255)
C_DIM = rgb(236, 244, 255)
C_SHADOW = rgb(20, 40, 90)

# ---------------------------------------------------------------- Parameter
CX = CY = 120
RING_R = 119          # Spielfeldrand = Rand des runden Displays (unsichtbar)
BALL_X = 70
BALL_R = 8
GRAVITY = 900.0       # px/s^2
JUMP = -290.0         # px/s
VMAX = 420.0
GAP = 84
OR = 14               # Radius der Kugeln in den Ketten
ORB_STEP = 22         # Abstand der Kugelmittelpunkte
AMP = 20.0            # Ausschlag der schwingenden Luecke (px)
OSC = 2.6             # Schwingfrequenz (rad/s)
SPACING = 125
SPEED0 = 75.0
SPEED_MAX = 130.0
SAFE_R = RING_R - BALL_R   # Ballmittelpunkt muss innerhalb liegen

# ---------------------------------------------------------------- Highscore
SCORE_FILE = "highscore.txt"


def load_best():
    try:
        with open(SCORE_FILE) as f:
            return int(f.read())
    except Exception:
        return 0


def save_best(v):
    try:
        with open(SCORE_FILE, "w") as f:
            f.write(str(v))
    except Exception:
        pass


# ---------------------------------------------------------------- Text
def text_big(s, cx, y, scale, color):
    if y + 8 * scale + 2 <= oy or y >= oy + BAND_H:
        return  # liegt nicht im aktuellen Band
    w = 8 * len(s)
    fb = framebuf.FrameBuffer(bytearray(w), w, 8, framebuf.MONO_HLSB)
    fb.text(s, 0, 0, 1)
    x0 = cx - (w * scale) // 2
    sh = 1 if scale == 1 else 2
    for yy in range(8):
        for xx in range(w):
            if fb.pixel(xx, yy):
                px = x0 + xx * scale
                py = y + yy * scale - oy
                lcd.fill_rect(px + sh, py + sh, scale, scale, C_SHADOW)
    for yy in range(8):
        for xx in range(w):
            if fb.pixel(xx, yy):
                lcd.fill_rect(x0 + xx * scale, y + yy * scale - oy, scale, scale, color)


# ---------------------------------------------------------------- Touch
_last_touch = 0


def poll_tap(now):
    """True bei einem neuen Tipp. Solange der Finger liegt, feuert der
    Interrupt weiter -> erst nach einer Pause (150 ms) zaehlt es neu."""
    global _last_touch
    if touch.Flag:
        touch.Flag = 0
        gap = time.ticks_diff(now, _last_touch)
        _last_touch = now
        return gap > 150
    return False


# ---------------------------------------------------------------- Logik
def orb_ys(gy):
    """Y-Mittelpunkte der Kugeln einer Kette; die ersten beiden Eintraege
    sind die Kugeln direkt an der Luecke (oben, unten)."""
    top = gy - GAP // 2 - OR
    bot = gy + GAP // 2 + OR
    ys = [top, bot]
    y = top - ORB_STEP
    while y > -OR:
        ys.append(y)
        y -= ORB_STEP
    y = bot + ORB_STEP
    while y < 240 + OR:
        ys.append(y)
        y += ORB_STEP
    return ys


def new_pipe(x):
    r = time.ticks_us()
    return [float(x), 120.0, False, 90 + (r * 7 + x * 13) % 61, (r % 628) / 100.0]


def reset():
    global by, vy, pipes, score, gt
    by = 120.0
    vy = 0.0
    score = 0
    gt = 0.0
    pipes = [new_pipe(270)]
    pipes[0][1] = pipes[0][3]


def ell(x, y, xr, yr, color):
    """Gefuellte Ellipse in Weltkoordinaten; ausserhalb des Bandes uebersprungen."""
    if y + yr < oy or y - yr >= oy + BAND_H:
        return
    lcd.ellipse(x, y - oy, xr, yr, color, True)


def draw_scenery():
    # Himmel als sechs Streifen, nach unten heller
    for k in range(6):
        lcd.fill_rect(0, k * 40 - oy, 240, 40, SKY[k])
    # Sonne
    ell(196, 62, 18, 18, C_SUN_GLOW)
    ell(196, 62, 13, 13, C_SUN)
    # Wolken (driften langsam nach links)
    for cx0, cy, k in ((20, 98, 9), (150, 148, 6)):
        x = (cx0 - int(bgt * k)) % 300 - 30
        ell(x, cy, 20, 9, C_CLOUD)
        ell(x - 14, cy + 3, 13, 7, C_CLOUD)
        ell(x + 15, cy + 3, 14, 7, C_CLOUD)
        ell(x + 2, cy - 6, 12, 8, C_CLOUD)
    # Huegel in zwei Ebenen (Parallaxe)
    for i in range(3):
        ell((i * 110 - int(bgt * 8)) % 330 - 45, 228, 55, 46, C_HILL_FAR)
    for i in range(3):
        ell((i * 110 + 40 - int(bgt * 22)) % 330 - 45, 246, 48, 36, C_HILL_NEAR)


def draw_world():
    draw_scenery()
    for p in pipes:
        cx = int(p[0]) + OR
        if cx + OR < 0 or cx - OR > 240:
            continue
        ys = orb_ys(p[1])
        for i, y in enumerate(ys):
            y = int(y)
            if y + OR < oy or y - OR >= oy + BAND_H:
                continue  # liegt nicht im aktuellen Band
            lcd.ellipse(cx, y - oy, OR, OR, C_ORB_EDGE if i < 2 else C_ORB, True)
            lcd.ellipse(cx - 4, y - 4 - oy, 3, 3, C_ORB_HI, True)
    iy = int(by) - oy
    lcd.ellipse(BALL_X, iy, BALL_R, BALL_R, C_BALL, True)
    lcd.ellipse(BALL_X - 3, iy - 3, 2, 2, C_SHINE, True)


def render(state, best):
    """Bild in drei 80-Zeilen-Baendern zeichnen (spart RAM, siehe display_partial)."""
    global oy
    for oy in (0, BAND_H, 2 * BAND_H):
        draw_world()
        if state == "title":
            text_big("ORBIT", CX, 50, 3, C_TEXT)
            text_big("HOP", CX, 80, 3, C_BALL)
            text_big("TAP TO START", CX, 175, 1, C_DIM)
            text_big("BEST " + str(best), CX, 192, 1, C_DIM)
        elif state == "play":
            text_big(str(score), CX, 30, 3, C_TEXT)
        else:
            text_big("GAME OVER", CX, 60, 2, C_TEXT)
            text_big(str(score), CX, 95, 4, C_BALL)
            text_big("BEST " + str(best), CX, 140, 1, C_DIM)
            text_big("TAP TO RETRY", CX, 175, 1, C_DIM)
        lcd.show_at(oy)


# ---------------------------------------------------------------- Hauptschleife
def main():
    global by, vy, pipes, score, gt, bgt
    best = load_best()
    reset()
    state = "title"
    dead_at = 0
    last = time.ticks_ms()

    while True:
        now = time.ticks_ms()
        dt = min(time.ticks_diff(now, last) / 1000.0, 0.05)
        last = now
        bgt += dt
        tap = poll_tap(now)
        beep_service(now)
        vibrate_service(now)

        if state == "title":
            by = 120.0 + math.sin(now / 250.0) * 10
            if tap:
                reset()
                vy = JUMP
                beep(900, 40)
                state = "play"

        elif state == "play":
            if tap:
                vy = JUMP
                beep(900, 30)
            vy = min(vy + GRAVITY * dt, VMAX)
            by += vy * dt

            speed = min(SPEED0 + score * 2.0, SPEED_MAX)
            gt += dt
            for p in pipes:
                p[0] -= speed * dt
                p[1] = p[3] + AMP * math.sin(gt * OSC + p[4])
            if pipes[0][0] + 2 * OR < -4:
                pipes.pop(0)
            if pipes[-1][0] < 240 - SPACING + 20:
                pipes.append(new_pipe(int(pipes[-1][0]) + SPACING))

            dead = (BALL_X - CX) ** 2 + (by - CY) ** 2 > SAFE_R * SAFE_R
            r = BALL_R - 1
            lim = (OR + r) * (OR + r)
            for p in pipes:
                ox = p[0] + OR
                if not p[2] and ox + OR < BALL_X - BALL_R:
                    p[2] = True
                    score += 1
                    beep(1500, 50)
                if abs(BALL_X - ox) < OR + r:
                    for y in orb_ys(p[1]):
                        if (BALL_X - ox) ** 2 + (by - y) ** 2 < lim:
                            dead = True
                            break
            if dead:
                state = "dead"
                dead_at = now
                beep(200, 300)
                vibrate(150)
                if score > best:
                    best = score
                    save_best(best)

        elif state == "dead":
            if tap and time.ticks_diff(now, dead_at) > 700:
                reset()
                vy = JUMP
                beep(900, 40)
                state = "play"

        render(state, best)
