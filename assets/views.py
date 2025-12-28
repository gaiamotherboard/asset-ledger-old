"""
Asset Management Views
Ported from FastAPI app - handles all asset interactions

Key features:
- Auto-creates assets on first visit (get_or_create pattern)
- Hardware scan uploads with lshw parsing
- Intake form updates
- Drive status management
- Audit trail logging (AssetTouch)
"""

import hashlib
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple


def _walk(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            if isinstance(v, (dict, list)):
                yield from _walk(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk(item)


def _human_bytes(n):
    if n is None:
        return "—"
    try:
        n = float(n)
    except Exception:
        return "—"
    units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]
    i = 0
    while n >= 1024 and i < len(units) - 1:
        n /= 1024
        i += 1
    if i == 0:
        return f"{int(n)} {units[i]}"
    return f"{n:.1f} {units[i]}"


def _human_hz(hz):
    if not hz:
        return "—"
    try:
        hz = float(hz)
    except Exception:
        return "—"
    return f"{hz / 1e9:.2f} GHz"


def _upower_get(text, key):
    m = re.search(rf"^\s*{re.escape(key)}:\s*(.+)$", text or "", re.MULTILINE)
    return m.group(1).strip() if m else None


def build_hw_context(bundle):
    bundle = bundle or {}
    sources = bundle.get("sources", {}) or {}
    status = (bundle.get("meta", {}) or {}).get("status", {}) or {}

    # ----- lshw extraction -----
    lshw = sources.get("lshw") or {}
    cpu_node = next(
        (
            n
            for n in _walk(lshw)
            if isinstance(n, dict) and n.get("class") == "processor"
        ),
        None,
    )
    ram_node = next(
        (
            n
            for n in _walk(lshw)
            if isinstance(n, dict)
            and n.get("class") == "memory"
            and (n.get("description") or "").lower() == "system memory"
        ),
        None,
    )
    gpu_node = next(
        (n for n in _walk(lshw) if isinstance(n, dict) and n.get("class") == "display"),
        None,
    )

    net_nodes = [
        n for n in _walk(lshw) if isinstance(n, dict) and n.get("class") == "network"
    ]
    wifi_node = next(
        (
            n
            for n in net_nodes
            if "wireless" in (n.get("product") or "").lower()
            or (n.get("logicalname") or "").startswith(("wl", "wlan"))
        ),
        None,
    )
    eth_node = next((n for n in net_nodes if n is not wifi_node), None)

    tb_nodes = [
        n
        for n in _walk(lshw)
        if isinstance(n, dict)
        and "thunderbolt"
        in ((n.get("product") or "") + " " + (n.get("description") or "")).lower()
    ]
    tb_node = next(
        (n for n in tb_nodes if "NHI" in (n.get("product") or "")), None
    ) or (tb_nodes[0] if tb_nodes else None)

    # ----- edid extraction -----
    edid = sources.get("edid") or ""
    disp_mfg = None
    disp_panel = None
    disp_native = None
    m = re.search(r"Manufacturer:\s*([A-Za-z0-9]+)", edid)
    if m:
        disp_mfg = m.group(1).strip()
    m = re.search(r"Alphanumeric Data String:\s*'([^']+)'", edid)
    if m:
        disp_panel = m.group(1).strip()
    m = re.search(r"DTD 1:\s*([0-9]+x[0-9]+)\s+([0-9.]+)\s+Hz", edid)
    if m:
        disp_native = f"{m.group(1).replace('x', '×')} @ {float(m.group(2)):.2f} Hz"

    # ----- upower (battery) -----
    upower = sources.get("upower") or ""
    batt_vendor = _upower_get(upower, "vendor")
    batt_model = _upower_get(upower, "model")
    batt_full = _upower_get(upower, "energy-full")
    batt_design = _upower_get(upower, "energy-full-design")
    batt_cap = _upower_get(upower, "capacity")  # percent string

    # ----- lsblk (drives) -----
    lsblk = sources.get("lsblk") or {}
    blockdevices = lsblk.get("blockdevices") if isinstance(lsblk, dict) else None
    blockdevices = blockdevices or []
    drives = []
    for d in blockdevices:
        if not isinstance(d, dict):
            continue
        if d.get("type") != "disk":
            continue
        parts = []
        for c in d.get("children") or []:
            if not isinstance(c, dict) or c.get("type") != "part":
                continue
            parts.append(
                {
                    "name": c.get("name"),
                    "fstype": c.get("fstype"),
                    "size": _human_bytes(c.get("size")),
                    "mountpoint": c.get("mountpoint"),
                    "fsuse": c.get("fsuse%"),
                }
            )
        drives.append(
            {
                "name": f"/dev/{d.get('name')}" if d.get("name") else "—",
                "model": d.get("model") or "—",
                "serial": d.get("serial") or "—",
                "size": _human_bytes(d.get("size")),
                "tran": d.get("tran") or "—",
                "wwn": d.get("wwn") or "—",
                "parts": parts,
            }
        )

    # ----- lsusb (USB devices) -----
    lsusb = sources.get("lsusb") or ""
    usb_devices = []
    for line in lsusb.splitlines() if isinstance(lsusb, str) else []:
        if "Linux Foundation" in line:
            continue
        if line.strip():
            usb_devices.append(line.strip())

    # ----- smart (basic error hint) -----
    smart = sources.get("smart") or ""
    smart_hint = None
    if isinstance(smart, str) and "Permission denied" in smart:
        smart_hint = "Permission denied"
    elif isinstance(smart, str) and smart.strip():
        smart_hint = "OK"

    # ----- scan health -----
    health_rows = []
    for tool in ["lshw", "lsblk", "lspci", "lsusb", "upower", "edid", "smart"]:
        st = status.get(tool) or {}
        rc = st.get("rc")
        stderr = st.get("stderr")
        stderr_one = None
        if isinstance(stderr, str) and stderr.strip():
            stderr_one = stderr.strip().splitlines()[0][:140]
        health_rows.append(
            {
                "tool": tool,
                "rc": rc,
                "stderr": stderr_one,
            }
        )

    hw = {
        "intake": bundle.get("intake") or {},
        "cpu": {
            "model": (cpu_node.get("product") if cpu_node else None) or "—",
            "max": _human_hz(cpu_node.get("size") if cpu_node else None),
            "microcode": (cpu_node.get("configuration") or {}).get("microcode")
            if cpu_node
            else None,
        },
        "ram": {
            "total": _human_bytes(ram_node.get("size") if ram_node else None),
        },
        "gpu": {
            "model": (gpu_node.get("product") if gpu_node else None) or "—",
            "driver": (
                (gpu_node.get("configuration") or {}).get("driver")
                if gpu_node
                else None
            )
            or "—",
        },
        "display": {
            "panel": "—"
            if not (disp_mfg or disp_panel)
            else f"{disp_mfg or '—'} {disp_panel or '—'}",
            "native": disp_native or "—",
        },
        "battery": {
            "model": "—"
            if not (batt_vendor or batt_model)
            else f"{batt_vendor or '—'} {batt_model or '—'}",
            "health": "—"
            if not (batt_full or batt_design or batt_cap)
            else f"{batt_full or '—'} / {batt_design or '—'} ({(batt_cap or '—').strip()})",
        },
        "wifi": {
            "model": (wifi_node.get("product") if wifi_node else None) or "—",
            "driver": (
                (wifi_node.get("configuration") or {}).get("driver")
                if wifi_node
                else None
            )
            or "—",
        },
        "ethernet": {
            "model": (eth_node.get("product") if eth_node else None) or "—",
            "driver": (
                (eth_node.get("configuration") or {}).get("driver")
                if eth_node
                else None
            )
            or "—",
            "ifname": (eth_node.get("logicalname") if eth_node else None) or "—",
            "mac": (eth_node.get("serial") if eth_node else None) or "—",
        },
        "thunderbolt": {
            "model": (tb_node.get("product") if tb_node else None) or "—",
            "driver": (
                (tb_node.get("configuration") or {}).get("driver") if tb_node else None
            )
            or "—",
        },
        "drives": drives,
        "usb_devices": usb_devices,
        "smart_hint": smart_hint or "—",
        "scan": {
            "generated_at": bundle.get("generated_at") or "—",
            "scanner": f"{(bundle.get('scanner') or {}).get('hostname', '—')} / {(bundle.get('scanner') or {}).get('user', '—')}",
            "health_rows": health_rows,
        },
    }
    return hw


from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .forms import (
    AssetIntakeForm,
    DriveRemovalImportForm,
    DriveStatusForm,
    HardwareScanUploadForm,
)
from .lshw_parser import extract_serial, format_bytes, parse_disks, parse_lshw_json
from .models import (
    Asset,
    AssetTouch,
    Drive,
    DriveRemovalBatch,
    DriveRemovalLink,
    HardwareScan,
)
from .utils import norm_serial, resolve_removed_drives_for_asset


def _safe_get(d: Any, *path: str, default=None):
    """
    Safe dict traversal helper.
    Example: _safe_get(bundle, "sources", "lshw", default={})
    """
    cur = d
    for p in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(p)
    return default if cur is None else cur


def _format_hz(hz: Optional[int]) -> Optional[str]:
    if hz is None:
        return None
    try:
        hz = int(hz)
    except Exception:
        return None
    if hz <= 0:
        return None
    ghz = hz / 1_000_000_000
    if ghz >= 1:
        return f"{ghz:.2f} GHz"
    mhz = hz / 1_000_000
    return f"{mhz:.0f} MHz"


def _extract_cpu_details_from_lshw(lshw: dict) -> dict:
    cpu = {
        "model": None,
        "vendor": None,
        "cores": None,
        "threads": None,
        "max_hz": None,
        "max_hz_human": None,
    }
    if not isinstance(lshw, dict):
        return cpu
    # Reuse the existing parser's walk by calling parse_lshw_json, but that only returns a string for cpu_info.
    # For richer details, scan nodes similarly with light heuristics.
    stack = [lshw]
    while stack:
        n = stack.pop()
        if not isinstance(n, dict):
            continue
        kids = n.get("children")
        if isinstance(kids, list):
            stack.extend(kids)
        if n.get("class") == "processor":
            cpu["model"] = (n.get("product") or "").strip() or None
            cpu["vendor"] = (n.get("vendor") or "").strip() or None
            cfg = n.get("configuration") or {}
            if isinstance(cfg, dict):
                c = cfg.get("cores")
                t = cfg.get("threads")
                try:
                    cpu["cores"] = int(str(c)) if c is not None else None
                except Exception:
                    cpu["cores"] = None
                try:
                    cpu["threads"] = int(str(t)) if t is not None else None
                except Exception:
                    cpu["threads"] = None
            # lshw uses units Hz and stores max-ish in "capacity" or current in "size"
            for k in ("capacity", "size"):
                v = n.get(k)
                if isinstance(v, (int, float)):
                    cpu["max_hz"] = int(v)
                    break
                if isinstance(v, str) and v.isdigit():
                    cpu["max_hz"] = int(v)
                    break
            cpu["max_hz_human"] = _format_hz(cpu["max_hz"])
            break
    return cpu


def _extract_display_from_lshw(lshw: dict) -> List[dict]:
    displays: List[dict] = []
    if not isinstance(lshw, dict):
        return displays
    stack = [lshw]
    while stack:
        n = stack.pop()
        if not isinstance(n, dict):
            continue
        kids = n.get("children")
        if isinstance(kids, list):
            stack.extend(kids)
        if n.get("class") == "display":
            cfg = n.get("configuration") or {}
            res = None
            if isinstance(cfg, dict):
                res = cfg.get("resolution")
            displays.append(
                {
                    "product": (n.get("product") or n.get("description") or "").strip()
                    or None,
                    "vendor": (n.get("vendor") or "").strip() or None,
                    "resolution": res,
                    "driver": cfg.get("driver") if isinstance(cfg, dict) else None,
                }
            )
    return displays


def _extract_network_from_lshw(lshw: dict) -> List[dict]:
    adapters: List[dict] = []
    if not isinstance(lshw, dict):
        return adapters
    stack = [lshw]
    while stack:
        n = stack.pop()
        if not isinstance(n, dict):
            continue
        kids = n.get("children")
        if isinstance(kids, list):
            stack.extend(kids)
        if n.get("class") == "network":
            cfg = n.get("configuration") or {}
            adapters.append(
                {
                    "product": (n.get("product") or n.get("description") or "").strip()
                    or None,
                    "vendor": (n.get("vendor") or "").strip() or None,
                    "logicalname": n.get("logicalname"),
                    "mac": n.get("serial"),
                    "driver": cfg.get("driver") if isinstance(cfg, dict) else None,
                    "wireless": bool(isinstance(cfg, dict) and cfg.get("wireless")),
                    "ip": cfg.get("ip") if isinstance(cfg, dict) else None,
                }
            )
    return adapters


def _parse_upower_battery(upower_text: Optional[str]) -> dict:
    """
    Parse enough of `upower -d` output to show battery health and cycles.
    Returns a dict with keys like:
      present(bool), state(str), percentage(str), capacity_pct(float), cycles(int), energy_full(Wh), energy_full_design(Wh)
    """
    result = {
        "present": False,
        "state": None,
        "percentage": None,
        "capacity_pct": None,
        "charge_cycles": None,
        "energy_full_wh": None,
        "energy_full_design_wh": None,
        "vendor": None,
        "model": None,
        "serial": None,
    }
    if not upower_text or not isinstance(upower_text, str):
        return result

    # Only parse the BAT0 section (first battery device)
    # We stop when another "Device:" starts after we've begun.
    lines = upower_text.splitlines()
    in_bat = False
    for line in lines:
        if line.startswith("Device: "):
            if in_bat:
                break
            in_bat = "battery_BAT" in line
            continue
        if not in_bat:
            continue

        m = re.match(r"^\s*vendor:\s+(.*)$", line)
        if m:
            result["vendor"] = m.group(1).strip()
            continue
        m = re.match(r"^\s*model:\s+(.*)$", line)
        if m:
            result["model"] = m.group(1).strip()
            continue
        m = re.match(r"^\s*serial:\s+(.*)$", line)
        if m:
            result["serial"] = m.group(1).strip()
            continue

        m = re.match(r"^\s*present:\s+(yes|no)\s*$", line)
        if m:
            result["present"] = m.group(1) == "yes"
            continue
        m = re.match(r"^\s*state:\s+(.*)$", line)
        if m:
            result["state"] = m.group(1).strip()
            continue
        m = re.match(r"^\s*percentage:\s+(\d+%?)\s*$", line)
        if m:
            val = m.group(1)
            result["percentage"] = val if val.endswith("%") else f"{val}%"
            continue
        m = re.match(r"^\s*capacity:\s+([0-9.]+)%\s*$", line)
        if m:
            try:
                result["capacity_pct"] = float(m.group(1))
            except Exception:
                result["capacity_pct"] = None
            continue
        m = re.match(r"^\s*charge-cycles:\s+(\d+)\s*$", line)
        if m:
            try:
                result["charge_cycles"] = int(m.group(1))
            except Exception:
                result["charge_cycles"] = None
            continue
        m = re.match(r"^\s*energy-full:\s+([0-9.]+)\s+Wh\s*$", line)
        if m:
            try:
                result["energy_full_wh"] = float(m.group(1))
            except Exception:
                result["energy_full_wh"] = None
            continue
        m = re.match(r"^\s*energy-full-design:\s+([0-9.]+)\s+Wh\s*$", line)
        if m:
            try:
                result["energy_full_design_wh"] = float(m.group(1))
            except Exception:
                result["energy_full_design_wh"] = None
            continue

    return result


def _parse_smartctl_for_drive(smart_text: Optional[str]) -> dict:
    """
    Parse a subset of smartctl output for a single drive.
    Returns keys: model, serial, capacity_bytes, overall_health, power_on_hours, power_cycle_count, temperature_c
    """
    out = {
        "model": None,
        "serial": None,
        "capacity_bytes": None,
        "overall_health": None,
        "power_on_hours": None,
        "power_cycle_count": None,
        "temperature_c": None,
    }
    if not smart_text or not isinstance(smart_text, str):
        return out

    # Model / Serial / Capacity
    m = re.search(r"^Device Model:\s+(.*)$", smart_text, re.MULTILINE)
    if m:
        out["model"] = m.group(1).strip()
    m = re.search(r"^Serial Number:\s+(.*)$", smart_text, re.MULTILINE)
    if m:
        out["serial"] = m.group(1).strip()
    m = re.search(r"^User Capacity:\s+([\d,]+)\s+bytes", smart_text, re.MULTILINE)
    if m:
        try:
            out["capacity_bytes"] = int(m.group(1).replace(",", ""))
        except Exception:
            out["capacity_bytes"] = None

    # Overall health
    m = re.search(r"^SMART overall-health.*?:\s+(.*)$", smart_text, re.MULTILINE)
    if m:
        out["overall_health"] = m.group(1).strip()

    # Some key attributes (ATA) - parse RAW_VALUE from matching attribute names
    def _attr_raw(name: str) -> Optional[int]:
        mm = re.search(
            rf"^\s*\d+\s+{re.escape(name)}\s+.*?\s+(\d+)\s*$", smart_text, re.MULTILINE
        )
        if not mm:
            return None
        try:
            return int(mm.group(1))
        except Exception:
            return None

    out["power_on_hours"] = _attr_raw("Power_On_Hours")
    out["power_cycle_count"] = _attr_raw("Power_Cycle_Count")

    # Temperature line sometimes like: "194 Temperature_Celsius ... 41 (Min/Max ...)"
    m = re.search(
        r"^\s*194\s+Temperature_Celsius\s+.*?\s+(\d+)\s*(?:\(|$)",
        smart_text,
        re.MULTILINE,
    )
    if m:
        try:
            out["temperature_c"] = int(m.group(1))
        except Exception:
            out["temperature_c"] = None

    return out


def _filter_internal_drives_from_lsblk(lsblk: dict) -> List[dict]:
    """
    Return only "internal" disks from lsblk:
    - type == disk
    - tran in (sata, nvme, sas, ata, pci, scsi) or rm == False
    Filters out typical removable boot media (usb, mmc) where possible.
    """
    disks: List[dict] = []
    bds = _safe_get(lsblk, "blockdevices", default=[])
    if not isinstance(bds, list):
        return disks
    for bd in bds:
        if not isinstance(bd, dict):
            continue
        if bd.get("type") != "disk":
            continue
        tran = (bd.get("tran") or "").lower()
        rm = bd.get("rm")
        name = (bd.get("name") or "").lower()
        # Exclude typical removable/transient devices
        if tran in ("usb", "mmc"):
            continue
        if name.startswith("loop") or name.startswith("sr") or name.startswith("mmc"):
            continue
        # If it says removable, skip unless it looks like a fixed disk
        if rm is True and tran not in ("sata", "nvme", "sas", "scsi", "ata", "pci"):
            continue
        disks.append(bd)
    return disks


def _build_rich_hardware_summary(bundle: dict) -> dict:
    """
    Produce a richer summary from the scan bundle sources for template display.
    This intentionally remains a pure function (no DB writes) and is safe to call on GET.
    """
    sources = _safe_get(bundle, "sources", default={}) or {}
    lshw = sources.get("lshw") if isinstance(sources, dict) else None
    lsblk = sources.get("lsblk") if isinstance(sources, dict) else None
    upower_txt = sources.get("upower") if isinstance(sources, dict) else None
    edid_txt = sources.get("edid") if isinstance(sources, dict) else None
    smart_txt = sources.get("smart") if isinstance(sources, dict) else None

    # System / cpu / memory from lshw
    parsed_lshw = parse_lshw_json(lshw) if isinstance(lshw, dict) else {}
    system_info = parsed_lshw.get("system_info") or {}
    cpu = _extract_cpu_details_from_lshw(lshw) if isinstance(lshw, dict) else {}
    memory_slots = parsed_lshw.get("memory_slots") or []
    memory_total_bytes = parsed_lshw.get("memory_total_bytes")
    memory_total_human = None
    if memory_total_bytes:
        try:
            gb = float(memory_total_bytes) / (1024**3)
            memory_total_human = (
                f"{int(round(gb))} GB" if abs(gb - round(gb)) < 0.01 else f"{gb:.1f} GB"
            )
        except Exception:
            memory_total_human = None

    # Graphics & network
    graphics = _extract_display_from_lshw(lshw) if isinstance(lshw, dict) else []
    network = _extract_network_from_lshw(lshw) if isinstance(lshw, dict) else []

    # Battery from upower (preferred for health/cycles)
    battery = _parse_upower_battery(upower_txt)

    # Drives: merge internal disks from lsblk with SMART (single-drive output in this sample)
    internal_lsblk_disks = _filter_internal_drives_from_lsblk(
        lsblk if isinstance(lsblk, dict) else {}
    )
    smart = _parse_smartctl_for_drive(smart_txt)

    # Summarize drives for display: show internal disks only, but keep a count of removable too (optional)
    drive_summaries: List[dict] = []
    for d in internal_lsblk_disks:
        if not isinstance(d, dict):
            continue
        # Prefer lsblk for path/model/serial/transport; fill gaps from smart when serial matches.
        serial = d.get("serial") or smart.get("serial")
        model = d.get("model") or smart.get("model")
        size_bytes = d.get("size") or smart.get("capacity_bytes")
        try:
            size_bytes_int = (
                int(size_bytes) if isinstance(size_bytes, (int, float)) else None
            )
        except Exception:
            size_bytes_int = None
        drive_summaries.append(
            {
                "path": d.get("path"),
                "name": d.get("name"),
                "tran": d.get("tran"),
                "model": model,
                "serial": serial,
                "size_bytes": size_bytes_int,
                "size_human": format_bytes(size_bytes_int) if size_bytes_int else None,
                "smart_overall_health": smart.get("overall_health")
                if (serial and smart.get("serial") and serial == smart.get("serial"))
                else smart.get("overall_health"),
                "smart_power_on_hours": smart.get("power_on_hours"),
                "smart_power_cycle_count": smart.get("power_cycle_count"),
                "smart_temperature_c": smart.get("temperature_c"),
            }
        )

    # EDID: parse model string if present (simple extraction)
    panel_model = None
    if isinstance(edid_txt, str):
        m = re.search(r"Alphanumeric Data String:\s+'([^']+)'", edid_txt)
        if m:
            # first string is often vendor, second is panel model; keep both when possible
            strings = re.findall(r"Alphanumeric Data String:\s+'([^']+)'", edid_txt)
            if strings:
                panel_model = " / ".join(strings[:2])

    # Build a compact "spec line" as well (useful even if template doesn’t render all fields yet)
    spec_line_parts: List[str] = []
    if system_info.get("vendor") or system_info.get("product"):
        spec_line_parts.append(
            " ".join(
                [
                    str(system_info.get("vendor") or "").strip(),
                    str(system_info.get("product") or "").strip(),
                ]
            ).strip()
        )
    if cpu.get("model"):
        c = cpu["model"]
        if cpu.get("cores") and cpu.get("threads"):
            c = f"{c} ({cpu['cores']}C/{cpu['threads']}T)"
        spec_line_parts.append(c)
    if memory_total_human:
        spec_line_parts.append(f"RAM {memory_total_human}")
    if drive_summaries:
        # show internal storage total-ish as joined list
        ds = []
        for dr in drive_summaries:
            label = " ".join(
                [
                    p
                    for p in [dr.get("size_human"), dr.get("tran"), dr.get("model")]
                    if p
                ]
            ).strip()
            if label:
                ds.append(label)
        if ds:
            spec_line_parts.append("Storage: " + " + ".join(ds[:3]))

    return {
        "system": system_info,
        "cpu": cpu,
        "memory": {
            "total_bytes": memory_total_bytes,
            "total_human": memory_total_human,
            "slots": memory_slots,
        },
        "graphics": graphics,
        "network": network,
        "battery": battery,
        "display_panel": {"edid_summary": panel_model},
        "drives": drive_summaries,
        "spec_line": " • ".join([p for p in spec_line_parts if p]),
    }


def _log_touch(asset, touch_type, user, details=None):
    """
    Helper function to log an asset interaction (audit trail).
    Replaces manual INSERT INTO asset_touches from FastAPI.
    """
    AssetTouch.objects.create(
        asset=asset,
        touch_type=touch_type,
        touched_by=user,
        details=details or {},
    )


@login_required
def home(request):
    """
    Home page - shows recent assets
    """
    recent_assets = Asset.objects.select_related("created_by").prefetch_related(
        "hardware_scans"
    )[:20]
    return render(request, "home.html", {"recent_assets": recent_assets})


@login_required
@require_http_methods(["GET", "POST"])
def asset_detail(request, asset_tag):
    """
    Main asset detail view - shows all asset information.

    IMPORTANT: Auto-creates asset on first GET (like FastAPI app)

    Handles:
    - GET: Display asset with all related data
    - POST: Handle intake form OR scan upload
    """
    # Get or create asset (auto-create on first visit!)
    asset, created = Asset.objects.get_or_create(
        asset_tag=asset_tag,
        defaults={"created_by": request.user},
    )

    # REMOVED: View logging causes massive DB bloat from page refreshes
    # Only log meaningful state changes (intake updates, scans, drive status)
    # _log_touch(asset, "view", request.user, {"asset_tag": asset_tag})

    # Get latest hardware scan
    latest_scan = (
        asset.hardware_scans.select_related("scanned_by")
        .order_by("-scanned_at")
        .first()
    )

    # Extract hardware info from latest scan
    cpu_info = None
    hw_summary = None

    # Additional parsed fields we'll expose to the template (legacy + richer bundle-based)
    system_info = None
    graphics = []
    network = []
    multimedia = {}
    battery = None

    # Memory defaults to avoid UnboundLocalError when no scan or no parsed memory
    memory_slots = []
    memory_total_bytes = None
    memory_total_human = None

    # New: richer summary generated from bundle sources (lshw+lsblk+smart+upower+edid)
    rich_summary = None

    hw = None

    if latest_scan:
        # Prefer stored summary for legacy hw_summary display
        if latest_scan.summary:
            hw_summary = latest_scan.summary

        # raw_json is the full bundle. For older scans that stored lshw directly,
        # fall back to treating raw_json as lshw.
        if latest_scan.raw_json:
            bundle = latest_scan.raw_json

            # New: hw context for the Tailwind/daisyUI asset detail UI
            try:
                hw = build_hw_context(bundle if isinstance(bundle, dict) else {})
            except Exception:
                hw = build_hw_context({})

            # If this is a scan bundle, parse lshw from sources; otherwise treat raw_json as lshw
            lshw_json = _safe_get(bundle, "sources", "lshw", default=None)
            if not isinstance(lshw_json, dict):
                lshw_json = bundle if isinstance(bundle, dict) else None

            if isinstance(lshw_json, dict):
                parsed = parse_lshw_json(lshw_json)
                cpu_info = parsed.get("cpu_info")
                system_info = parsed.get("system_info")
                graphics = parsed.get("graphics", []) or []
                network = parsed.get("network", []) or []
                multimedia = parsed.get("multimedia", {}) or {}
                battery = parsed.get("battery")

                memory_slots = parsed.get("memory_slots", []) or []
                memory_total_bytes = parsed.get("memory_total_bytes")
                memory_total_human = None
                if memory_total_bytes:
                    try:
                        gb = float(memory_total_bytes) / (1024**3)
                        if abs(gb - round(gb)) < 0.01:
                            memory_total_human = f"{int(round(gb))} GB"
                        else:
                            memory_total_human = f"{gb:.1f} GB"
                    except Exception:
                        memory_total_human = None

                if not hw_summary:
                    hw_summary = parsed.get("hw_summary")

            # New: richer summary from full bundle (only when schema looks right)
            if (
                isinstance(bundle, dict)
                and bundle.get("schema") == "motherboard.scan_bundle.v1"
            ):
                try:
                    rich_summary = _build_rich_hardware_summary(bundle)
                except Exception:
                    # Do not break the page if parsing has unexpected edge cases
                    rich_summary = None

    if hw is None:
        hw = build_hw_context({})

    # Get drives
    drives = asset.drives.all()

    # Filter out ephemeral / runtime block devices that come from the live media
    # (examples: mmcblk*, loop*, sr*). We keep the full `drives` queryset for
    # storage but expose `display_drives` to the template for the user-facing list.
    def _is_ephemeral(drive):
        ln = (drive.logicalname or "").lower()
        # Canonicalize common /dev/ names
        if ln.startswith("/dev/"):
            ln = ln[5:]
        # Exclude mmc (mmcblk*), loop devices, and optical (sr*)
        return ln.startswith("mmc") or ln.startswith("loop") or ln.startswith("sr")

    display_drives = [d for d in drives if not _is_ephemeral(d)]

    # Flag that a first-class hard drive is present (used by the UI to show a warning)
    hard_drive_present = bool(display_drives)

    # Get audit trail (touches)
    touches = asset.touches.select_related("touched_by").order_by("-touched_at")[:50]

    # Forms
    intake_form = AssetIntakeForm(instance=asset)
    upload_form = HardwareScanUploadForm()

    context = {
        "asset": asset,
        "latest_scan": latest_scan,
        "cpu_info": cpu_info,
        "hw_summary": hw_summary,
        # Rich bundle-derived summary for modern scan bundles
        "rich_summary": rich_summary,
        # New Tailwind/daisyUI hardware context (from latest scan bundle)
        "hw": hw,
        # New hardware fields exposed to the template
        "system_info": system_info,
        "graphics": graphics,
        "network": network,
        "multimedia": multimedia,
        "battery": battery,
        "drives": drives,
        "display_drives": display_drives,
        "hard_drive_present": hard_drive_present,
        # Memory fields (per-slot and totals) for template display
        "memory_slots": memory_slots,
        "memory_total_bytes": memory_total_bytes,
        "memory_total_human": memory_total_human,
        "touches": touches,
        "intake_form": intake_form,
        "upload_form": upload_form,
        "saved": False,
        "scan_saved": False,
    }

    return render(request, "assets/asset_detail.html", context)


@login_required
@require_http_methods(["POST"])
def asset_intake_update(request, asset_tag):
    """
    Update asset intake information (status, device type, cosmetic grade, etc.)
    Replaces /asset/{asset_tag}/intake_form from FastAPI
    """
    asset = get_object_or_404(Asset, asset_tag=asset_tag)
    form = AssetIntakeForm(request.POST, instance=asset)

    if form.is_valid():
        # Save changes
        updated_asset = form.save()

        # Log the update
        changed_fields = {}
        for field in form.changed_data:
            changed_fields[field] = form.cleaned_data[field]

        _log_touch(
            asset,
            "intake_update",
            request.user,
            {
                "updated_fields": changed_fields,
            },
        )

        messages.success(request, "Asset intake information updated successfully!")
    else:
        messages.error(
            request, "Error updating asset information. Please check the form."
        )

    return redirect("asset_detail", asset_tag=asset_tag)


def _canonical_bundle_and_hash(bundle: dict) -> Tuple[str, str]:
    """
    Return (canonical_json, sha256_hex) for a scan bundle dict.
    """
    try:
        canonical = json.dumps(
            bundle, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
    except (TypeError, ValueError):
        canonical = json.dumps(
            bundle,
            default=str,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    return canonical, hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _ingest_scan_bundle_for_asset(
    *,
    asset: Asset,
    bundle: dict,
    user,
    user_notes: str,
    allow_asset_id_mismatch: bool = False,
) -> Tuple[bool, str]:
    """
    Ingest a scan bundle for an existing Asset.

    Returns (created_scan, message).
    - Deduplicates by (asset, bundle_hash)
    - Updates asset.computer_serial if blank
    - Upserts Drive rows from parsed disks
    - Logs AssetTouch scan_upload
    """
    from django.utils.dateparse import parse_datetime

    intake = bundle.get("intake", {}) or {}
    bundle_asset_id = str(intake.get("asset_id", "") or "")

    if (
        (not allow_asset_id_mismatch)
        and bundle_asset_id
        and bundle_asset_id != str(asset.asset_tag)
    ):
        return (
            False,
            f"Bundle asset_id '{bundle_asset_id}' does not match asset '{asset.asset_tag}'.",
        )

    _canonical, bundle_hash = _canonical_bundle_and_hash(bundle)

    existing = HardwareScan.objects.filter(asset=asset, bundle_hash=bundle_hash).first()
    if existing:
        return (False, "Duplicate scan bundle (already exists).")

    gen_at_raw = bundle.get("generated_at")
    generated_at = None
    if gen_at_raw:
        try:
            generated_at = parse_datetime(gen_at_raw)
        except Exception:
            generated_at = None

    tech_name = intake.get("tech_name", "") or ""
    client_name = intake.get("client_name", "") or ""
    cosmetic_condition = intake.get("cosmetic_condition", "") or ""
    intake_note = intake.get("note", "") or ""

    sources = bundle.get("sources", {}) or {}
    lshw_json = sources.get("lshw")

    parsed = {}
    if lshw_json:
        parsed = parse_lshw_json(lshw_json) or {}
    device_serial = parsed.get("device_serial")
    hw_summary = parsed.get("hw_summary")
    disks = parsed.get("disks", []) or []

    # Mirror device serial onto Asset.computer_serial (if blank).
    norm_device_serial = norm_serial(device_serial)
    if norm_device_serial:
        existing_cs = norm_serial(getattr(asset, "computer_serial", None))
        if not existing_cs:
            asset.computer_serial = norm_device_serial
            asset.save(update_fields=["computer_serial"])

    scan = HardwareScan.objects.create(
        asset=asset,
        device_serial=device_serial,
        raw_json=bundle,
        bundle_hash=bundle_hash,
        schema=bundle.get("schema", ""),
        generated_at=generated_at,
        tech_name=tech_name,
        client_name=client_name,
        cosmetic_condition=cosmetic_condition,
        intake_note=intake_note,
        summary=hw_summary,
        scanned_by=user,
        user_notes=user_notes,
    )

    for disk in disks:
        serial = disk.get("serial")
        if not serial or not serial.strip():
            continue
        defaults = {
            "logicalname": disk.get("logicalname", ""),
            "capacity_bytes": disk.get("size_bytes"),
            "model": disk.get("model", ""),
            "source": "lshw",
        }
        Drive.objects.update_or_create(asset=asset, serial=serial, defaults=defaults)

    resolved_count = resolve_removed_drives_for_asset(asset)

    _log_touch(
        asset,
        "scan_upload",
        user,
        {
            "scan_id": scan.id,
            "device_serial": device_serial,
            "drive_count": len(disks),
            "resolved_removed_before_scan": resolved_count,
        },
    )

    return (True, f"Saved scan bundle. Found {len(disks)} drive(s).")


@login_required
@require_http_methods(["POST"])
def asset_scan_upload(request, asset_tag):
    """
    Upload scan bundle JSON (motherboard.scan_bundle.v1).

    Replaces the old lshw-only upload flow. This view:
    - validates and accepts only the new scan bundle (form enforces schema)
    - requires that bundle.intake.asset_id matches the URL asset_tag
    - computes a canonical sha256 bundle hash and deduplicates
    - stores the raw bundle and bundle metadata on HardwareScan
    - calls the existing lshw parsing logic using bundle['sources']['lshw']
      so existing drive extraction and summary behavior remains unchanged
    - updates/creates Drive records from parsed lshw disks
    - logs the upload via AssetTouch
    """
    from django.utils.dateparse import parse_datetime

    asset = get_object_or_404(Asset, asset_tag=asset_tag)
    form = HardwareScanUploadForm(request.POST, request.FILES)

    if form.is_valid():
        bundle = form.cleaned_data.get("parsed_json")
        user_notes = form.cleaned_data.get("user_notes", "")

        created, msg = _ingest_scan_bundle_for_asset(
            asset=asset,
            bundle=bundle,
            user=request.user,
            user_notes=user_notes,
            allow_asset_id_mismatch=False,
        )
        if created:
            messages.success(request, msg)
        else:
            # duplicate or mismatch message
            if "does not match" in msg:
                messages.error(request, msg + " Upload rejected.")
            else:
                messages.success(request, msg)
    else:
        for error in form.errors.values():
            messages.error(request, error)

    return redirect("asset_detail", asset_tag=asset_tag)


@login_required
@require_http_methods(["POST"])
def asset_scan_bulk_upload(request):
    """
    Bulk upload scan bundles.

    Behavior:
    - Accept multiple JSON files in one request (input name: files)
    - Asset tag is derived from filename: ASSETTAG.json
    - If asset does not exist: create it + create a HardwareScan
    - If asset exists: ingest scan bundle for that asset (dedupe by bundle_hash)
    - If the bundle is a duplicate for that asset: skipped
    - If the bundle asset_id mismatches filename asset tag: error for that file
    """
    files = request.FILES.getlist("files")
    if not files:
        messages.error(request, "No files selected.")
        return redirect(request.META.get("HTTP_REFERER", "home"))

    results = {
        "total": len(files),
        "created_assets": 0,
        "updated_assets": 0,
        "created_scans": 0,
        "duplicates": 0,
        "failed": 0,
        "errors": [],
    }

    for f in files:
        name = os.path.basename(getattr(f, "name", "") or "").strip()
        m = re.match(r"^([A-Za-z0-9_-]+)\.json$", name)
        if not m:
            results["failed"] += 1
            results["errors"].append(
                {"file": name or "(unnamed)", "error": "Filename must be ASSETTAG.json"}
            )
            continue

        asset_tag = m.group(1)

        try:
            raw = f.read()
            bundle = json.loads(raw.decode("utf-8"))
            if not isinstance(bundle, dict):
                raise ValueError("Top-level JSON must be an object")
        except Exception as e:
            results["failed"] += 1
            results["errors"].append(
                {"file": name, "asset": asset_tag, "error": str(e)}
            )
            continue

        # Ensure the bundle asset_id matches the filename-derived asset tag
        intake = bundle.get("intake", {}) or {}
        bundle_asset_id = str(intake.get("asset_id", "") or "")
        if bundle_asset_id != str(asset_tag):
            results["failed"] += 1
            results["errors"].append(
                {
                    "file": name,
                    "asset": asset_tag,
                    "error": f"Bundle asset_id '{bundle_asset_id}' does not match filename asset '{asset_tag}'",
                }
            )
            continue

        asset, created_asset = Asset.objects.get_or_create(
            asset_tag=asset_tag,
            defaults={"created_by": request.user},
        )
        if created_asset:
            results["created_assets"] += 1
        else:
            results["updated_assets"] += 1

        created_scan, msg = _ingest_scan_bundle_for_asset(
            asset=asset,
            bundle=bundle,
            user=request.user,
            user_notes=f"Bulk upload from {name}",
            allow_asset_id_mismatch=False,
        )

        if created_scan:
            results["created_scans"] += 1
        else:
            if "Duplicate scan bundle" in msg:
                results["duplicates"] += 1
            else:
                results["failed"] += 1
                results["errors"].append(
                    {"file": name, "asset": asset_tag, "error": msg}
                )

    # User-friendly summary + short error preview
    if (
        results["created_scans"]
        or results["duplicates"]
        or results["created_assets"]
        or results["updated_assets"]
    ):
        messages.success(
            request,
            f"Bulk upload: {results['total']} file(s) processed · "
            f"{results['created_assets']} new asset(s), {results['updated_assets']} existing asset(s) · "
            f"{results['created_scans']} scan(s) saved · {results['duplicates']} duplicate(s) skipped · "
            f"{results['failed']} failed.",
        )
    if results["errors"]:
        preview = results["errors"][:5]
        preview_text = " | ".join(
            [f"{e.get('file')}: {e.get('error')}" for e in preview]
        )
        messages.warning(
            request,
            f"Bulk upload errors (first {len(preview)}): {preview_text}",
        )

    return redirect(request.META.get("HTTP_REFERER", "home"))


@login_required
@require_http_methods(["POST"])
def drive_status_update(request, asset_tag, drive_id):
    """
    Update drive status (present, removed, wiped, shredded, etc.)
    Replaces /asset/{asset_tag}/drive/{drive_id}/status from FastAPI
    """
    asset = get_object_or_404(Asset, asset_tag=asset_tag)
    drive = get_object_or_404(Drive, id=drive_id, asset=asset)

    form = DriveStatusForm(request.POST, instance=drive)

    if form.is_valid():
        drive = form.save(commit=False)
        drive.status_by = request.user
        drive.save()

        # Log the status change
        _log_touch(
            asset,
            "drive_status",
            request.user,
            {
                "drive_id": drive.id,
                "serial": drive.serial,
                "status": drive.status,
                "status_note": drive.status_note,
            },
        )

        messages.success(
            request, f"Drive status updated to '{drive.get_status_display()}'"
        )
    else:
        messages.error(request, "Error updating drive status.")

    return redirect("asset_detail", asset_tag=asset_tag)


@login_required
@require_http_methods(["GET", "POST"])
def drive_removals_import(request):
    """
    Upload/paste a 2-column list (computer_serial, drive_serial) representing
    drives removed BEFORE lshw scan.

    Creates a DriveRemovalBatch for audit, upserts DriveRemovalLink for idempotency,
    and resolves to real Drive rows for any Assets that already exist.
    """
    stats = None
    errors_preview = []

    if request.method == "POST":
        form = DriveRemovalImportForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file = form.cleaned_data.get("file")
            manual_text = form.cleaned_data.get("manual_text", "") or ""
            note = form.cleaned_data.get("note", "") or ""

            batch = DriveRemovalBatch.objects.create(
                created_by=request.user,
                original_file=uploaded_file if uploaded_file else None,
                original_filename=(getattr(uploaded_file, "name", "") or "")
                if uploaded_file
                else "",
                manual_text=manual_text,
                note=note,
            )

            total_rows = 0
            imported_rows = 0
            duplicate_rows = 0
            error_rows = 0

            # Track distinct computer_serials seen in this batch so we can resolve after import.
            seen_computer_serials = set()

            for cs, ds, raw_line, row_idx in form.iter_pairs():
                total_rows += 1

                if not cs or not ds:
                    error_rows += 1
                    if len(errors_preview) < 10:
                        errors_preview.append(
                            {
                                "row": row_idx,
                                "line": raw_line,
                                "error": "Missing computer_serial or drive_serial",
                            }
                        )
                    continue

                seen_computer_serials.add(cs)

                link, created = DriveRemovalLink.objects.get_or_create(
                    computer_serial=cs,
                    drive_serial=ds,
                    defaults={
                        "seen_count": 1,
                        "last_batch": batch,
                    },
                )

                if created:
                    imported_rows += 1
                else:
                    duplicate_rows += 1
                    link.seen_count = (link.seen_count or 0) + 1
                    link.last_batch = batch
                    link.save(
                        update_fields=["seen_count", "last_batch", "last_seen_at"]
                    )

            # Persist stats on the batch
            batch.total_rows = total_rows
            batch.imported_rows = imported_rows
            batch.duplicate_rows = duplicate_rows
            batch.error_rows = error_rows
            batch.save(
                update_fields=[
                    "total_rows",
                    "imported_rows",
                    "duplicate_rows",
                    "error_rows",
                ]
            )

            # Resolve for any assets already present.
            resolved_assets = 0
            resolved_drives = 0
            for cs in sorted(seen_computer_serials):
                asset = Asset.objects.filter(computer_serial=cs).first()
                if not asset:
                    continue
                resolved_assets += 1
                resolved_drives += resolve_removed_drives_for_asset(asset)

            stats = {
                "batch_id": batch.id,
                "total_rows": total_rows,
                "imported_rows": imported_rows,
                "duplicate_rows": duplicate_rows,
                "error_rows": error_rows,
                "resolved_assets": resolved_assets,
                "resolved_drives": resolved_drives,
            }

            messages.success(
                request,
                f"Imported drive removals batch #{batch.id}: "
                f"{imported_rows} new, {duplicate_rows} duplicate, {error_rows} error.",
            )
        else:
            for error in form.errors.values():
                messages.error(request, error)
    else:
        form = DriveRemovalImportForm()

    return render(
        request,
        "assets/drive_removals_import.html",
        {
            "form": form,
            "stats": stats,
            "errors_preview": errors_preview,
        },
    )


def drive_search_by_serial(request):
    """
    Search for drives by serial number.
    Replaces /drive/by_serial from FastAPI

    Returns JSON response with all drives matching the serial.
    """
    serial = request.GET.get("serial", "").strip()

    if not serial:
        return JsonResponse({"error": "Serial number required"}, status=400)

    # Find all drives with this serial
    drives = (
        Drive.objects.filter(serial=serial)
        .select_related("asset", "status_by")
        .order_by("-id")
    )

    matches = []
    for drive in drives:
        matches.append(
            {
                "drive_id": drive.id,
                "asset_tag": drive.asset.asset_tag,
                "drive_serial": drive.serial,
                "logicalname": drive.logicalname,
                "capacity_bytes": drive.capacity_bytes,
                "capacity_human": drive.capacity_human,
                "model": drive.model,
                "status": drive.status,
                "status_note": drive.status_note,
                "status_at": drive.status_at.isoformat() if drive.status_at else None,
            }
        )

    return JsonResponse(
        {
            "serial": serial,
            "count": len(matches),
            "matches": matches,
        }
    )


@login_required
def asset_list_json(request):
    """
    JSON API endpoint - list all assets with basic info
    Useful for external tools or scripts
    """
    assets = Asset.objects.select_related("created_by").order_by("-created_at")[:100]

    data = []
    for asset in assets:
        data.append(
            {
                "asset_tag": asset.asset_tag,
                "status": asset.status,
                "device_type": asset.device_type,
                "location": asset.location,
                "created_at": asset.created_at.isoformat(),
                "created_by": asset.created_by.username,
            }
        )

    return JsonResponse({"assets": data, "count": len(data)})
