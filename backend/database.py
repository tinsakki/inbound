from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

MASTER_DATABASE_URL = "sqlite:///./master.db"

master_engine = create_engine(
    MASTER_DATABASE_URL, connect_args={"check_same_thread": False}
)
MasterSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=master_engine)

MasterBase = declarative_base()
TenantBase = declarative_base()

def get_master_db():
    db = MasterSessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_tenant_db_engine(campaign_name: str):
    """Dynamically creates or retrieves an engine for a specific tenant DB."""
    # Sanitize campaign name for file system safety
    safe_name = "".join(c for c in campaign_name if c.isalnum() or c in ('_','-')).lower()
    url = f"sqlite:///./metrics_{safe_name}.db"
    
    tenant_engine = create_engine(url, connect_args={"check_same_thread": False})
    
    # Ensure tenant schema tables exist upon engine definition
    TenantBase.metadata.create_all(bind=tenant_engine)
    return tenant_engine

def get_tenant_db(campaign: str):
    """Dynamic wrapper generator yielding the requested Tenant DB connection."""
    engine = get_tenant_db_engine(campaign)
    TenantSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TenantSessionLocal()
    try:
        yield db
    finally:
        db.close()
