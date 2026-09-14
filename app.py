"""
Hugging Face Spaces Entrypoint (Gradio SDK).
Wraps the Job Search Automation FastAPI backend and React frontend.
"""
import os
os.environ["GRADIO_SSR_MODE"] = "false"
import subprocess
import sys
from pathlib import Path

# 1. ZeroGPU compatibility guard (prevents shutdown if space hardware is set to ZeroGPU)
try:
    import spaces
    @spaces.GPU(duration=1)
    def dummy_gpu():
        return None
except Exception as e:
    print(f"[!] spaces notice: {e}")

# 2. Install / verify Playwright Chromium on container boot
try:
    print("[*] Checking / installing Playwright Chromium browser...")
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    print("[✓] Playwright Chromium ready.")
except Exception as e:
    print(f"[!] Playwright notice (non-fatal): {e}")

# 3. Import Gradio and FastAPI components
import gradio as gr
from fastapi.staticfiles import StaticFiles
from web.backend.app import app as fastapi_app
from web.backend.scheduler import AutomateScheduler

# Start background scheduler
try:
    scheduler = AutomateScheduler()
    scheduler.start()
except Exception as e:
    print(f"[!] Scheduler notice: {e}")

# 4. Locate compiled React frontend
dist_path = Path(__file__).resolve().parent / "web" / "frontend" / "dist"

# 5. Build Gradio Interface
custom_css = """
body, .gradio-container { margin: 0 !important; padding: 0 !important; max-width: 100% !important; }
footer { display: none !important; }
"""

with gr.Blocks(title="Job Search Automation") as demo:
    gr.HTML(
        """
        <style>
            body, .gradio-container { margin: 0 !important; padding: 0 !important; max-width: 100% !important; width: 100vw !important; height: 100vh !important; }
            footer { display: none !important; }
            #root-iframe-container { position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; overflow: hidden; z-index: 9999; }
        </style>
        <div id="root-iframe-container">
            <iframe src="/app/" style="width: 100%; height: 100%; border: none;"></iframe>
        </div>
        """
    )

from fastapi.responses import FileResponse
from starlette.routing import Mount, Route

# 6. Launch Gradio and attach FastAPI backend & React frontend
if __name__ == "__main__":
    server_app, local_url, _ = demo.launch(
        server_name="0.0.0.0",
        ssr_mode=False,
        prevent_thread_lock=True,
    )

    if dist_path.exists():
        index_html = str(dist_path / "index.html")
        server_app.routes.insert(0, Mount("/app", StaticFiles(directory=str(dist_path), html=True), name="frontend_app"))
        server_app.routes.insert(0, Route("/app", lambda req: FileResponse(index_html)))
        if (dist_path / "assets").exists():
            server_app.routes.insert(0, Mount("/assets", StaticFiles(directory=str(dist_path / "assets")), name="frontend_assets"))

    for route in reversed(fastapi_app.routes):
        if isinstance(route, Mount):
            continue
        path = getattr(route, "path", None)
        if path and not path.startswith("/api"):
            continue
        server_app.routes.insert(0, route)

    print("[✓] Job Search Automation routes mounted successfully.")
    demo.block_thread()
