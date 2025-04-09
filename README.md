# ra-signatures
Dynamically generate a .png file with RetroAchievements profile info, hosted at an unchanging URL - useful for embeds, e.g. forum signatures. The idea is that you'd have an image that lives at `https://ra.site.com/users/MyRetroAchievementsUsername.png` that dynamically updates itself when the GET request is made. This way, you can have a forum signature that always has up-to-date info about the game you're playing and totals for points and games mastered, displayed in a neat little graphic. Here's what it looks like:

![example](https://raw.githubusercontent.com/tmfc666/ra-signatures/refs/heads/main/example.png)

The included font is **Pixellari** by [Zacchary Dempsey-Plante](https://ztdp.ca/). You can grab it for free at [DaFont](https://www.dafont.com/pixellari.font) (or via this repo), but please make sure you attribute him for making such a slick bitmap / pixel font and making it totally free, like I've done here. Background art is included, but see below for more info on how to change it. 

## Requirements

### Debian packages
```
python3
python3-venv
python3-pip
nginx                  # for reverse proxy
certbot                # for SSL certs, if proxying
python3-certbot-nginx  # 

```
### Python dependencies
```
flask
gunicorn
requests
pillow
python-dotenv
```

### Background Images
The repo includes a set of background images that are ...reminiscent... of many classic NES, SNES, and Genesis games. Feel free to swap these out with your own, but keep the filenames consistent (`background##.png`). You can increase or decrease the number of backgrounds that are chosen by updating the relevant portion of the `generate_signature_image` function in `app.py` (change the `26` to whatever your highest incremented .png filename is):

```
def generate_signature_image(profile: GamerProfile, output_path=None):
    background_file = f"./backgrounds/background{random.randint(1, 26):02}.png"
```

## RetroAchievements API Access
API username and key are defined in the .env file and passed to the Python app via python-dotenv. The code is configured to only allow one request at a time, and I'd recommend running this with only one worker and one thread in Gunicorn to avoid tripping the RetroAchievements API rate limit. I also highly recommend adding CDN caching via Cloudflare or similar as this will greatly improve performance and reduce GET requests to your app and API requests to RetroAchievements.

## Running as a Service - Example
You can configure this to run as a service. Here's an example for running this as a systemd service on Ubuntu, assuming the app and venv are installed in `/opt/ra-signaures/`.

Substitute `<username_here>` with the username of the user that will run the service (I recommend creating a dedicated non-root service account):

### `/etc/systemd/system/ra-signatures.service`
```
[Unit]
Description=RetroAchievements Signature Generator
After=network.target

[Service]
User=<username_here>
WorkingDirectory=/opt/ra-signatures
#ExecStart=/opt/ra-signatures/venv/bin/python /opt/ra-signatures/app.py
ExecStart=/opt/ra-signatures/venv/bin/gunicorn --workers=1 --threads=1 --bind 127.0.0.1:5000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

## Reverse Proxy - Example
You can put this behind a reverse proxy to enable SSL via certbot / letsencrypt. Here's an example site / server block config for Nginx, which assumes the service is running at `https://ra.site.com`:

### `/etc/nginx/sites-available/ra-signatures`
```
server {
    server_name ra.site.com;

    location /users/ {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    listen 443 ssl; # managed by Certbot
    ssl_certificate /etc/letsencrypt/live/ra.site.com/fullchain.pem; # managed by Certbot
    ssl_certificate_key /etc/letsencrypt/live/ra.site.com/privkey.pem; # managed by Certbot
    include /etc/letsencrypt/options-ssl-nginx.conf; # managed by Certbot
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem; # managed by Certbot

}
server {
    if ($host = ra.site.com) {
        return 301 https://$host$request_uri;
    } # managed by Certbot


    listen 80;
    server_name ra.site.com;
    return 404; # managed by Certbot


}
```

## To Do (last updated 2025-04-08):
- **Functional tweaks:**
  - Improve logic for selecting a random background image (e.g. by importing `random`, utilizing `random.choice()`, and adding per-run seeding and/or logic to prevent repeats across calls)
 
- **Aesthetic tweaks:**
  - Add more backgrounds
  - Add console icons from RA
  - Explore other fonts with emoji/unicode glyph support (to improve rich presence text appearance; see example image above.)

- **Organizational tweaks:**
  - Move other parameters to .env file (e.g. cache TTLs)
  - Break app out into multiple .py files for best practices
