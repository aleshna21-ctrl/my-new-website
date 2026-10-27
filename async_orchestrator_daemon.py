#!/usr/bin/env python3
"""
async_orchestrator_daemon.py
============================
Backward-compatible supervisory wrapper and CLI runner for AIOS Async Orchestrator.
Delegates multi-agent scheduling, matrix state transitions, prompt translation,
and resilient sweeping directly to AsyncOrchestrator.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sqlite3
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

from async_orchestrator import (
    AsyncOrchestrator,
    EphemeralSandboxRunner,
    SandboxResult,
    SAFE_HOTL_PERSONAS,
    PENDING_TO_ACTIVE_LOCK,
    ROLE_TO_ACTIVE_LOCK,
    detect_specialist_request,
    extract_executable_code,
    get_default_db_path,
    utc_now_iso,
    DEFAULT_INTERVAL_SECONDS,
    DEFAULT_ENDPOINT,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_STALLED_THRESHOLD_SEC,
    MAX_STRIKES_LIMIT,
)

# Reconfigure stdout/stderr for clean UTF-8 logging in Windows consoles
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [AsyncOrchestrator] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("AsyncOrchestratorDaemon")


class AsyncOrchestratorDaemon:
    """
    Independent message broker and Sandboxed Durable Execution orchestrator daemon.
    Supervises background polling loop and forwards multi-agent execution directly
    to AsyncOrchestrator.
    """

    def __init__(
        self,
        db_path: Optional[Path | str] = None,
        endpoint: str = DEFAULT_ENDPOINT,
        model_name: str = DEFAULT_MODEL,
        interval_sec: float = DEFAULT_INTERVAL_SECONDS,
        timeout_sec: float = DEFAULT_TIMEOUT_SECONDS,
        target_state: str = "[ DONE ]",
        allow_simulation: bool = False,
        verbose: bool = False,
        sandbox_runner: Optional[EphemeralSandboxRunner] = None,
        force_subprocess_jail: bool = False,
        sweep_interval_sec: float = 300.0,
    ):
        self.db_path = Path(db_path) if db_path else get_default_db_path()
        self.endpoint = endpoint
        self.model_name = model_name
        self.interval_sec = interval_sec
        self.timeout_sec = timeout_sec
        self.target_state = target_state
        self.allow_simulation = allow_simulation
        self.verbose = verbose
        self.force_subprocess_jail = force_subprocess_jail
        self.sweep_interval_sec = sweep_interval_sec
        self._last_sweep_time = time.time()
        self._stop_requested = False

        if sandbox_runner:
            self.sandbox_runner = sandbox_runner
        else:
            self.sandbox_runner = EphemeralSandboxRunner(
                force_subprocess_jail=force_subprocess_jail,
                default_timeout=min(self.timeout_sec, 5.0)
            )

        if self.verbose:
            logger.setLevel(logging.DEBUG)

        self.orchestrator = AsyncOrchestrator(
            ledger=self.db_path,
            sandbox=self.sandbox_runner,
            poll_interval=self.interval_sec,
            stalled_threshold_sec=60.0,
            endpoint=self.endpoint,
            model_name=self.model_name,
            timeout_sec=self.timeout_sec,
            target_state=self.target_state,
            allow_simulation=self.allow_simulation,
            verbose=self.verbose,
            force_subprocess_jail=self.force_subprocess_jail,
            sweep_interval_sec=self.sweep_interval_sec,
        )

    def ensure_schema(self, conn: sqlite3.Connection) -> None:
        """Safely verifies and ensures all required columns and tables exist."""
        self.orchestrator.ensure_schema(conn)

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Opens a connection to the ledger database with schema verification, closing on exit."""
        with self.orchestrator.get_connection() as conn:
            yield conn

    def get_role_system_prompt(self, role: Optional[str]) -> str:
        """Loads the text-based system prompt corresponding to the given assigned_role."""
        return self.orchestrator.get_role_system_prompt(role)

    def check_concurrency_lock(self, conn: sqlite3.Connection) -> Optional[str]:
        """Enforces a strict 1-active-LLM-agent limit across all jobs."""
        return self.orchestrator.check_concurrency_lock(conn)

    def get_active_lock_for_role(self, role: Optional[str]) -> str:
        """Maps an agent role to its designated active lock state."""
        return self.orchestrator.get_active_lock_for_role(role)

    def get_soft_reset_state(self, active_state: str, payload: str = "") -> str:
        """Determines the appropriate prior pending state for soft resetting a stalled task."""
        return self.orchestrator.get_soft_reset_state(active_state, payload)

    def poll_and_lock_next_task(self) -> Optional[Dict[str, Any]]:
        """Polls for the next pending task in the state machine matrix with atomic lock."""
        return self.orchestrator.poll_and_lock_next_task()

    def poll_inbox_tasks(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Queries job_ledger.db specifically for tasks in the '[ INBOX ]' state."""
        return self.orchestrator.poll_inbox_tasks(limit=limit)

    def translate_task_to_prompt(self, task: Dict[str, Any]) -> str:
        """Translates raw task row and payload into a standard text-based LLM prompt."""
        return self.orchestrator.translate_task_to_prompt(task)

    def _generate_simulated_response(self, prompt: str, note: str = "") -> str:
        """Generates deterministic simulated responses for offline testing."""
        return self.orchestrator._generate_simulated_response(prompt, note=note)

    def send_prompt_to_llm(
        self,
        prompt: str,
        system_prompt: Optional[str] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """Dispatches prompt to local Hermes inference endpoint."""
        return self.orchestrator.send_prompt_to_llm(prompt, system_prompt=system_prompt)

    async def send_prompt_to_llm_async(
        self,
        prompt: str,
        system_prompt: Optional[str] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """Asynchronously executes the LLM network call in an async executor thread."""
        return await self.orchestrator.send_prompt_to_llm_async(prompt, system_prompt=system_prompt)

    def handle_proactive_baton_pass(
        self,
        task: Dict[str, Any],
        target_specialist: str,
        agent_output: str,
        new_retry_count: int
    ) -> bool:
        """Executes proactive baton pass to requested specialist."""
        return self.orchestrator.handle_proactive_baton_pass(task, target_specialist, agent_output, new_retry_count)

    def handle_reactive_crash_swap(
        self,
        task: Dict[str, Any],
        sandbox_result: SandboxResult,
        new_retry_count: int,
        helper_role: str = "qa-telemetry-daemon",
        next_state: str = "[ INBOX ]"
    ) -> bool:
        """Executes reactive crash swap to helper agent upon sandbox failure."""
        return self.orchestrator.handle_reactive_crash_swap(task, sandbox_result, new_retry_count, helper_role, next_state)

    def handle_hard_ejection(
        self,
        task: Dict[str, Any],
        last_output: str,
        reason: str,
        error_trace: Optional[str] = None
    ) -> bool:
        """Executes hard ejection on 3rd strike, escalating to [ NEEDS_REVIEW ]."""
        return self.orchestrator.handle_hard_ejection(task, last_output, reason, error_trace)

    def update_to_done(
        self,
        job_id: str,
        model_output: str,
        from_state: str = "[ INBOX ]",
        target_state: Optional[str] = None
    ) -> bool:
        """Atomically updates job state to '[ DONE ]' and routes deliverable payload."""
        return self.orchestrator.update_to_done(job_id, model_output, from_state=from_state, target_state=target_state)

    def update_to_staged_review(
        self,
        job_id: str,
        model_output: str,
        from_state: str = "[ INBOX ]"
    ) -> bool:
        """Compatibility alias updating to '[ STAGED / REVIEW ]'."""
        return self.orchestrator.update_to_staged_review(job_id, model_output, from_state=from_state)

    def record_job_attempt_failure(self, job_id: str, error_msg: str) -> None:
        """Increments attempt count and records failure note in updated_at."""
        self.orchestrator.record_job_attempt_failure(job_id, error_msg)

    def process_task(self, task: Dict[str, Any]) -> bool:
        """Processes a single task through the Sandboxed Durable Execution pipeline."""
        return self.orchestrator.process_task(
            task,
            send_prompt_fn=self.send_prompt_to_llm,
            sandbox_runner=self.sandbox_runner,
        )

    async def process_task_async(self, task: Dict[str, Any]) -> bool:
        """Asynchronously processes a single task in an executor thread."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.process_task, task)

    def step_state_machine_once(self) -> Optional[Dict[str, Any]]:
        """Pulls and locks the next pending task, processes it, and returns the result dictionary."""
        return self.orchestrator.step(
            send_prompt_fn=self.send_prompt_to_llm,
            sandbox_runner=self.sandbox_runner,
        )

    def sweep_stalled_tasks(self, stalled_threshold_sec: float = 60.0) -> List[Dict[str, Any]]:
        """Resilient sweeper scanning for tasks trapped in [ ACTIVE_* ] states."""
        return self.orchestrator.sweep_stalled_tasks(stalled_threshold_sec=stalled_threshold_sec)

    def poll_and_process_once(self) -> List[Dict[str, Any]]:
        """Polls once for all available tasks across the state machine and legacy [ INBOX ]."""
        return self.orchestrator.poll_and_process_once(
            send_prompt_fn=self.send_prompt_to_llm,
            sandbox_runner=self.sandbox_runner,
        )

    async def run_async_loop(self) -> None:
        """Continuous asynchronous polling loop running every interval_sec seconds."""
        sweep_interval = getattr(self, "sweep_interval_sec", 300.0)
        last_sweep = time.time()
        logger.info(
            f"[STARTED] Async Orchestrator Daemon active. "
            f"Polling database '{self.db_path}' every {self.interval_sec}s (sweeper: {sweep_interval}s)..."
        )
        while not self._stop_requested:
            try:
                if time.time() - last_sweep >= sweep_interval:
                    logger.info("[SWEEPER] Triggering 5-minute trend-monitor sweeper cycle...")
                    self.sweep_stalled_tasks(stalled_threshold_sec=60.0)
                    last_sweep = time.time()

                task = self.poll_and_lock_next_task()
                if task:
                    logger.info(f"[POLL] Locked task '{task['job_id']}' in state '{task['state']}'.")
                    await self.process_task_async(task)
                else:
                    logger.debug(f"[POLL] No pending tasks found. Sleeping {self.interval_sec}s.")
            except Exception as exc:
                logger.error(f"[LOOP_ERROR] Error in orchestrator loop: {exc}", exc_info=True)

            try:
                await asyncio.sleep(self.interval_sec)
            except asyncio.CancelledError:
                break

        logger.info("[STOPPED] Async Orchestrator Daemon loop terminated.")

    def run_sync_loop(self) -> None:
        """Synchronous wrapper for standard thread/process daemon execution."""
        asyncio.run(self.run_async_loop())

    def stop(self) -> None:
        """Signals daemon loop to cleanly terminate."""
        self._stop_requested = True


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Async Orchestrator Daemon: Decoupled message broker & Sandboxed Durable Execution layer."
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Path to job_ledger.db (default: autodetected in delivery-offline or data/)."
    )
    parser.add_argument(
        "--endpoint",
        type=str,
        default=DEFAULT_ENDPOINT,
        help=f"Ollama loopback endpoint (default: {DEFAULT_ENDPOINT})."
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help=f"Model tag for chat completions (default: {DEFAULT_MODEL})."
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_INTERVAL_SECONDS,
        help=f"Polling interval in seconds (default: {DEFAULT_INTERVAL_SECONDS}s)."
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"HTTP network timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS}s)."
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Poll and process current [ INBOX ] tasks once, then exit."
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Allow simulated fallback if local Ollama endpoint times out or is offline."
    )
    parser.add_argument(
        "--target-state",
        type=str,
        default="[ DONE ]",
        help="Target state upon successful completion (default: '[ DONE ]')."
    )
    parser.add_argument(
        "--force-subprocess-jail",
        action="store_true",
        help="Force ephemeral subprocess jail instead of attempting Docker."
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable detailed debug logging."
    )
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    daemon = AsyncOrchestratorDaemon(
        db_path=args.db_path,
        endpoint=args.endpoint,
        model_name=args.model,
        interval_sec=args.interval,
        timeout_sec=args.timeout,
        target_state=args.target_state,
        allow_simulation=args.simulate,
        verbose=args.verbose,
        force_subprocess_jail=args.force_subprocess_jail,
    )

    def handle_signal(sig, frame):
        logger.info(f"Signal {sig} received. Initiating graceful shutdown...")
        daemon.stop()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    if args.once:
        logger.info("[MODE: SINGLE PASS] Polling and processing current [ INBOX ] tasks...")
        results = daemon.poll_and_process_once()
        logger.info(f"Single pass completed: {len(results)} task(s) processed.")
        sys.exit(0)
    else:
        logger.info("[MODE: CONTINUOUS DAEMON] Starting polling loop...")
        try:
            daemon.run_sync_loop()
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt received. Exiting.")
            sys.exit(0)


if __name__ == "__main__":
    main()
