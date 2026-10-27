#!/usr/bin/env python3
"""
Unit tests for deploy_vps_mock_payload.py
"""

import json
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

from deploy_vps_mock_payload import (
    locate_ssh_key,
    execute_ssh_command,
    deploy_mock_payload_to_vps,
    REMOTE_MOCK_SCRIPT_CONTENT
)


class TestDeployVpsMockPayload(unittest.TestCase):
    def test_locate_ssh_key_prefers_existing_key(self):
        with patch("pathlib.Path.is_file") as mock_is_file:
            mock_is_file.return_value = True
            key = locate_ssh_key()
            self.assertIsNotNone(key)

    def test_remote_script_content_contains_required_fields(self):
        # The deployed script must declare the exact fields requested
        self.assertIn('"source": "hostinger_web_ui"', REMOTE_MOCK_SCRIPT_CONTENT)
        self.assertIn('"task": "Extract the core requirements from this sample client inquiry"', REMOTE_MOCK_SCRIPT_CONTENT)
        self.assertIn('"priority": "high"', REMOTE_MOCK_SCRIPT_CONTENT)
        self.assertIn('"timestamp": int(now_ts)', REMOTE_MOCK_SCRIPT_CONTENT)
        self.assertIn('"unix_timestamp": now_ts', REMOTE_MOCK_SCRIPT_CONTENT)
        self.assertIn("inbound_queue.json", REMOTE_MOCK_SCRIPT_CONTENT)

    def test_dry_run_mode(self):
        res = deploy_mock_payload_to_vps(
            vps_ip="127.0.0.1",
            vps_user="testuser",
            remote_dir="/tmp/aios",
            dry_run=True
        )
        self.assertEqual(res["status"], "dry_run_success")
        self.assertEqual(res["remote_dir"], "/tmp/aios")

    @patch("deploy_vps_mock_payload.execute_ssh_command")
    @patch("deploy_vps_mock_payload.locate_ssh_key")
    def test_full_deployment_workflow(self, mock_locate, mock_ssh):
        mock_locate.return_value = "/fake/.ssh/id_rsa"
        
        # Responses for:
        # 1. mkdir & handshake
        # 2. cat << EOF (staging script)
        # 3. python3 execution
        # 4. cat inbound_queue.json
        sample_payload = {
            "source": "hostinger_web_ui",
            "task": "Extract the core requirements from this sample client inquiry",
            "priority": "high",
            "timestamp": 1729987200,
            "unix_timestamp": 1729987200.5,
            "created_at": "2026-10-26T23:45:00Z"
        }
        mock_ssh.side_effect = [
            (0, "VPS_READY\n", ""),
            (0, "", ""),
            (0, "STAGED_PAYLOAD_PATH=/opt/aios/inbound_queue.json", ""),
            (0, json.dumps(sample_payload), "")
        ]

        result = deploy_mock_payload_to_vps(
            vps_ip="2.25.249.27",
            vps_user="root",
            remote_dir="/opt/aios",
            key_path="/fake/.ssh/id_rsa",
            dry_run=False
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["payload"]["source"], "hostinger_web_ui")
        self.assertEqual(result["payload"]["task"], "Extract the core requirements from this sample client inquiry")
        self.assertEqual(result["payload"]["priority"], "high")
        self.assertEqual(result["payload"]["timestamp"], 1729987200)
        self.assertEqual(mock_ssh.call_count, 4)


if __name__ == "__main__":
    unittest.main()
