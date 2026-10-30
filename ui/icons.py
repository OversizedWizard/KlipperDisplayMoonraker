"""HD full-colour vector icons.

Icons are embedded SVG (gradients only - QtSvg does not support filters), rendered
on demand at the exact pixel size needed, so they stay crisp at any resolution.
"""

from functools import lru_cache

from .qt import QtCore, QtGui, QtSvg, Qt

_SVG = {
    # Official Klipper mark (from Klipper3d/klipper docs/img/klipper.svg, wordmark
    # removed). Slate (#3c4b5a) is lightened so it reads on the dark theme.
    "logo": """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="10 -116 740 740">
  <defs>
    <linearGradient id="slate" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#E2E8F0"/><stop offset="1" stop-color="#94A3B8"/>
    </linearGradient>
    <linearGradient id="red" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#F0525A"/><stop offset="1" stop-color="#B12F35"/>
    </linearGradient>
  </defs>
  <path fill="url(#slate)"
        d="m 30,34 v 140 l 260,255 115,-5 h 80 L 730,174 V 34 H 720 L 385,374 40,34 Z"/>
  <path fill="url(#red)"
        d="M 259,424 H 360 V 359 L 30,34 H 90 L 385,324 670,34 h 60 L 410,359 v 84.99783 C 410,449 405,454 400,454 H 259 c -12,0 -14,-10 -14,-15 0,-5 2,-15 14,-15 z"/>
</svg>""",

    # Hotend: heatsink fins, heater block, brass nozzle
    "nozzle": """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="fin" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#F1F5F9"/><stop offset="1" stop-color="#8A9AB2"/>
    </linearGradient>
    <linearGradient id="blk" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#FFA44D"/><stop offset="1" stop-color="#E8590C"/>
    </linearGradient>
    <linearGradient id="brass" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#FFE59A"/><stop offset="1" stop-color="#C98A12"/>
    </linearGradient>
  </defs>
  <rect x="29" y="4" width="6" height="24" fill="#64748B"/>
  <rect x="17" y="4" width="30" height="4" rx="2" fill="url(#fin)"/>
  <rect x="17" y="10.5" width="30" height="4" rx="2" fill="url(#fin)"/>
  <rect x="17" y="17" width="30" height="4" rx="2" fill="url(#fin)"/>
  <rect x="13" y="26" width="38" height="16" rx="3" fill="url(#blk)"/>
  <circle cx="21" cy="34" r="3.6" fill="#7C2D12"/>
  <rect x="13" y="26" width="38" height="4" rx="2" fill="#FFFFFF" fill-opacity="0.22"/>
  <path d="M23 42 H41 V46 L35.5 54 H28.5 L23 46 Z" fill="url(#brass)"/>
  <rect x="30" y="54" width="4" height="3" fill="#B7791F"/>
  <circle cx="32" cy="60.5" r="2.5" fill="#FF6A00"/>
</svg>""",

    # Heated bed: build plate with rising heat waves
    "bed": """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="heat" gradientUnits="userSpaceOnUse" x1="0" y1="30" x2="0" y2="4">
      <stop offset="0" stop-color="#FF3D00"/><stop offset="1" stop-color="#FFC15C"/>
    </linearGradient>
    <linearGradient id="top" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#7DF3FF"/><stop offset="1" stop-color="#3B82F6"/>
    </linearGradient>
  </defs>
  <g fill="none" stroke="url(#heat)" stroke-width="3.5" stroke-linecap="round">
    <path d="M20 29 C16 25 24 21 20 16 C16 12 24 8 20 4"/>
    <path d="M32 29 C28 25 36 21 32 16 C28 12 36 8 32 4"/>
    <path d="M44 29 C40 25 48 21 44 16 C40 12 48 8 44 4"/>
  </g>
  <path d="M4 44 L16 34 H60 L48 44 Z" fill="url(#top)"/>
  <path d="M4 44 H48 V51 H4 Z" fill="#1E40AF"/>
  <path d="M48 44 L60 34 V41 L48 51 Z" fill="#172E7A"/>
  <path d="M12 41 H52 M18 37 H56" stroke="#FFFFFF" stroke-opacity="0.3" stroke-width="1"/>
</svg>""",

    "home": """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="roof" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#5EF2FF"/><stop offset="1" stop-color="#2F6BFF"/>
    </linearGradient>
    <linearGradient id="wall" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#EEF4FF"/><stop offset="1" stop-color="#A3B8DA"/>
    </linearGradient>
    <linearGradient id="door" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#FFC15C"/><stop offset="1" stop-color="#FF6A00"/>
    </linearGradient>
  </defs>
  <rect x="43" y="12" width="7" height="14" rx="1.5" fill="url(#roof)"/>
  <path d="M14 30 L32 15 L50 30 V52 A3 3 0 0 1 47 55 H17 A3 3 0 0 1 14 52 Z" fill="url(#wall)"/>
  <path d="M6 32 L32 9 L58 32" fill="none" stroke="url(#roof)" stroke-width="7"
        stroke-linecap="round" stroke-linejoin="round"/>
  <rect x="26" y="36" width="12" height="19" rx="2.5" fill="url(#door)"/>
  <circle cx="35" cy="46" r="1.3" fill="#7A2E00"/>
</svg>""",

    "spool": """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <radialGradient id="flange" cx="0.5" cy="0.5" r="0.5">
      <stop offset="0.75" stop-color="#3A4458"/><stop offset="1" stop-color="#1B2130"/>
    </radialGradient>
    <linearGradient id="fil" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#FF6FB0"/><stop offset="1" stop-color="#A21CE0"/>
    </linearGradient>
    <linearGradient id="hub" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#F1F5FB"/><stop offset="1" stop-color="#8C9AB3"/>
    </linearGradient>
  </defs>
  <path d="M50 46 Q57 54 62 51" fill="none" stroke="#C026D3" stroke-width="3" stroke-linecap="round"/>
  <circle cx="30" cy="30" r="27" fill="url(#flange)"/>
  <circle cx="30" cy="30" r="22" fill="url(#fil)"/>
  <circle cx="30" cy="30" r="18.5" fill="none" stroke="#FFFFFF" stroke-opacity="0.18" stroke-width="1.4"/>
  <circle cx="30" cy="30" r="15" fill="none" stroke="#FFFFFF" stroke-opacity="0.14" stroke-width="1.4"/>
  <circle cx="30" cy="30" r="11" fill="url(#hub)"/>
  <circle cx="30" cy="30" r="4.5" fill="#1B2130"/>
  <circle cx="30" cy="22.5" r="1.8" fill="#5B6780"/>
  <circle cx="23.5" cy="34" r="1.8" fill="#5B6780"/>
  <circle cx="36.5" cy="34" r="1.8" fill="#5B6780"/>
  <path d="M12 21 A20 20 0 0 1 25 9.5" fill="none" stroke="#FFFFFF" stroke-opacity="0.4"
        stroke-width="3" stroke-linecap="round"/>
</svg>""",

    "settings": """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="g" gradientUnits="userSpaceOnUse" x1="6" y1="6" x2="58" y2="58">
      <stop offset="0" stop-color="#D8B4FE"/><stop offset="1" stop-color="#6D28D9"/>
    </linearGradient>
    <linearGradient id="c" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#FFFFFF"/><stop offset="1" stop-color="#C4B5FD"/>
    </linearGradient>
  </defs>
  <g fill="url(#g)">
    <rect x="26.5" y="4" width="11" height="14" rx="3"/>
    <rect x="26.5" y="4" width="11" height="14" rx="3" transform="rotate(45 32 32)"/>
    <rect x="26.5" y="4" width="11" height="14" rx="3" transform="rotate(90 32 32)"/>
    <rect x="26.5" y="4" width="11" height="14" rx="3" transform="rotate(135 32 32)"/>
    <rect x="26.5" y="4" width="11" height="14" rx="3" transform="rotate(180 32 32)"/>
    <rect x="26.5" y="4" width="11" height="14" rx="3" transform="rotate(225 32 32)"/>
    <rect x="26.5" y="4" width="11" height="14" rx="3" transform="rotate(270 32 32)"/>
    <rect x="26.5" y="4" width="11" height="14" rx="3" transform="rotate(315 32 32)"/>
    <circle cx="32" cy="32" r="20"/>
  </g>
  <circle cx="32" cy="32" r="19" fill="none" stroke="#FFFFFF" stroke-opacity="0.18" stroke-width="2"/>
  <circle cx="32" cy="32" r="9" fill="url(#c)"/>
  <circle cx="32" cy="32" r="4" fill="#5B21B6"/>
</svg>""",

    "power": """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="p" gradientUnits="userSpaceOnUse" x1="10" y1="8" x2="54" y2="56">
      <stop offset="0" stop-color="#FFB86B"/><stop offset="0.5" stop-color="#FF5A5F"/>
      <stop offset="1" stop-color="#E11D48"/>
    </linearGradient>
    <radialGradient id="bg" cx="0.5" cy="0.5" r="0.5">
      <stop offset="0" stop-color="#E11D48" stop-opacity="0.28"/>
      <stop offset="1" stop-color="#E11D48" stop-opacity="0.05"/>
    </radialGradient>
  </defs>
  <circle cx="32" cy="32" r="29" fill="url(#bg)"/>
  <path d="M20.5 19 A18 18 0 1 0 43.5 19" fill="none" stroke="url(#p)" stroke-width="6"
        stroke-linecap="round"/>
  <path d="M32 10 V31" fill="none" stroke="url(#p)" stroke-width="6" stroke-linecap="round"/>
</svg>""",

    "estop": """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="estop_grad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#EF4444"/>
      <stop offset="1" stop-color="#B91C1C"/>
    </linearGradient>
  </defs>
  <polygon points="19,5 45,5 59,19 59,45 45,59 19,59 5,45 5,19" fill="url(#estop_grad)" stroke="#FFFFFF" stroke-opacity="0.4" stroke-width="2.5"/>
  <rect x="22" y="22" width="20" height="20" rx="3.5" fill="#FFFFFF"/>
</svg>""",
}


# ---------------------------------------------------------------- calibration
_SVG.update({
    # Crosshair - sidebar "Calibrate" + Probe Accuracy
    "calibrate": """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="r" gradientUnits="userSpaceOnUse" x1="4" y1="4" x2="60" y2="60">
      <stop offset="0" stop-color="#6EE7B7"/><stop offset="1" stop-color="#0EA5E9"/>
    </linearGradient>
  </defs>
  <circle cx="32" cy="32" r="21" fill="#0EA5E9" fill-opacity="0.12" stroke="url(#r)" stroke-width="6"/>
  <path d="M32 4 V15 M32 49 V60 M4 32 H15 M49 32 H60" stroke="url(#r)" stroke-width="6" stroke-linecap="round"/>
  <circle cx="32" cy="32" r="7" fill="#F43F5E"/>
  <circle cx="30" cy="30" r="2.2" fill="#FFFFFF" fill-opacity="0.7"/>
</svg>""",

    "probe": """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="b" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#7CB8FF"/><stop offset="1" stop-color="#1D4ED8"/>
    </linearGradient>
    <linearGradient id="p" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#64748B"/><stop offset="1" stop-color="#1E293B"/>
    </linearGradient>
  </defs>
  <path d="M32 6 C32 2 44 2 46 6" fill="none" stroke="#94A3B8" stroke-width="2.5" stroke-linecap="round"/>
  <rect x="21" y="6" width="22" height="28" rx="5" fill="url(#b)"/>
  <rect x="21" y="6" width="22" height="7" rx="3.5" fill="#FFFFFF" fill-opacity="0.25"/>
  <circle cx="32" cy="22" r="3.2" fill="#F87171"/>
  <rect x="30" y="34" width="4" height="13" fill="#CBD5E1"/>
  <circle cx="32" cy="48.5" r="2.6" fill="#F1F5F9"/>
  <rect x="6" y="52" width="52" height="7" rx="2.5" fill="url(#p)"/>
</svg>""",

    "zoffset": """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="o" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#FFA44D"/><stop offset="1" stop-color="#E8590C"/>
    </linearGradient>
    <linearGradient id="bed" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#22D3EE"/><stop offset="1" stop-color="#3B82F6"/>
    </linearGradient>
  </defs>
  <rect x="10" y="6" width="26" height="14" rx="3" fill="url(#o)"/>
  <path d="M15 20 H31 L26.5 30 H19.5 Z" fill="#F5C542"/>
  <path d="M8 38 H38" stroke="#FFFFFF" stroke-opacity="0.55" stroke-width="2" stroke-dasharray="3 3"/>
  <g fill="none" stroke="#34D399" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
    <path d="M50 14 V42"/><path d="M43 21 L50 13 L57 21"/><path d="M43 35 L50 43 L57 35"/>
  </g>
  <rect x="4" y="48" width="56" height="8" rx="2.5" fill="url(#bed)"/>
</svg>""",

    "mesh": """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="h" gradientUnits="userSpaceOnUse" x1="4" y1="0" x2="60" y2="0">
      <stop offset="0" stop-color="#22D3EE"/><stop offset="0.5" stop-color="#A3E635"/>
      <stop offset="1" stop-color="#F97316"/>
    </linearGradient>
  </defs>
  <path d="M4 46 C18 38 34 54 56 44 L60 22 C44 30 30 14 14 22 Z" fill="url(#h)" fill-opacity="0.22"/>
  <g fill="none" stroke="url(#h)" stroke-width="2.6" stroke-linecap="round">
    <path d="M4 46 C18 38 34 54 56 44"/>
    <path d="M7.5 38.5 C21 31 36 45 57.5 36.5"/>
    <path d="M11 30 C24 23 38 37 59 29"/>
    <path d="M14 22 C30 14 44 30 60 22"/>
    <path d="M4 46 L14 22"/><path d="M21 44 L28 19"/><path d="M38 47 L43 24"/><path d="M56 44 L60 22"/>
  </g>
</svg>""",

    "screws": """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <radialGradient id="s" cx="0.4" cy="0.35" r="0.7">
      <stop offset="0" stop-color="#F8FAFC"/><stop offset="1" stop-color="#64748B"/>
    </radialGradient>
  </defs>
  <circle cx="28" cy="36" r="20" fill="url(#s)"/>
  <circle cx="28" cy="36" r="20" fill="none" stroke="#334155" stroke-opacity="0.5" stroke-width="1.5"/>
  <path d="M28 25 V47 M17 36 H39" stroke="#334155" stroke-width="5" stroke-linecap="round"/>
  <g fill="none" stroke="#FBBF24" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
    <path d="M40 8 A26 26 0 0 1 56 24"/><path d="M49 25 L57 26 L58 17"/>
  </g>
</svg>""",

    "gantry": """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#6EE7B7"/><stop offset="1" stop-color="#059669"/>
    </linearGradient>
  </defs>
  <rect x="6" y="6" width="6" height="52" rx="2" fill="#64748B"/>
  <rect x="52" y="6" width="6" height="52" rx="2" fill="#64748B"/>
  <path d="M4 31 H60" stroke="#FFFFFF" stroke-opacity="0.45" stroke-width="1.5" stroke-dasharray="3 3"/>
  <rect x="3" y="25" width="58" height="11" rx="3" fill="url(#g)" transform="rotate(-9 32 30.5)"/>
  <g fill="none" stroke="#FBBF24" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round">
    <path d="M22 54 V44"/><path d="M18 48 L22 44 L26 48"/>
    <path d="M42 10 V20"/><path d="M38 16 L42 20 L46 16"/>
  </g>
</svg>""",

    "shaper": """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="w" gradientUnits="userSpaceOnUse" x1="4" y1="0" x2="60" y2="0">
      <stop offset="0" stop-color="#F472B6"/><stop offset="1" stop-color="#8B5CF6"/>
    </linearGradient>
  </defs>
  <path d="M4 32 H60" stroke="#FFFFFF" stroke-opacity="0.15" stroke-width="1.5"/>
  <path d="M4 32 C9 6 15 6 19 32 S28 54 32 32 S40 18 44 32 S50 40 53 32 S57 29 60 32"
        fill="none" stroke="url(#w)" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>
</svg>""",

    "endstop": """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="e" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#F87171"/><stop offset="1" stop-color="#B91C1C"/>
    </linearGradient>
  </defs>
  <path d="M14 28 L50 14" stroke="#E2E8F0" stroke-width="4" stroke-linecap="round"/>
  <circle cx="51" cy="14" r="4.5" fill="#CBD5E1"/>
  <rect x="10" y="28" width="44" height="20" rx="3" fill="url(#e)"/>
  <rect x="10" y="28" width="44" height="5" rx="2.5" fill="#FFFFFF" fill-opacity="0.25"/>
  <circle cx="18" cy="40" r="2.5" fill="#7F1D1D"/><circle cx="46" cy="40" r="2.5" fill="#7F1D1D"/>
  <rect x="16" y="48" width="4" height="9" fill="#FBBF24"/>
  <rect x="30" y="48" width="4" height="9" fill="#FBBF24"/>
  <rect x="44" y="48" width="4" height="9" fill="#FBBF24"/>
</svg>""",

    "tower": """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <rect x="12" y="47" width="40" height="10" rx="2.5" fill="#22D3EE"/>
  <rect x="15" y="35" width="34" height="10" rx="2.5" fill="#A3E635"/>
  <rect x="18" y="23" width="28" height="10" rx="2.5" fill="#FBBF24"/>
  <rect x="21" y="11" width="22" height="10" rx="2.5" fill="#F97316"/>
  <path d="M12 52 H52 M15 40 H49 M18 28 H46 M21 16 H43" stroke="#FFFFFF" stroke-opacity="0.25" stroke-width="1"/>
  <path d="M58 54 V12" stroke="#94A3B8" stroke-width="2" stroke-linecap="round" stroke-dasharray="2 3"/>
</svg>""",

    "delta": """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <path d="M32 9 L56 51 H8 Z" fill="#8B5CF6" fill-opacity="0.15" stroke="#A78BFA" stroke-width="3.5"
        stroke-linejoin="round"/>
  <path d="M32 37 L32 9 M32 37 L56 51 M32 37 L8 51" stroke="#E2E8F0" stroke-opacity="0.6" stroke-width="2"/>
  <circle cx="32" cy="9" r="6" fill="#F472B6"/>
  <circle cx="56" cy="51" r="6" fill="#22D3EE"/>
  <circle cx="8" cy="51" r="6" fill="#A3E635"/>
  <circle cx="32" cy="37" r="5" fill="#F8FAFC"/>
</svg>""",

    "twist": """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="t" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#E2E8F0"/><stop offset="1" stop-color="#64748B"/>
    </linearGradient>
  </defs>
  <rect x="5" y="28" width="54" height="9" rx="4.5" fill="url(#t)"/>
  <g fill="none" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
    <path d="M20 18 A16 16 0 0 1 44 18" stroke="#F59E0B"/><path d="M45 10 V18 H37" stroke="#F59E0B"/>
    <path d="M44 47 A16 16 0 0 1 20 47" stroke="#22D3EE"/><path d="M19 55 V47 H27" stroke="#22D3EE"/>
  </g>
</svg>""",

    "network": """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="nw" x1="0" y1="1" x2="0" y2="0">
      <stop offset="0" stop-color="#3B82F6"/><stop offset="1" stop-color="#00E5FF"/>
    </linearGradient>
  </defs>
  <circle cx="32" cy="48" r="4.5" fill="url(#nw)"/>
  <path d="M21 37 A16 16 0 0 1 43 37" fill="none" stroke="url(#nw)" stroke-width="4" stroke-linecap="round"/>
  <path d="M12 26 A28 28 0 0 1 52 26" fill="none" stroke="url(#nw)" stroke-width="4" stroke-linecap="round"/>
  <path d="M4 15 A40 40 0 0 1 60 15" fill="none" stroke="url(#nw)" stroke-width="4" stroke-linecap="round"/>
</svg>""",

    "save": """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="sv" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#10B981"/><stop offset="1" stop-color="#059669"/>
    </linearGradient>
  </defs>
  <rect x="10" y="8" width="44" height="48" rx="6" fill="url(#sv)"/>
  <path d="M42 8 L54 20 V50 A6 6 0 0 1 48 56 H16 A6 6 0 0 1 10 50 V14 A6 6 0 0 1 16 8 Z" fill="url(#sv)"/>
  <rect x="20" y="8" width="22" height="16" rx="2" fill="#FFFFFF" fill-opacity="0.85"/>
  <rect x="24" y="12" width="6" height="8" rx="1" fill="#065F46"/>
  <rect x="18" y="32" width="28" height="18" rx="3" fill="#064E3B"/>
  <rect x="22" y="36" width="20" height="2.5" rx="1" fill="#A7F3D0"/>
  <rect x="22" y="42" width="14" height="2.5" rx="1" fill="#A7F3D0"/>
</svg>""",

    "restart": """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="rs" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#F59E0B"/><stop offset="1" stop-color="#D97706"/>
    </linearGradient>
  </defs>
  <path d="M50 32 A18 18 0 1 1 44.5 19.5" fill="none" stroke="url(#rs)" stroke-width="5" stroke-linecap="round"/>
  <path d="M46 9 L46 22 L33 22" fill="none" stroke="url(#rs)" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>
</svg>""",

    "reload": """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="rl" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#10B981"/><stop offset="1" stop-color="#059669"/>
    </linearGradient>
  </defs>
  <path d="M50 32 A18 18 0 1 1 44.5 19.5" fill="none" stroke="url(#rl)" stroke-width="5" stroke-linecap="round"/>
  <path d="M46 9 L46 22 L33 22" fill="none" stroke="url(#rl)" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>
</svg>""",

    "sun": """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <radialGradient id="sn" cx="0.5" cy="0.5" r="0.5">
      <stop offset="0" stop-color="#FDE047"/><stop offset="1" stop-color="#EAB308"/>
    </radialGradient>
  </defs>
  <circle cx="32" cy="32" r="13" fill="url(#sn)"/>
  <g stroke="#FACC15" stroke-width="4" stroke-linecap="round">
    <path d="M32 6 V12 M32 52 V58 M6 32 H12 M52 32 H58"/>
    <path d="M13.6 13.6 L17.8 17.8 M46.2 46.2 L50.4 50.4 M13.6 50.4 L17.8 46.2 M46.2 17.8 L50.4 13.6"/>
  </g>
</svg>""",

    "firmware": """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="fwg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#38BDF8"/><stop offset="1" stop-color="#0284C7"/>
    </linearGradient>
    <linearGradient id="coreg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#0284C7"/><stop offset="1" stop-color="#0369A1"/>
    </linearGradient>
  </defs>
  <!-- Chip body -->
  <rect x="14" y="14" width="36" height="36" rx="6" fill="#0F172A" stroke="url(#fwg)" stroke-width="3"/>
  <rect x="23" y="23" width="18" height="18" rx="3" fill="url(#coreg)" stroke="#38BDF8" stroke-width="1.5"/>
  <circle cx="19" cy="19" r="1.5" fill="#38BDF8"/>
  <!-- Pins: top & bottom -->
  <g stroke="#38BDF8" stroke-width="3" stroke-linecap="round">
    <line x1="22" y1="7" x2="22" y2="14"/>
    <line x1="32" y1="7" x2="32" y2="14"/>
    <line x1="42" y1="7" x2="42" y2="14"/>
    <line x1="22" y1="50" x2="22" y2="57"/>
    <line x1="32" y1="50" x2="32" y2="57"/>
    <line x1="42" y1="50" x2="42" y2="57"/>
    <!-- Pins: left & right -->
    <line x1="7" y1="22" x2="14" y2="22"/>
    <line x1="7" y1="32" x2="14" y2="32"/>
    <line x1="7" y1="42" x2="14" y2="42"/>
    <line x1="50" y1="22" x2="57" y2="22"/>
    <line x1="50" y1="32" x2="57" y2="32"/>
    <line x1="50" y1="42" x2="57" y2="42"/>
  </g>
</svg>""",

    "files": """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="flg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#38BDF8"/><stop offset="1" stop-color="#2563EB"/>
    </linearGradient>
    <linearGradient id="cube" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#00E5FF"/><stop offset="1" stop-color="#0284C7"/>
    </linearGradient>
  </defs>
  <rect x="12" y="8" width="40" height="48" rx="6" fill="#1E293B" stroke="url(#flg)" stroke-width="3"/>
  <path d="M38 8 L52 22 H41 A3 3 0 0 1 38 19 Z" fill="url(#flg)"/>
  <polygon points="32,24 44,30 32,36 20,30" fill="url(#cube)"/>
  <polygon points="20,30 32,36 32,48 20,42" fill="#0284C7"/>
  <polygon points="44,30 32,36 32,48 44,42" fill="#0369A1"/>
  <circle cx="32" cy="18" r="2" fill="#38BDF8"/>
</svg>""",

    "print": """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="prg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#00E5FF"/><stop offset="1" stop-color="#3B82F6"/>
    </linearGradient>
    <linearGradient id="noz" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#F59E0B"/><stop offset="1" stop-color="#D97706"/>
    </linearGradient>
  </defs>
  <path d="M14 12 H50 M14 52 H50 M14 12 V52 M50 12 V52" fill="none" stroke="#475569" stroke-width="4" stroke-linecap="round"/>
  <line x1="14" y1="26" x2="50" y2="26" stroke="#64748B" stroke-width="3"/>
  <polygon points="32,34 27,24 37,24" fill="url(#noz)"/>
  <rect x="22" y="44" width="20" height="6" rx="2" fill="url(#prg)"/>
  <rect x="25" y="38" width="14" height="6" rx="2" fill="#38BDF8"/>
</svg>""",

    "folder": """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="fdg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#FBBF24"/><stop offset="1" stop-color="#D97706"/>
    </linearGradient>
    <linearGradient id="fbg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#F59E0B"/><stop offset="1" stop-color="#B45309"/>
    </linearGradient>
  </defs>
  <path d="M8 18 A4 4 0 0 1 12 14 H24 L30 20 H52 A4 4 0 0 1 56 24 V46 A4 4 0 0 1 52 50 H12 A4 4 0 0 1 8 46 Z" fill="url(#fbg)"/>
  <path d="M8 25 A4 4 0 0 1 12 21 H52 A4 4 0 0 1 56 25 V46 A4 4 0 0 1 52 50 H12 A4 4 0 0 1 8 46 Z" fill="url(#fdg)"/>
</svg>""",

    "back": """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="bkg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#38BDF8"/><stop offset="1" stop-color="#0284C7"/>
    </linearGradient>
  </defs>
  <circle cx="32" cy="32" r="28" fill="#1E293B" stroke="url(#bkg)" stroke-width="3"/>
  <path d="M38 20 L26 32 L38 44" fill="none" stroke="#38BDF8" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>
</svg>""",

    "list": """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <g stroke="#38BDF8" stroke-width="4" stroke-linecap="round">
    <line x1="22" y1="18" x2="52" y2="18"/>
    <line x1="22" y1="32" x2="52" y2="32"/>
    <line x1="22" y1="46" x2="52" y2="46"/>
  </g>
  <circle cx="12" cy="18" r="3" fill="#38BDF8"/>
  <circle cx="12" cy="32" r="3" fill="#38BDF8"/>
  <circle cx="12" cy="46" r="3" fill="#38BDF8"/>
</svg>""",

    "grid": """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <rect x="10" y="10" width="18" height="18" rx="4" fill="#38BDF8"/>
  <rect x="36" y="10" width="18" height="18" rx="4" fill="#38BDF8"/>
  <rect x="10" y="36" width="18" height="18" rx="4" fill="#38BDF8"/>
  <rect x="36" y="36" width="18" height="18" rx="4" fill="#38BDF8"/>
</svg>""",

    "tune": """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <g stroke="#38BDF8" stroke-width="4" stroke-linecap="round">
    <line x1="16" y1="10" x2="16" y2="54"/>
    <line x1="32" y1="10" x2="32" y2="54"/>
    <line x1="48" y1="10" x2="48" y2="54"/>
  </g>
  <circle cx="16" cy="22" r="6" fill="#0284C7" stroke="#38BDF8" stroke-width="2.5"/>
  <circle cx="32" cy="42" r="6" fill="#0284C7" stroke="#38BDF8" stroke-width="2.5"/>
  <circle cx="48" cy="28" r="6" fill="#0284C7" stroke="#38BDF8" stroke-width="2.5"/>
</svg>""",

    "pause": """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <rect x="16" y="12" width="10" height="40" rx="3" fill="#FBBF24"/>
  <rect x="38" y="12" width="10" height="40" rx="3" fill="#FBBF24"/>
</svg>""",

    "resume": """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <polygon points="18,12 52,32 18,52" fill="#34D399"/>
</svg>""",

    "cancel": """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <circle cx="32" cy="32" r="28" fill="#EF4444" fill-opacity="0.2" stroke="#EF4444" stroke-width="3"/>
  <line x1="22" y1="22" x2="42" y2="42" stroke="#EF4444" stroke-width="5" stroke-linecap="round"/>
  <line x1="42" y1="22" x2="22" y2="42" stroke="#EF4444" stroke-width="5" stroke-linecap="round"/>
</svg>""",

    "refresh": """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <path d="M48 32 A18 18 0 1 1 42.7 19.3" fill="none" stroke="#38BDF8" stroke-width="5" stroke-linecap="round"/>
  <polygon points="46,10 52,22 40,22" fill="#38BDF8"/>
</svg>""",
})


def _device_pixel_ratio() -> float:
    screen = QtGui.QGuiApplication.primaryScreen()
    return screen.devicePixelRatio() if screen else 1.0


@lru_cache(maxsize=128)
def pixmap(name: str, size: int) -> QtGui.QPixmap:
    """Render icon `name` to a square pixmap of `size` logical pixels."""
    dpr = _device_pixel_ratio()
    real = max(1, round(size * dpr))
    renderer = QtSvg.QSvgRenderer(QtCore.QByteArray(_SVG[name].encode("utf-8")))
    pm = QtGui.QPixmap(real, real)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pm)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
    renderer.render(painter)
    painter.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def icon(name: str, size: int) -> QtGui.QIcon:
    """QIcon with the same pixmap for every mode (keeps full colour when checked)."""
    pm = pixmap(name, size)
    ic = QtGui.QIcon()
    for mode in (QtGui.QIcon.Mode.Normal, QtGui.QIcon.Mode.Active, QtGui.QIcon.Mode.Selected):
        for state in (QtGui.QIcon.State.Off, QtGui.QIcon.State.On):
            ic.addPixmap(pm, mode, state)
    return ic
