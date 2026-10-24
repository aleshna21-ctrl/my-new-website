# AIOS Command Center — Hostinger VPS Deployment Guide

This guide walks you through deploying your **AIOS Command Center** to a **Hostinger VPS** using Docker and Docker Compose.

---

## 1. Prerequisites on Hostinger VPS

1. **Hostinger VPS** running Ubuntu 22.04 LTS or 24.04 LTS.
2. **Docker & Docker Compose** installed.
   - If not already installed, run on your VPS:
     ```bash
     sudo apt update && sudo apt upgrade -y
     curl -fsSL https://get.docker.com -o get-docker.sh
     sudo sh get-docker.sh
     sudo apt install -y docker-compose-plugin
     sudo usermod -aG docker $USER
     # Log out and log back in for docker group to take effect
     ```
3. Open firewall port `5050` (or `80`/`443` if using Nginx reverse proxy):
   - In Hostinger hPanel -> **VPS** -> **Security** -> **Firewall**, add an allow rule for port `5050` (TCP).
   - Or via UFW on the VPS:
     ```bash
     sudo ufw allow 5050/tcp
     sudo ufw allow 80/tcp
     sudo ufw allow 443/tcp
     sudo ufw enable
     ```

---

## 2. Quick Deploy

### Option A: One-Command Automated Deploy from Windows PowerShell
From your local `c:\Users\alesh\jev-workspace\hud-interface` folder, run [`deploy-hostinger.ps1`](file:///c:/Users/alesh/jev-workspace/hud-interface/deploy-hostinger.ps1):
```powershell
# Preview the deployment bundle and remote commands without connecting:
.\deploy-hostinger.ps1 -DryRun

# Package, upload via SCP, build, launch, and verify on root@2.25.249.27:
.\deploy-hostinger.ps1

# Or bind strictly to 127.0.0.1 if using Nginx reverse proxy on the VPS:
.\deploy-hostinger.ps1 -BindIp "127.0.0.1"
```

---

### Option B: Manual 3-Step Deploy

#### Step 1: Transfer Project Files to your VPS
SSH into your VPS (`2.25.249.27`) and create an application directory:
```bash
ssh root@2.25.249.27
mkdir -p /opt/aios
cd /opt/aios
```

Copy your `hud-interface` files to `/opt/aios` via `git clone` or `rsync`:
```bash
# Example using rsync from your local machine:
rsync -avz --exclude '.git' --exclude '__pycache__' ./ root@2.25.249.27:/opt/aios/
```

### Step 2: Configure Environment
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Edit `.env` if desired (e.g. set your timezone `TZ=America/New_York`):
```bash
nano .env
```

### Step 3: Launch with Docker Compose
Run the following command to build and launch the container in the background:
```bash
docker compose up -d --build
```

Verify that the container is running and healthy:
```bash
docker compose ps
```
You should see:
```text
NAME                  IMAGE                        COMMAND                  SERVICE    STATUS
aios-command-center   aios-command-center:latest   "python hud_server.py"   aios-app   Up (healthy)
```

Now open your browser and navigate to:
```text
http://2.25.249.27:5050/
```

---

## 3. Production Domain & SSL (Optional Reverse Proxy with Nginx)

To access your command center securely over HTTPS at `https://aios.yourdomain.com`:

1. In `.env`, bind the AIOS container to loopback only:
   ```env
   HUD_BIND_IP=127.0.0.1
   HUD_PORT=5050
   ```
   Restart the container:
   ```bash
   docker compose up -d
   ```

2. Install Nginx & Certbot on the VPS:
   ```bash
   sudo apt install -y nginx certbot python3-certbot-nginx
   ```

3. Create `/etc/nginx/sites-available/aios.conf`:
   ```nginx
   server {
       server_name aios.yourdomain.com;

       location / {
           proxy_pass http://127.0.0.1:5050;
           proxy_http_version 1.1;

           # SSE streaming & WebSocket support
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection "upgrade";
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;

           # Prevent proxy buffering for the live SSE telemetry stream
           proxy_buffering off;
           proxy_cache off;
           chunked_transfer_encoding off;
       }
   }
   ```

4. Enable site and issue free SSL certificate:
   ```bash
   sudo ln -s /etc/nginx/sites-available/aios.conf /etc/nginx/sites-enabled/
   sudo nginx -t && sudo systemctl reload nginx
   sudo certbot --nginx -d aios.yourdomain.com
   ```

---

## 4. Syncing your Second Brain (Obsidian Vault)

The compose configuration mounts `./vault` into `/app/vault:ro` (read-only).
- To sync notes from your Second Brain into the VPS:
  ```bash
  mkdir -p /opt/aios/vault
  # Copy your .md files or sync via rsync / git:
  rsync -avz --exclude '.obsidian' /path/to/second-brain/ root@2.25.249.27:/opt/aios/vault/
  ```
- Click **`↻ Rescan`** in the Obsidian widget header on the dashboard to immediately index newly added notes into the live graph.

---

## 5. Automated Volume Backups & Nginx Basic Auth (`vps-backup-and-auth.sh`)

Your deployment bundle includes [`vps-backup-and-auth.sh`](file:///c:/Users/alesh/jev-workspace/hud-interface/vps-backup-and-auth.sh) (installed to `/opt/aios/vps-backup-and-auth.sh` on `2.25.249.27`).

### A. Automated Daily Backups (`aios-data` + `aios-scratch`)
```bash
# 1. Run an immediate snapshot backup into /opt/aios/backups/ (14-day retention):
/opt/aios/vps-backup-and-auth.sh backup

# 2. Install the daily 03:15 UTC cron job (/etc/cron.d/aios-backup) and run an initial backup:
/opt/aios/vps-backup-and-auth.sh install-cron

# 3. Restore a backup archive into the Docker volumes:
/opt/aios/vps-backup-and-auth.sh restore /opt/aios/backups/aios-backup-YYYYMMDD-HHMMSS.tar.gz
```
*(Or pass `-InstallBackupCron` when running `.\deploy-hostinger.ps1 -InstallBackupCron` from Windows).*

### B. One-Command Nginx HTTP Basic Authentication
To protect `http://2.25.249.27` (or your domain) with bcrypt-hashed HTTP Basic Auth:
```bash
/opt/aios/vps-backup-and-auth.sh setup-basic-auth admin "YourStrongPasswordHere"
```
This automatically installs `apache2-utils`, writes `/etc/nginx/.htpasswd_aios` (`chmod 640`), configures `/etc/nginx/sites-available/aios.conf` with `auth_basic` and unbuffered SSE proxy settings, and reloads Nginx.

---

## 6. Useful Maintenance Commands

- **View Live Logs:**
  ```bash
  docker compose logs -f
  ```
- **Restart Application:**
  ```bash
  docker compose restart
  ```
- **Stop Application:**
  ```bash
  docker compose down
  ```
- **Update Application:**
  ```bash
  git pull
  docker compose up -d --build
  ```
