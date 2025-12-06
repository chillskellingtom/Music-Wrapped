# Deploying Apple Music Dashboard Securely

This guide covers how to deploy the dashboard so only your family can access it.

## Quick Comparison

| Method | Difficulty | Cost | Best For |
|--------|------------|------|----------|
| **Streamlit Cloud** | Easy | Free | Quick sharing, data in repo |
| **Tailscale** | Easy | Free | Private family access, data stays local |
| **Railway/Render** | Medium | Free tier | More control, private data |
| **Home Server** | Medium | Free | Full control, always available |

---

## Option 1: Streamlit Community Cloud (Easiest)

**Pros:** Free, easy, automatic HTTPS  
**Cons:** Data must be in the repo (or use cloud storage)

### Step 1: Prepare the Repository

1. Create a **private** GitHub repository
2. Push your Music-Wrapped code to it
3. Add the Apple Music data to a `data/` folder in the repo
   ```
   Music-Wrapped/
   ├── dashboard.py
   ├── apple_music_parser.py
   ├── data/
   │   └── Apple Music Activity/
   │       ├── Apple Music Play Activity.csv
   │       └── ... other files
   └── requirements.txt
   ```

### Step 2: Deploy to Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Sign in with GitHub
3. Click "New app"
4. Select your private repository
5. Set main file: `dashboard.py`
6. Click "Advanced settings" → **Secrets**

### Step 3: Add Secrets

In the Streamlit Cloud secrets section, add:

```toml
[auth]
# Individual accounts for mum and dad
[auth.users]
mum = "secure-password-for-mum"
dad = "secure-password-for-dad"

[data]
default_path = "data/Apple Music Activity"
```

### Step 4: Share the Link

Streamlit gives you a URL like:  
`https://your-app-name.streamlit.app`

Share this with the parents along with their login credentials.

---

## Option 2: Tailscale (Most Private) ⭐ RECOMMENDED

**Pros:** Data stays on your computer, very secure, free  
**Cons:** Requires Tailscale app on their devices

This lets you run the dashboard on YOUR computer while the parents access it securely from anywhere.

### Step 1: Install Tailscale

1. **On your computer:** Install from [tailscale.com](https://tailscale.com)
2. **On parents' devices:** Have them install Tailscale (iPhone, iPad, Mac, Windows)
3. Invite them to your Tailscale network (free for up to 3 users)

### Step 2: Run the Dashboard

```bash
cd Music-Wrapped
streamlit run dashboard.py --server.address 0.0.0.0 -- \
  --data-dir "/path/to/Apple Music Activity"
```

### Step 3: Get Your Tailscale IP

```bash
tailscale ip -4
# Example output: 100.64.0.1
```

### Step 4: Share with Parents

Send them the link:  
`http://100.64.0.1:8501`

They can **only** access this if they're on your Tailscale network!

### Optional: Keep it Running

Use `tmux` or `screen` to keep it running:
```bash
tmux new -s dashboard
streamlit run dashboard.py --server.address 0.0.0.0 -- --data-dir "/path/to/data"
# Press Ctrl+B, then D to detach
```

---

## Option 3: Railway/Render (Free Tier)

**Pros:** Professional hosting, free tier available  
**Cons:** More setup, data must be uploaded

### Railway.app

1. Sign up at [railway.app](https://railway.app)
2. Create new project → Deploy from GitHub
3. Select your private repo
4. Add environment variables:
   ```
   STREAMLIT_SERVER_PORT=8501
   ```
5. Add secrets via Railway dashboard

### Render.com

1. Sign up at [render.com](https://render.com)
2. Create new Web Service
3. Connect your private GitHub repo
4. Set build command: `pip install -r requirements.txt`
5. Set start command: `streamlit run dashboard.py --server.port $PORT`

---

## Option 4: Home Server (Always On)

If you have a Mac Mini, NAS, or Raspberry Pi:

### Using Docker

Create `Dockerfile`:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 8501
CMD ["streamlit", "run", "dashboard.py", "--server.address", "0.0.0.0"]
```

Run:
```bash
docker build -t music-dashboard .
docker run -d -p 8501:8501 -v /path/to/data:/data music-dashboard
```

### Expose via Cloudflare Tunnel (Free)

1. Install [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/)
2. Create tunnel: `cloudflared tunnel create music-dashboard`
3. Configure to point to `localhost:8501`
4. Add Cloudflare Access policy to restrict to specific emails

---

## Security Checklist

- [ ] Use a **private** GitHub repository
- [ ] Never commit `secrets.toml` (it's in `.gitignore`)
- [ ] Use strong, unique passwords for each user
- [ ] If using Streamlit Cloud, ensure repo is private
- [ ] Consider Tailscale for maximum privacy (data never leaves your network)

---

## Quick Start: Local with Auth

For immediate testing with authentication:

1. Edit `.streamlit/secrets.toml`:
   ```toml
   [auth.users]
   mum = "your-chosen-password"
   dad = "another-password"
   ```

2. Run:
   ```bash
   streamlit run dashboard.py -- --data-dir "/path/to/Apple Music Activity"
   ```

3. Open http://localhost:8501 and log in!

---

## Questions?

- **Streamlit Cloud docs:** https://docs.streamlit.io/streamlit-community-cloud
- **Tailscale setup:** https://tailscale.com/kb/1017/install
- **Cloudflare Access:** https://developers.cloudflare.com/cloudflare-one/policies/access/

