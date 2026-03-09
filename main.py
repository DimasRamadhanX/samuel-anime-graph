from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks, HTTPException
import logging

# Internal imports
from core.database import Neo4jProvider
from services.graph_service import GraphService
from services.anilist import fetch_anime_stream

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Neo4j Connection...")
    # Inisialisasi provider dan service
    db = Neo4jProvider()
    service = GraphService(db)
    
    # Simpan ke state agar bisa diakses di endpoint
    app.state.db = db
    app.state.service = service
    service.setup_constraints()
    
    yield
    # Cleanup saat aplikasi dimatikan
    db.close()

app = FastAPI(title="Anime Graph API", lifespan=lifespan)

@app.get("/")
async def health():
    return {"status": "online", "version": "2.0"}

@app.post("/sync")
async def start_sync(background_tasks: BackgroundTasks, pages: int = 300):
    if pages <= 0:
        raise HTTPException(status_code=400, detail="Pages must be > 0")
    
    # Oper service secara eksplisit ke background task
    service = app.state.service
    background_tasks.add_task(run_pipeline_task, pages, service)
    
    return {"message": f"Syncing {pages * 50} anime in background v2"}

async def run_pipeline_task(pages: int, service: GraphService):
    """
    Fungsi ini sekarang menerima 'service' secara langsung 
    untuk menghindari error akses global app.state
    """
    try:
        # 1. TRUNCATE SEKALI SAAT START 
        # (Fungsi ini sekarang menghapus data, menghapus constraint lama, dan MEMBUAT ULANG constraint baru)
        service.truncate_database()
        
        count = 0
        # 2. FETCH & SYNC BATCHING (50 data per batch)
        async for batch in fetch_anime_stream(pages):
            service.sync_to_neo4j(batch)
            count += len(batch)
            logger.info(f"Progress: {count} anime synced to Neo4j.")
            
        logger.info(f"Full Sync Complete! Total: {count} media entities processed.")
    except Exception as e:
        logger.error(f"Pipeline Critical Error: {str(e)}")