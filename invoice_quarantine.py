"""
invoice_quarantine.py
Authoritative Deep Invoice Quarantine Invariant Module for AIOS & JEV Cockpit.

Encapsulates CSV fixture parsing, StrictStr financial validation, duplicate tracking,
zero-loss accounting invariant mathematics, and safe atomic fixture repairs.
"""

from __future__ import annotations
import copy
import csv
import json
import os
import re
import shutil
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Set, List, Any, Union

BASE_DIR = Path(__file__).resolve().parent

BASELINE_ADVERSARIAL_CSV = (
    "InvoiceID,Amount ,Date\n"
    "INV-3250-VTFZ,173.51,2026-04-25\n"
    "INV-2772-UOKV,105.78,2026-07-16\n"
    "INV-7401-WQWB,242.75,2026-10-05\n"
    "INV-9783-WNNC,46,2026-02-10\n"
    "INV-2059-IYIG,226.74,2026-03-09\n"
    "INV-5960-WCJS,206.3,2026-05-25\n"
    "INV-8931-WZNB,330.66,2026-06-26\n"
    "INV-3083-MRUI,267.23,2026-04-21\n"
    "INV-2337-OTPK,202.48,2026-01-18\n"
    "INV-7234-GIXD,121.38,2026-09-03\n"
    "INV-2059-IYIG,226.74,2026-03-09\n"
    "INV-4459-QZJZ,-999.995,2026-05-16\n"
)


def get_default_csv_path() -> Path:
    env_csv = os.environ.get("INVOICE_QUARANTINE_CSV")
    if env_csv:
        return Path(env_csv)
    env_dir = os.environ.get("DELIVERY_OFFLINE_DIR")
    if env_dir and (Path(env_dir) / "adversarial_fixture.csv").exists():
        return Path(env_dir) / "adversarial_fixture.csv"
    parent_fixture = BASE_DIR.parent / "delivery-offline" / "adversarial_fixture.csv"
    if parent_fixture.exists():
        return parent_fixture
    local_fixture = BASE_DIR / "delivery-offline" / "adversarial_fixture.csv"
    if local_fixture.exists():
        return local_fixture
    return BASE_DIR / "data" / "adversarial_fixture.csv"


def _atomic_write(target_path: Path, writer_fn: Any) -> None:
    target_dir = target_path.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    temp_file = None
    try:
        temp_file = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=str(target_dir),
            prefix=".quarantine-",
            suffix=".tmp",
            delete=False
        )
        writer_fn(temp_file)
        temp_file.flush()
        os.fsync(temp_file.fileno())
        temp_file.close()
        os.replace(temp_file.name, str(target_path))
    except Exception:
        if temp_file is not None and os.path.exists(temp_file.name):
            try:
                os.remove(temp_file.name)
            except OSError:
                pass
        raise


def _atomic_write_csv(target_path: Path, header: List[str], data_rows: List[List[str]]) -> None:
    def write_csv(f):
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(data_rows)
    _atomic_write(target_path, write_csv)


def _atomic_write_text(target_path: Path, content: str) -> None:
    _atomic_write(target_path, lambda f: f.write(content))


def _classify_invoice_row(
    idx: int,
    inv_id: str,
    amt_str: str,
    dt_str: str,
    seen: Set[str]
) -> Dict[str, Any]:
    """
    Evaluates StrictStr validation and duplicate status for a single invoice row.
    Mutates seen set with newly accepted unique IDs.
    """
    inv_id = (inv_id or "").strip()
    amt_str = (amt_str or "").strip()
    dt_str = (dt_str or "").strip()

    is_dup = inv_id in seen
    is_malformed = False
    reason = None
    status = "accepted"

    if is_dup:
        status = "duplicate"
        reason = f"Duplicate InvoiceID ({inv_id})"
    elif not inv_id:
        status = "quarantined"
        is_malformed = True
        reason = "Missing InvoiceID"
    elif not amt_str:
        status = "quarantined"
        is_malformed = True
        reason = "Missing Amount"
    elif amt_str.startswith("-"):
        status = "quarantined"
        is_malformed = True
        reason = f"Negative StrictStr amount ({amt_str})"
    elif not amt_str.replace(".", "", 1).isdigit():
        status = "quarantined"
        is_malformed = True
        reason = f"Non-numeric amount string ({amt_str})"
    else:
        parts = amt_str.split(".")
        if len(parts) == 2 and len(parts[1]) > 2:
            status = "quarantined"
            is_malformed = True
            reason = f"Sub-penny fractional precision ({amt_str}, {len(parts[1])} decimal places)"
        else:
            seen.add(inv_id)
            status = "accepted"

    return {
        "row_idx": idx,
        "row": idx,
        "invoice_id": inv_id or "MISSING",
        "amount": amt_str,
        "raw_amount": amt_str,
        "date": dt_str,
        "status": status,
        "is_malformed": is_malformed,
        "reason": reason
    }


def _clean_amount_for_recovery(amt_str: str, default: str = "0.00") -> Optional[str]:
    """
    Cleanses negative sign, sub-penny precision, or non-numeric amount for auto-recovery.
    Returns cleaned amount string if modified, or None if amount is already valid.
    """
    amt = (amt_str or "").strip()
    is_malformed = amt.startswith("-") or not amt.replace(".", "", 1).isdigit() or (len(amt.split(".")) == 2 and len(amt.split(".")[1]) > 2)
    if not is_malformed:
        return None
    cleaned = amt.lstrip("-").strip()
    if cleaned.replace(".", "", 1).isdigit():
        parts = cleaned.split(".")
        if len(parts) == 2 and len(parts[1]) > 2:
            return f"{parts[0]}.{parts[1][:2]}"
        elif len(parts) == 1:
            return f"{parts[0]}.00"
        return cleaned
    return default


def _deconflict_invoice_id(inv_id: str, idx: int, seen: Set[str]) -> Optional[str]:
    """
    Deconflicts duplicate or missing invoice IDs for auto-recovery.
    Returns new ID if modified, or None if ID is unique and valid.
    """
    inv_id = (inv_id or "").strip()
    if not inv_id:
        return f"AUTO-REC-{idx}"
    if inv_id in seen:
        return f"{inv_id}-REC"
    seen.add(inv_id)
    return None



class QuarantineInspectionSnapshot(dict):
    """
    Dual-access contract for quarantine inspection results.
    Operates as a standard dict for JSON serialization, while exposing typed properties.
    """
    def __init__(
        self,
        fixture: str = "",
        path: str = "",
        metrics: Optional[Dict[str, int]] = None,
        invariant: Optional[Dict[str, Any]] = None,
        rows: Optional[List[Dict[str, Any]]] = None
    ):
        super().__init__()
        self["fixture"] = fixture
        self["path"] = path
        self["metrics"] = metrics or {"received": 0, "accepted": 0, "quarantined": 0, "duplicates": 0}
        self["invariant"] = invariant or {
            "passed": True,
            "formula": "0 == 0 + 0 + 0",
            "metrics": self["metrics"],
            "quarantined_samples": []
        }
        self["rows"] = rows or []

    @property
    def fixture(self) -> str:
        return self.get("fixture", "")

    @property
    def path(self) -> str:
        return self.get("path", "")

    @property
    def metrics(self) -> Dict[str, int]:
        return self.get("metrics", {})

    @property
    def invariant(self) -> Dict[str, Any]:
        return self.get("invariant", {})

    @property
    def rows(self) -> List[Dict[str, Any]]:
        return self.get("rows", [])

    @property
    def quarantined_samples(self) -> List[Dict[str, Any]]:
        return self.invariant.get("quarantined_samples", [])

    @property
    def passed(self) -> bool:
        return bool(self.invariant.get("passed", False))

    @property
    def received_count(self) -> int:
        return self.metrics.get("received", 0)

    @property
    def accepted_count(self) -> int:
        return self.metrics.get("accepted", 0)

    @property
    def quarantined_count(self) -> int:
        return self.metrics.get("quarantined", 0)

    @property
    def duplicates_count(self) -> int:
        return self.metrics.get("duplicates", 0)


class QuarantineRepairResult(dict):
    """
    Dual-access contract for quarantine repair results.
    """
    def __init__(
        self,
        status: str,
        repaired_records: Optional[List[Dict[str, Any]]] = None,
        metrics: Optional[Dict[str, int]] = None,
        invariant: Optional[Dict[str, Any]] = None,
        quarantined_count: int = 0,
        duplicates_count: int = 0,
        rows: Optional[List[Dict[str, Any]]] = None,
        error: Optional[str] = None
    ):
        super().__init__()
        self["status"] = status
        if error is not None:
            self["error"] = error
        if repaired_records is not None:
            self["repaired_records"] = repaired_records
        if metrics is not None:
            self["metrics"] = metrics
        if invariant is not None:
            self["invariant"] = invariant
        self["quarantined_count"] = quarantined_count
        self["duplicates_count"] = duplicates_count
        if rows is not None:
            self["rows"] = rows

    @property
    def status(self) -> str:
        return self.get("status", "")

    @property
    def error(self) -> Optional[str]:
        return self.get("error")

    @property
    def repaired_records(self) -> List[Dict[str, Any]]:
        return self.get("repaired_records", [])

    @property
    def metrics(self) -> Dict[str, int]:
        return self.get("metrics", {})

    @property
    def invariant(self) -> Dict[str, Any]:
        return self.get("invariant", {})

    @property
    def rows(self) -> List[Dict[str, Any]]:
        return self.get("rows", [])

    @property
    def quarantined_count(self) -> int:
        return self.get("quarantined_count", 0)

    @property
    def duplicates_count(self) -> int:
        return self.get("duplicates_count", 0)


class QuarantineResetResult(dict):
    """
    Dual-access contract for quarantine fixture reset operations.
    """
    def __init__(
        self,
        status: str = "ok",
        message: str = "",
        data: Optional[Dict[str, Any]] = None
    ):
        super().__init__()
        self["status"] = status
        self["message"] = message
        if data is not None:
            self["data"] = data

    @property
    def status(self) -> str:
        return self.get("status", "")

    @property
    def message(self) -> str:
        return self.get("message", "")

    @property
    def data(self) -> Dict[str, Any]:
        return self.get("data", {})


class InvoiceQuarantine:
    """
    Authoritative Deep Invoice Quarantine Seam.
    Encapsulates CSV parsing, StrictStr rules, duplicate detection, and zero-loss accounting.
    """
    def __init__(
        self,
        csv_path: Optional[Union[str, Path]] = None,
        backup_path: Optional[Union[str, Path]] = None,
        sync_paths: Optional[List[Union[str, Path]]] = None
    ):
        self.csv_path = Path(csv_path) if csv_path is not None else get_default_csv_path()
        self.backup_path = Path(backup_path) if backup_path is not None else Path(str(self.csv_path) + ".original")
        if sync_paths is not None:
            self.sync_paths = [Path(p) for p in sync_paths]
        else:
            fallback = BASE_DIR / "data" / "adversarial_fixture.csv"
            self.sync_paths = [fallback] if fallback.resolve() != self.csv_path.resolve() and fallback.exists() else []

    def inspect(self) -> QuarantineInspectionSnapshot:
        """
        Parses CSV fixture, verifies StrictStr format & duplicates, and evaluates the Zero-Loss accounting invariant.
        Formula: received == accepted + quarantined + duplicates
        """
        if not self.csv_path.exists():
            return QuarantineInspectionSnapshot(
                fixture=self.csv_path.name,
                path=str(self.csv_path),
                metrics={"received": 0, "accepted": 0, "quarantined": 0, "duplicates": 0},
                invariant={
                    "passed": True,
                    "formula": "0 == 0 + 0 + 0",
                    "metrics": {"received": 0, "accepted": 0, "quarantined": 0, "duplicates": 0},
                    "quarantined_samples": []
                },
                rows=[]
            )

        rows: List[Dict[str, Any]] = []
        metrics = {"received": 0, "accepted": 0, "quarantined": 0, "duplicates": 0}
        seen: Set[str] = set()
        quarantined_samples: List[Dict[str, Any]] = []

        with open(self.csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for idx, raw_row in enumerate(reader, start=1):
                clean_row = {k.strip(): (v or "").strip() for k, v in raw_row.items() if k}
                metrics["received"] += 1
                row_dict = _classify_invoice_row(
                    idx=idx,
                    inv_id=clean_row.get("InvoiceID", ""),
                    amt_str=clean_row.get("Amount", ""),
                    dt_str=clean_row.get("Date", ""),
                    seen=seen
                )
                if row_dict["status"] == "accepted":
                    metrics["accepted"] += 1
                elif row_dict["status"] == "duplicate":
                    metrics["duplicates"] += 1
                elif row_dict["status"] == "quarantined":
                    metrics["quarantined"] += 1
                    quarantined_samples.append(row_dict)
                rows.append(row_dict)

        invariant_ok = (metrics["received"] == (metrics["accepted"] + metrics["quarantined"] + metrics["duplicates"]))
        return QuarantineInspectionSnapshot(
            fixture=self.csv_path.name,
            path=str(self.csv_path),
            metrics=metrics,
            invariant={
                "passed": invariant_ok,
                "formula": f"{metrics['received']} == {metrics['accepted']} + {metrics['quarantined']} + {metrics['duplicates']}",
                "metrics": metrics,
                "quarantined_samples": quarantined_samples[:10]
            },
            rows=rows
        )

    def repair(
        self,
        row_idx: int = 0,
        invoice_id: Optional[str] = None,
        amount: Optional[str] = None,
        date: Optional[str] = None,
        auto_recover: bool = False,
        auto_recover_all: bool = False
    ) -> QuarantineRepairResult:
        """
        Repairs in-memory CSV rows with validation, writes atomically, and synchronizes mirror paths.
        """
        if not self.csv_path.exists():
            return QuarantineRepairResult(
                status="error",
                error=f"Fixture file not found at {self.csv_path}"
            )

        # Back up original baseline if not yet present
        if not self.backup_path.exists():
            try:
                shutil.copy2(self.csv_path, self.backup_path)
            except Exception:
                pass

        with open(self.csv_path, "r", encoding="utf-8-sig") as f:
            reader = list(csv.reader(f))

        if not reader:
            return QuarantineRepairResult(status="error", error="Empty CSV fixture")

        header = reader[0]
        data_rows = reader[1:]
        repaired_records: List[Dict[str, Any]] = []

        if auto_recover_all:
            seen: Set[str] = set()
            for idx, r in enumerate(data_rows, start=1):
                if len(r) >= 2:
                    inv = r[0].strip()
                    amt = r[1].strip()
                    cleaned_amt = _clean_amount_for_recovery(amt, default="0.00")
                    if cleaned_amt is not None:
                        r[1] = cleaned_amt
                        repaired_records.append({"row_idx": idx, "invoice_id": inv, "repaired_amount": cleaned_amt})
                    fixed_inv = _deconflict_invoice_id(inv, idx, seen)
                    if fixed_inv is not None:
                        r[0] = fixed_inv
                        seen.add(fixed_inv)
                        repaired_records.append({"row_idx": idx, "repaired_invoice_id": fixed_inv})
        else:
            if row_idx < 1 or row_idx > len(data_rows):
                return QuarantineRepairResult(
                    status="error",
                    error=f"Row index {row_idx} out of range (1..{len(data_rows)})"
                )

            target_row = data_rows[row_idx - 1]
            cur_inv = target_row[0].strip() if len(target_row) >= 1 else ""
            cur_amt = target_row[1].strip() if len(target_row) >= 2 else ""

            if auto_recover:
                cleaned_amt = _clean_amount_for_recovery(cur_amt, default="0.00") or "0.00"
                target_row[1] = cleaned_amt
                repaired_records.append({"row_idx": row_idx, "invoice_id": cur_inv, "repaired_amount": cleaned_amt})
            else:
                if invoice_id is not None:
                    target_row[0] = str(invoice_id).strip()
                if amount is not None:
                    amt_str = str(amount).strip()
                    if not amt_str.replace(".", "", 1).isdigit() or amt_str.startswith("-"):
                        return QuarantineRepairResult(
                            status="error",
                            error=f"Invalid StrictStr amount '{amt_str}'. Must be a positive decimal."
                        )
                    target_row[1] = amt_str
                if date is not None and len(target_row) >= 3:
                    target_row[2] = str(date).strip()

                repaired_records.append({
                    "row_idx": row_idx,
                    "invoice_id": target_row[0],
                    "amount": target_row[1],
                    "date": target_row[2] if len(target_row) >= 3 else ""
                })

        _atomic_write_csv(self.csv_path, header, data_rows)

        # Synchronize mirror paths
        for sync_path in self.sync_paths:
            try:
                _atomic_write_csv(sync_path, header, data_rows)
            except Exception:
                pass

        updated = self.inspect()
        return QuarantineRepairResult(
            status="ok",
            repaired_records=repaired_records,
            metrics=updated.metrics,
            invariant=updated.invariant,
            quarantined_count=updated.quarantined_count,
            duplicates_count=updated.duplicates_count,
            rows=updated.rows
        )

    def reset(self) -> QuarantineResetResult:
        """
        Restores the adversarial fixture to its baseline state and synchronizes mirrors.
        """
        content = BASELINE_ADVERSARIAL_CSV
        if self.backup_path.exists():
            try:
                with open(self.backup_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                content = BASELINE_ADVERSARIAL_CSV

        _atomic_write_text(self.csv_path, content)

        for sync_path in self.sync_paths:
            try:
                _atomic_write_text(sync_path, content)
            except Exception:
                pass

        updated = self.inspect()
        return QuarantineResetResult(
            status="ok",
            message=f"Reset {self.csv_path.name} to baseline state",
            data=dict(updated)
        )

    # Provider compatibility aliases
    def get_quarantine_data(self) -> QuarantineInspectionSnapshot:
        return self.inspect()

    def repair_quarantine_row(
        self,
        row_idx: int = 0,
        invoice_id: Optional[str] = None,
        amount: Optional[str] = None,
        date: Optional[str] = None,
        auto_recover: bool = False,
        auto_recover_all: bool = False
    ) -> QuarantineRepairResult:
        return self.repair(
            row_idx=row_idx,
            invoice_id=invoice_id,
            amount=amount,
            date=date,
            auto_recover=auto_recover,
            auto_recover_all=auto_recover_all
        )

    def reset_quarantine_fixture(self) -> QuarantineResetResult:
        return self.reset()


class FakeInvoiceQuarantine:
    """
    Deterministic in-memory test double for InvoiceQuarantine.
    Executes identical StrictStr parsing, zero-loss invariant calculations,
    and row repairs in memory without filesystem interaction.
    Maintains an audit trail in `calls`.
    """
    def __init__(
        self,
        initial_rows: Optional[List[Dict[str, Any]]] = None,
        should_fail: bool = False
    ):
        self.calls: List[Dict[str, Any]] = []
        self.should_fail = should_fail
        self._initial_rows: List[Dict[str, Any]] = copy.deepcopy(initial_rows or [])
        self._rows: List[Dict[str, Any]] = copy.deepcopy(self._initial_rows)

    def _check_failure(self) -> None:
        if self.should_fail:
            raise RuntimeError("Simulated quarantine failure")

    def _analyze(self) -> QuarantineInspectionSnapshot:
        rows: List[Dict[str, Any]] = []
        metrics = {"received": 0, "accepted": 0, "quarantined": 0, "duplicates": 0}
        seen: Set[str] = set()
        quarantined_samples: List[Dict[str, Any]] = []

        for idx, raw_row in enumerate(self._rows, start=1):
            inv_id_val = raw_row.get("InvoiceID") if "InvoiceID" in raw_row else raw_row.get("invoice_id", "")
            amt_val = raw_row.get("Amount") if "Amount" in raw_row else raw_row.get("amount", "")
            dt_val = raw_row.get("Date") if "Date" in raw_row else raw_row.get("date", "")

            metrics["received"] += 1
            row_dict = _classify_invoice_row(
                idx=idx,
                inv_id=str(inv_id_val or ""),
                amt_str=str(amt_val or ""),
                dt_str=str(dt_val or ""),
                seen=seen
            )
            if row_dict["status"] == "accepted":
                metrics["accepted"] += 1
            elif row_dict["status"] == "duplicate":
                metrics["duplicates"] += 1
            elif row_dict["status"] == "quarantined":
                metrics["quarantined"] += 1
                quarantined_samples.append(row_dict)
            rows.append(row_dict)

        invariant_ok = (metrics["received"] == (metrics["accepted"] + metrics["quarantined"] + metrics["duplicates"]))
        return QuarantineInspectionSnapshot(
            fixture="in_memory",
            path="in_memory",
            metrics=metrics,
            invariant={
                "passed": invariant_ok,
                "formula": f"{metrics['received']} == {metrics['accepted']} + {metrics['quarantined']} + {metrics['duplicates']}",
                "metrics": metrics,
                "quarantined_samples": quarantined_samples[:10]
            },
            rows=rows
        )

    def inspect(self) -> QuarantineInspectionSnapshot:
        self._check_failure()
        self.calls.append({"action": "inspect"})
        return self._analyze()

    def repair(
        self,
        row_idx: int = 0,
        invoice_id: Optional[str] = None,
        amount: Optional[str] = None,
        date: Optional[str] = None,
        auto_recover: bool = False,
        auto_recover_all: bool = False
    ) -> QuarantineRepairResult:
        self._check_failure()
        self.calls.append({
            "action": "repair",
            "row_idx": row_idx,
            "invoice_id": invoice_id,
            "amount": amount,
            "date": date,
            "auto_recover": auto_recover,
            "auto_recover_all": auto_recover_all
        })

        repaired_records: List[Dict[str, Any]] = []

        if auto_recover_all:
            seen_ids: Set[str] = set()
            for idx, r in enumerate(self._rows, start=1):
                inv_key = "InvoiceID" if "InvoiceID" in r else "invoice_id"
                amt_key = "Amount" if "Amount" in r else "amount"

                cur_inv = str(r.get(inv_key, "")).strip()
                cur_amt = str(r.get(amt_key, "")).strip()

                cleaned_amt = _clean_amount_for_recovery(cur_amt, default="0.00")
                if cleaned_amt is not None:
                    r[amt_key] = cleaned_amt
                    repaired_records.append({"row_idx": idx, "invoice_id": cur_inv, "repaired_amount": cleaned_amt})

                fixed_inv = _deconflict_invoice_id(cur_inv, idx, seen_ids)
                if fixed_inv is not None:
                    r[inv_key] = fixed_inv
                    seen_ids.add(fixed_inv)
                    repaired_records.append({"row_idx": idx, "repaired_invoice_id": fixed_inv})
        else:
            if row_idx < 1 or row_idx > len(self._rows):
                return QuarantineRepairResult(
                    status="error",
                    error=f"Row index {row_idx} out of range (1..{len(self._rows)})"
                )

            target_row = self._rows[row_idx - 1]
            inv_key = "InvoiceID" if "InvoiceID" in target_row else "invoice_id"
            amt_key = "Amount" if "Amount" in target_row else "amount"
            dt_key = "Date" if "Date" in target_row else "date"

            cur_inv = str(target_row.get(inv_key, "")).strip()
            cur_amt = str(target_row.get(amt_key, "")).strip()

            if auto_recover:
                cleaned_amt = _clean_amount_for_recovery(cur_amt, default="0.00") or "0.00"
                target_row[amt_key] = cleaned_amt
                repaired_records.append({"row_idx": row_idx, "invoice_id": cur_inv, "repaired_amount": cleaned_amt})
            else:
                if invoice_id is not None:
                    target_row[inv_key] = str(invoice_id).strip()
                if amount is not None:
                    amt_str = str(amount).strip()
                    if not amt_str.replace(".", "", 1).isdigit() or amt_str.startswith("-"):
                        return QuarantineRepairResult(
                            status="error",
                            error=f"Invalid StrictStr amount '{amt_str}'. Must be a positive decimal."
                        )
                    target_row[amt_key] = amt_str
                if date is not None:
                    target_row[dt_key] = str(date).strip()

                repaired_records.append({
                    "row_idx": row_idx,
                    "invoice_id": target_row.get(inv_key, ""),
                    "amount": target_row.get(amt_key, ""),
                    "date": target_row.get(dt_key, "")
                })

        updated = self._analyze()
        return QuarantineRepairResult(
            status="ok",
            repaired_records=repaired_records,
            metrics=updated.metrics,
            invariant=updated.invariant,
            quarantined_count=updated.quarantined_count,
            duplicates_count=updated.duplicates_count,
            rows=updated.rows
        )

    def reset(self) -> QuarantineResetResult:
        self._check_failure()
        self.calls.append({"action": "reset"})
        self._rows = copy.deepcopy(self._initial_rows)
        updated = self._analyze()
        return QuarantineResetResult(
            status="ok",
            message="Reset in-memory fixture to initial state",
            data=dict(updated)
        )

    # Provider compatibility aliases
    def get_quarantine_data(self) -> QuarantineInspectionSnapshot:
        return self.inspect()

    def repair_quarantine_row(
        self,
        row_idx: int = 0,
        invoice_id: Optional[str] = None,
        amount: Optional[str] = None,
        date: Optional[str] = None,
        auto_recover: bool = False,
        auto_recover_all: bool = False
    ) -> QuarantineRepairResult:
        return self.repair(
            row_idx=row_idx,
            invoice_id=invoice_id,
            amount=amount,
            date=date,
            auto_recover=auto_recover,
            auto_recover_all=auto_recover_all
        )

    def reset_quarantine_fixture(self) -> QuarantineResetResult:
        return self.reset()


# --------------------------------------------------------------------------- #
# Module-level default singleton & backward-compatible delegation
# --------------------------------------------------------------------------- #
_DEFAULT_QUARANTINE: Optional[InvoiceQuarantine] = None
_DEFAULT_QUARANTINE_LOCK = threading.RLock()


def get_default_quarantine(csv_path: Optional[Union[str, Path]] = None) -> InvoiceQuarantine:
    """
    Returns the thread-safe singleton instance of InvoiceQuarantine.
    Automatically re-initializes if the target CSV path changes (e.g. via test isolation).
    """
    global _DEFAULT_QUARANTINE
    with _DEFAULT_QUARANTINE_LOCK:
        active_csv = Path(csv_path) if csv_path is not None else get_default_csv_path()
        if _DEFAULT_QUARANTINE is None or _DEFAULT_QUARANTINE.csv_path.resolve() != active_csv.resolve():
            _DEFAULT_QUARANTINE = InvoiceQuarantine(csv_path=active_csv)
        return _DEFAULT_QUARANTINE


def reset_default_quarantine() -> None:
    """Resets the module-level singleton instance for clean test teardowns."""
    global _DEFAULT_QUARANTINE
    with _DEFAULT_QUARANTINE_LOCK:
        _DEFAULT_QUARANTINE = None


def get_quarantine_data(csv_path: Optional[Union[str, Path]] = None) -> QuarantineInspectionSnapshot:
    """Top-level convenience wrapper for inspecting invoice quarantine."""
    return get_default_quarantine(csv_path=csv_path).inspect()


def repair_quarantine_row(
    row_idx: int = 0,
    invoice_id: Optional[str] = None,
    amount: Optional[str] = None,
    date: Optional[str] = None,
    auto_recover: bool = False,
    auto_recover_all: bool = False,
    csv_path: Optional[Union[str, Path]] = None,
) -> QuarantineRepairResult:
    """Top-level convenience wrapper for repairing invoice quarantine rows."""
    return get_default_quarantine(csv_path=csv_path).repair(
        row_idx=row_idx,
        invoice_id=invoice_id,
        amount=amount,
        date=date,
        auto_recover=auto_recover,
        auto_recover_all=auto_recover_all,
    )


def reset_quarantine_fixture(csv_path: Optional[Union[str, Path]] = None) -> QuarantineResetResult:
    """Top-level convenience wrapper for resetting the invoice quarantine fixture."""
    return get_default_quarantine(csv_path=csv_path).reset()


def get_adversarial_csv_path() -> str:
    """Returns the resolved string path to the active adversarial CSV fixture."""
    return str(get_default_csv_path())

