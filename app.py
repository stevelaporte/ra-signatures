import os
import time
import json
import hashlib
import requests
import email.utils
from flask import Flask, send_file, abort, make_response, request
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from dotenv import load_dotenv

# Load API credentials
load_dotenv()
RA_API_USERNAME = os.getenv("RA_API_USERNAME")
RA_API_KEY = os.getenv("RA_API_KEY")

# Flask app init
app = Flask(__name__)

# Constants
CACHE_TTL = 120               # Image cache TTL (seconds)
API_CACHE_TTL = 120           # API response cache TTL
CACHE_DIR = "./cache"
API_CACHE_DIR = "./api_cache"
BACKGROUND_PATH = "./background.png"
FONT_PATH = "./Pixellari.ttf"

# Ensure required directories exist
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(API_CACHE_DIR, exist_ok=True)

class GamerProfile:
    """
    Represents a RetroAchievements user profile.
    Handles API data retrieval and caching.
    """
    def __init__(self, username):
        self.username = username
        self.user_data = {}
        self.awards_data = {}
        self.game_data = {}
        self.valid = self.fetch_data()

    def fetch_data(self):
        """Fetches and caches profile, awards, and game data from RA API."""
        cache_path = os.path.join(API_CACHE_DIR, f"{self.username}.json")

        # Load from cache if fresh
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
                    print(f"Failed to load cached API data: {e}")

        # Fetch live data from RA API
        try:
            self.user_data = requests.get(
                f"https://retroachievements.org/API/API_GetUserProfile.php?u={self.username}",
                params={"z": RA_API_USERNAME, "y": RA_API_KEY}
            ).json()
            if "Error" in self.user_data:
                return False

            self.awards_data = requests.get(
                f"https://retroachievements.org/API/API_GetUserAwards.php?u={self.username}",
                params={"z": RA_API_USERNAME, "y": RA_API_KEY}
            ).json()

            last_game_id = self.user_data.get("LastGameID")
            self.game_data = {}
            if last_game_id:
                self.game_data = requests.get(
                    f"https://retroachievements.org/API/API_GetGameInfoAndUserProgress.php?g={last_game_id}&u={self.username}",
                    params={"z": RA_API_USERNAME, "y": RA_API_KEY}
                ).json()

            # Save to cache
            with open(cache_path, "w") as f:
                json.dump({
                    "user_data": self.user_data,
                    "awards_data": self.awards_data,
                    "game_data": self.game_data
                }, f)

            return True

        except Exception as e:
            print(f"Error fetching from RA API: {e}")
            return False

    def mastery_count(self):
        return self.awards_data.get("MasteryAwardsCount", "0")

def generate_signature_image(profile: GamerProfile, output_path=None):
    """Creates and saves or returns the badge image for a user."""
    try:
        img = Image.open(BACKGROUND_PATH).convert("RGBA")
    except IOError:
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
        draw.text((10, 105), f"Now Playing: {g.get('Title', 'Unknown')}", font=font_large, fill=(128, 255, 128))
        draw.text((10, 140), f"Platform: {g.get('ConsoleName', 'N/A')}", font=font_small, fill=(128, 255, 128))
        draw.text((10, 160), f"Currently: {u.get('RichPresenceMsg', 'N/A')}", font=font_small, fill=(128, 255, 128))

    if output_path:
        img.save(output_path, "PNG")
    else:
        img_io = BytesIO()
        img.save(img_io, "PNG")
        img_io.seek(0)
        return img_io

def calculate_etag(path):
    """Generate MD5 hash of file contents for ETag."""
    with open(path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()

@app.route("/users/<username>.png")
def serve_signature(username):
    """
    Serves a badge image with caching, ETag, and conditional 304 support.
    """
    cache_path = os.path.join(CACHE_DIR, f"{username}.png")

    # Serve from cache if fresh
    if os.path.exists(cache_path):
        age = time.time() - os.path.getmtime(cache_path)
        if age < CACHE_TTL:
            etag = calculate_etag(cache_path)
            last_modified = email.utils.formatdate(os.path.getmtime(cache_path), usegmt=True)

            # Conditional GET: respond with 304 if nothing changed
            if (
                request.headers.get("If-None-Match") == etag or
                request.headers.get("If-Modified-Since") == last_modified
            ):
                return '', 304

            # Serve cached image with cache headers
            response = make_response(send_file(cache_path, mimetype="image/png"))
            response.headers["Cache-Control"] = f"public, max-age={CACHE_TTL}"
            response.headers["Last-Modified"] = last_modified
            response.headers["ETag"] = etag
            return response

    # Cache miss or expired — generate new
    profile = GamerProfile(username)
    if not profile.valid:
        abort(404)

    generate_signature_image(profile, output_path=cache_path)
    return serve_signature(username)  # recursive to apply headers

@app.route("/invalidate/<username>", methods=["POST", "GET"])
def invalidate_cache(username):
    """
    Clears cached image and API data for a user.
    Useful for testing, debugging, or on-demand refresh.
    """
    files_deleted = []

    image_path = os.path.join(CACHE_DIR, f"{username}.png")
    api_path = os.path.join(API_CACHE_DIR, f"{username}.json")

    for path in [image_path, api_path]:
        if os.path.exists(path):
            try:
                os.remove(path)
                files_deleted.append(path)
            except Exception as e:
                return f"Error deleting {path}: {e}", 500

    if not files_deleted:
        return f"No cache files found for '{username}'.", 404

    return f"Cleared: {', '.join(files_deleted)}", 200

@app.route("/invalidate_all", methods=["POST", "GET"])
def invalidate_all_cache():
    """
    Clears all cached images and API JSON files.
    """
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

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
