import glob
import os
import time
import json
import hashlib
import requests
import email.utils
import threading
import random
from flask import Flask, send_file, abort, make_response, request
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from dotenv import load_dotenv

__version__ = "1.1.0"

# overrides.py is optional and gitignored; start from overrides.example.py.
try:
    from overrides import OVERRIDES
except ImportError:
    OVERRIDES = {}

# Load API credentials
load_dotenv()
RA_API_USERNAME = os.getenv("RA_API_USERNAME")
RA_API_KEY = os.getenv("RA_API_KEY")

_missing_env = [name for name, value in (("RA_API_USERNAME", RA_API_USERNAME),
                                          ("RA_API_KEY", RA_API_KEY)) if not value]
if _missing_env:
    raise RuntimeError(
        f"Missing required setting(s): {', '.join(_missing_env)}. "
        "Copy .env.example to .env and fill it in."
    )

# Flask app init
app = Flask(__name__)

# Constants
CACHE_TTL = 300
API_CACHE_TTL = 300
CACHE_DIR = "./cache"
API_CACHE_DIR = "./api_cache"
OVERRIDE_DIR = "./overrides"
BACKGROUND_DIR = "./backgrounds"
DEFAULT_ASSET_SUFFIX = "_default.png"  # bundled placeholder assets end with this
FONT_PATH = "./Pixellari.ttf"

# Softcore overlay: a local softcore.png (gitignored) wins; otherwise the
# repo's placeholder overlay is used. If neither exists, no overlay is drawn.
SOFTCORE_OVERLAY_PATHS = ("./softcore.png", "./softcore_default.png")

# Sent on every outbound HTTP request so RetroAchievements can identify this app.
HTTP_HEADERS = {
    "User-Agent": f"ra-signatures/{__version__} (+https://github.com/tmfc666/ra-signatures)"
}
COLOR_EMOJI_FONT_PATH = "./NotoColorEmoji.ttf"
MONO_EMOJI_FONT_PATH = "./EmojiFallback.ttf"  # fallback only, used if a glyph is missing from the color font

# NotoColorEmoji is a bitmap-strike (CBDT/CBLC) font: it only renders at one
# fixed native pixel size, so we always render glyphs at that size, then
# downscale to whatever height we actually need with high-quality resampling.
# This keeps full color/detail instead of relying on a thin monochrome outline.
COLOR_EMOJI_NATIVE_SIZE = 109
EMOJI_SIZE_SCALE = 0.85  # rendered emoji height, as a fraction of the paired text's point size
EMOJI_Y_SHIFT = -2       # pixels to nudge emoji up to better sit on the text baseline

# Characters that Pixellari lacks glyphs for but which aren't emoji (so they
# won't be caught by the emoji fallback path). Map each to a visually similar
# substitute that Pixellari does render correctly.
# Add more entries here as you encounter them in rich presence messages.
CHAR_SUBSTITUTIONS = {
    "\u2022": "|",   # bullet, used as a divider -> pipe
    "\u00b7": "|",   # middle dot, same role -> pipe
    "\u2013": "-",   # en dash -> hyphen
    "\u2014": "-",   # em dash -> hyphen
    "\u2019": "'",   # right single quotation mark -> straight quote
    "\u201c": '"',   # left double quotation mark -> straight quote
    "\u201d": '"',   # right double quotation mark -> straight quote
}

# Console icon settings.
# Icons come from API_GetConsoleIDs (IconURL field) and are resized to sit
# neatly beside the small font's "Platform:" label.
CONSOLE_ICON_HEIGHT = 14       # px; sized to sit comfortably on the 16px font_small line
CONSOLE_ICON_GAP = 4           # px gap between icon and console name text
CONSOLE_ICON_MAP_TTL = 86400   # how long to trust the cached console list (seconds); 24h
CONSOLE_ICON_MAP_PATH = os.path.join("api_cache", "console_icon_map.json")

os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(API_CACHE_DIR, exist_ok=True)
os.makedirs(OVERRIDE_DIR, exist_ok=True)
os.makedirs(BACKGROUND_DIR, exist_ok=True)

# Scanned once at startup; add new backgrounds and restart Gunicorn to pick them up.
# The repo ships generic placeholders named *_default.png. Any other .png in
# BACKGROUND_DIR is treated as a custom background (gitignored); if at least one
# custom background exists, the placeholders are left out of the random pool.
_all_backgrounds = sorted(glob.glob(os.path.join(BACKGROUND_DIR, "*.png")))
_default_backgrounds = [p for p in _all_backgrounds if p.endswith(DEFAULT_ASSET_SUFFIX)]
_custom_backgrounds = [p for p in _all_backgrounds if not p.endswith(DEFAULT_ASSET_SUFFIX)]
_backgrounds = _custom_backgrounds or _default_backgrounds

# Loaded once at import time rather than per-request: the color emoji font
# file is ~10MB and there's no need to re-parse it on every cache miss.
try:
    _font_color_emoji = ImageFont.truetype(COLOR_EMOJI_FONT_PATH, COLOR_EMOJI_NATIVE_SIZE)
except Exception as e:
    print(f"Failed to load color emoji font, will fall back to monochrome: {e}")
    _font_color_emoji = None

try:
    _font_mono_emoji = ImageFont.truetype(MONO_EMOJI_FONT_PATH, COLOR_EMOJI_NATIVE_SIZE)
except Exception as e:
    print(f"Failed to load monochrome emoji fallback font: {e}")
    _font_mono_emoji = None

# Unicode ranges covering emoji & pictographs that Pixellari (and most pixel
# fonts) doesn't have glyphs for. Range-based detection is used instead of
# probing Pixellari directly, since Pillow has no cheap "does this font have
# a glyph for this codepoint" check without pulling in libraqm.
_EMOJI_RANGES = (
    (0x1F300, 0x1FAFF),  # misc symbols/pictographs, emoticons, transport, supplemental, extended-A
    (0x2600, 0x27BF),    # misc symbols & dingbats (sun, stars, check marks, etc.)
    (0x2190, 0x21FF),    # arrows (some are used decoratively in RP messages)
    (0x2B00, 0x2BFF),    # misc symbols and arrows (large stars, etc.)
    (0x1F1E6, 0x1F1FF),  # regional indicator letters (flag emoji)
    (0xFE00, 0xFE0F),    # variation selectors
    (0x200D, 0x200D),    # zero-width joiner (combines emoji like family/profession ZWJ sequences)
)

def _is_emoji_char(ch):
    cp = ord(ch)
    return any(start <= cp <= end for start, end in _EMOJI_RANGES)

def _split_runs(text):
    """Splits text into a list of (substring, is_emoji) runs of consecutive
    same-type characters, so each run can be drawn with the right font."""
    if not text:
        return []
    runs = []
    current_chars = [text[0]]
    current_is_emoji = _is_emoji_char(text[0])
    for ch in text[1:]:
        ch_is_emoji = _is_emoji_char(ch)
        if ch_is_emoji == current_is_emoji:
            current_chars.append(ch)
        else:
            runs.append(("".join(current_chars), current_is_emoji))
            current_chars = [ch]
            current_is_emoji = ch_is_emoji
    runs.append(("".join(current_chars), current_is_emoji))
    return runs

# Cache of rendered/downscaled emoji glyphs, keyed by (char, target_height).
# Small and cheap to keep for the life of the process -- there are only a
# few hundred distinct emoji that will realistically show up in RP messages.
_emoji_glyph_cache = {}

def _render_emoji_glyph(ch, target_height):
    """Renders a single emoji character to a small RGBA image at target_height,
    in full color if possible (NotoColorEmoji), falling back to the monochrome
    OpenMoji outline font if the color font is unavailable or lacks the glyph.
    Returns None if neither font can render it."""
    key = (ch, target_height)
    if key in _emoji_glyph_cache:
        return _emoji_glyph_cache[key]

    glyph = None
    if _font_color_emoji is not None:
        glyph = _rasterize_and_scale(ch, target_height, _font_color_emoji, embedded_color=True)
    if glyph is None and _font_mono_emoji is not None:
        glyph = _rasterize_and_scale(ch, target_height, _font_mono_emoji, embedded_color=False)

    _emoji_glyph_cache[key] = glyph
    return glyph

def _rasterize_and_scale(ch, target_height, font, embedded_color):
    try:
        # Native strike is COLOR_EMOJI_NATIVE_SIZE square-ish; pad the scratch
        # canvas generously so nothing gets clipped before we crop to content.
        pad = COLOR_EMOJI_NATIVE_SIZE
        scratch = Image.new("RGBA", (pad * 2, pad * 2), (0, 0, 0, 0))
        d = ImageDraw.Draw(scratch)
        if embedded_color:
            d.text((pad // 2, pad // 2), ch, font=font, embedded_color=True)
        else:
            d.text((pad // 2, pad // 2), ch, font=font, fill=(255, 255, 255, 255))
        bbox = scratch.getbbox()
        if not bbox:
            return None
        cropped = scratch.crop(bbox)
        w, h = cropped.size
        if h == 0:
            return None
        new_w = max(1, round(w * target_height / h))
        return cropped.resize((new_w, target_height), Image.LANCZOS)
    except Exception as e:
        print(f"Failed to rasterize emoji glyph {ch!r}: {e}")
        return None

def mixed_textlength(draw, text, font_main, font_main_size):
    """Like draw.textlength, but measures emoji/symbol runs as the sum of
    their rendered glyph widths at the paired text size, and everything else
    with font_main."""
    total = 0
    target_height = max(1, round(font_main_size * EMOJI_SIZE_SCALE))
    for run_text, is_emoji in _split_runs(text):
        if is_emoji:
            for ch in run_text:
                glyph = _render_emoji_glyph(ch, target_height)
                if glyph:
                    total += glyph.width + 1
        else:
            total += draw.textlength(run_text, font=font_main)
    return total

def draw_mixed_text(img, draw, xy, text, font_main, font_main_size, fill):
    """Like draw.text, but renders emoji/symbol runs as composited color
    glyph images and everything else with font_main, advancing the cursor
    between runs/characters. `img` is the underlying Image (not just the
    ImageDraw), since emoji glyphs are pasted in rather than drawn."""
    x, y = xy
    target_height = max(1, round(font_main_size * EMOJI_SIZE_SCALE))
    y_paste = y + (font_main_size - target_height) // 2 + EMOJI_Y_SHIFT
    for run_text, is_emoji in _split_runs(text):
        if is_emoji:
            for ch in run_text:
                glyph = _render_emoji_glyph(ch, target_height)
                if glyph:
                    img.paste(glyph, (round(x), round(y_paste)), glyph)
                    x += glyph.width + 1
        else:
            draw.text((x, y), run_text, font=font_main, fill=fill)
            x += draw.textlength(run_text, font=font_main)

# --- Console icon support -------------------------------------------------- #

# In-memory map of ConsoleID (int) -> IconURL (str). Populated lazily on the
# first request that needs it, then refreshed per CONSOLE_ICON_MAP_TTL.
_console_icon_map = {}
_console_icon_map_lock = threading.Lock()

# In-memory cache of downloaded + resized console icon images, keyed by
# ConsoleID. There are only ~50 active game systems so this stays small.
_console_image_cache = {}

def _load_console_icon_map():
    """Returns a dict of {ConsoleID (int): IconURL (str)}.

    Reads from the local JSON cache if it's fresh enough; otherwise fetches
    API_GetConsoleIDs (active game systems only) and writes a new cache file.
    Thread-safe: concurrent callers block until the first one finishes."""
    global _console_icon_map

    with _console_icon_map_lock:
        # If already populated in memory, use it (lifetime of process is fine
        # since we re-fetch on disk cache miss/expiry at startup or next reload)
        if _console_icon_map:
            return _console_icon_map

        # Try the on-disk cache first
        if os.path.exists(CONSOLE_ICON_MAP_PATH):
            age = time.time() - os.path.getmtime(CONSOLE_ICON_MAP_PATH)
            if age < CONSOLE_ICON_MAP_TTL:
                try:
                    with open(CONSOLE_ICON_MAP_PATH, "r") as f:
                        _console_icon_map = {int(k): v for k, v in json.load(f).items()}
                        return _console_icon_map
                except Exception as e:
                    print(f"Failed to load console icon map cache: {e}")

        # Fetch from RA API: a=1 (active only), g=1 (game systems only)
        try:
            resp = requests.get(
                "https://retroachievements.org/API/API_GetConsoleIDs.php",
                params={"z": RA_API_USERNAME, "y": RA_API_KEY, "a": 1, "g": 1},
                headers=HTTP_HEADERS,
                timeout=8
            )
            data = resp.json()
            if isinstance(data, list):
                _console_icon_map = {
                    int(entry["ID"]): entry["IconURL"]
                    for entry in data
                    if "ID" in entry and entry.get("IconURL")
                }
                try:
                    with open(CONSOLE_ICON_MAP_PATH, "w") as f:
                        json.dump(_console_icon_map, f)
                except Exception as e:
                    print(f"Failed to write console icon map cache: {e}")
        except Exception as e:
            print(f"Failed to fetch console icon map: {e}")

        return _console_icon_map

def _get_console_icon(console_id):
    """Returns a resized RGBA Image for the given ConsoleID, or None on failure.
    The image is cached in memory after the first download."""
    if console_id is None:
        return None
    if console_id in _console_image_cache:
        return _console_image_cache[console_id]

    icon_map = _load_console_icon_map()
    icon_url = icon_map.get(int(console_id))
    if not icon_url:
        _console_image_cache[console_id] = None
        return None

    try:
        resp = requests.get(icon_url, headers=HTTP_HEADERS, timeout=5)
        if resp.status_code == 200:
            raw = Image.open(BytesIO(resp.content)).convert("RGBA")
            # Resize to target height, preserving aspect ratio
            aspect = raw.width / raw.height
            new_w = max(1, round(CONSOLE_ICON_HEIGHT * aspect))
            icon = raw.resize((new_w, CONSOLE_ICON_HEIGHT), Image.LANCZOS)
            _console_image_cache[console_id] = icon
            return icon
    except Exception as e:
        print(f"Failed to fetch console icon for ConsoleID {console_id}: {e}")

    _console_image_cache[console_id] = None
    return None

# In-memory locks
profile_locks = {}
global_api_lock = threading.Lock()

def get_profile_lock(username):
    if username not in profile_locks:
        profile_locks[username] = threading.Lock()
    return profile_locks[username]

def safe_request(url, params, max_retries=3, delay=0.5):
    for attempt in range(max_retries):
        with global_api_lock:
            try:
                resp = requests.get(url, params=params, headers=HTTP_HEADERS, timeout=5).json()
                if "Error" not in resp and resp:
                    return resp
            except Exception as e:
                print(f"RA API error ({url}): {e}")
        time.sleep(delay * (attempt + 1))
    return None

class GamerProfile:
    def __init__(self, username):
        self.username = username
        self.user_data = {}
        self.awards_data = {}
        self.game_data = {}
        self.valid = self.fetch_data()

    def fetch_data(self):
        cache_path = os.path.join(API_CACHE_DIR, f"{self.username}.json")

        if os.path.exists(cache_path):
            age = time.time() - os.path.getmtime(cache_path)
            if age < API_CACHE_TTL:
                try:
                    with open(cache_path, "r") as f:
                        data = json.load(f)
                        self.user_data = data["user_data"]
                        self.awards_data = data["awards_data"]
                        self.game_data = data.get("game_data", {})
                        return True
                except Exception as e:
                    print(f"Failed to load cache: {e}")

        with get_profile_lock(self.username):
            if os.path.exists(cache_path):
                age = time.time() - os.path.getmtime(cache_path)
                if age < API_CACHE_TTL:
                    try:
                        with open(cache_path, "r") as f:
                            data = json.load(f)
                            self.user_data = data["user_data"]
                            self.awards_data = data["awards_data"]
                            self.game_data = data.get("game_data", {})
                            return True
                    except Exception:
                        pass

            self.user_data = safe_request(
                f"https://retroachievements.org/API/API_GetUserProfile.php?u={self.username}",
                {"z": RA_API_USERNAME, "y": RA_API_KEY}
            )
            if not self.user_data:
                return False

            self.awards_data = safe_request(
                f"https://retroachievements.org/API/API_GetUserAwards.php?u={self.username}",
                {"z": RA_API_USERNAME, "y": RA_API_KEY}
            )
            if not self.awards_data:
                return False

            # Check for a manual override before hitting the "current game" API.
            # Real account stats above (points, mastery, etc.) stay real --
            # only the "currently playing" section gets swapped out.
            override = OVERRIDES.get(self.username.lower())
            if override:
                self.game_data = self._build_override_game_data(override)
                if "RichPresenceMsg" in override:
                    self.user_data["RichPresenceMsg"] = override["RichPresenceMsg"]
            else:
                self.game_data = {}
                last_game_id = self.user_data.get("LastGameID")
                if last_game_id:
                    self.game_data = safe_request(
                        f"https://retroachievements.org/API/API_GetGameInfoAndUserProgress.php?g={last_game_id}&u={self.username}",
                        {"z": RA_API_USERNAME, "y": RA_API_KEY}
                    ) or {}

            try:
                with open(cache_path, "w") as f:
                    json.dump({
                        "user_data": self.user_data,
                        "awards_data": self.awards_data,
                        "game_data": self.game_data
                    }, f)
            except Exception as e:
                print(f"Cache write failed: {e}")

            return True

    def _build_override_game_data(self, override):
        """Shapes an override dict into the same structure generate_signature_image
        expects from the real RA API's GetGameInfoAndUserProgress response.

        If ImageIcon isn't explicitly set in the override, this falls back to
        ./overrides/<username>.png (matching the existing backgrounds/cache
        folder convention), if that file exists.
        """
        if "ImageIcon" in override:
            icon = override["ImageIcon"]
        else:
            default_icon_path = os.path.join(OVERRIDE_DIR, f"{self.username.lower()}.png")
            icon = f"local:{default_icon_path}" if os.path.exists(default_icon_path) else None

        return {
            "Title": override.get("Title", "Unknown"),
            "ConsoleName": override.get("ConsoleName", "N/A"),
            "ConsoleID": override.get("ConsoleID"),  # optional; enables the console icon
            "ImageIcon": icon,
        }

    def mastery_count(self):
        return self.awards_data.get("MasteryAwardsCount", "0")

def generate_signature_image(profile: GamerProfile, output_path=None):
    img = None
    if _backgrounds:
        try:
            img = Image.open(random.choice(_backgrounds)).convert("RGBA")
        except Exception as e:
            print(f"Failed to load background: {e}")
    if img is None:
        img = Image.new("RGBA", (768, 192), (30, 30, 30, 255))

    draw = ImageDraw.Draw(img)
    try:
        font_large = ImageFont.truetype(FONT_PATH, 32)
        font_small = ImageFont.truetype(FONT_PATH, 16)
    except IOError:
        font_large = font_small = ImageFont.load_default()

    u = profile.user_data
    g = profile.game_data
    m = profile.mastery_count()

    draw.text((10, 5), f"{profile.username}'s RetroAchievements", font=font_large, fill=(255, 255, 255))
    draw.text((10, 40), f"Hardcore Points: {u.get('TotalPoints', '0')}", font=font_small, fill=(255, 255, 255))
    draw.text((10, 60), f"Softcore Points (flame if >0): {u.get('TotalSoftcorePoints', '0')}", font=font_small, fill=(255, 255, 255))
    draw.text((10, 80), f"Games Mastered: {m}", font=font_small, fill=(255, 255, 255))

    if g:
        now_playing_text = f"Now Playing: {g.get('Title', 'Unknown')}"
        text_width = mixed_textlength(draw, now_playing_text, font_large, 32)
        if text_width > img.width - 20:
            now_playing_y = 120
            draw_mixed_text(img, draw, (10, now_playing_y), now_playing_text, font_small, 16, (128, 255, 128))
        else:
            now_playing_y = 105
            draw_mixed_text(img, draw, (10, now_playing_y), now_playing_text, font_large, 32, (128, 255, 128))

        draw.text((10, 140), f"Platform: ", font=font_small, fill=(128, 255, 128))
        platform_label_w = draw.textlength("Platform: ", font=font_small)

        console_id = g.get("ConsoleID")
        console_icon = _get_console_icon(console_id)
        icon_x = 10 + platform_label_w
        if console_icon:
            # Vertically center the icon on the small font's line
            icon_y = 140 + (16 - CONSOLE_ICON_HEIGHT) // 2
            img.paste(console_icon, (round(icon_x), round(icon_y)), console_icon)
            icon_x += console_icon.width + CONSOLE_ICON_GAP

        draw.text((icon_x, 140), g.get('ConsoleName', 'N/A'), font=font_small, fill=(128, 255, 128))

        prefix = "Currently: "
        rich_msg = u.get('RichPresenceMsg', 'N/A')
        for ch, replacement in CHAR_SUBSTITUTIONS.items():
            rich_msg = rich_msg.replace(ch, replacement)
        max_width = 763 - 10  # right margin minus left padding

        full_text = prefix + rich_msg
        if mixed_textlength(draw, full_text, font_small, 16) > max_width:
            # Truncate RichPresenceMsg to fit with ellipsis
            for i in range(len(rich_msg), 0, -1):
                test_text = prefix + rich_msg[:i].rstrip() + "..."
                if mixed_textlength(draw, test_text, font_small, 16) <= max_width:
                    full_text = test_text
                    break

        draw_mixed_text(img, draw, (10, 160), full_text, font_small, 16, (128, 255, 128))

        # Try to add game icon (local override file or RA-hosted ImageIcon URL)
        icon_path = g.get("ImageIcon")
        icon_img = None

        if icon_path and icon_path.startswith("local:"):
            local_path = icon_path[len("local:"):]
            try:
                icon_img = Image.open(local_path).convert("RGBA")
            except Exception as e:
                print(f"Failed to load local override icon ({local_path}): {e}")
        elif icon_path:
            icon_url = f"https://retroachievements.org{icon_path}"
            try:
                icon_resp = requests.get(icon_url, headers=HTTP_HEADERS, timeout=5)
                if icon_resp.status_code == 200:
                    icon_img = Image.open(BytesIO(icon_resp.content)).convert("RGBA")
            except Exception as e:
                print(f"Failed to load ImageIcon: {e}")

        if icon_img:
            icon_x = img.width - icon_img.width - 10
            icon_y = 5
            # Draw green border around the icon
            border_color = (128, 255, 128)
            border_box = [
                (icon_x - 1, icon_y - 1),
                (icon_x + icon_img.width, icon_y + icon_img.height)
            ]
            draw.rectangle(border_box, outline=border_color)
            img.paste(icon_img, (icon_x, icon_y), icon_img)

    # Overlay the softcore image if the user has any softcore points
    try:
        softcore_points = int(u.get('TotalSoftcorePoints', '0'))
        overlay_path = next((p for p in SOFTCORE_OVERLAY_PATHS if os.path.exists(p)), None)
        if softcore_points > 0 and overlay_path:
            softcore_overlay = Image.open(overlay_path).convert("RGBA")
            if softcore_overlay.size != img.size:
                softcore_overlay = softcore_overlay.resize(img.size, Image.LANCZOS)
            img.alpha_composite(softcore_overlay)
    except Exception as e:
        print(f"Failed to apply softcore overlay: {e}")

    if output_path:
        img.save(output_path, "PNG", optimize=True)
    else:
        img_io = BytesIO()
        img.save(img_io, "PNG", optimize=True)
        img_io.seek(0)
        return img_io

def calculate_etag(path):
    with open(path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()

@app.route("/users/<username>.png")
def serve_signature(username):
    cache_path = os.path.join(CACHE_DIR, f"{username}.png")

    if os.path.exists(cache_path):
        age = time.time() - os.path.getmtime(cache_path)
        if age < CACHE_TTL:
            etag = calculate_etag(cache_path)
            last_modified = email.utils.formatdate(os.path.getmtime(cache_path), usegmt=True)

            if (
                request.headers.get("If-None-Match") == etag or
                request.headers.get("If-Modified-Since") == last_modified
            ):
                return '', 304

            response = make_response(send_file(cache_path, mimetype="image/png"))
            response.headers["Cache-Control"] = f"public, max-age={CACHE_TTL}"
            response.headers["Last-Modified"] = last_modified
            response.headers["ETag"] = etag
            return response

    profile = GamerProfile(username)
    if not profile.valid:
        abort(404)

    generate_signature_image(profile, output_path=cache_path)
    return serve_signature(username)

@app.route("/invalidate/<username>", methods=["GET", "POST"])
def invalidate_cache(username):
    deleted = []
    for path in [
        os.path.join(CACHE_DIR, f"{username}.png"),
        os.path.join(API_CACHE_DIR, f"{username}.json")
    ]:
        if os.path.exists(path):
            try:
                os.remove(path)
                deleted.append(path)
            except Exception as e:
                return f"Error deleting {path}: {e}", 500

    if not deleted:
        return f"No cache files found for '{username}'.", 404
    return f"Cleared: {', '.join(deleted)}", 200

@app.route("/invalidate_all", methods=["GET", "POST"])
def invalidate_all_cache():
    deleted = []
    for dir_path, ext in [(CACHE_DIR, ".png"), (API_CACHE_DIR, ".json")]:
        for filename in os.listdir(dir_path):
            if filename.endswith(ext):
                full_path = os.path.join(dir_path, filename)
                try:
                    os.remove(full_path)
                    deleted.append(full_path)
                except Exception as e:
                    return f"Error deleting {full_path}: {e}", 500

    if not deleted:
        return "No cached files found.", 404
    return f"Cleared {len(deleted)} files:\n" + "\n".join(deleted), 200

# Disabling built-in Flask dev server block
#if __name__ == "__main__":
#    app.run(host="127.0.0.1", port=5000)
# Gunicorn entrypoint
