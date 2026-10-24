#!/usr/bin/env bash
# ==============================================================================
# AIOS Command Center — Hostinger VPS Backup & Nginx Basic Auth Utility
# Target VPS: root@2.25.249.27 (/opt/aios/vps-backup-and-auth.sh)
#
# Subcommands:
#   ./vps-backup-and-auth.sh backup
#   ./vps-backup-and-auth.sh install-cron
#   ./vps-backup-and-auth.sh restore <path-to-archive.tar.gz>
#   ./vps-backup-and-auth.sh setup-basic-auth <username> <password>
# ==============================================================================
set -euo pipefail

AIOS_DIR="${AIOS_DIR:-/opt/aios}"
BACKUP_DIR="${BACKUP_DIR:-/opt/aios/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
HTPASSWD_FILE="/etc/nginx/.htpasswd_aios"

cmd="${1:-help}"

run_backup() {
    mkdir -p "$BACKUP_DIR"
    chmod 700 "$BACKUP_DIR"
    ts="$(date -u +%Y%m%d-%H%M%S)"
    archive="$BACKUP_DIR/aios-backup-${ts}.tar.gz"

    echo "[AIOS Backup] Exporting aios-data and aios-scratch volumes to $archive ..."
    docker run --rm \
        -v aios-data:/source/data:ro \
        -v aios-scratch:/source/scratch:ro \
        -v "$BACKUP_DIR":/backup \
        alpine:3.20 \
        tar -czf "/backup/aios-backup-${ts}.tar.gz" -C /source data scratch

    chmod 600 "$archive"
    size_kb="$(du -k "$archive" | cut -f1)"
    echo "[AIOS Backup] Created $archive (${size_kb} KB)."

    # Prune backups older than RETENTION_DAYS
    find "$BACKUP_DIR" -maxdepth 1 -type f -name "aios-backup-*.tar.gz" -mtime +"$RETENTION_DAYS" -delete
    echo "[AIOS Backup] Retention policy applied (kept last ${RETENTION_DAYS} days)."
}

install_cron() {
    chmod +x "$AIOS_DIR/vps-backup-and-auth.sh"
    cron_file="/etc/cron.d/aios-backup"
    cat > "$cron_file" <<EOF
# Daily automated backup of AIOS Command Center Docker volumes at 03:15 UTC
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin
15 3 * * * root $AIOS_DIR/vps-backup-and-auth.sh backup >> /var/log/aios-backup.log 2>&1
EOF
    chmod 644 "$cron_file"
    echo "[AIOS Cron] Installed daily backup schedule at $cron_file (03:15 UTC)."
    run_backup
}

restore_backup() {
    archive_path="${2:-}"
    if [[ -z "$archive_path" || ! -f "$archive_path" ]]; then
        echo "Usage: $0 restore /opt/aios/backups/aios-backup-YYYYMMDD-HHMMSS.tar.gz" >&2
        exit 1
    fi
    abs_archive="$(realpath "$archive_path")"
    archive_dir="$(dirname "$abs_archive")"
    archive_name="$(basename "$abs_archive")"

    echo "[AIOS Restore] Restoring $abs_archive into aios-data and aios-scratch..."
    docker run --rm \
        -v aios-data:/target/data \
        -v aios-scratch:/target/scratch \
        -v "$archive_dir":/backup:ro \
        alpine:3.20 \
        sh -c "tar -xzf '/backup/$archive_name' -C /target && chown -R 10001:10001 /target/data /target/scratch"

    echo "[AIOS Restore] Restore complete. Restarting container..."
    (cd "$AIOS_DIR" && docker compose restart)
}

setup_basic_auth() {
    auth_user="${2:-}"
    auth_pass="${3:-}"
    if [[ -z "$auth_user" || -z "$auth_pass" ]]; then
        echo "Usage: $0 setup-basic-auth <username> <password>" >&2
        exit 1
    fi

    if ! command -v htpasswd >/dev/null 2>&1; then
        echo "[AIOS Auth] Installing apache2-utils for htpasswd..."
        apt-get update -y && apt-get install -y apache2-utils
    fi

    mkdir -p /etc/nginx
    htpasswd -Bbc "$HTPASSWD_FILE" "$auth_user" "$auth_pass"
    chown root:www-data "$HTPASSWD_FILE" 2>/dev/null || true
    chmod 640 "$HTPASSWD_FILE"
    echo "[AIOS Auth] Wrote bcrypt credentials for user '$auth_user' to $HTPASSWD_FILE"

    nginx_conf="/etc/nginx/sites-available/aios.conf"
    if [[ ! -f "$nginx_conf" ]]; then
        cat > "$nginx_conf" <<'EOF'
server {
    listen 80;
    listen [::]:80;
    server_name 2.25.249.27 _;

    # HTTP Basic Authentication Gate
    auth_basic "AIOS Command Center — Restricted";
    auth_basic_user_file /etc/nginx/.htpasswd_aios;

    location / {
        proxy_pass http://127.0.0.1:5050;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Real-time SSE telemetry stream settings (unbuffered)
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
        chunked_transfer_encoding off;

        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
EOF
        ln -sf "$nginx_conf" /etc/nginx/sites-enabled/aios.conf
        rm -f /etc/nginx/sites-enabled/default
        echo "[AIOS Auth] Created $nginx_conf with Basic Auth + SSE proxy."
    else
        echo "[AIOS Auth] Existing $nginx_conf detected. Ensure it includes:"
        echo "    auth_basic \"AIOS Command Center — Restricted\";"
        echo "    auth_basic_user_file /etc/nginx/.htpasswd_aios;"
    fi

    if command -v nginx >/dev/null 2>&1; then
        nginx -t && systemctl reload nginx
        echo "[AIOS Auth] Nginx reloaded successfully."
    fi
}

case "$cmd" in
    backup)
        run_backup
        ;;
    install-cron)
        install_cron
        ;;
    restore)
        restore_backup "$@"
        ;;
    setup-basic-auth)
        setup_basic_auth "$@"
        ;;
    *)
        echo "Usage: $0 {backup|install-cron|restore <archive>|setup-basic-auth <user> <pass>}"
        exit 1
        ;;
esac
