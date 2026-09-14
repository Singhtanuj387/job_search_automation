"""
FastAPI Backend Application Entrypoint for Job Search Automation.
"""
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from web.backend.routes import apply, automate, chat, materials, opportunities, profile, settings, tracker
from web.backend.scheduler import AutomateScheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start scheduler
    scheduler = AutomateScheduler()
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(
    title="Job Search Engine & Tailoring Web App",
    description="Phase 2 Web Application wrapping Phase 1 Job Acquisition Engine.",
    version="2.0.0",
    lifespan=lifespan,
)

# Enable CORS for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(profile.router)
app.include_router(settings.router)
app.include_router(chat.router)
app.include_router(tracker.router)
app.include_router(automate.router)
app.include_router(materials.router)
app.include_router(opportunities.router)
app.include_router(apply.router)

@app.get("/api/health")
def health():
    return {"status": "ok", "app": "Job Search Automation Web App", "version": "2.0.0"}

# Mount compiled React frontend if dist exists
dist_path = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if dist_path.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=str(dist_path), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web.backend.app:app", host="127.0.0.1", port=8000, reload=True)
