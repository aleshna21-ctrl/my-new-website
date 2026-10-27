#!/usr/bin/env python3
"""
deploy_vps_mock_payload.py
==========================
Automated deployment script to stage synthetic diode payloads on Hostinger VPS.

Workflow:
1. Connects to the Hostinger VPS via SSH (supports auto-detected SSH keys).
2. Deploys remote Python script `mock_vps_payload.py` into `/opt/aios`.
3. Ensures `mock_vps_payload.py` generates `inbound_queue.json` with required schema:
   - source: "hostinger_web_ui"
   - task: "Extract the core requirements from this sample client inquiry"
   - priority: "high"
   - timestamp: <unix_timestamp>
4. Executes `mock_vps_payload.py` remotely and verifies `inbound_queue.json` is staged
   and ready for the local Windows diode to pull down.
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [VPSDeploy] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("VPSDeploy")

DEFAULT_VPS_IP = os.environ.get("VPS_IP", "2.25.249.27")
DEFAULT_VPS_USER = os.environ.get("VPS_USER", "root")
DEFAULT_REMOTE_DIR = os.environ.get("REMOTE_DIR", "/opt/aios")

REMOTE_MOCK_SCRIPT_CONTENT = '''#!/usr/bin/env python3
"""
mock_vps_payload.py - Synthetic Payload Generator on Hostinger VPS
Generated and staged via automated deployment for the Local-Core, Cloud-Relay diode.
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

def create_inbound_payload(output_path: str = "/opt/aios/inbound_queue.json") -> dict:
    now_ts = time.time()
    iso_time = datetime.now(timezone.utc).isoformat()
    
    # Required diode payload contract
    payload = {
        "source": "hostinger_web_ui",
        "task": "Extract the core requirements from this sample client inquiry",
        "priority": "high",
        "timestamp": int(now_ts),
        "unix_timestamp": now_ts,
        "created_at": iso_time,
        "status": "staged_for_diode",
        "relay_node": "hostinger_vps_relay"
    }
    
    target_file = Path(output_path).resolve()
    target_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Atomic write to avoid partial reads by downstream diode
    tmp_file = target_file.with_suffix(".tmp")
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    tmp_file.replace(target_file)
    
    # Also replicate to data and inbox subdirectories for diode compatibility
    for sub in ["data", "inbox"]:
        sub_dir = target_file.parent / sub
        if sub_dir.is_dir():
            sub_file = sub_dir / "inbound_queue.json"
            try:
                with open(sub_file, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2)
            except Exception as e:
                print(f"[WARN] Could not mirror to {sub_file}: {e}", file=sys.stderr)

    return payload

if __name__ == "__main__":
    out_path = sys.argv[1] if len(sys.argv) > 1 else "/opt/aios/inbound_queue.json"
    staged = create_inbound_payload(out_path)
    print(f"STAGED_PAYLOAD_PATH={out_path}")
    print(json.dumps(staged, indent=2))
'''


def locate_ssh_key(explicit_key: Optional[str] = None) -> Optional[str]:
    """Finds available SSH private key for connecting to Hostinger VPS."""
    if explicit_key and Path(explicit_key).is_file():
        return str(Path(explicit_key).resolve())

    ssh_dir = Path.home() / ".ssh"
    candidates = [
        ssh_dir / "id_rsa",
        ssh_dir / "id_ed25519",
    ]
    for cand in candidates:
        if cand.is_file():
            return str(cand.resolve())
    return None


def execute_ssh_command(
    vps_ip: str,
    vps_user: str,
    remote_command: str,
    key_path: Optional[str] = None,
    timeout_sec: int = 20,
    check: bool = True
) -> Tuple[int, str, str]:
    """Runs a remote command over SSH."""
    target = f"{vps_user}@{vps_ip}"
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={timeout_sec}"]
    if key_path:
        cmd.extend(["-i", key_path])
    cmd.extend([target, remote_command])

    logger.debug(f"Executing SSH: {' '.join(cmd[:-1])} '{remote_command}'")
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout_sec + 5
    )
    if check and proc.returncode != 0:
        logger.error(f"SSH command failed with code {proc.returncode}: {proc.stderr.strip()}")
        raise RuntimeError(f"SSH failed ({proc.returncode}): {proc.stderr.strip()}")
    return proc.returncode, proc.stdout, proc.stderr


def deploy_mock_payload_to_vps(
    vps_ip: str = DEFAULT_VPS_IP,
    vps_user: str = DEFAULT_VPS_USER,
    remote_dir: str = DEFAULT_REMOTE_DIR,
    key_path: Optional[str] = None,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Connects to Hostinger VPS, stages mock_vps_payload.py, executes it,
    and returns verified inbound_queue.json content.
    """
    resolved_key = locate_ssh_key(key_path)
    logger.info(f"Connecting to Hostinger VPS: {vps_user}@{vps_ip} (Key: {resolved_key or 'default-agent'})")

    if dry_run:
        logger.info("[DRY_RUN] Would stage mock_vps_payload.py and execute it remotely.")
        return {
            "status": "dry_run_success",
            "vps": f"{vps_user}@{vps_ip}",
            "remote_dir": remote_dir
        }

    # Step 1: Verify connectivity & ensure remote directory exists
    test_cmd = f"mkdir -p {remote_dir} && echo VPS_READY"
    code, stdout, stderr = execute_ssh_command(vps_ip, vps_user, test_cmd, resolved_key)
    if "VPS_READY" not in stdout:
        raise ConnectionError(f"Hostinger VPS handshake failed: {stderr}")
    logger.info("Hostinger VPS connectivity verified.")

    # Step 2: Create remote Python script `mock_vps_payload.py`
    remote_script_path = f"{remote_dir}/mock_vps_payload.py"
    logger.info(f"Staging remote Python script at {remote_script_path}...")
    
    # Safely stream content into the remote file using EOF heredoc
    remote_install_cmd = f"cat << 'EOF' > {remote_script_path}\n{REMOTE_MOCK_SCRIPT_CONTENT}\nEOF\nchmod +x {remote_script_path}"
    execute_ssh_command(vps_ip, vps_user, remote_install_cmd, resolved_key)
    logger.info("Remote script mock_vps_payload.py staged and set to executable.")

    # Step 3: Execute remote Python script immediately
    remote_queue_path = f"{remote_dir}/inbound_queue.json"
    logger.info(f"Executing {remote_script_path} remotely to write {remote_queue_path}...")
    exec_cmd = f"python3 {remote_script_path} {remote_queue_path}"
    code, stdout, stderr = execute_ssh_command(vps_ip, vps_user, exec_cmd, resolved_key)
    logger.info("Remote script execution complete.")

    # Step 4: Verify and retrieve staged payload directly from VPS
    verify_cmd = f"cat {remote_queue_path}"
    code, stdout, stderr = execute_ssh_command(vps_ip, vps_user, verify_cmd, resolved_key)
    
    try:
        staged_payload = json.loads(stdout.strip())
    except Exception as e:
        logger.error(f"Failed to parse remote JSON output: {stdout}")
        raise ValueError(f"Invalid remote JSON: {e}")

    # Validate required fields
    required_fields = ["source", "task", "priority", "timestamp"]
    for field in required_fields:
        if field not in staged_payload:
            raise ValueError(f"Missing required field '{field}' in staged payload")

    if staged_payload.get("source") != "hostinger_web_ui":
        raise ValueError(f"Invalid source: {staged_payload.get('source')}")
    if staged_payload.get("task") != "Extract the core requirements from this sample client inquiry":
        raise ValueError(f"Invalid task description: {staged_payload.get('task')}")
    if staged_payload.get("priority") != "high":
        raise ValueError(f"Invalid priority: {staged_payload.get('priority')}")

    logger.info("Successfully validated staged payload on Hostinger VPS!")
    logger.info(f"Remote Payload: {json.dumps(staged_payload, indent=2)}")

    return {
        "status": "success",
        "vps_host": vps_ip,
        "remote_file": remote_queue_path,
        "payload": staged_payload
    }


def main():
    parser = argparse.ArgumentParser(description="Stage synthetic payload on Hostinger VPS for diode verification.")
    parser.add_argument("--vps-ip", default=DEFAULT_VPS_IP, help="Hostinger VPS IP address")
    parser.add_argument("--vps-user", default=DEFAULT_VPS_USER, help="Hostinger VPS SSH username")
    parser.add_argument("--remote-dir", default=DEFAULT_REMOTE_DIR, help="Remote AIOS directory on VPS")
    parser.add_argument("--key-path", default=None, help="Path to private SSH key")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without executing SSH commands")

    args = parser.parse_args()

    try:
        result = deploy_mock_payload_to_vps(
            vps_ip=args.vps_ip,
            vps_user=args.vps_user,
            remote_dir=args.remote_dir,
            key_path=args.key_path,
            dry_run=args.dry_run
        )
        print("\n" + "="*60)
        print("[SUCCESS] HOSTINGER VPS DIODE STAGING COMPLETE")
        print("="*60)
        print(f"VPS Host:     {args.vps_user}@{args.vps_ip}")
        print(f"Staged File:  {result.get('remote_file')}")
        print(f"Source:       {result.get('payload', {}).get('source')}")
        print(f"Task:         {result.get('payload', {}).get('task')}")
        print(f"Priority:     {result.get('payload', {}).get('priority')}")
        print(f"Timestamp:    {result.get('payload', {}).get('timestamp')}")
        print("="*60)
        sys.exit(0)
    except Exception as exc:
        logger.error(f"Deployment failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
