# ra-signatures
Dynamically generate a .png file with RetroAchievements profile info, hosted at an unchanging URL - useful for embeds, e.g. forum signatures.

## Requirements

### Debian packages
```
python3
python3-venv
python3-pip
nginx                  # if placing behind a reverse proxy
certbot                # for SSL certs, if proxying
python3-certbot-nginx  # ditto

```
### Python dependencies
```
flask
gunicorn
requests
pillow
python-dotenv
```
## RetroAchievements API Access
API username and key are defined in the .env file and passed to the Python app via python-dotenv. The code is configured to only allow one request at a time, and I'd recommend running this with only one worker and one thread in Gunicorn to avoid tripping the RetroAchievements API rate limit. I also highly recommend adding CDN caching via Cloudflare or similar as this will greatly improve performance and reduce GET requests to your app and API requests to RetroAchievements.

## Running as a Service - Example
You can configure this to run as a service. Here's an example for running this as a systemd service on Ubuntu, assuming the app and venv are installed in `/opt/ra-signaures/`. Substitute `username` with the username of the user that will run the service (I recommend creating a dedicated non-root service account for this):

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

## To Do (last updated 2025-03-24):
- Aesthetic tweaks
  - Move game icon up (justify with top of username field)
  - Add overflow exception for rich presence text (e.g. truncate with "..." if too long)
  - Add more backgrounds
- Organizational tasks
  - Move backgrounds to their own directory and update code accordingly
