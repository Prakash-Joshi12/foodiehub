# FoodieNepal — Real-World Edition

A full-stack Nepali food-delivery app (Flask + SQLAlchemy + Leaflet) — order
tracking, live delivery GPS, restaurant admin, payments (demo QR), reviews,
and notifications. This edition takes the working demo and makes it
**deployable as a real, publicly-reachable web application**, while staying
100% runnable locally with zero setup.

---

## 1. Run it locally (2 minutes)

```bash
python -m pip install -r requirements.txt
python server.py
```

Open **http://127.0.0.1:5000**

That's it — it creates its own SQLite database on first run and seeds demo
accounts automatically. No `.env` file is required for local use.

**Demo accounts** (role: password)
| Role | Email | Password |
|---|---|---|
| Admin | admin@foodienepal.com | admin123 |
| Customer | customer@foodienepal.com | customer123 |
| Delivery | delivery@foodienepal.com | delivery123 |
| Restaurant owner | owner@foodienepal.com | owner123 |

### Access it from your phone / another device on the same Wi-Fi
```bash
HOST=0.0.0.0 python server.py
```
Then find your computer's local IP (`ipconfig` on Windows / `ifconfig` or
`ip addr` on Mac/Linux) and open `http://<that-ip>:5000` on your phone.

---

## 2. Turn it into a real, internet-reachable application

The app is now fully environment-driven — the same code runs in "demo mode"
or "production mode" depending on env vars, no code edits needed. See
`.env.example` for the full list.

### Option A — Docker (recommended, works anywhere)
Ships with a `Dockerfile` and a `docker-compose.yml` that runs the app
**and** a real PostgreSQL database together:
```bash
docker compose up --build
```
Open **http://localhost:5000**. Data persists in a Docker volume across
restarts. This is the closest thing to how it would run on a real server.

### Option B — Deploy to a cloud platform (Render, Railway, Fly.io, etc.)
1. Push this folder to a GitHub repo.
2. Create a new **Web Service** on the platform and point it at the repo —
   it will detect the `Procfile` (`gunicorn server:app`) automatically.
3. Add a managed **PostgreSQL** database from the same platform and copy its
   connection string into an environment variable named `DATABASE_URL`.
4. Set these environment variables in the platform's dashboard:
   - `FLASK_ENV=production`
   - `SECRET_KEY` = output of `python -c "import secrets; print(secrets.token_hex(32))"`
   - `DATABASE_URL` = your Postgres connection string
5. Deploy. The platform gives you a public HTTPS URL
   (e.g. `https://foodienepal.onrender.com`) — that's how customers, delivery
   partners and restaurant owners actually access the app.
6. Point a custom domain (e.g. `foodienepal.com`) at that URL via your
   domain registrar's DNS if you have one.

### Option C — Your own VPS (DigitalOcean, Linode, AWS EC2, a home server…)
```bash
git clone <your-repo> && cd FoodieNepal_Advanced
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then edit SECRET_KEY, DATABASE_URL, FLASK_ENV=production
gunicorn server:app --bind 0.0.0.0:5000 --workers 3
```
Put **Nginx or Caddy** in front of it as a reverse proxy for HTTPS (Caddy
gets you free auto-renewing TLS with a couple of lines), and run the
gunicorn process under `systemd` or inside the provided `Dockerfile` so it
restarts automatically on crash/reboot.

---

## 3. What makes this the "real-world" edition

| Concern | Demo behaviour | This edition |
|---|---|---|
| Config | Hard-coded secret key & SQLite path | Everything read from environment vars (`.env.example`) |
| Database | SQLite only | SQLite locally, **PostgreSQL** in production via `DATABASE_URL` |
| Web server | Flask's built-in dev server (`debug=True`) | **gunicorn** in production (`Procfile`, `Dockerfile`); dev server only for local use |
| Secrets | Committed default secret key | Refuses to boot in production without a real `SECRET_KEY` |
| Cookies | Default | `HttpOnly`, `SameSite=Lax`, and `Secure` automatically once `FLASK_ENV=production` (i.e. once served over HTTPS) |
| Packaging | Run from source only | `Dockerfile` + `docker-compose.yml` for one-command, reproducible deploys |
| Network access | Localhost only | `HOST`/`PORT` configurable — LAN, container, or public cloud |

### Still simulation, by design
- **Payments**: eSewa/Khalti QR screens are demo flows that generate a real,
  scannable QR encoding a fake reference — no money moves. Real collection
  requires signing up for merchant accounts with eSewa/Khalti/IME
  Pay/Fonepay and verifying their webhook callbacks server-side.
- **Delivery GPS**: uses the delivery partner's own phone browser
  (`navigator.geolocation.watchPosition`) as a stand-in for a real courier
  app's authenticated location feed — this part already works with real
  device GPS, no changes needed to go live.
- **File uploads** (review photos, restaurant images) are saved to local
  disk (`static/uploads/`). For a multi-server production deployment, point
  this at cloud object storage (S3, Cloudflare R2, etc.) instead so uploads
  survive redeploys and scale across instances.

---

## Architecture
- Admin panel receives order, payment, delivery, restaurant and review activity.
- Restaurant owners receive new order and review notifications.
- Delivery partners can accept unassigned orders and share live GPS while delivering.
- Customers can search restaurants by province or geolocation, track deliveries
  live on the map, and leave photo reviews.

## Feature tour (unchanged from prior edition)
- `home.html` — animated hero, live search + province filter, "near me"
  geolocation sort, restaurant cards with star ratings, live Leaflet map.
- `auth.html` — animated login/register tabs, role picker.
- `restaurant.html` — menu grouped by category, add-to-cart, star-rating
  review form with photo upload.
- `cart.html` — AJAX quantity stepper, live-updating totals.
- `checkout.html` / `payment.html` — payment-method picker, animated demo
  QR for eSewa/Khalti, reference confirmation flow.
- `orders.html` — animated status timeline, role-specific actions, and a
  live GPS-sharing button for delivery partners.
- `dashboard.html` — role-aware quick actions, animated counters, notifications.
- `admin.html` — restaurant approvals, users, orders, live activity feed,
  direct messaging and role-wide broadcasts.
- `static/track.html` — real-time delivery tracking map, polling every 5s.

## Files added in this edition
```
.env.example        # every configurable setting, documented
Procfile             # for Render/Railway/Heroku-style platforms
Dockerfile           # containerized production image
docker-compose.yml   # app + real Postgres, one command
.gitignore / .dockerignore
```
