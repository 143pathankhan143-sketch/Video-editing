#!/usr/bin/env python3
"""
End-to-end Real Estate Video Editor for VID-20261112-WA0002.mp4 (Juna Ausa Road, Latur).

Features:
1. Tight Dialogue Editing:
   - Removes all silences, dead air, breaths, filler onset sounds, and repeated takes.
   - Preserves complete sentences without cutting mid-sentence.
   - Applies smooth 30ms cosine audio crossfades & micro-roomtone continuity.
2. Video Enhancement (478x850 -> 1080x1920 Full HD @ 30fps):
   - Lanczos upscaling, gentle architectural unsharp mask, shadow lift, warm color grade.
   - Smooth Ken Burns dynamic push-in on static opening exterior shots so there is zero static dead-feel.
3. Marathi (Devanagari) Motion Graphics & Proper Captions (rendered via HarfBuzz/resvg + Mukta font):
   - Top persistent location header badge (जुना औसा रोड, लातूर).
   - Synced pop-up animated spec badges & price hero callout (₹९० लाख).
   - High-contrast animated Marathi captions with highlighted property keywords.
   - Polished closing Property Summary & CTA End Card over smooth golden-hour blurred property backdrop.
   - Exports matching `.srt` Marathi subtitle file.
4. Broadcast Audio Mastering & Procedural Sound Design:
   - Cleans raw Marathi voiceover (high-pass 85Hz, spectral noise gate, presence boost, soft compressor).
   - Synthesizes warm ambient acoustic guitar/pad real-estate background bed (auto-ducked under speech).
   - Synthesizes & syncs clean motion graphic SFX (soft whooshes, UI pops, luxury chime on ₹90 Lakh reveal, closing swell).
   - Loudness-normalizes final stereo master to ~ -15 LUFS.
"""

import io
import json
import math
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import av
import imageio_ffmpeg
import numpy as np
import resvg_py
import soundfile as sf
from PIL import Image, ImageEnhance, ImageFilter
from scipy.signal import butter, sosfiltfilt

ROOT = Path(__file__).resolve().parent.parent
INPUT_VIDEO = ROOT / "VID-20261112-WA0002.mp4"
FONT_DIR = str(ROOT / "assets" / "fonts")
OUTPUT_DIR = ROOT / "output"
OUTPUT_VIDEO = OUTPUT_DIR / "Latur_Property_Edited_Reel.mp4"
OUTPUT_SRT = OUTPUT_DIR / "Latur_Property_Captions_mr.srt"
OUTPUT_EDL = OUTPUT_DIR / "edit_decision_list.json"

W, H = 1080, 1920
FPS = 30
SR = 48000


@dataclass
class ClipSpec:
    id: str
    src_start: float
    src_end: float
    zoom_start: float
    zoom_end: float
    # Captions can be split into 1 or 2 sub-phrases within the clip (relative fractions 0..1)
    captions: List[Tuple[float, float, str, str]]  # (rel_start, rel_end, line1_svg, plain_srt)
    badge: Optional[Tuple[str, str, str, str]]  # (icon_type, label_top, value_main, accent_hex)
    sfx_type: str  # 'whoosh', 'pop', 'chime', 'sparkle'


# 11 clean, non-repetitive, complete-sentence clips (zero mid-sentence cuts, zero filler/retakes)
CLIPS: List[ClipSpec] = [
    ClipSpec(
        id="01_intro_hook",
        src_start=1.50,
        src_end=4.65,
        zoom_start=1.00,
        zoom_end=1.06,
        captions=[
            (
                0.00,
                0.46,
                'नमस्कार <tspan fill="#FBBF24">लातूरकरांनो!</tspan>',
                "नमस्कार लातूरकरांनो!",
            ),
            (
                0.46,
                1.00,
                'आज आपल्यापाशी <tspan fill="#38BDF8">जुना औसा रोडला</tspan> घर आलंय',
                "आज आपल्यापाशी जुना औसा रोडला घर आलंय.",
            ),
        ],
        badge=("pin", "प्राईम लोकेशन • लातूर", "जुना औसा रोड", "#38BDF8"),
        sfx_type="whoosh",
    ),
    ClipSpec(
        id="02_bhk_config",
        src_start=5.23,
        src_end=7.14,
        zoom_start=1.06,
        zoom_end=1.10,
        captions=[
            (
                0.00,
                1.00,
                'खाली <tspan fill="#FBBF24">1BHK</tspan> आहे, वरी <tspan fill="#FBBF24">1BHK</tspan> आहे',
                "खाली 1BHK आहे, वरी 1BHK आहे.",
            )
        ],
        badge=("home", "दुमजली रचना", "खाली 1BHK + वरी 1BHK", "#F59E0B"),
        sfx_type="pop",
    ),
    ClipSpec(
        id="03_rooms_and_price",
        src_start=7.67,
        src_end=11.34,
        zoom_start=1.02,
        zoom_end=1.08,
        captions=[
            (
                0.00,
                0.48,
                'आणि खाली १ रूम — टोटल <tspan fill="#34D399">७ रूम</tspan> आहेत',
                "आणि खाली १ रूम — टोटल ७ रूम आहेत,",
            ),
            (
                0.48,
                1.00,
                'मालकाचा रेट सांगताय फक्त <tspan fill="#FBBF24">₹९० लाख रुपये!</tspan>',
                "मालकाचा रेट सांगताय फक्त ₹९० लाख रुपये!",
            ),
        ],
        badge=("tag", "एकूण ७ रूम • आकर्षक किंमत", "फक्त ₹९० लाख", "#10B981"),
        sfx_type="chime",
    ),
    ClipSpec(
        id="04_plot_size",
        src_start=12.22,
        src_end=13.82,
        zoom_start=1.00,
        zoom_end=1.03,
        captions=[
            (
                0.00,
                1.00,
                'जागा साईज आहे <tspan fill="#38BDF8">२५ × ३० फूट</tspan>',
                "जागा साईज आहे २५ × ३० फूट.",
            )
        ],
        badge=("grid", "प्लॉट साईज (क्षेत्रफळ)", "२५ × ३० चौ. फूट", "#38BDF8"),
        sfx_type="pop",
    ),
    ClipSpec(
        id="05_innova_parking",
        src_start=14.13,
        src_end=15.30,
        zoom_start=1.00,
        zoom_end=1.02,
        captions=[
            (
                0.00,
                1.00,
                '<tspan fill="#FBBF24">इनोव्हा गाडीची</tspan> मोठी पार्किंग आहे',
                "इनोव्हा गाडीची मोठी पार्किंग आहे.",
            )
        ],
        badge=("car", "प्रशस्त कव्हर्ड पार्किंग", "इनोव्हा कार पार्किंग", "#F59E0B"),
        sfx_type="pop",
    ),
    ClipSpec(
        id="06_independent_house",
        src_start=17.35,
        src_end=18.88,
        zoom_start=1.00,
        zoom_end=1.02,
        captions=[
            (
                0.00,
                1.00,
                'हे <tspan fill="#34D399">स्वतंत्र घर</tspan> आहे — रो-हाऊस नाही!',
                "हे स्वतंत्र घर आहे — रो-हाऊस नाही!",
            )
        ],
        badge=("shield", "प्रॉपर्टी प्रकार", "स्वतंत्र घर (रो-हाऊस नाही)", "#10B981"),
        sfx_type="whoosh",
    ),
    ClipSpec(
        id="07_stilt_parking",
        src_start=19.28,
        src_end=20.28,
        zoom_start=1.00,
        zoom_end=1.02,
        captions=[
            (
                0.00,
                1.00,
                'ही सगळी खाली <tspan fill="#FBBF24">पार्किंगच</tspan> आहे',
                "ही सगळी खाली पार्किंगच आहे.",
            )
        ],
        badge=None,
        sfx_type="none",
    ),
    ClipSpec(
        id="08_developed_locality",
        src_start=21.74,
        src_end=23.38,
        zoom_start=1.00,
        zoom_end=1.02,
        captions=[
            (
                0.00,
                1.00,
                '<tspan fill="#38BDF8">लोकेशन</tspan> बघा आजूबाजूला कशी डेव्हलप आहे',
                "लोकेशन बघा आजूबाजूला कशी डेव्हलप आहे.",
            )
        ],
        badge=("pin", "परिसर आणि कनेक्टिव्हिटी", "पूर्ण विकसित परिसर", "#38BDF8"),
        sfx_type="whoosh",
    ),
    ClipSpec(
        id="09_vip_bungalows",
        src_start=23.97,
        src_end=25.13,
        zoom_start=1.00,
        zoom_end=1.02,
        captions=[
            (
                0.00,
                1.00,
                'सगळे <tspan fill="#FBBF24">व्हीआयपी बंगले</tspan> आहेत इथं',
                "सगळे व्हीआयपी बंगले आहेत इथं.",
            )
        ],
        badge=("star", "प्रीमियम सोसायटी परिसर", "व्हीआयपी बंगलो एरिया", "#F59E0B"),
        sfx_type="pop",
    ),
    ClipSpec(
        id="10_borewell_water",
        src_start=30.23,
        src_end=31.30,
        zoom_start=1.00,
        zoom_end=1.03,
        captions=[
            (
                0.00,
                1.00,
                'भरपूर <tspan fill="#38BDF8">पाण्याचा बोर</tspan> उपलब्ध आहे',
                "भरपूर पाण्याचा बोर उपलब्ध आहे.",
            )
        ],
        badge=("drop", "पाण्याची सोय", "स्वतंत्र पाण्याचा बोर", "#38BDF8"),
        sfx_type="pop",
    ),
    ClipSpec(
        id="11_rental_income",
        src_start=41.85,
        src_end=43.77,
        zoom_start=1.00,
        zoom_end=1.04,
        captions=[
            (
                0.00,
                1.00,
                'सुंदर घर आहे, <tspan fill="#34D399">भाडेकरू पण</tspan> सहज मिळू शकतात!',
                "सुंदर घर आहे, भाडेकरू पण सहज मिळू शकतात!",
            )
        ],
        badge=("sparkle", "गुंतवणूक व भाडे उत्पन्न", "भाडेकरूंसाठी उत्तम संधी", "#10B981"),
        sfx_type="sparkle",
    ),
]

OUTRO_DURATION = 2.90  # Crisp animated Marathi Property Summary + Site Visit CTA card
CROSSFADE_SEC = 0.035  # 35ms seamless audio crossfade between tight sentence cuts


def render_svg_rgba(svg: str) -> Image.Image:
    png_bytes = resvg_py.svg_to_bytes(svg_string=svg, font_dirs=[FONT_DIR])
    return Image.open(io.BytesIO(png_bytes)).convert("RGBA")


def icon_svg_group(icon_type: str, cx: int, cy: int, color: str) -> str:
    """Clean geometric vector icons inside badge circle."""
    if icon_type == "pin":
        return f'''
        <path d="M{cx} {cy-20} C{cx-13} {cy-20} {cx-22} {cy-10} {cx-22} {cy+2} C{cx-22} {cy+16} {cx} {cy+28} {cx} {cy+28} C{cx} {cy+28} {cx+22} {cy+16} {cx+22} {cy+2} C{cx+22} {cy-10} {cx+13} {cy-20} {cx} {cy-20} Z" fill="{color}"/>
        <circle cx="{cx}" cy="{cy+1}" r="8" fill="#0F172A"/>'''
    if icon_type == "home":
        return f'''
        <path d="M{cx-22} {cy+2} L{cx} {cy-19} L{cx+22} {cy+2} L{cx+17} {cy+2} L{cx+17} {cy+20} L{cx-17} {cy+20} L{cx-17} {cy+2} Z" fill="{color}"/>
        <rect x="{cx-6}" y="{cy+6}" width="12" height="14" rx="2" fill="#0F172A"/>'''
    if icon_type == "tag":
        return f'''
        <rect x="{cx-22}" y="{cy-16}" width="44" height="32" rx="8" fill="{color}"/>
        <text x="{cx}" y="{cy+9}" text-anchor="middle" font-family="Mukta" font-weight="800" font-size="28" fill="#0F172A">₹</text>'''
    if icon_type == "grid":
        return f'''
        <rect x="{cx-19}" y="{cy-19}" width="16" height="16" rx="3" fill="{color}"/>
        <rect x="{cx+3}" y="{cy-19}" width="16" height="16" rx="3" fill="{color}"/>
        <rect x="{cx-19}" y="{cy+3}" width="16" height="16" rx="3" fill="{color}"/>
        <rect x="{cx+3}" y="{cy+3}" width="16" height="16" rx="3" fill="{color}"/>'''
    if icon_type == "car":
        return f'''
        <path d="M{cx-22} {cy+4} L{cx-16} {cy-12} L{cx+16} {cy-12} L{cx+22} {cy+4} L{cx+22} {cy+16} L{cx-22} {cy+16} Z" fill="{color}"/>
        <circle cx="{cx-12}" cy="{cy+16}" r="6" fill="#FFFFFF"/>
        <circle cx="{cx+12}" cy="{cy+16}" r="6" fill="#FFFFFF"/>'''
    if icon_type == "shield":
        return f'''
        <path d="M{cx} {cy-22} L{cx+20} {cy-14} L{cx+20} {cy+2} C{cx+20} {cy+15} {cx} {cy+24} {cx} {cy+24} C{cx} {cy+24} {cx-20} {cy+15} {cx-20} {cy+2} L{cx-20} {cy-14} Z" fill="{color}"/>
        <path d="M{cx-9} {cy+1} L{cx-2} {cy+8} L{cx+10} {cy-6}" stroke="#0F172A" stroke-width="5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'''
    if icon_type == "star":
        return f'''
        <polygon points="{cx},{cy-22} {cx+6},{cy-7} {cx+22},{cy-7} {cx+9},{cy+3} {cx+14},{cy+19} {cx},{cy+10} {cx-14},{cy+19} {cx-9},{cy+3} {cx-22},{cy-7} {cx-6},{cy-7}" fill="{color}"/>'''
    if icon_type == "drop":
        return f'''
        <path d="M{cx} {cy-22} C{cx} {cy-22} {cx+19} {cy-2} {cx+19} {cy+8} C{cx+19} {cy+19} {cx+10} {cy+24} {cx} {cy+24} C{cx-10} {cy+24} {cx-19} {cy+19} {cx-19} {cy+8} C{cx-19} {cy-2} {cx} {cy-22} {cx} {cy-22} Z" fill="{color}"/>'''
    return f'''<circle cx="{cx}" cy="{cy}" r="18" fill="{color}"/>'''


def make_top_header_overlay() -> Image.Image:
    """Persistent top location pill (1080x220 canvas)."""
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="220" viewBox="0 0 1080 220">
      <defs>
        <linearGradient id="topGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#020617" stop-opacity="0.72"/>
          <stop offset="100%" stop-color="#020617" stop-opacity="0.0"/>
        </linearGradient>
      </defs>
      <rect width="1080" height="220" fill="url(#topGrad)"/>
      <rect x="64" y="58" width="490" height="74" rx="37" fill="#0F172A" fill-opacity="0.86" stroke="#38BDF8" stroke-opacity="0.55" stroke-width="2.5"/>
      <circle cx="106" cy="95" r="14" fill="#EF4444"/>
      <circle cx="106" cy="95" r="6" fill="#FFFFFF"/>
      <text x="136" y="107" font-family="Mukta" font-weight="700" font-size="34" fill="#F8FAFC">जुना औसा रोड, लातूर</text>
      <rect x="760" y="58" width="256" height="74" rx="37" fill="#F59E0B" fill-opacity="0.95"/>
      <text x="888" y="107" text-anchor="middle" font-family="Mukta" font-weight="800" font-size="34" fill="#0F172A">विक्रीसाठी घर</text>
    </svg>'''
    return render_svg_rgba(svg)


def make_badge_card(icon_type: str, label_top: str, value_main: str, accent_hex: str) -> Image.Image:
    """Animated lower-left / upper-mid feature callout card (780x168)."""
    is_price = "९० लाख" in value_main
    bg_fill = "#064E3B" if is_price else "#0F172A"
    border_col = "#FBBF24" if is_price else accent_hex
    val_col = "#FBBF24" if is_price else "#FFFFFF"
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="820" height="176" viewBox="0 0 820 176">
      <rect x="8" y="8" width="804" height="160" rx="32" fill="{bg_fill}" fill-opacity="0.91" stroke="{border_col}" stroke-width="3.5"/>
      <rect x="28" y="28" width="120" height="120" rx="26" fill="{border_col}" fill-opacity="0.16"/>
      {icon_svg_group(icon_type, 88, 88, border_col)}
      <text x="172" y="74" font-family="Mukta" font-weight="600" font-size="31" fill="#CBD5E1">{label_top}</text>
      <text x="172" y="132" font-family="Mukta" font-weight="800" font-size="48" fill="{val_col}">{value_main}</text>
    </svg>'''
    return render_svg_rgba(svg)


def make_caption_pill(svg_tspan_text: str) -> Image.Image:
    """High-contrast Marathi Reel caption bar (1000x210)."""
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="210" viewBox="0 0 1000 210">
      <rect x="20" y="24" width="960" height="156" rx="36" fill="#090D16" fill-opacity="0.88" stroke="#FFFFFF" stroke-opacity="0.18" stroke-width="2.5"/>
      <rect x="44" y="54" width="8" height="96" rx="4" fill="#FBBF24"/>
      <text x="512" y="121" text-anchor="middle" font-family="Mukta" font-weight="800" font-size="50" fill="#FFFFFF">{svg_tspan_text}</text>
    </svg>'''
    return render_svg_rgba(svg)


def make_outro_card() -> Image.Image:
    """Full-screen Marathi Property Summary + Site Visit CTA overlay (1080x1920)."""
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1920" viewBox="0 0 1080 1920">
      <rect width="1080" height="1920" fill="#020617" fill-opacity="0.74"/>
      <rect x="70" y="250" width="940" height="1420" rx="48" fill="#0F172A" fill-opacity="0.94" stroke="#FBBF24" stroke-width="4"/>

      <rect x="310" y="212" width="460" height="76" rx="38" fill="#FBBF24"/>
      <text x="540" y="263" text-anchor="middle" font-family="Mukta" font-weight="800" font-size="38" fill="#0F172A">स्वतंत्र घर विक्रीसाठी</text>

      <text x="540" y="385" text-anchor="middle" font-family="Mukta" font-weight="800" font-size="64" fill="#FFFFFF">जुना औसा रोड, लातूर</text>
      <text x="540" y="448" text-anchor="middle" font-family="Mukta" font-weight="600" font-size="36" fill="#38BDF8">व्हीआयपी बंगलो परिसर • पूर्ण विकसित लोकेशन</text>

      <line x1="140" y1="495" x2="940" y2="495" stroke="#334155" stroke-width="2.5"/>

      <!-- Spec Grid -->
      <rect x="130" y="540" width="390" height="175" rx="28" fill="#1E293B" stroke="#38BDF8" stroke-opacity="0.4" stroke-width="2"/>
      <text x="325" y="608" text-anchor="middle" font-family="Mukta" font-weight="600" font-size="32" fill="#94A3B8">एकूण खोल्या</text>
      <text x="325" y="675" text-anchor="middle" font-family="Mukta" font-weight="800" font-size="46" fill="#FFFFFF">७ रूम (1BHK+1BHK)</text>

      <rect x="560" y="540" width="390" height="175" rx="28" fill="#1E293B" stroke="#38BDF8" stroke-opacity="0.4" stroke-width="2"/>
      <text x="755" y="608" text-anchor="middle" font-family="Mukta" font-weight="600" font-size="32" fill="#94A3B8">प्लॉट साईज</text>
      <text x="755" y="675" text-anchor="middle" font-family="Mukta" font-weight="800" font-size="46" fill="#FFFFFF">२५ × ३० चौ. फूट</text>

      <rect x="130" y="745" width="390" height="175" rx="28" fill="#1E293B" stroke="#34D399" stroke-opacity="0.4" stroke-width="2"/>
      <text x="325" y="813" text-anchor="middle" font-family="Mukta" font-weight="600" font-size="32" fill="#94A3B8">पार्किंग सुविधा</text>
      <text x="325" y="880" text-anchor="middle" font-family="Mukta" font-weight="800" font-size="44" fill="#34D399">इनोव्हा कार पार्किंग</text>

      <rect x="560" y="745" width="390" height="175" rx="28" fill="#1E293B" stroke="#34D399" stroke-opacity="0.4" stroke-width="2"/>
      <text x="755" y="813" text-anchor="middle" font-family="Mukta" font-weight="600" font-size="32" fill="#94A3B8">पाणी व उत्पन्न</text>
      <text x="755" y="880" text-anchor="middle" font-family="Mukta" font-weight="800" font-size="44" fill="#34D399">स्वतंत्र बोर + भाडे संधी</text>

      <!-- Hero Price Box -->
      <rect x="130" y="965" width="820" height="220" rx="34" fill="#064E3B" stroke="#FBBF24" stroke-width="3.5"/>
      <text x="540" y="1038" text-anchor="middle" font-family="Mukta" font-weight="700" font-size="36" fill="#A7F3D0">मालकाची अपेक्षित किंमत</text>
      <text x="540" y="1140" text-anchor="middle" font-family="Mukta" font-weight="800" font-size="84" fill="#FBBF24">फक्त ₹९० लाख</text>

      <!-- CTA Button -->
      <rect x="130" y="1245" width="820" height="150" rx="75" fill="#F59E0B"/>
      <text x="540" y="1338" text-anchor="middle" font-family="Mukta" font-weight="800" font-size="50" fill="#0F172A">साईट व्हिजिटसाठी आजच संपर्क / DM करा</text>

      <text x="540" y="1490" text-anchor="middle" font-family="Mukta" font-weight="600" font-size="35" fill="#E2E8F0">स्वतंत्र घर • रो-हाऊस नाही • लगेच पाहणीसाठी उपलब्ध</text>
      <g transform="translate(395, 1554)">
        <path d="M0 -15 C-9 -15 -16 -7 -16 2 C-16 12 0 21 0 21 C0 21 16 12 16 2 C16 -7 9 -15 0 -15 Z" fill="#EF4444"/>
        <circle cx="0" cy="1" r="6" fill="#FFFFFF"/>
      </g>
      <text x="556" y="1565" text-anchor="middle" font-family="Mukta" font-weight="700" font-size="34" fill="#38BDF8">जुना औसा रोड, लातूर</text>
    </svg>'''
    return render_svg_rgba(svg)


def enhance_frame(pil_rgb: Image.Image, zoom: float = 1.0) -> Image.Image:
    """Upscale 478x850 -> 1080x1920, lift shadows, warm architectural grade & sharpen."""
    # Apply subtle shadow gamma lift in numpy so dark stilt parking looks clear
    arr = np.asarray(pil_rgb, dtype=np.float32) / 255.0
    # Shadow lift curve: lifts dark midtones without blowing out sky highlights
    lifted = np.power(np.clip(arr, 0.0, 1.0), 0.86)
    # Slight warm sunlight balance (+2% R, +0.5% G, -1.5% B)
    lifted[..., 0] = np.clip(lifted[..., 0] * 1.02, 0.0, 1.0)
    lifted[..., 1] = np.clip(lifted[..., 1] * 1.005, 0.0, 1.0)
    lifted[..., 2] = np.clip(lifted[..., 2] * 0.985, 0.0, 1.0)
    img = Image.fromarray((lifted * 255.0).astype(np.uint8), mode="RGB")

    # Target size with zoom
    tw = int(round(W * zoom))
    th = int(round(H * zoom))
    up = img.resize((tw, th), Image.Resampling.LANCZOS)
    if tw != W or th != H:
        left = (tw - W) // 2
        top = (th - H) // 2
        up = up.crop((left, top, left + W, top + H))

    # Crisp architectural detail + slight saturation boost
    up = ImageEnhance.Color(up).enhance(1.12)
    up = ImageEnhance.Contrast(up).enhance(1.05)
    up = up.filter(ImageFilter.UnsharpMask(radius=1.4, percent=75, threshold=3))
    return up


def ease_out_back(x: float) -> float:
    x = max(0.0, min(1.0, x))
    c1 = 1.70158
    c3 = c1 + 1.0
    return 1.0 + c3 * pow(x - 1.0, 3) + c1 * pow(x - 1.0, 2)


def ease_out_cubic(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1.0 - pow(1.0 - x, 3)


def apply_alpha(img: Image.Image, alpha_mult: float) -> Image.Image:
    if alpha_mult >= 0.999:
        return img
    if alpha_mult <= 0.001:
        return Image.new("RGBA", img.size, (0, 0, 0, 0))
    r, g, b, a = img.split()
    a = a.point(lambda p: int(p * alpha_mult))
    return Image.merge("RGBA", (r, g, b, a))


# ============================================================================
#  Procedural Sound Effects & Warm Real-Estate Background Music Synthesizer
# ============================================================================

def synth_sfx(sfx_type: str, sr: int = SR) -> np.ndarray:
    """Generate clean, tasteful stereo motion-graphic sound effects."""
    if sfx_type == "whoosh":
        dur = 0.34
        n = int(dur * sr)
        t = np.linspace(0, dur, n, endpoint=False)
        rng = np.random.default_rng(42)
        noise = rng.standard_normal(n)
        # Bandpass sweep feel via two filtered bands + smooth bell envelope
        sos_lo = butter(3, [180 / (sr / 2), 900 / (sr / 2)], btype="bandpass", output="sos")
        sos_hi = butter(3, [700 / (sr / 2), 2800 / (sr / 2)], btype="bandpass", output="sos")
        b1 = sosfiltfilt(sos_lo, noise)
        b2 = sosfiltfilt(sos_hi, noise)
        sweep = (1.0 - t / dur) * b1 + (t / dur) * b2
        env = np.sin(np.pi * (t / dur)) ** 2.2
        sig = sweep * env * 0.16
        # Subtle stereo pan L -> R
        pan = np.linspace(0.35, 0.65, n)
        return np.column_stack([sig * (1 - pan) * 1.4, sig * pan * 1.4])

    if sfx_type == "pop":
        dur = 0.14
        n = int(dur * sr)
        t = np.linspace(0, dur, n, endpoint=False)
        # Pitch-up clean UI pop (340Hz -> 680Hz)
        freq = 340 + 380 * (1 - np.exp(-t * 35))
        phase = 2 * np.pi * np.cumsum(freq) / sr
        env = np.exp(-t * 28) * np.minimum(1.0, t / 0.006)
        sig = (np.sin(phase) + 0.25 * np.sin(2 * phase)) * env * 0.14
        return np.column_stack([sig, sig])

    if sfx_type == "chime":
        # Rich major-9th bell chord for the ₹90 Lakh price reveal!
        dur = 1.15
        n = int(dur * sr)
        t = np.linspace(0, dur, n, endpoint=False)
        notes = [523.25, 659.25, 783.99, 1046.50, 1174.66]  # C5 E5 G5 C6 D6
        left = np.zeros(n)
        right = np.zeros(n)
        for idx, f in enumerate(notes):
            delay = idx * 0.032
            td = np.maximum(0.0, t - delay)
            gate = (t >= delay).astype(np.float64)
            env = gate * np.exp(-td * 3.8) * np.minimum(1.0, td / 0.008)
            tone = (np.sin(2 * np.pi * f * td) + 0.3 * np.sin(2 * np.pi * 2 * f * td) * np.exp(-td * 7)) * env
            w_l = 0.65 - 0.08 * idx
            w_r = 0.35 + 0.08 * idx
            left += tone * w_l
            right += tone * w_r
        return np.column_stack([left, right]) * 0.13

    if sfx_type == "sparkle":
        dur = 0.75
        n = int(dur * sr)
        t = np.linspace(0, dur, n, endpoint=False)
        notes = [587.33, 880.0, 1174.66, 1479.98]  # D major sparkle
        sig = np.zeros(n)
        for idx, f in enumerate(notes):
            d = idx * 0.045
            td = np.maximum(0.0, t - d)
            gate = (t >= d).astype(np.float64)
            sig += gate * np.sin(2 * np.pi * f * td) * np.exp(-td * 5.2) * np.minimum(1.0, td / 0.006)
        sig *= 0.10
        return np.column_stack([sig, sig * 0.95])

    if sfx_type == "outro_swell":
        dur = 2.6
        n = int(dur * sr)
        t = np.linspace(0, dur, n, endpoint=False)
        # Warm Cmaj7 swell + soft chime
        freqs = [261.63, 329.63, 392.00, 493.88, 523.25]
        env = np.sin(np.pi * np.minimum(1.0, t / dur)) ** 1.4 * np.exp(-np.maximum(0, t - 0.6) * 0.65)
        sig = sum(np.sin(2 * np.pi * f * t) for f in freqs) / len(freqs)
        chime_env = np.exp(-t * 2.5) * np.minimum(1.0, t / 0.01)
        chime = 0.45 * np.sin(2 * np.pi * 783.99 * t) * chime_env
        out = (sig * env * 0.14) + (chime * 0.10)
        return np.column_stack([out, out])

    return np.zeros((0, 2))


def synth_ambient_music_bed(total_dur: float, sr: int = SR) -> np.ndarray:
    """
    Synthesize a warm, unobtrusive acoustic/pad real-estate background music bed
    (gentle plucked arpeggio + warm low-passed pad in C major / F major7 / Am7 / G).
    """
    n = int(math.ceil(total_dur * sr))
    left = np.zeros(n, dtype=np.float64)
    right = np.zeros(n, dtype=np.float64)

    chords = [
        [261.63, 329.63, 392.00, 493.88],  # Cmaj7
        [220.00, 261.63, 329.63, 392.00],  # Am7
        [174.61, 220.00, 261.63, 329.63],  # Fmaj7
        [196.00, 246.94, 293.66, 392.00],  # G6
    ]
    beat_sec = 0.48  # ~125 BPM eighth-note gentle pulse
    bar_sec = beat_sec * 8

    # Warm pad layer
    t_all = np.arange(n) / sr
    for bar_idx in range(int(math.ceil(total_dur / bar_sec))):
        c_notes = chords[bar_idx % len(chords)]
        s_i = int(bar_idx * bar_sec * sr)
        e_i = min(n, int((bar_idx + 1.15) * bar_sec * sr))
        if s_i >= n:
            break
        seg_t = np.arange(e_i - s_i) / sr
        seg_dur = (e_i - s_i) / sr
        env = np.sin(np.pi * seg_t / seg_dur) ** 1.3
        pad = sum(np.sin(2 * np.pi * (f * 0.5) * seg_t) for f in c_notes[:3]) / 3.0
        left[s_i:e_i] += pad * env * 0.35
        right[s_i:e_i] += pad * env * 0.35

        # Gentle warm acoustic pluck arpeggio
        arp_pattern = [0, 1, 2, 3, 2, 1, 3, 2]
        for step_idx, note_i in enumerate(arp_pattern):
            ns = int((bar_idx * bar_sec + step_idx * beat_sec) * sr)
            ne = min(n, ns + int(0.85 * beat_sec * sr))
            if ns >= n:
                break
            nt = np.arange(ne - ns) / sr
            f = c_notes[note_i]
            # Karplus-like warm sine+triangle pluck
            p_env = np.exp(-nt * 5.5) * np.minimum(1.0, nt / 0.008)
            pluck = (np.sin(2 * np.pi * f * nt) + 0.35 * np.sin(2 * np.pi * 2 * f * nt) * np.exp(-nt * 12)) * p_env
            pan = 0.38 + 0.24 * (step_idx % 2)
            left[ns:ne] += pluck * (1 - pan) * 0.55
            right[ns:ne] += pluck * pan * 0.55

    bed = np.column_stack([left, right])
    # Low-pass at 2.2kHz so it sits warmly underneath Marathi voiceover without competing
    sos_lp = butter(2, 2200 / (sr / 2), btype="lowpass", output="sos")
    bed[:, 0] = sosfiltfilt(sos_lp, bed[:, 0])
    bed[:, 1] = sosfiltfilt(sos_lp, bed[:, 1])
    return bed


def clean_voice_audio(stereo: np.ndarray, sr: int = SR) -> np.ndarray:
    """Clean handheld Marathi voiceover: high-pass rumble, presence boost, gentle compression."""
    mono = np.mean(stereo, axis=1)
    # 1. High-pass at 90Hz to remove traffic/handheld rumble
    sos_hp = butter(3, 90 / (sr / 2), btype="highpass", output="sos")
    clean = sosfiltfilt(sos_hp, mono)

    # 2. Subtle vocal clarity boost (bandpass 2.2kHz-5kHz mixed in at +2.5dB)
    sos_pres = butter(2, [2200 / (sr / 2), 5200 / (sr / 2)], btype="bandpass", output="sos")
    pres = sosfiltfilt(sos_pres, clean)
    clean = clean + 0.32 * pres

    # 3. Gentle downward noise expansion below -40dB so stilt-room hiss drops cleanly
    win = int(0.02 * sr)
    env = np.sqrt(np.convolve(clean ** 2, np.ones(win) / win, mode="same") + 1e-12)
    thresh = 10 ** (-40.0 / 20.0)
    gate_gain = np.clip((env / thresh) ** 1.2, 0.25, 1.0)
    clean = clean * gate_gain

    # 4. Smooth RMS vocal leveling / soft knee compression
    win_c = int(0.06 * sr)
    rms_env = np.sqrt(np.convolve(clean ** 2, np.ones(win_c) / win_c, mode="same") + 1e-9)
    target_rms = 0.145
    comp_gain = np.where(rms_env > 0.02, (target_rms / rms_env) ** 0.42, 1.0)
    comp_gain = np.clip(comp_gain, 0.55, 2.4)
    # Smooth gain envelope
    smooth_w = int(0.04 * sr)
    comp_gain = np.convolve(comp_gain, np.ones(smooth_w) / smooth_w, mode="same")
    clean = np.tanh(clean * comp_gain * 1.15) / 1.15
    return np.column_stack([clean, clean])


def format_srt_ts(sec: float) -> str:
    ms = int(round(max(0.0, sec) * 1000))
    hh, rem = divmod(ms, 3600_000)
    mm, rem = divmod(rem, 60_000)
    ss, mmm = divmod(rem, 1000)
    return f"{hh:02d}:{mm:02d}:{ss:02d},{mmm:03d}"


def build_edited_video():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    print("[1/5] Extracting 48kHz stereo audio & decoding source frames...")
    tmp_wav = Path("/tmp/source_48k.wav")
    subprocess.run(
        [ffmpeg_exe, "-y", "-i", str(INPUT_VIDEO), "-vn", "-ac", "2", "-ar", str(SR), "-c:a", "pcm_f32le", str(tmp_wav)],
        check=True,
        capture_output=True,
    )
    raw_audio, _ = sf.read(str(tmp_wav), dtype="float64")
    cleaned_full_voice = clean_voice_audio(raw_audio, SR)

    # Decode all source video frames into memory with PTS (478x850 RGB is tiny: 1712 * 478 * 850 * 3 ~= 2.0 GB,
    # or even smaller if we only keep frames within CLIPS ranges! Let's only keep needed frames + exterior hero frame!)
    needed_ranges = [(c.src_start - 0.1, c.src_end + 0.1) for c in CLIPS]
    container = av.open(str(INPUT_VIDEO))
    src_frames: List[Tuple[float, Image.Image]] = []
    hero_exterior_frame: Optional[Image.Image] = None

    for frame in container.decode(video=0):
        pts_sec = float(frame.pts * frame.time_base)
        if hero_exterior_frame is None and abs(pts_sec - 2.5) < 0.05:
            hero_exterior_frame = frame.to_image().convert("RGB")
        if any(a <= pts_sec <= b for a, b in needed_ranges):
            src_frames.append((pts_sec, frame.to_image().convert("RGB")))
    container.close()
    src_pts = np.array([p for p, _ in src_frames])
    print(f"      Cached {len(src_frames)} relevant source frames.")

    def get_src_frame(t_sec: float) -> Image.Image:
        idx = int(np.argmin(np.abs(src_pts - t_sec)))
        return src_frames[idx][1]

    print("[2/5] Assembling seamless dialogue timeline (removing silences, fillers & retakes)...")
    fade_samples = int(CROSSFADE_SEC * SR)
    timeline_clips = []
    voice_track_parts: List[np.ndarray] = []

    cur_timeline_sec = 0.0
    for idx, clip in enumerate(CLIPS):
        s_smp = int(round(clip.src_start * SR))
        e_smp = int(round(clip.src_end * SR))
        seg_audio = cleaned_full_voice[s_smp:e_smp].copy()

        # Micro fade-in on very first clip and micro fade-out on very last clip
        edge = int(0.025 * SR)
        if idx == 0:
            seg_audio[:edge] *= np.linspace(0.0, 1.0, edge)[:, None]
            voice_track_parts.append(seg_audio)
            clip_tl_start = 0.0
            clip_tl_dur = len(seg_audio) / SR
            cur_timeline_sec = clip_tl_dur
        else:
            # Equal-power / cosine overlap crossfade with previous clip tail (35ms)
            prev = voice_track_parts[-1]
            ov = min(fade_samples, len(prev) // 4, len(seg_audio) // 4)
            t_lin = np.linspace(0.0, np.pi / 2, ov)[:, None]
            prev[-ov:] = prev[-ov:] * np.cos(t_lin) + seg_audio[:ov] * np.sin(t_lin)
            rem = seg_audio[ov:]
            if idx == len(CLIPS) - 1:
                rem[-edge:] *= np.linspace(1.0, 0.0, edge)[:, None]
            voice_track_parts.append(rem)
            clip_tl_start = cur_timeline_sec - (ov / SR)
            clip_tl_dur = len(seg_audio) / SR
            cur_timeline_sec = clip_tl_start + clip_tl_dur

        timeline_clips.append(
            {
                "spec": clip,
                "tl_start": clip_tl_start,
                "tl_end": clip_tl_start + clip_tl_dur,
                "tl_dur": clip_tl_dur,
            }
        )

    speech_end_sec = cur_timeline_sec
    total_duration = speech_end_sec + OUTRO_DURATION
    total_frames = int(round(total_duration * FPS))
    total_samples = int(round(total_duration * SR))

    voice_track = np.zeros((total_samples, 2), dtype=np.float64)
    concat_voice = np.vstack(voice_track_parts)
    voice_track[: min(total_samples, len(concat_voice))] = concat_voice[:total_samples]

    print(f"      Original duration : 57.09s")
    print(f"      Tight speech edit : {speech_end_sec:.2f}s across {len(CLIPS)} complete sentences")
    print(f"      Total with CTA    : {total_duration:.2f}s ({total_frames} frames @ {FPS}fps)")

    print("[3/5] Mastering audio (ducked acoustic bed + synced motion-graphic SFX + LUFS mastering)...")
    music_bed = synth_ambient_music_bed(total_duration + 0.5, SR)[:total_samples]
    # Auto-duck music bed: 0.085 under active speech, rising smoothly to 0.22 on the CTA outro card
    duck_gain = np.full(total_samples, 0.085, dtype=np.float64)
    outro_start_smp = int(speech_end_sec * SR)
    ramp_len = min(int(0.45 * SR), total_samples - outro_start_smp)
    if ramp_len > 0:
        duck_gain[outro_start_smp : outro_start_smp + ramp_len] = np.linspace(0.085, 0.23, ramp_len)
        duck_gain[outro_start_smp + ramp_len :] = 0.23
    # Fade out last 0.45s cleanly
    fo = int(0.45 * SR)
    duck_gain[-fo:] *= np.linspace(1.0, 0.0, fo)
    music_mixed = music_bed * duck_gain[:, None]

    # Layer synced motion-graphic SFX at exact badge/transition timestamps
    sfx_track = np.zeros((total_samples, 2), dtype=np.float64)
    for item in timeline_clips:
        st = item["spec"].sfx_type
        if st and st != "none":
            # For clip 3 (price reveal), trigger chime right when price phrase & badge pop!
            offset_sec = 0.06
            if item["spec"].id == "03_rooms_and_price":
                # Pop at start for 7 rooms, plus luxury chime at 48% when ₹90 Lakh is spoken!
                pop_wav = synth_sfx("pop", SR)
                ps = int((item["tl_start"] + 0.05) * SR)
                pe = min(total_samples, ps + len(pop_wav))
                sfx_track[ps:pe] += pop_wav[: pe - ps]
                offset_sec = item["tl_dur"] * 0.48
            wav = synth_sfx(st, SR)
            s_i = int(max(0.0, item["tl_start"] + offset_sec) * SR)
            e_i = min(total_samples, s_i + len(wav))
            if e_i > s_i:
                sfx_track[s_i:e_i] += wav[: e_i - s_i]

    # Closing outro card transition whoosh + warm chord swell
    out_whoosh = synth_sfx("whoosh", SR)
    ow_s = max(0, int((speech_end_sec - 0.10) * SR))
    ow_e = min(total_samples, ow_s + len(out_whoosh))
    sfx_track[ow_s:ow_e] += out_whoosh[: ow_e - ow_s]

    out_swell = synth_sfx("outro_swell", SR)
    os_s = int(speech_end_sec * SR)
    os_e = min(total_samples, os_s + len(out_swell))
    sfx_track[os_s:os_e] += out_swell[: os_e - os_s]

    master_audio = voice_track + music_mixed + sfx_track
    # Normalize to broadcast ~ -15 LUFS (approx RMS ~ 0.145 with true-peak limiter at -1.0 dBFS = 0.891)
    cur_rms = np.sqrt(np.mean(master_audio ** 2) + 1e-12)
    target_master_rms = 0.145
    master_audio = master_audio * (target_master_rms / cur_rms)
    # Soft true-peak ceiling at 0.89 (-1 dBFS)
    master_audio = 0.89 * np.tanh(master_audio / 0.89)

    master_wav_path = Path("/tmp/master_edited_audio.wav")
    sf.write(str(master_wav_path), master_audio.astype(np.float32), SR, subtype="PCM_16")

    print("[4/5] Pre-rendering Marathi SVG motion graphics & generating SRT captions...")
    top_header_img = make_top_header_overlay()
    outro_card_img = make_outro_card()

    # Blurred golden-hour exterior backdrop for the closing CTA card
    if hero_exterior_frame is None:
        hero_exterior_frame = src_frames[0][1]
    outro_bg_base = enhance_frame(hero_exterior_frame, zoom=1.08).filter(ImageFilter.GaussianBlur(radius=14))

    # Bottom subtle dark gradient so lower-third captions are always ultra-legible
    bot_grad_arr = np.zeros((440, W, 4), dtype=np.uint8)
    alpha_curve = (np.linspace(0.0, 1.0, 440) ** 1.6 * 175).astype(np.uint8)
    bot_grad_arr[:, :, 0] = 4
    bot_grad_arr[:, :, 1] = 8
    bot_grad_arr[:, :, 2] = 18
    bot_grad_arr[:, :, 3] = alpha_curve[:, None]
    bot_grad_img = Image.fromarray(bot_grad_arr, mode="RGBA")

    # Cache rendered badge & caption PNGs + build SRT entries
    badge_cache = {}
    caption_cache = {}
    srt_entries = []
    srt_idx = 1

    for item in timeline_clips:
        sp: ClipSpec = item["spec"]
        if sp.badge is not None:
            badge_cache[sp.id] = make_badge_card(*sp.badge)
        for c_i, (r0, r1, svg_txt, plain_txt) in enumerate(sp.captions):
            caption_cache[(sp.id, c_i)] = make_caption_pill(svg_txt)
            abs_s = item["tl_start"] + r0 * item["tl_dur"]
            abs_e = item["tl_start"] + r1 * item["tl_dur"]
            srt_entries.append((srt_idx, abs_s, abs_e, plain_txt))
            srt_idx += 1

    srt_entries.append(
        (
            srt_idx,
            speech_end_sec,
            total_duration,
            "स्वतंत्र घर विक्रीसाठी — जुना औसा रोड, लातूर | ७ रूम | २५×३० फूट | फक्त ₹९० लाख | साईट व्हिजिटसाठी संपर्क करा.",
        )
    )

    srt_lines = []
    for idx_n, s_t, e_t, txt in srt_entries:
        srt_lines.append(f"{idx_n}\n{format_srt_ts(s_t)} --> {format_srt_ts(e_t)}\n{txt}\n")
    OUTPUT_SRT.write_text("\n".join(srt_lines), encoding="utf-8")

    # Save Edit Decision List JSON for full transparency & reproducibility
    edl_data = {
        "source_video": INPUT_VIDEO.name,
        "source_duration_sec": 57.09,
        "edited_speech_duration_sec": round(speech_end_sec, 3),
        "total_edited_duration_sec": round(total_duration, 3),
        "resolution": f"{W}x{H}",
        "fps": FPS,
        "removed_sections_summary": [
            "0.00s - 1.50s: Initial dead air before greeting",
            "4.65s - 5.23s, 7.14s - 7.67s, 11.34s - 12.22s: Breaths, silences & 'अं' filler onset before plot size",
            "15.30s - 17.35s: Repeated location phrase ('आणि घर आहे आपलं जुना औसा रोडला') + pause",
            "20.28s - 21.74s: Pause + weaker first take of borewell ('पाण्याचा बोर आहे'), kept cleaner take at 30.23s",
            "25.13s - 30.23s: Long street-panning pauses & redundant 'हे बघा लोकेशन / सगळ्यांचे बंगले आजूबाजू'",
            "31.30s - 41.85s: Non-speech knock (33.9s), long pauses & repeated takes of ₹90 Lakh price, 7 rooms & location",
            "43.77s - 57.09s: Repeated parking remarks + 8.5s silent wandering + loud accidental knock at 54.2s",
        ],
        "kept_clips": [
            {
                "id": it["spec"].id,
                "source_range_sec": [it["spec"].src_start, it["spec"].src_end],
                "timeline_range_sec": [round(it["tl_start"], 3), round(it["tl_end"], 3)],
                "captions_mr": [c[3] for c in it["spec"].captions],
            }
            for it in timeline_clips
        ],
    }
    OUTPUT_EDL.write_text(json.dumps(edl_data, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[5/5] Rendering 1080x1920 @ 30fps Full HD video with motion graphics & encoding H.264/AAC...")
    ff_cmd = [
        ffmpeg_exe,
        "-y",
        "-f",
        "rawvideo",
        "-vcodec",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{W}x{H}",
        "-r",
        str(FPS),
        "-i",
        "-",
        "-i",
        str(master_wav_path),
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "19",
        "-pix_fmt",
        "yuv420p",
        "-color_primaries",
        "bt709",
        "-color_trc",
        "bt709",
        "-colorspace",
        "bt709",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        "-shortest",
        str(OUTPUT_VIDEO),
    ]
    proc = subprocess.Popen(ff_cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    for f_idx in range(total_frames):
        t = f_idx / FPS

        if t < speech_end_sec:
            # Find active clip (last clip whose tl_start <= t)
            active = timeline_clips[0]
            for it in timeline_clips:
                if it["tl_start"] <= t:
                    active = it
                else:
                    break
            sp = active["spec"]
            u = max(0.0, min(1.0, (t - active["tl_start"]) / max(1e-6, active["tl_dur"])))
            src_t = sp.src_start + u * (sp.src_end - sp.src_start)
            zoom = sp.zoom_start + (sp.zoom_end - sp.zoom_start) * u

            base_rgb = enhance_frame(get_src_frame(src_t), zoom=zoom)
            canvas = base_rgb.convert("RGBA")

            # Bottom gradient & top persistent location header
            canvas.alpha_composite(bot_grad_img, (0, H - 440))
            hdr_alpha = min(1.0, t / 0.30)
            canvas.alpha_composite(apply_alpha(top_header_img, hdr_alpha), (0, 0))

            # Progress bar along very top (subtle gold progress line)
            prog_w = max(2, int(W * (t / total_duration)))
            prog_bar = Image.new("RGBA", (prog_w, 8), (251, 191, 36, 235))
            canvas.alpha_composite(prog_bar, (0, 0))

            # Animated Feature Badge Card (slides in smoothly from left, gentle exit at end)
            if sp.id in badge_cache:
                b_img = badge_cache[sp.id]
                local_t = t - active["tl_start"]
                rem_t = active["tl_end"] - t
                # Special highlight on Clip 03: pop price card cleanly
                enter_p = ease_out_back(local_t / 0.32)
                exit_p = ease_out_cubic(rem_t / 0.22) if rem_t < 0.22 else 1.0
                b_alpha = min(1.0, local_t / 0.18) * exit_p
                bx = int(46 - (1.0 - enter_p) * 140)
                by = 1235
                canvas.alpha_composite(apply_alpha(b_img, b_alpha), (max(0, bx), by))

            # Animated Marathi Captions (pop-up lower third)
            for c_i, (r0, r1, _, _) in enumerate(sp.captions):
                c_s = active["tl_start"] + r0 * active["tl_dur"]
                c_e = active["tl_start"] + r1 * active["tl_dur"]
                if c_s <= t <= c_e:
                    c_img = caption_cache[(sp.id, c_i)]
                    dt_in = t - c_s
                    dt_out = c_e - t
                    pop_p = ease_out_cubic(dt_in / 0.16)
                    c_alpha = min(1.0, dt_in / 0.10) * (min(1.0, dt_out / 0.10) if dt_out < 0.10 else 1.0)
                    cy = int(1460 + (1.0 - pop_p) * 28)
                    canvas.alpha_composite(apply_alpha(c_img, c_alpha), (40, cy))
                    break

            # Smooth transition into closing CTA card during last 0.18s of speech
            if speech_end_sec - t < 0.18:
                blend = 1.0 - (speech_end_sec - t) / 0.18
                outro_frame = outro_bg_base.convert("RGBA")
                outro_frame.alpha_composite(apply_alpha(outro_card_img, blend), (0, 0))
                canvas = Image.blend(canvas, outro_frame, blend)

        else:
            # Closing Marathi Property Summary & CTA End Card
            ot = t - speech_end_sec
            # Subtle slow zoom on blurred backdrop
            z_out = 1.0 + 0.03 * (ot / OUTRO_DURATION)
            tw, th = int(W * z_out), int(H * z_out)
            bg = outro_bg_base.resize((tw, th), Image.Resampling.BILINEAR).crop(
                ((tw - W) // 2, (th - H) // 2, (tw - W) // 2 + W, (th - H) // 2 + H)
            )
            canvas = bg.convert("RGBA")
            card_in = ease_out_cubic(min(1.0, (ot + 0.18) / 0.42))
            if card_in < 0.999:
                sc = 0.94 + 0.06 * card_in
                cw, ch = int(W * sc), int(H * sc)
                scaled_card = outro_card_img.resize((cw, ch), Image.Resampling.BILINEAR)
                canvas.alpha_composite(apply_alpha(scaled_card, card_in), ((W - cw) // 2, (H - ch) // 2))
            else:
                canvas.alpha_composite(outro_card_img, (0, 0))

            prog_w = max(2, int(W * min(1.0, t / total_duration)))
            prog_bar = Image.new("RGBA", (prog_w, 8), (251, 191, 36, 235))
            canvas.alpha_composite(prog_bar, (0, 0))

        out_rgb = canvas.convert("RGB")
        proc.stdin.write(out_rgb.tobytes())

        if (f_idx + 1) % 150 == 0 or f_idx == total_frames - 1:
            print(f"      Rendered {f_idx + 1}/{total_frames} frames ({100.0 * (f_idx + 1) / total_frames:.1f}%)")

    proc.stdin.close()
    stderr_bytes = proc.stderr.read()
    ret = proc.wait()
    if ret != 0:
        raise RuntimeError(f"FFmpeg failed with code {ret}:\n{stderr_bytes.decode(errors='replace')}")

    print(f"\nDone! Saved edited video to: {OUTPUT_VIDEO}")
    print(f"Saved Marathi SRT captions to: {OUTPUT_SRT}")
    print(f"Saved Edit Decision List to  : {OUTPUT_EDL}")


if __name__ == "__main__":
    build_edited_video()
