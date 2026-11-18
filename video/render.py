# -*- coding: utf-8 -*-
"""Motivasyon videosu üretici — 1080x1920 dikey, kinetik tipografi + ambient müzik.

Kullanım:  python3 render.py   ->  out/motivasyon.mp4
"""
import math, os, subprocess, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS = 1080, 1920, 30
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)

FONT_BOLD = "/usr/share/fonts/opentype/inter/InterDisplay-Bold.otf"
FONT_BLACK = "/usr/share/fonts/opentype/inter/InterDisplay-Black.otf"
FONT_MED = "/usr/share/fonts/opentype/inter/InterDisplay-Medium.otf"
if not os.path.exists(FONT_BLACK):
    FONT_BLACK = FONT_BOLD

WHITE = (245, 242, 235)
DIM = (150, 146, 140)
GOLD = (255, 196, 60)

# (metin, vurgulu kelimeler, stil)  stil: hook | normal | quiet | turn | climax
SCRIPT = [
    ("Başarılı olmak için motivasyona ihtiyacın yok.", {"motivasyona", "yok."}, "hook"),
    ("Sana bi şey söyliyim mi?", set(), "quiet"),
    ("Başarılı olmak için her sabah motive uyanmana gerek yok.", {"motive", "gerek", "yok."}, "normal"),
    ("Çünkü motivasyon dediğin şey bugün var, yarın yok.", {"bugün", "var,", "yarın", "yok."}, "normal"),
    ("Mesela bi akşam oturuyosun, hayatını değiştirmeye karar veriyosun.", {"hayatını", "değiştirmeye"}, "normal"),
    ("Yarın spora başlıycam, kitap okuycam, kendimi geliştiricem…", {"spora", "kitap", "geliştiricem…"}, "normal"),
    ("O an her şey çok güzel.", {"güzel."}, "quiet"),
    ("Ama sabah oluyo, o istekten eser yok.", {"eser", "yok."}, "normal"),
    ("İşte çoğumuz burada bırakıyoruz.", {"bırakıyoruz."}, "normal"),
    ("Çünkü bi şey yapmak için önce içimizden gelmesini bekliyoruz.", {"içimizden", "gelmesini"}, "normal"),
    ("Halbuki düşün bi…", set(), "turn"),
    ("Her gün işe gitmek için motive mi oluyosun?", {"motive"}, "normal"),
    ("Hayır.", {"Hayır."}, "turn"),
    ("Gitmen gerektiği için gidiyosun.", {"gerektiği"}, "normal"),
    ("Demek ki mesele motivasyon değil.", {"motivasyon", "değil."}, "normal"),
    ("Kendine verdiğin sözü, canın istemediğinde de tutabilmek.", {"sözü,", "tutabilmek."}, "climax"),
]

STYLE = {
    "hook":   dict(size=104, font=FONT_BLACK, word_dt=0.16, hold=1.6),
    "normal": dict(size=86,  font=FONT_BOLD,  word_dt=0.20, hold=1.25),
    "quiet":  dict(size=76,  font=FONT_MED,   word_dt=0.24, hold=1.2),
    "turn":   dict(size=120, font=FONT_BLACK, word_dt=0.30, hold=1.4),
    "climax": dict(size=96,  font=FONT_BLACK, word_dt=0.30, hold=3.0),
}
FADE_OUT = 0.35
GAP = 0.15
END_CARD = 3.0


def ease_out(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


# ---------------------------------------------------------------- seslendirme (Google TTS)
SR = 44100
VOICE_DIR = os.path.join(OUT, "voice")
VOICE_TEMPO = 1.12   # gTTS biraz yavaş konuşuyor, hafif hızlandır
VOICE_LEAD = 0.25    # ses, sahne başladıktan bu kadar sonra girer


def load_voice(i, text):
    """Satırı gTTS ile seslendir, sessizlikleri kırp, 44.1k mono float dizi döndür (önbellekli)."""
    os.makedirs(VOICE_DIR, exist_ok=True)
    mp3 = os.path.join(VOICE_DIR, f"{i:02d}.mp3")
    raw = os.path.join(VOICE_DIR, f"{i:02d}.raw")
    if not os.path.exists(mp3):
        from gtts import gTTS
        gTTS(text, lang="tr").save(mp3)
    if not os.path.exists(raw):
        af = ("silenceremove=start_periods=1:start_threshold=-45dB,"
              "areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
              f"atempo={VOICE_TEMPO},highpass=f=80,acompressor=threshold=-20dB:ratio=3")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", mp3, "-af", af,
                        "-ac", "1", "-ar", str(SR), "-f", "f32le", raw], check=True)
    return np.fromfile(raw, dtype=np.float32).astype(np.float64)


# ---------------------------------------------------------------- zamanlama
scenes, t = [], 0.6
for idx, (text, hl, st) in enumerate(SCRIPT):
    s = STYLE[st]
    words = text.split()
    voice = load_voice(idx, text)
    vlen = len(voice) / SR
    # kelimeler konuşmayla birlikte belirsin
    word_dt = max(0.08, (vlen * 0.9) / max(1, len(words)))
    hold = {"climax": 2.2, "hook": 1.0, "turn": 0.6}.get(st, 0.45)
    dur = VOICE_LEAD + vlen + hold + FADE_OUT
    if text.endswith("…"):
        dur += 0.4
    scenes.append(dict(text=text, words=words, hl=hl, style=st, start=t, dur=dur,
                       voice=voice, word_dt=word_dt))
    t += dur + GAP
END_START = t
TOTAL = t + END_CARD
NFRAMES = int(TOTAL * FPS)


# ---------------------------------------------------------------- yerleşim
def layout(scene):
    s = STYLE[scene["style"]]
    font = ImageFont.truetype(s["font"], s["size"])
    maxw = 880
    space = font.getlength(" ")
    lines, cur, curw = [], [], 0
    for w in scene["words"]:
        ww = font.getlength(w)
        if cur and curw + space + ww > maxw:
            lines.append((cur, curw)); cur, curw = [], 0
        curw = ww if not cur else curw + space + ww
        cur.append((w, ww))
    if cur:
        lines.append((cur, curw))
    lh = int(s["size"] * 1.22)
    top = H // 2 - (len(lines) * lh) // 2 - 40
    placed = []
    for i, (ln, lw) in enumerate(lines):
        x = (W - lw) / 2
        for w, ww in ln:
            placed.append((w, x, top + i * lh))
            x += ww + space
    scene["font"] = font
    scene["placed"] = placed
    scene["lh"] = lh
    scene["box"] = (top, top + len(lines) * lh)


for sc in scenes:
    layout(sc)

# ---------------------------------------------------------------- arka plan
rng = np.random.default_rng(7)
BW, BH = 270, 480
yy, xx = np.mgrid[0:BH, 0:BW].astype(np.float32)
nx, ny = xx / BW, yy / BH
vign = np.clip(1.15 - 1.1 * np.sqrt((nx - 0.5) ** 2 * 1.4 + (ny - 0.5) ** 2), 0, 1)
GRAIN = [(rng.normal(0, 1, (H // 2, W // 2)) * 7).astype(np.float32) for _ in range(6)]


def background(tt, warm):
    # yavaş hareket eden iki ışık lekesi
    b1x, b1y = 0.5 + 0.25 * math.sin(tt * 0.13), 0.38 + 0.12 * math.cos(tt * 0.11)
    b2x, b2y = 0.5 + 0.3 * math.cos(tt * 0.09 + 1), 0.72 + 0.1 * math.sin(tt * 0.15)
    g1 = np.exp(-(((nx - b1x) ** 2) / 0.10 + ((ny - b1y) ** 2) / 0.05))
    g2 = np.exp(-(((nx - b2x) ** 2) / 0.12 + ((ny - b2y) ** 2) / 0.06))
    base = np.stack([np.full_like(nx, 9), np.full_like(nx, 9), np.full_like(nx, 12)], -1)
    c1 = np.array([28 + 40 * warm, 22 + 22 * warm, 34 - 10 * warm], np.float32)
    c2 = np.array([14, 20, 34], np.float32)
    img = base + g1[..., None] * c1 + g2[..., None] * c2
    img *= vign[..., None]
    return img


def bg_frame(fi, tt, warm):
    small = background(tt, warm)
    im = Image.fromarray(np.clip(small, 0, 255).astype(np.uint8)).resize((W // 2, H // 2), Image.BILINEAR)
    a = np.asarray(im).astype(np.float32) + GRAIN[(fi // 2) % len(GRAIN)][..., None]
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).resize((W, H), Image.BILINEAR)
    return im.convert("RGBA")


# ---------------------------------------------------------------- sahne çizimi
def draw_scene(overlay, glow, sc, lt):
    s = STYLE[sc["style"]]
    d, dg = ImageDraw.Draw(overlay), ImageDraw.Draw(glow)
    out_a = 1.0
    if lt > sc["dur"] - FADE_OUT:
        out_a = max(0.0, (sc["dur"] - lt) / FADE_OUT)
    for i, (w, x, y) in enumerate(sc["placed"]):
        t0 = 0.25 + i * sc["word_dt"]
        p = ease_out((lt - t0) / 0.38)
        if p <= 0:
            continue
        a = int(255 * p * out_a)
        dy = (1 - p) * 26 - (1 - out_a) * 18
        hl = w in sc["hl"]
        col = GOLD if hl else (DIM if sc["style"] == "quiet" else WHITE)
        d.text((x, y + dy), w, font=sc["font"], fill=col + (a,))
        if hl:
            dg.text((x, y + dy), w, font=sc["font"], fill=GOLD + (int(a * 0.55),))
    # vurgulu sahnelerde alt çizgi
    if sc["style"] in ("hook", "climax"):
        p = ease_out((lt - 0.25 - len(sc["words"]) * sc["word_dt"]) / 0.6)
        if p > 0:
            yb = sc["box"][1] + 30
            half = 160 * p
            d.rounded_rectangle((W / 2 - half, yb, W / 2 + half, yb + 8), 4,
                                fill=GOLD + (int(255 * out_a),))


def draw_endcard(overlay, lt):
    d = ImageDraw.Draw(overlay)
    a = ease_out(lt / 0.6)
    if lt > END_CARD - 0.5:
        a *= max(0.0, (END_CARD - lt) / 0.5)
    f1 = ImageFont.truetype(FONT_BLACK, 92)
    f2 = ImageFont.truetype(FONT_MED, 52)
    t1, t2 = "Söz ver. Tut.", "@feyzibozdag"
    d.text(((W - f1.getlength(t1)) / 2, H / 2 - 120), t1, font=f1, fill=WHITE + (int(255 * a),))
    d.rounded_rectangle((W / 2 - 60, H / 2 + 5, W / 2 + 60, H / 2 + 11), 3, fill=GOLD + (int(255 * a),))
    d.text(((W - f2.getlength(t2)) / 2, H / 2 + 50), t2, font=f2, fill=GOLD + (int(255 * a),))


def progress(overlay, tt):
    d = ImageDraw.Draw(overlay)
    d.rectangle((0, 0, W, 6), fill=(255, 255, 255, 30))
    d.rectangle((0, 0, int(W * tt / TOTAL), 6), fill=GOLD + (200,))


def render_video(path):
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-c:v", "libx264", "-preset", "slow", "-crf", "24", "-tune", "grain", "-maxrate", "9M", "-bufsize", "18M", "-pix_fmt", "yuv420p", path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for fi in range(NFRAMES):
        tt = fi / FPS
        active = next((sc for sc in scenes if sc["start"] <= tt < sc["start"] + sc["dur"]), None)
        warm = 1.0 if active and active["style"] in ("climax", "hook") else 0.35
        frame = bg_frame(fi, tt, warm)
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        if active:
            draw_scene(overlay, glow, active, tt - active["start"])
        elif tt >= END_START:
            draw_endcard(overlay, tt - END_START)
        if active and active["hl"]:
            frame = Image.alpha_composite(frame, glow.filter(ImageFilter.GaussianBlur(18)))
        progress(overlay, tt)
        # hafif yakınlaştırma (sahne boyunca)
        if active:
            z = 1.0 + 0.035 * ease_out((tt - active["start"]) / active["dur"])
            ow, oh = int(W * z), int(H * z)
            ov = overlay.resize((ow, oh), Image.BILINEAR)
            overlay = ov.crop(((ow - W) // 2, (oh - H) // 2, (ow - W) // 2 + W, (oh - H) // 2 + H))
        frame = Image.alpha_composite(frame, overlay)
        proc.stdin.write(frame.convert("RGB").tobytes())
        if fi % 150 == 0:
            print(f"  kare {fi}/{NFRAMES}", flush=True)
    proc.stdin.close()
    proc.wait()


# ---------------------------------------------------------------- müzik


def render_audio(path):
    n = int(TOTAL * SR)
    t = np.arange(n) / SR
    out = np.zeros(n, np.float64)

    def note(f):
        return 440.0 * 2 ** ((f - 69) / 12)

    # Am – F – C – G  (her akor 4 sn)
    chords = [[57, 60, 64], [53, 57, 60], [48, 55, 60], [55, 59, 62]]
    bass = [45, 41, 48, 43]
    CL = 4.0
    turn_t = next(sc["start"] for sc in scenes if sc["text"].startswith("Halbuki"))
    climax_t = next(sc["start"] for sc in scenes if sc["style"] == "climax")

    # pad
    for k in range(int(TOTAL / CL) + 1):
        s0, s1 = int(k * CL * SR), min(n, int((k + 1) * CL * SR + 1.0 * SR))
        if s0 >= n:
            break
        tt = t[s0:s1] - k * CL
        env = np.minimum(1, tt / 1.2) * np.clip((CL + 1.0 - tt) / 1.2, 0, 1)
        ch = chords[k % 4]
        sig = np.zeros_like(tt)
        for m in ch + [ch[0] + 12]:
            f = note(m)
            for det in (-0.12, 0.12):
                sig += np.sin(2 * np.pi * (f + det) * tt) + 0.25 * np.sin(2 * np.pi * 2 * (f + det) * tt)
        sig += 1.6 * np.sin(2 * np.pi * note(bass[k % 4]) * tt)
        out[s0:s1] += 0.022 * sig * env

    # piyano benzeri arpej (Halbuki'den sonra başlar, final'de yoğunlaşır)
    step = 0.5
    for i in range(int(TOTAL / step)):
        st = i * step
        if st < turn_t + 0.8 or st > END_START + 1.5:
            continue
        k = int(st / CL) % 4
        ch = chords[k]
        m = ch[i % 3] + 12 + (12 if i % 4 == 3 else 0)
        f = note(m)
        s0 = int(st * SR); s1 = min(n, s0 + int(1.8 * SR))
        tt = t[s0:s1] - st
        env = np.exp(-tt * 3.2) * np.minimum(1, tt / 0.005)
        sig = np.sin(2 * np.pi * f * tt) + 0.35 * np.sin(2 * np.pi * 2 * f * tt) + 0.1 * np.sin(2 * np.pi * 3 * f * tt)
        vol = 0.07 if st < climax_t else 0.10
        out[s0:s1] += vol * sig * env

    # derin vuruşlar: dönüm noktası ve final
    for hit in (turn_t, climax_t):
        s0 = int(hit * SR); s1 = min(n, s0 + int(2.5 * SR))
        tt = t[s0:s1] - hit
        f = 55 * np.exp(-tt * 1.5) + 38
        ph = 2 * np.pi * np.cumsum(f) / SR
        out[s0:s1] += 0.45 * np.sin(ph) * np.exp(-tt * 1.8)

    # Halbuki öncesi kısa sessizlik (gerilim)
    duck = np.ones(n)
    a, b = int((turn_t - 0.6) * SR), int(turn_t * SR)
    duck[a:b] = np.linspace(1, 0.25, b - a)
    duck[b:b + int(0.8 * SR)] = np.linspace(0.25, 1, len(duck[b:b + int(0.8 * SR)]))
    out *= duck

    # basit reverb (çoklu gecikme)
    rev = out.copy()
    for dly, g in ((0.031, 0.35), (0.047, 0.3), (0.071, 0.25), (0.113, 0.2), (0.173, 0.15)):
        dd = int(dly * SR)
        rev[dd:] += g * out[:-dd]
    out = rev
    # giriş/çıkış fade
    fi_, fo = int(1.5 * SR), int(2.5 * SR)
    out[:fi_] *= np.linspace(0, 1, fi_)
    out[-fo:] *= np.linspace(1, 0, fo)
    out = np.tanh(out * 1.4) / np.tanh(1.4)
    out /= max(1e-9, np.abs(out).max()) / 0.8

    # seslendirme: müzik altta kalsın (ducking), ses önde
    music = out * 0.22
    voice = np.zeros(n)
    env = np.zeros(n)
    for sc in scenes:
        v = sc["voice"]
        s0 = int((sc["start"] + VOICE_LEAD) * SR)
        s1 = min(n, s0 + len(v))
        voice[s0:s1] += v[: s1 - s0]
        env[max(0, s0 - int(0.2 * SR)):min(n, s1 + int(0.3 * SR))] = 1
    k = int(0.25 * SR)
    env = np.convolve(env, np.ones(k) / k, mode="same")
    music *= 1 - 0.45 * env
    voice /= max(1e-9, np.abs(voice).max()) / 0.85
    vrev = voice.copy()
    for dly, g in ((0.023, 0.12), (0.041, 0.08)):
        dd = int(dly * SR)
        vrev[dd:] += g * voice[:-dd]
    mix = np.tanh((music + vrev) * 1.1) / np.tanh(1.1)
    mix /= max(1e-9, np.abs(mix).max()) / 0.9
    out = mix
    stereo = np.stack([out, out], -1)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(SR)
        wf.writeframes((stereo * 32767).astype(np.int16).tobytes())


if __name__ == "__main__":
    print(f"Süre: {TOTAL:.1f} sn, {NFRAMES} kare")
    v, a = os.path.join(OUT, "_video.mp4"), os.path.join(OUT, "_audio.wav")
    render_audio(a)
    render_video(v)
    final = os.path.join(OUT, "motivasyon.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", v, "-i", a, "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", final], check=True)
    os.remove(v); os.remove(a)
    print("Hazır:", final)
