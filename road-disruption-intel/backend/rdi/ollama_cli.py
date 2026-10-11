"""Interactive local-LLM (Ollama) setup used by setup_llm.bat.

Steps: detect Ollama -> check service -> hardware check -> recommend -> operator picks a
model -> download ONLY after confirmation -> verify -> small inference test -> optionally
make it the active provider. Nothing is installed silently.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import webbrowser

import httpx

from .db.session import SessionLocal, init_db
from .services import ollama_setup, settings_store

BASE = "http://127.0.0.1:11434"


def ask(prompt: str, default: str = "n") -> str:
    try:
        ans = input(prompt).strip()
    except EOFError:
        return default
    return ans or default


def main() -> int:
    print("=" * 70)
    print(" Local LLM setup (Ollama)")
    print("=" * 70)
    st = ollama_setup.detect(BASE)
    if not st["installed"] and not st["reachable"]:
        print("\nOllama is NOT installed on this computer.")
        print("Installing it requires an internet connection and the official installer, which")
        print("needs you to click through its setup window. Official download page:")
        print(f"   {ollama_setup.OLLAMA_DOWNLOAD_URL}")
        if ask("\nOpen the official download page in your browser now? [y/N] ").lower() == "y":
            webbrowser.open(ollama_setup.OLLAMA_DOWNLOAD_URL)
        print("\nAfter installing, start Ollama from the Start menu and run setup_llm.bat again.")
        print("You can also skip the local LLM and use your own cloud API key in the web UI.")
        return 3
    if not st["reachable"]:
        print("\nOllama is installed but its background service is not responding at", BASE)
        exe = st["executable"]
        if exe and ask("Try to start the Ollama service now? [Y/n] ", "y").lower() == "y":
            subprocess.Popen([exe, "serve"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            import time
            for _ in range(15):
                time.sleep(1)
                st = ollama_setup.detect(BASE)
                if st["reachable"]:
                    break
        if not st["reachable"]:
            print("Ollama is still not reachable. Start 'Ollama' from the Start menu and try again.")
            return 4
    print(f"\nOllama {st['version']} is running.")

    hw = ollama_setup.hardware_info()
    rec = ollama_setup.recommend(hw)
    gpus = ", ".join(f"{g['name']} ({g['vram_gb']} GB)" for g in hw["gpus"]) or "no NVIDIA GPU detected"
    print(f"Hardware: {hw['ram_gb']} GB RAM, {gpus}, {hw['disk_free_gb']} GB free disk")
    print(rec["reason"])

    installed = [m["name"] for m in st["models"] if not m["embedding_only"]]
    print("\nInstalled chat models:", ", ".join(installed) or "none")
    print("\nAvailable choices:")
    options = []
    for m in rec["catalog"]:
        tag = "installed" if m["name"] in installed else f"download ~{m['download_gb']} GB"
        fit = "GPU" if m["gpu_accelerated"] else ("CPU only, slow" if m["suitable"] else "NOT recommended for this PC")
        options.append(m["name"])
        star = "*" if m["name"] == rec["recommended"] else " "
        print(f" {len(options):>2}. {star}{m['name']:<16} {tag:<20} needs {m['min_ram_gb']}+ GB RAM  [{fit}]  {m['notes']}")
    for name in installed:
        if name not in options:
            options.append(name)
            print(f" {len(options):>2}.  {name:<16} installed")
    print("  0.  cancel")
    default_idx = str(options.index(rec["recommended"]) + 1) if rec["recommended"] in options else "0"
    choice = ask(f"\nChoose a model [{default_idx}]: ", default_idx)
    if not choice.isdigit() or int(choice) == 0 or int(choice) > len(options):
        print("Cancelled. Nothing was changed.")
        return 0
    model = options[int(choice) - 1]

    if model not in installed:
        size = next((m["download_gb"] for m in rec["catalog"] if m["name"] == model), "?")
        print(f"\n'{model}' will be downloaded by Ollama from the internet (~{size} GB).")
        if hw["disk_free_gb"] is not None and isinstance(size, (int, float)) and hw["disk_free_gb"] < size * 1.5:
            print("WARNING: free disk space looks too low for this model.")
        if ask("Download now? [y/N] ").lower() != "y":
            print("Download cancelled. Nothing was changed.")
            return 0
        exe = st["executable"] or shutil.which("ollama")
        if exe:
            rc = subprocess.call([exe, "pull", model])
        else:
            class Ctx:
                def update(self, **kw):
                    if kw.get("message"):
                        print("  ", kw["message"], end="\r")

                def cancelled(self):
                    return False
            rc = 0 if ollama_setup.pull_model(BASE, model, Ctx()).get("_status") == "COMPLETED" else 1
        if rc != 0:
            print("\nDownload failed. Check your internet connection and disk space, then try again.")
            return 5

    print("\nVerifying the model with a small test...")
    try:
        r = httpx.post(f"{BASE}/api/chat", timeout=300, json={
            "model": model, "stream": False, "format": "json",
            "messages": [{"role": "user", "content": 'Reply with the JSON {"status": "ok"} only.'}]})
        r.raise_for_status()
        print("Model replied:", r.json()["message"]["content"][:120])
    except Exception as e:  # noqa: BLE001
        print(f"Inference test FAILED: {type(e).__name__}: {e}")
        return 6

    init_db()
    if ask(f"\nUse '{model}' as the active classification model? [Y/n] ", "y").lower() == "y":
        with SessionLocal() as db:
            settings_store.patch(db, "llm", {"active_provider": "ollama", "providers": {"ollama": {"base_url": BASE, "model": model}}})
            db.commit()
        print(f"Done. Classification will use ollama/{model}. (Restart is not required.)")
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.exit(main())
