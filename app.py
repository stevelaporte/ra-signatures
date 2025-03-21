import os
import requests
from flask import Flask, send_file, abort
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from dotenv import load_dotenv

# Load API credentials from .env
load_dotenv()
RA_API_USERNAME = os.getenv("RA_API_USERNAME")
RA_API_KEY = os.getenv("RA_API_KEY")

# Initialize Flask app
app = Flask(__name__)

# Paths to static image/font assets
BACKGROUND_PATH = "./background.png"
FONT_PATH = "./Pixellari.ttf"

class GamerProfile:
    """
    Represents a RetroAchievements user profile.
    Handles API data retrieval and organizes user, award, and game data.
    """
    def __init__(self, username):
        self.username = username
        self.user_data = {}
        self.awards_data = {}
        self.game_data = {}
        self.valid = self.fetch_data()

    def fetch_data(self):
        """Fetches user profile, awards, and last played game data."""
        try:
            # Get profile info
            self.user_data = requests.get(
                f"https://retroachievements.org/API/API_GetUserProfile.php?u={self.username}",
                params={"z": RA_API_USERNAME, "y": RA_API_KEY}
            ).json()
            if "Error" in self.user_data:
                return False

            # Get mastery award data
            self.awards_data = requests.get(
                f"https://retroachievements.org/API/API_GetUserAwards.php?u={self.username}",
                params={"z": RA_API_USERNAME, "y": RA_API_KEY}
            ).json()

            # Get current/last played game data
            last_game_id = self.user_data.get("LastGameID")
            if last_game_id:
                self.game_data = requests.get(
                    f"https://retroachievements.org/API/API_GetGameInfoAndUserProgress.php?g={last_game_id}&u={self.username}",
                    params={"z": RA_API_USERNAME, "y": RA_API_KEY}
                ).json()
            return True
        except Exception as e:
            print(f"Error: {e}")
            return False

    def mastery_count(self):
        """Returns the user's total mastery awards."""
        return self.awards_data.get("MasteryAwardsCount", "0")

def generate_signature_image(profile: GamerProfile):
    """
    Composes and returns a signature image for the given profile.
    Uses Pillow to render user stats and game data on a background image.
    """
    # Load background image or fallback to solid color
    try:
        img = Image.open(BACKGROUND_PATH).convert("RGBA")
    except IOError:
        img = Image.new("RGBA", (768, 192), (30, 30, 30, 255))

    draw = ImageDraw.Draw(img)

    # Load custom or default font
    try:
        font_large = ImageFont.truetype(FONT_PATH, 32)
        font_small = ImageFont.truetype(FONT_PATH, 16)
    except IOError:
        font_large = font_small = ImageFont.load_default()

    # Shortcut aliases
    u = profile.user_data
    g = profile.game_data
    m = profile.mastery_count()

    # Draw profile and stat text
    draw.text((10, 5), f"{profile.username}'s RetroAchievements", font=font_large, fill=(255, 255, 255))
    draw.text((10, 40), f"Hardcore Points: {u.get('TotalPoints', '0')}", font=font_small, fill=(255, 255, 255))
    draw.text((10, 60), f"Softcore Points (flame if >0): {u.get('TotalSoftcorePoints', '0')}", font=font_small, fill=(255, 255, 255))
    draw.text((10, 80), f"Games Mastered: {m}", font=font_small, fill=(255, 255, 255))

    # Draw current game info if available
    if g:
        draw.text((10, 105), f"Now Playing: {g.get('Title', 'Unknown')}", font=font_large, fill=(128, 255, 128))
        draw.text((10, 140), f"Platform: {g.get('ConsoleName', 'N/A')}", font=font_small, fill=(128, 255, 128))
        draw.text((10, 160), f"Currently: {u.get('RichPresenceMsg', 'N/A')}", font=font_small, fill=(128, 255, 128))

    # Save image to in-memory file
    img_io = BytesIO()
    img.save(img_io, "PNG")
    img_io.seek(0)
    return img_io

@app.route("/users/<username>.png")
def serve_signature(username):
    """
    Flask route: dynamically generates and returns a .png badge for the given username.
    """
    profile = GamerProfile(username)
    if not profile.valid:
        abort(404)
    return send_file(generate_signature_image(profile), mimetype="image/png")

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
