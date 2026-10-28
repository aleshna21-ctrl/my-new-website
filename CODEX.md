# CODEX.md — AIOS Command Center Universal Agent & Platform Contract

> **Universal Runtime & Compatibility Specification for Codex, Claude Code, Cursor, GitHub Actions, and Hostinger VPS.**

---

## 1. System Identity & Core Invariant

- **System Name**: AIOS Command Center & Human-on-the-Loop (HOTL) Operations Cockpit.
- **Architectural Category**: Multi-agent observability, telemetry stream engine, scheduled task monitor, and diode queue manager.
- **CRITICAL INVARIANT**: **STRICTLY NOT A TRADING BOT**.
  - This system does NOT execute financial trades, manage broker capital, or run live market arbitrage loops.
  - Any historical references to "JEV Trading" or "Market State" in legacy nodes are purely **analytical mock data models**, read-only schema simulations, and architectural validation fixtures.
  - The primary function is an operational cockpit providing real-time telemetry, cron scheduling, and multi-agent coordination.

---

## 2. Canonical Remotes & Release Targets

| Target | Specification | Details |
| :--- | :--- | :--- |
| **Primary Git Remote** | `origin` | `https://github.com/aleshna21-ctrl/my-new-website.git` |
| **Hostinger VPS Target** | `2.25.249.27:5050` | Deployed via Docker Compose (`Dockerfile` + `compose.yml`) |
| **CI/CD Pipeline** | GitHub Actions | `.github/workflows/deploy.yml` (SSH keys: `HOSTINGER_SSH_KEY` / `APLHA2`) |
| **Excluded Remotes** | `aplha2` | Purged. Strictly forbidden as a separate repository remote. |

---

## 3. Cross-Platform Portability Rules

To maintain seamless compatibility across Windows, Linux (Hostinger Ubuntu / Debian), macOS, containerized Docker sandboxes, and cloud agent runtimes (Codex, Antigravity, GitHub Codespaces):

1. **Zero Hardcoded Paths**:
   - NEVER hardcode absolute paths like `C:\Users\...` or `G:\...`.
   - Always resolve paths dynamically using `pathlib.Path`:
     ```python
     HUD_ROOT = Path(os.environ.get("HUD_DIR", str(Path(__file__).resolve().parent)))
     WORKSPACE_ROOT = Path(os.environ.get("JEV_PROJECT_ROOT", str(HUD_ROOT.parent)))
     ```
   - Provide graceful fallback checks with `.exists()` when linking external directories (e.g. `second-brain` or `mark-lvi`).
2. **Deterministic Line Endings**:
   - Enforced via `.gitattributes` (`* text=auto eol=lf`).
   - Shell scripts (`*.sh`) and Python files (`*.py`) must always use LF line endings.
3. **Environment Isolation**:
   - All runtime configuration flows through `.env` (template provided in `.env.example`).
   - Default port: `HUD_PORT=5050`. Default binding: `HUD_BIND_IP=0.0.0.0` (or `127.0.0.1` behind reverse proxy).

---

## 4. Standard Operational Commands

### Local Development & Execution
```bash
# 1. Run full test suite (292 tests)
python -m pytest tests/

# 2. Start Command Center HUD Server (Standalone)
python hud_server.py

# 3. Start Command Center in Production Supervisor Mode
python app.py
```

### Docker Containerization (Hostinger VPS)
```bash
# 1. Build and launch Docker Compose stack in background
docker compose up -d --build

# 2. Inspect running container status
docker compose ps

# 3. View live server logs
docker compose logs -f aios

# 4. Stop stack
docker compose down
```

### Deployment
```bash
# Manual deploy to Hostinger VPS
./deploy-hostinger.sh

# Or dry-run inspection
./deploy-hostinger.sh --dry-run
```

---

## 5. REST & Streaming API Surface

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/api/os/telemetry` | `GET` | System heartbeat, health state, and SHA256 integrity hash |
| `/api/stream/events` | `GET` | Real-time Server-Sent Events (SSE) telemetry stream |
| `/api/cron/monitor` | `GET` | Scheduled jobs roster, next run countdowns, and execution status |
| `/api/cron/trigger` | `POST` | Manual execution trigger for scheduled agent jobs |
| `/api/cron/toggle` | `POST` | Enable/pause scheduled cron job triggers |
| `/api/kanban/queue` | `GET` | Active multi-agent task queue categorized by status |
| `/api/omnibus/bundle` | `GET` | Second Brain Ring 0-3 Graph, Diode Queues, and Capability Matrix |
| `/api/board` | `GET/POST` | AIOS HOTL operator board task tracking |

---

## 6. Directory Structure Reference

```text
hud-interface/
├── .github/workflows/deploy.yml  # Hostinger SSH CI/CD deployment workflow
├── Dockerfile                    # Container specification for Python 3.12-slim
├── compose.yml                   # Docker Compose specification with volume persistence
├── CODEX.md                      # Universal agent contract and runtime specification (this file)
├── README.md                     # System documentation and setup guide
├── DEPLOY_HOSTINGER.md           # Hostinger deployment manual and troubleshooting
├── app.py                        # Production application wrapper
├── hud_server.py                 # Core AIOS HTTP server, SSE stream engine & cron monitor
├── hud/                          # Core backend modules
│   ├── omnibus.py                # Graph indexer, untrusted data boundary, and diode manager
│   ├── os_dashboard.py           # Board task manager, daily horizon scheduler, state store
│   ├── je_cheap_read.py          # Level 8 cheap reads & isolated file inspector
│   ├── jev_multi_file.py         # Level 9 multi-file recursive vault scout
│   └── routes/                   # HTTP Route handlers
│       ├── stream_routes.py      # SSE stream & cron endpoints
│       ├── ledger_routes.py      # SQLite job ledger endpoints
│       └── cortex_routes.py      # Credit & token quota monitor
├── static/                       # Client assets, Three.js 3D graph visualizer, and CSS
├── tests/                        # Pytest suite (27 test files, 292 tests)
└── vault/                        # AIOS core markdown specifications & operational taxonomies
```
