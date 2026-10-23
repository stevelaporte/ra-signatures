# ra-signatures

![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)

Dynamically generate a PNG with your RetroAchievements profile info, served from an unchanging URL. It's built for forum signatures and other embeds: an image at `https://ra.example.com/users/YourRAUsername.png` regenerates itself on request, so your signature always shows your current game, rich presence, and point/mastery totals.

![example](https://raw.githubusercontent.com/tmfc666/ra-signatures/main/example.png)

## Features

- **Live profile stats**: hardcore points, softcore points, and games mastered, pulled from the RetroAchievements API.
- **Now Playing**: current game title, platform, rich presence ("Currently: ...") line, and game icon. Long titles automatically drop to a smaller font; long rich presence messages are truncated with an ellipsis.
- **Console icons**: the system logo (e.g. NES, SNES) is drawn inline on the Platform line, sourced from RetroAchievements' own system icons.
- **Color emoji**: emoji in game titles and rich presence render in full color (Noto Color Emoji) instead of tofu boxes, with a monochrome fallback (OpenMoji).
- **Character substitution**: typographic characters the pixel font can't render (bullets, en/em dashes, curly quotes) are swapped for ASCII lookalikes.
- **Random backgrounds**: any `.png` you drop into `./backgrounds/` joins the random rotation, with no naming convention required. Generic placeholders are included so it works out of the box.
- **Softcore overlay**: a warning overlay is applied if the account has any softcore points. Supply your own `softcore.png` to customize it.
- **Overrides**: fake the "now playing" section for specific users while their real stats stay live. Great for pranking your friends.
- **Two-layer caching**: rendered images and API responses are cached on disk, with ETag / Last-Modified support for conditional requests, to keep RetroAchievements API usage low.

## How it works

1. A request hits `/users/<username>.png`.
2. If a rendered image younger than `CACHE_TTL` exists, it's served (or `304 Not Modified` is returned if the client's copy matches).
3. Otherwise, profile and awards data are fetched (or read from the API cache), then current-game data. Users with an override skip that last call entirely.
4. The image is composed with Pillow, written to `./cache/`, and served.

All RetroAchievements API calls are serialized through a single global lock with retry/backoff, and identify themselves with a `ra-signatures/<version>` User-Agent.

## Repository layout

```
ra-signatures/
|-- app.py                  # Flask app (Gunicorn entrypoint: app:app)
|-- overrides.example.py    # copy to overrides.py to enable overrides
|-- .env.example            # copy to .env and add your API credentials
|-- requirements.txt
|-- Pixellari.ttf           # main pixel font
|-- NotoColorEmoji.ttf      # color emoji font (~10 MB)
|-- EmojiFallback.ttf       # monochrome emoji fallback (OpenMoji)
|-- softcore_default.png    # placeholder softcore overlay
|-- example.png             # README screenshot
|-- backgrounds/            # random background pool (768x192 PNGs)
|   `-- *_default.png       # generic placeholder backgrounds
|-- licenses/               # third-party license texts
`-- CHANGELOG.md
```

These are created automatically at startup and are gitignored: `cache/` (rendered PNGs), `api_cache/` (API responses and the console icon list), and `overrides/` (override icons). Your own backgrounds, `softcore.png`, `overrides.py`, and `.env` are gitignored too, so local customizations never end up in a commit.

## Requirements

### Debian/Ubuntu packages
```
python3
python3-venv
python3-pip
nginx                  # reverse proxy
certbot                # SSL certs, if proxying
python3-certbot-nginx
```

### Python dependencies
```
flask
gunicorn
pillow
python-dotenv
requests
```

## Installation

```bash
sudo git clone https://github.com/stevelaporte/ra-signatures.git /opt/ra-signatures
cd /opt/ra-signatures
sudo python3 -m venv venv
sudo venv/bin/pip install -r requirements.txt
sudo cp .env.example .env                    # then add your credentials
sudo chmod 600 .env
sudo cp overrides.example.py overrides.py    # optional
sudo chown -R <service_user>:<service_user> /opt/ra-signatures
# optional: add your own backgrounds to ./backgrounds/ (see below)
```

## Configuration

### API credentials (`.env`)

| Variable | Required | Description |
|---|---|---|
| `RA_API_USERNAME` | Yes | Your RetroAchievements username |
| `RA_API_KEY` | Yes | Your RetroAchievements Web API key, from your account settings |

```
RA_API_USERNAME=your_ra_username
RA_API_KEY=your_ra_web_api_key
```

The app refuses to start if either value is missing, with an error naming the missing setting. **Upgrading from 1.0.0:** the old `.env` placeholder used `RA_API_USER`; rename it to `RA_API_USERNAME`. Treat the API key like a password: `.env` is gitignored, and `chmod 600` keeps it readable only by its owner.

### Tunable constants (top of `app.py`)

| Constant | Default | Purpose |
|---|---|---|
| `CACHE_TTL` | `300` | Seconds a rendered PNG is reused |
| `API_CACHE_TTL` | `300` | Seconds RetroAchievements API responses are reused |
| `CONSOLE_ICON_MAP_TTL` | `86400` | Seconds the on-disk console icon list is trusted |
| `CONSOLE_ICON_HEIGHT` | `14` | Console icon height (px) on the Platform line |
| `CONSOLE_ICON_GAP` | `4` | Gap (px) between the console icon and name |
| `EMOJI_SIZE_SCALE` | `0.85` | Emoji height as a fraction of the text size |
| `EMOJI_Y_SHIFT` | `-2` | Vertical nudge (px) for emoji baseline alignment |
| `CHAR_SUBSTITUTIONS` | see source | Unsupported characters -> ASCII replacements |
| `BACKGROUND_DIR` | `./backgrounds` | Folder scanned for background PNGs |
| `SOFTCORE_OVERLAY_PATHS` | `softcore.png`, `softcore_default.png` | Overlay lookup order |

### Backgrounds
The repository ships with a few generic gradient placeholders (`backgrounds/*_default.png`) so the app works out of the box. **It looks best with real 8- and 16-bit game backgrounds**, which can't be included here for copyright reasons, so bring your own:

- Drop any `.png` into `./backgrounds/` and restart the service to pick it up. Any filename works, as long as it doesn't end in `_default.png`.
- Once at least one custom background exists, the placeholders are left out of the random pool automatically.
- Custom backgrounds are gitignored, so they stay on your server.
- Backgrounds should be **768x192**, since text positions assume that canvas size. Darker images keep the white and green text readable.
- If the folder has no PNGs at all, a plain dark background is used.

### Softcore overlay
If the account has any softcore points, an overlay is composited over the finished image. The app uses `./softcore.png` if it exists (gitignored, so your custom overlay stays local), otherwise the bundled placeholder `./softcore_default.png`. Use a 768x192 PNG; partial transparency lets the stats show through. Other sizes are stretched to fit.

### Overrides
`overrides.py` replaces the "now playing" section for specific users. Hardcore points, softcore points, and mastery count are always real. Start from the template:

```bash
cp overrides.example.py overrides.py
```

```python
OVERRIDES = {
    "someusername": {                      # keys are lowercase
        "Title": "Barbie Dreamhouse Adventures",
        "ConsoleName": "PC",
        # "ConsoleID": 7,                  # optional; enables the console icon
        "RichPresenceMsg": "Decorating the Dreamhouse",
        # "ImageIcon": "local:./overrides/other.png" | "/Images/012345.png" | None
    },
}
```

If `ImageIcon` is omitted, `./overrides/<username>.png` is used automatically when it exists. Set it to `None` to force no icon. Console IDs come from the RetroAchievements `API_GetConsoleIDs` endpoint.

`overrides.py` is loaded once at startup, so **restart the service after editing it**, then invalidate that user's cache (see [Endpoints](#endpoints)). Adding or swapping just an icon PNG only needs the invalidation.

### Unsupported characters
If a rich presence message shows a glyph Pixellari lacks, add it to `CHAR_SUBSTITUTIONS`. Use `\uXXXX` escapes for the keys and keep `app.py` ASCII-only: pasting literal non-ASCII characters through some editors or terminals saves non-UTF-8 bytes and breaks the Python import.

## Endpoints

| Route | Method | Purpose |
|---|---|---|
| `/users/<username>.png` | GET | The signature image |
| `/invalidate/<username>` | GET, POST | Delete that user's cached image and API data |
| `/invalidate_all` | GET, POST | Clear all cached images and API data |

> **The invalidation endpoints are unauthenticated.** The example Nginx config only proxies `/users/`, so call them locally on the server:
> ```bash
> curl -X POST http://127.0.0.1:5000/invalidate/someusername
> ```

## RetroAchievements API usage

Only one API request runs at a time. Run Gunicorn with **one worker and one thread** to keep it that way, and consider CDN caching (e.g. Cloudflare) in front of the app. It dramatically reduces requests to both your server and RetroAchievements.

## Running as a service

Example systemd unit, assuming the app lives in `/opt/ra-signatures/`. Use a dedicated non-root service account.

### `/etc/systemd/system/ra-signatures.service`
```ini
[Unit]
Description=RetroAchievements Signature Generator
After=network.target

[Service]
User=<service_user>
WorkingDirectory=/opt/ra-signatures
# Without this, Python buffers print() output and app errors reach the journal late
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/ra-signatures/venv/bin/gunicorn --workers=1 --threads=1 --bind 127.0.0.1:5000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ra-signatures
journalctl -u ra-signatures -f      # follow the logs
```

## Reverse proxy

Example Nginx server block for `https://ra.example.com`, with SSL via Certbot:

### `/etc/nginx/sites-available/ra-signatures`
```nginx
server {
    server_name ra.example.com;

    location /users/ {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    listen 443 ssl; # managed by Certbot
    ssl_certificate /etc/letsencrypt/live/ra.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ra.example.com/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
}

server {
    listen 80;
    server_name ra.example.com;
    return 301 https://$host$request_uri;
}
```

## Credits and third-party licenses

- **Pixellari** by [Zacchary Dempsey-Plante](https://ztdp.ca/). The author offers it free, including for commercial use, and asks only for credit for the original font. Get it from [DaFont](https://www.dafont.com/pixellari.font) or this repo.
- **Noto Color Emoji** by Google, licensed under the [SIL Open Font License 1.1](licenses/NotoColorEmoji-OFL.txt).
- **OpenMoji**: all emojis designed by [OpenMoji](https://openmoji.org/), the open-source emoji and icon project. License: [CC BY-SA 4.0](licenses/OpenMoji-CC-BY-SA-4.0.txt). Bundled as `EmojiFallback.ttf` (renamed from `OpenMoji-black-glyf.ttf`, otherwise unmodified).
- **RetroAchievements**: profile data, game icons, and console icons come from the [RetroAchievements Web API](https://api-docs.retroachievements.org/) at runtime and are not redistributed here. This project is not affiliated with RetroAchievements.

See [`licenses/`](licenses/) for the full texts.

The placeholder backgrounds and softcore overlay are original to this project and covered by its license.

## Roadmap

- Move tunables (TTLs, sizes) into `.env`
- Split `app.py` into modules (API client, rendering, routes)
- Hot-reload `overrides.py` without a restart
- Optional auth token for the invalidation endpoints
- Log HTTP status codes on RetroAchievements API failures (distinguish rate limiting from outages)
- Return 404 for nonexistent usernames instead of an all-zeros image

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## License

The source code is licensed under GPL-3.0; see [LICENSE](LICENSE). Bundled fonts and images keep their own licenses, listed above.
