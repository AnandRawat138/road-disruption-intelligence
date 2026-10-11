"""Local LLM (Ollama) detection, hardware check, model recommendation and model download."""
from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import subprocess

import httpx

from ..config import settings

log = logging.getLogger(__name__)

OLLAMA_DOWNLOAD_URL = "https://ollama.com/download/windows"

# Approximate requirements for 4-bit quantised models (download size / comfortable system RAM).
MODEL_CATALOG = [
    {"name": "llama3.2:3b", "download_gb": 2.0, "min_ram_gb": 8, "min_vram_gb": 0,
     "notes": "Small and fast; acceptable for headline classification, weaker at extraction."},
    {"name": "qwen2.5:7b", "download_gb": 4.7, "min_ram_gb": 12, "min_vram_gb": 6,
     "notes": "Good structured-output quality for its size. Recommended default for 16 GB machines."},
    {"name": "llama3:8b", "download_gb": 4.7, "min_ram_gb": 12, "min_vram_gb": 6,
     "notes": "Solid general model; tested with this application."},
    {"name": "qwen2.5:14b", "download_gb": 9.0, "min_ram_gb": 24, "min_vram_gb": 10,
     "notes": "Better extraction quality; slow without a GPU with 10 GB+ VRAM."},
    {"name": "qwen2.5:32b", "download_gb": 20.0, "min_ram_gb": 48, "min_vram_gb": 24,
     "notes": "Workstation-class hardware only."},
]


def hardware_info() -> dict:
    info = {"os": platform.platform(), "cpu_count": os.cpu_count(), "ram_gb": None, "gpus": [],
            "disk_free_gb": None}
    try:
        info["disk_free_gb"] = round(shutil.disk_usage(settings.runtime_dir).free / 1e9, 1)
    except OSError:
        pass
    if os.name == "nt":
        try:
            import ctypes

            class MEMSTATUS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
            st = MEMSTATUS()
            st.dwLength = ctypes.sizeof(MEMSTATUS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
            info["ram_gb"] = round(st.ullTotalPhys / 1e9, 1)
        except Exception:
            pass
    else:
        try:
            info["ram_gb"] = round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1e9, 1)
        except (ValueError, OSError, AttributeError):
            pass
    smi = shutil.which("nvidia-smi")
    if smi:
        try:
            out = subprocess.run([smi, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                                 capture_output=True, text=True, timeout=10).stdout
            for line in out.strip().splitlines():
                name, mem = [x.strip() for x in line.split(",")[:2]]
                info["gpus"].append({"name": name, "vram_gb": round(float(mem) / 1024, 1)})
        except Exception:
            pass
    return info


def recommend(hw: dict) -> dict:
    ram = hw.get("ram_gb") or 0
    vram = max([g.get("vram_gb", 0) for g in hw.get("gpus", [])] or [0])
    suitable = [m for m in MODEL_CATALOG if ram >= m["min_ram_gb"]]
    fast = [m for m in suitable if vram >= m["min_vram_gb"]]
    pick = None
    for name in ("qwen2.5:7b", "llama3:8b", "llama3.2:3b"):
        cand = next((m for m in (fast or suitable) if m["name"] == name), None)
        if cand:
            pick = cand
            break
    reason = (f"Detected {ram or 'unknown'} GB RAM and {vram or 'no'} GB GPU memory. "
              + ("A GPU was detected; models within its memory run fastest." if vram else
                 "No NVIDIA GPU detected – models run on the CPU and will be slower."))
    return {"recommended": pick["name"] if pick else None, "reason": reason,
            "catalog": [{**m, "suitable": m in suitable, "gpu_accelerated": m in fast} for m in MODEL_CATALOG]}


def detect(base_url: str) -> dict:
    exe = shutil.which("ollama")
    if not exe and os.name == "nt":
        cand = os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe")
        exe = cand if os.path.exists(cand) else None
    status = {"installed": bool(exe), "executable": exe, "reachable": False, "version": None, "models": [],
              "base_url": base_url, "download_url": OLLAMA_DOWNLOAD_URL, "error": None}
    try:
        with httpx.Client(timeout=5) as c:
            v = c.get(f"{base_url.rstrip('/')}/api/version")
            if v.status_code == 200:
                status["reachable"] = True
                status["version"] = v.json().get("version")
                tags = c.get(f"{base_url.rstrip('/')}/api/tags")
                if tags.status_code == 200:
                    for m in tags.json().get("models", []):
                        det = m.get("details") or {}
                        status["models"].append({
                            "name": m.get("name"), "size_gb": round((m.get("size") or 0) / 1e9, 1),
                            "parameter_size": det.get("parameter_size"),
                            "embedding_only": det.get("family") in ("nomic-bert", "bert") or "embed" in (m.get("name") or "")})
    except httpx.HTTPError as e:
        status["error"] = f"Ollama service not reachable at {base_url} ({type(e).__name__})"
    return status


def pull_model(base_url: str, model: str, ctx) -> dict:
    """Stream ``/api/pull`` and report progress. Called only after explicit operator confirmation."""
    url = f"{base_url.rstrip('/')}/api/pull"
    last_status = ""
    with httpx.Client(timeout=httpx.Timeout(60, read=600)) as c:
        with c.stream("POST", url, json={"model": model, "stream": True}) as resp:
            if resp.status_code != 200:
                return {"message": f"Ollama refused the pull (HTTP {resp.status_code})", "_status": "FAILED"}
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if ev.get("error"):
                    return {"message": f"Pull failed: {ev['error']}", "_status": "FAILED"}
                last_status = ev.get("status", last_status)
                total, done = ev.get("total"), ev.get("completed")
                if total and done is not None:
                    ctx.update(processed=int(done // 1_000_000), total=int(total // 1_000_000),
                               message=f"{last_status}: {done / 1e9:.2f} / {total / 1e9:.2f} GB")
                else:
                    ctx.update(message=last_status)
                if ctx.cancelled():
                    return {"message": "Download cancelled by operator", "_status": "CANCELLED"}
    ok = last_status == "success"
    return {"message": f"Model {model} downloaded and verified" if ok else f"Pull ended with status '{last_status}'",
            "_status": "COMPLETED" if ok else "FAILED"}
