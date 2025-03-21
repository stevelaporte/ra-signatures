import os
import requests
from flask import Flask, send_file, abort
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from dotenv import load_dotenv

# Load API credentials
load_dotenv()
RA_API_USERNAME = os.getenv("RA_API_USERNAME")
RA_API_KEY = os.getenv("RA_API_KEY")

# Flask app setup
app = Flask(__name__)

# API URLs
USER_PROFILE_URL = "https://retroachievements.org/API/API_GetUserProfile.php?u={}"
GAME_PROGRESS_URL = "https://retroachievements.org/API/API_GetGameInfoAndUserProgress.php?g={}&u={}"
USER_AWARDS_URL = "https://retroachievements.org/API/API_GetUserAwards.php?u={}"

# Image assets
BACKGROUND_PATH = "./background.png"
FONT_PATH = "./Pixellari.ttf"

def fetch_ra_data(username):
    """Fetch user profile and mastery awards data from RetroAchievements API."""
    try:
        user_resp = requests.get(USER_PROFILE_URL.format(username), params={
            "z": RA_API_USERNAME,
            "y": RA_API_KEY
        }).json()

        if "Error" in user_resp:
            return None

        awards_resp = requests.get(USER_AWARDS_URL.format(username), params={
            "z": RA_API_USERNAME,
            "y": RA_API_KEY
        }).json()

        mastery_count = awards_resp.get("MasteryAwardsCount", "0")
        
        last_game_id = user_resp.get("LastGameID")
        game_resp = None
        if last_game_id:
            game_resp = requests.get(GAME_PROGRESS_URL.format(last_game_id, username), params={
                "z": RA_API_USERNAME,
                "y": RA_API_KEY
            }).json()
        
        return user_resp, game_resp, mastery_count
    
    except Exception as e:
        print(f"Error fetching data: {e}")
        return None

def generate_signature_image(username):
    """Generate a PNG image dynamically."""
    data = fetch_ra_data(username)
    if not data:
        return None
    
    user_data, game_data, mastery_count = data
    
    # Load background image
    try:
        img = Image.open(BACKGROUND_PATH).convert("RGBA")
    except IOError:
        img = Image.new("RGBA", (768, 192), (30, 30, 30, 255))
    
    draw = ImageDraw.Draw(img)
    
    # Load Pixellari font
    try:
        font_large = ImageFont.truetype(FONT_PATH, 32)  # Headings
        font_small = ImageFont.truetype(FONT_PATH, 16)  # Details
    except IOError:
        font_large = font_small = ImageFont.load_default()
    
    # Draw user details
    draw.text((10, 5), f"{username}'s RetroAchievements", font=font_large, fill=(255, 255, 255))
    draw.text((10, 40), f"Hardcore Points: {user_data.get('TotalPoints', '0')}", font=font_small, fill=(255, 255, 255))
    draw.text((10, 60), f"Softcore Points (flame if >0): {user_data.get('TotalSoftcorePoints', '0')}", font=font_small, fill=(255, 255, 255))
    draw.text((10, 80), f"Games Mastered: {mastery_count}", font=font_small, fill=(255, 255, 255))
    
    if game_data:
        draw.text((10, 105), f"Now Playing: {game_data.get('Title', 'Unknown')}", font=font_large, fill=(128, 255, 128))
        draw.text((10, 140), f"Platform: {game_data.get('ConsoleName', 'N/A')}", font=font_small, fill=(128, 255, 128))
        draw.text((10, 160), f"Currently: {user_data.get('RichPresenceMsg', 'N/A')}", font=font_small, fill=(128, 255, 128))
    
    # Convert and save image
    img_io = BytesIO()
    img.save(img_io, "PNG")
    img_io.seek(0)
    return img_io

@app.route("/users/<username>.png")
def serve_signature(username):
    img_io = generate_signature_image(username)
    if not img_io:
        abort(404)
    return send_file(img_io, mimetype="image/png")

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
