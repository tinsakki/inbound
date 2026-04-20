from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

import models
from database import master_engine, MasterSessionLocal
from routers import sync, metrics
import os

# Create the Global Master database tables (CampaignGroups)
models.MasterBase.metadata.create_all(bind=master_engine)
app = FastAPI(title="Dashboard Backend API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(sync.router)
app.include_router(metrics.router)


@app.on_event("startup")
async def startup_event():
    import asyncio
    
    # ---------------------------------------------------------
    # Legacy Migration: Seed fresh Master DB with .env configurations
    # ---------------------------------------------------------
    db = MasterSessionLocal()
    try:
        from routers.sync import OZONETEL_CAMPAIGNS
        
        # Ensure 'Inbound' group exists and has its sub-campaigns
        inbound_group = db.query(models.CampaignGroup).filter(models.CampaignGroup.name == "Inbound").first()
        
        if not inbound_group:
            inbound_group = models.CampaignGroup(
                name="Inbound",
                description="Legacy configuration mapped from .env",
                icon="phone-incoming",
                status="Live"
            )
            db.add(inbound_group)
            db.flush()
            print("📦 Created new 'Inbound' campaign group.")

        # Sync relational sub-campaigns
        if inbound_group and OZONETEL_CAMPAIGNS:
            current_campaigns = [c.strip() for c in OZONETEL_CAMPAIGNS if c.strip()]
            
            # 1. Add missing
            existing_subs = {s.ozonetel_name for s in inbound_group.sub_campaigns}
            added_count = 0
            for c_name in current_campaigns:
                if c_name not in existing_subs:
                    db.add(models.SubCampaign(parent_id=inbound_group.id, ozonetel_name=c_name))
                    added_count += 1
            
            # 2. Remove stale
            removed_count = 0
            for sub in inbound_group.sub_campaigns:
                if sub.ozonetel_name not in current_campaigns:
                    db.delete(sub)
                    removed_count += 1
            
            if added_count > 0 or removed_count > 0:
                db.commit()
                print(f"✅ Synced 'Inbound' campaigns: Added {added_count}, Removed {removed_count}")
            else:
                print(f"✨ 'Inbound' group is already in sync with {len(inbound_group.sub_campaigns)} campaigns.")

    except Exception as e:
        print(f"⚠️ Failed to migrate campaigns: {e}")
    finally:
        db.close()

    asyncio.create_task(sync.bootstrap_historical_data())

# Explicit UI Routes
@app.get("/campaign")
async def serve_campaign():
    return FileResponse("static/campaign.html")

@app.get("/inbound")
async def serve_inbound():
    return FileResponse("static/inbound.html")


# Mount static files for simple HTML/JS frontend
os.makedirs("static", exist_ok=True)
app.mount("/", StaticFiles(directory="static", html=True), name="static")
