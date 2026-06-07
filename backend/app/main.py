import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import engine, Base, SessionLocal
from app.models.models import ICPConfig, UserFeedback
from app.api.endpoints import router as api_router

# Configure logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize database tables
logger.info("Initializing database tables...")
Base.metadata.create_all(bind=engine)

# Dynamic DB Migration for new columns (e.g. linkedin_url in companies)
from sqlalchemy import text
try:
    if engine.dialect.name == "sqlite":
        with engine.begin() as conn:
            result = conn.execute(text("PRAGMA table_info(companies);")).fetchall()
            columns = [row[1] for row in result]
            if "linkedin_url" not in columns:
                logger.info("Database migration: adding linkedin_url column to companies table...")
                conn.execute(text("ALTER TABLE companies ADD COLUMN linkedin_url TEXT;"))
except Exception as e:
    logger.error(f"Database migration check failed: {str(e)}")

# Seed database with a default active ICP configuration if empty
db = SessionLocal()
try:
    if db.query(ICPConfig).count() == 0:
        logger.info("Seeding default active ICP configuration for EasySDR insurance targets.")
        default_icp = ICPConfig(
            industry="insurance",
            sub_vertical="MGA",
            geography="USA",
            min_employee=50,
            max_employee=2000,
            keywords="claims, underwriting, risk management, automation",
            excluded_keywords="healthcare, life insurance",
            is_active=True
        )
        db.add(default_icp)
        db.commit()
except Exception as e:
    logger.error(f"Error seeding database: {str(e)}")
finally:
    db.close()

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Autonomous sales prospecting and lead enrichment pipeline for EasySDR.",
    version="1.0.0"
)

# CORS configurations
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, lock down to the frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routers
app.include_router(api_router, prefix="/api")

# Serve React Frontend static files if dist exists
import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi import HTTPException

# Relative to backend/app/main.py, frontend/dist is at ../../frontend/dist
frontend_dist = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist"))

if os.path.exists(frontend_dist):
    logger.info(f"Serving frontend static files from: {frontend_dist}")
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")

    @app.get("/{fallback_path:path}")
    async def serve_frontend(fallback_path: str):
        # Prevent intercepting docs or api calls
        if fallback_path.startswith("api") or fallback_path.startswith("docs") or fallback_path.startswith("redoc") or fallback_path.startswith("openapi.json"):
            raise HTTPException(status_code=404)
        return FileResponse(os.path.join(frontend_dist, "index.html"))
else:
    @app.get("/")
    def read_root():
        return {"message": "EasySDR Engine API is running.", "docs_url": "/docs"}

