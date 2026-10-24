import json
import re
import tempfile
import threading
import unittest
import urllib.request
from datetime import date, datetime
from pathlib import Path

import hud_server
from hud import os_dashboard as osd


class TestOSDashboard(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parent.parent

    def test_os_dashboard_assets_are_strictly_csp_compliant(self):
        static = self.root / "static"
        html = (static / "os.html").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html), "inline <script> prohibited")
        self.assertNotIn("<style", html)
        self.assertIsNone(re.search(r"\son[a-z]+\s*=", html), "inline event handler prohibited")
        self.assertIsNone(re.search(r"\sstyle\s*=", html), "inline style attribute prohibited")

        for asset in ("os.css", "os.js"):
            self.assertIn("/static/" + asset, html)
            self.assertTrue((static / asset).is_file())

        # Left vertical flowchart sidebar, primary Obsidian canvas, and hidden secondary drawers
        self.assertIn('id="flow-sidebar"', html)
        self.assertIn('id="sidebar-flow-svg"', html)
        self.assertIn('id="card-obsidian"', html)
        self.assertIn('id="obsidian-canvas"', html)
        self.assertIsNotNone(re.search(r'<section[^>]*id="drawer-calendar"[^>]*\bhidden\b', html))
        self.assertIsNotNone(re.search(r'<section[^>]*id="drawer-tracker"[^>]*\bhidden\b', html))

        js = (static / "os.js").read_text(encoding="utf-8")
        self.assertNotIn("innerHTML", js)
        self.assertNotIn("parseFloat", js)

        ext_urls = re.findall(r"https?://(?!127\.0\.0\.1|localhost|www\.w3\.org)", html + js)
        self.assertEqual(ext_urls, [])

    def test_board_crud_and_smart_calendar_scheduler(self):
        with tempfile.TemporaryDirectory() as tmp:
            bpath = Path(tmp) / "board.json"
            day = date(2026, 10, 23)
            board = osd.load_board(bpath, today=day)
            self.assertEqual(board["schema_version"], 1)
            self.assertGreaterEqual(len(board["tasks"]), 3)

            # Add a high-priority vital task
            board = osd.apply_board_op({
                "op": "task.add",
                "title": "Verify zero-loss batch",
                "priority": 1,
                "vital": True,
                "estimate_min": 45,
                "due": day.isoformat(),
            }, path=bpath)
            added = [t for t in board["tasks"] if t["title"] == "Verify zero-loss batch"][0]
            self.assertTrue(added["vital"])

            # Add a fixed calendar event 09:30 - 10:00
            board = osd.apply_board_op({
                "op": "event.add",
                "title": "Morning standup",
                "date": day.isoformat(),
                "start": "09:30",
                "end": "10:00",
            }, path=bpath)

            # Add a goal + milestone and toggle it
            board = osd.apply_board_op({"op": "goal.add", "title": "Q4 Launch", "horizon": "quarter"}, path=bpath)
            goal = [g for g in board["goals"] if g["title"] == "Q4 Launch"][0]
            board = osd.apply_board_op({"op": "milestone.add", "goal_id": goal["id"], "title": "Ship HUD"}, path=bpath)
            ms = [g for g in board["goals"] if g["id"] == goal["id"]][0]["milestones"][0]
            board = osd.apply_board_op({"op": "milestone.toggle", "goal_id": goal["id"], "id": ms["id"]}, path=bpath)
            ms_after = [g for g in board["goals"] if g["id"] == goal["id"]][0]["milestones"][0]
            self.assertTrue(ms_after["done"])

            # Run auto-scheduler at 09:00 on that day
            now = datetime(2026, 10, 23, 9, 0)
            plan = osd.plan_day(board, day, now)
            self.assertEqual(plan["date"], day.isoformat())
            self.assertGreaterEqual(len(plan["blocks"]), 4)
            # Fixed event at 09:30-10:00 should be preserved, tasks scheduled around it with 5m buffer
            ev_blocks = [b for b in plan["blocks"] if b["kind"] == "event"]
            self.assertEqual(len(ev_blocks), 1)
            self.assertEqual(ev_blocks[0]["start"], "09:30")

    def test_ics_parser_and_scratch_editor_confinement(self):
        ics_sample = (
            "BEGIN:VCALENDAR\r\n"
            "BEGIN:VEVENT\r\n"
            "UID:evt-123\r\n"
            "SUMMARY:Architecture Review\r\n"
            "DTSTART:20261023T140000\r\n"
            "DTEND:20261023T143000\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        )
        parsed = osd.parse_ics(ics_sample, "team.ics")
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["title"], "Architecture Review")
        self.assertEqual(parsed[0]["start"], "14:00")
        self.assertEqual(parsed[0]["end"], "14:30")

        with tempfile.TemporaryDirectory() as tmp:
            sdir = Path(tmp)
            saved = osd.editor_save("test_note.md", "# Hello AI OS", None, scratch=sdir)
            self.assertEqual(saved["name"], "test_note.md")
            read_back = osd.editor_read("test_note.md", scratch=sdir)
            self.assertEqual(read_back["text"], "# Hello AI OS")

            # Stale SHA-256 must raise conflict
            with self.assertRaises(RuntimeError):
                osd.editor_save("test_note.md", "overwrite", "stale_sha", scratch=sdir)

            # Path traversal and bad extension must be rejected
            with self.assertRaises(ValueError):
                osd.editor_save("../escape.md", "bad", None, scratch=sdir)
            with self.assertRaises(ValueError):
                osd.editor_save("malware.exe", "bad", None, scratch=sdir)

    def test_live_flowchart_telemetry_frame_and_http_routes(self):
        frame = hud_server.os_frame()
        self.assertEqual([g["id"] for g in frame["groups"]], ["aios", "hermes", "offline"])
        for node_id in ("hud", "jev", "mark", "brain", "hermes", "model",
                        "inbox", "harness", "quarantine", "gtm", "notify", "relay"):
            self.assertIn(node_id, frame["nodes"])
        self.assertIn("obsidian", frame)
        self.assertGreaterEqual(len(frame["obsidian"]["notes"]), 12)
        self.assertGreaterEqual(len(frame["obsidian"]["links"]), 20)
        self.assertIn("activity_pct", frame["obsidian"]["notes"][0])
        self.assertIn("strength_pct", frame["obsidian"]["links"][0])
        self.assertIn("flow_rate", frame["obsidian"]["links"][0])
        # Zero-PII & zero-currency in telemetry frame
        raw_frame = json.dumps(frame)
        self.assertNotIn("@", raw_frame)
        self.assertIsNone(re.search(r"[\$€£]", raw_frame))

        # Test HTTP server endpoints on an ephemeral port
        server = hud_server.HUDHTTPServer(("127.0.0.1", 0), hud_server.HUDRequestHandler)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/os", timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                self.assertIn("script-src 'self'", resp.headers.get("Content-Security-Policy", ""))
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/os/telemetry", timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                self.assertIn("nodes", data)
                self.assertIn("edges", data)
                self.assertIn("obsidian", data)
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/os/obsidian", timeout=5) as resp:
                obs = json.loads(resp.read().decode("utf-8"))
                self.assertGreaterEqual(len(obs.get("notes", [])), 12)
                self.assertGreaterEqual(len(obs.get("links", [])), 20)
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/os/docs", timeout=5) as resp:
                docs = json.loads(resp.read().decode("utf-8"))
                self.assertGreaterEqual(len(docs.get("docs", [])), 5)
        finally:
            server.shutdown()
            server.server_close()

    def test_readonly_obsidian_scanner_and_local_scratch_notes(self):
        with tempfile.TemporaryDirectory() as tmp_sb_str, tempfile.TemporaryDirectory() as tmp_sc_str:
            tmp_sb = Path(tmp_sb_str)
            tmp_sc = Path(tmp_sc_str)

            # Create a simulated Second Brain note and verify read-only scanning
            (tmp_sb / "modules").mkdir(parents=True, exist_ok=True)
            sb_note = tmp_sb / "modules" / "incident-playbook.md"
            sb_note.write_text(
                "# Incident Triage Playbook\n\n"
                "Deterministic checklist linked to [[core.md]] and [[verification]].\n",
                encoding="utf-8",
            )
            # Legacy trade-bot files must be ignored by the scanner
            (tmp_sb / "modules" / "jev-trading.md").write_text("# Legacy Ignore", encoding="utf-8")

            graph1 = osd.build_obsidian_graph(second_brain_dir=tmp_sb, scratch_dir=tmp_sc, force_scan=True)
            note_ids1 = {n["id"] for n in graph1["notes"]}
            self.assertIn("sb:modules-incident-playbook", note_ids1)
            self.assertNotIn("sb:modules-jev-trading", note_ids1)

            # Create a custom note strictly in local scratch (Second Brain folder untouched)
            sb_files_before = sorted(p.relative_to(tmp_sb).as_posix() for p in tmp_sb.rglob("*"))
            res = osd.create_vault_note(
                {
                    "title": "Audit Gate Checklist",
                    "links": "core.md, verification, gtm-outbox",
                    "flow_node": "jev",
                    "summary": "Pre-release verification checklist for JEV gates.",
                },
                scratch=tmp_sc,
                second_brain=tmp_sb,
            )
            sb_files_after = sorted(p.relative_to(tmp_sb).as_posix() for p in tmp_sb.rglob("*"))
            self.assertEqual(sb_files_before, sb_files_after, "Second Brain vault must never be modified")

            self.assertEqual(res["note_id"], "vault:audit-gate-checklist")
            graph2 = res["obsidian"]
            vault_node = [n for n in graph2["notes"] if n["id"] == "vault:audit-gate-checklist"][0]
            self.assertTrue(vault_node["editable"])
            self.assertEqual(vault_node["group"], "vault")
            self.assertGreaterEqual(vault_node["activity_pct"], 90)

            # Verify wiki-links created high-strength edges (95%)
            vault_links = [lk for lk in graph2["links"] if lk["source"] == "vault:audit-gate-checklist" or lk["target"] == "vault:audit-gate-checklist"]
            self.assertGreaterEqual(len(vault_links), 3)
            self.assertEqual(vault_links[0]["strength_pct"], 95)

            # Verify read_doc can read the newly scanned note
            doc_data = osd.read_doc(vault_node["doc_id"], second_brain=tmp_sb, scratch=tmp_sc)
            self.assertIn("Audit Gate Checklist", doc_data["text"])


if __name__ == "__main__":
    unittest.main()
