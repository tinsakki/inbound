from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session
import pandas as pd
import io
import hashlib
import os
import requests
import json
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv

from database import get_master_db, get_tenant_db_engine, MasterSessionLocal
import models

# Load configurations from .env
load_dotenv()

OZONETEL_API_KEY = os.getenv("OZONETEL_API_KEY")
OZONETEL_USER_NAME = os.getenv("OZONETEL_USER_NAME")
OZONETEL_CAMPAIGNS = [c.strip() for c in os.getenv("OZONETEL_CAMPAIGNS", "").split(",") if c.strip()]
OZONETEL_AUTH_URL = os.getenv("OZONETEL_AUTH_URL")
OZONETEL_CDR_URL = os.getenv("OZONETEL_CDR_URL")

router = APIRouter(
    prefix="/api/sync",
    tags=["sync"],
)

# ---------------------------------------------------------------------------
# Global State
# ---------------------------------------------------------------------------
is_bootstrapping = False
_active_token = None   # In-memory token cache; refreshed on 401

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_categorical(val):
    """Strips whitespace and converts to lowercase for categorical consistency."""
    if val is None:
        return ""
    str_val = str(val).strip().lower()
    if str_val in ['nan', 'none', 'null']:
        return ""
    return str_val

def get_row_hash(row):
    """Generates a unique hash using UCID or composite keys with normalized data."""
    ucid = row.get('UCID') or row.get('CallID')
    if ucid:
        return hashlib.md5(str(ucid).encode()).hexdigest()
    
    date_val = row.get('CallDate')
    if date_val and '-' in date_val and len(date_val.split('-')[0]) == 4:
        y, m, d = date_val.split('-')
        date_val = f"{d}-{m}-{y}"

    unique_str = (
        f"{normalize_categorical(date_val)}-"
        f"{normalize_categorical(row.get('CallerID'))}-"
        f"{normalize_categorical(row.get('StartTime'))}-"
        f"{normalize_categorical(row.get('AgentID'))}"
    )
    return hashlib.md5(unique_str.encode()).hexdigest()

# ---------------------------------------------------------------------------
# Token Management — auto-refresh
# ---------------------------------------------------------------------------

def fetch_ozonetel_token():
    """Generates a fresh bearer token from the OzoneTel Auth API."""
    global _active_token
    if not OZONETEL_API_KEY or not OZONETEL_USER_NAME:
        raise Exception("OzoneTel credentials missing in .env")
    
    headers = {
        "Content-Type": "application/json",
        "apiKey": OZONETEL_API_KEY
    }
    payload = {"userName": OZONETEL_USER_NAME}
    
    try:
        response = requests.post(OZONETEL_AUTH_URL, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            data = response.json()
            token = data.get("token")
            _active_token = token
            print(f"🔑 Fresh token acquired.")
            return token
        else:
            raise Exception(f"Auth failed [{response.status_code}]: {response.text}")
    except Exception as e:
        raise Exception(f"Token Generation Error: {str(e)}")

def get_or_refresh_token():
    """Returns the cached token, fetching a new one if none exists."""
    global _active_token
    if not _active_token:
        return fetch_ozonetel_token()
    return _active_token

# ---------------------------------------------------------------------------
# CDR Fetching — detects 401 and auto-refreshes token, with retry
# ---------------------------------------------------------------------------

class RateLimitError(Exception):
    """Raised when OzoneTel returns a rate-limit response (HTTP 200 with message body)."""
    def __init__(self, new_token=None):
        self.new_token = new_token
        super().__init__("Rate limit hit. Will retry after sleep.")


def _is_rate_limited(data: dict) -> bool:
    """Returns True if the response body signals a rate limit."""
    if not isinstance(data, dict):
        return False
    msg = str(data.get("message", "")).lower()
    return "rate limit" in msg or "rate_limit" in msg or "ratelimit" in msg


def _try_fetch_cdrs(token, payload):
    """
    Fetches CDR data using GET with JSON body — the only method OzoneTel accepts.
    - GET with URL params → returns 'Invalid Json Pass Valid Json'
    - POST → returns 405 Method Not Allowed
    - GET with JSON body → works correctly
    Returns (data, is_401).
    Raises RateLimitError if rate-limit detected in response body.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "apiKey": OZONETEL_API_KEY,
        "Content-Type": "application/json"
    }

    r = requests.get(OZONETEL_CDR_URL, headers=headers, json=payload, timeout=60)

    # Log non-200 for diagnostics
    if r.status_code == 401:
        try:
            print(f"    🔐 401 body: {r.json()}")
        except Exception:
            print(f"    🔐 401 raw: {r.text[:300]}")
        return None, True

    if r.status_code != 200:
        raise Exception(f"CDR fetch failed [HTTP {r.status_code}]: {r.text[:300]}")

    try:
        data = r.json()
    except Exception:
        raise Exception(f"CDR returned non-JSON body: {r.text[:300]}")

    # Detect rate limit signalled via HTTP 200 + message body
    if _is_rate_limited(data):
        new_token = data.get("token") or None
        print(f"    ⚡ Rate limit body detected. New token provided: {'yes' if new_token else 'no'}")
        raise RateLimitError(new_token=new_token)

    # Detect "Invalid Json" — means we're sending the request wrong
    if isinstance(data, dict) and "invalid" in str(data.get("message", "")).lower():
        raise Exception(f"OzoneTel rejected request format: {data}")

    return data, False


def fetch_ozonetel_cdrs(token, from_date, to_date, campaign_name):
    """
    Fetches CDR data.
    - Auto-refreshes token on HTTP 401.
    - Raises RateLimitError (with new_token) when body signals rate limit.
    Returns (cdr_data, current_token).
    """
    global _active_token
    payload = {
        "fromDate": from_date,
        "toDate": to_date,
        "userName": OZONETEL_USER_NAME,
        "campaignName": campaign_name
    }

    try:
        data, is_401 = _try_fetch_cdrs(token, payload)
    except RateLimitError:
        raise   # bubble up so ingest_days can sleep + retry with new token

    if is_401:
        print(f"⚠️  Token expired (HTTP 401). Re-authenticating...")
        new_token = fetch_ozonetel_token()
        import time; time.sleep(3)  # propagation delay
        data, is_401_again = _try_fetch_cdrs(new_token, payload)
        if is_401_again:
            raise Exception("Still getting 401 after token refresh. Check credentials.")
        return data, new_token

    return data, token

# ---------------------------------------------------------------------------
# Model Mapping with strict normalization
# ---------------------------------------------------------------------------

def map_ozonetel_to_model(oz_row):
    """Maps PascalCase OzoneTel keys to snake_case models with strict normalization."""
    raw_date = oz_row.get("CallDate")
    normalized_date = raw_date
    if raw_date and '-' in raw_date:
        parts = raw_date.split('-')
        if len(parts[0]) == 4:
            normalized_date = f"{parts[2]}-{parts[1]}-{parts[0]}"

    mapping = {
        "CallID": "Call_ID",
        "Type": "Call_Type",
        "CampaignName": "Campaign",
        "Location": "Location",
        "CallerID": "Caller_No",
        "E164": "Caller_E164",
        "Skill": "Skill",
        "QueueTime": "Queue_Time",
        "StartTime": "Start_Time",
        "TimeToAnswer": "Time_to_Answer",
        "EndTime": "End_Time",
        "TalkTime": "Talk_Time",
        "HoldDuration": "Hold_Time",
        "Duration": "Duration",
        "CallFlow": "Call_Flow",
        "DialedNumber": "Dialed_Number",
        "AgentName": "Agent",
        "Disposition": "Disposition",
        "WrapupDuration": "Wrapup_Duration",
        "HandlingTime": "Handling_Time",
        "Status": "Status",
        "DialStatus": "Dial_Status",
        "CustomerDialStatus": "Customer_Dial_Status",
        "AgentDialStatus": "Agent_Dial_Status",
        "HangupBy": "Hangup_By",
        "UUI": "UUI",
        "Comments": "Comments",
        "CustomerRingTime": "Customer_Ring_Time",
        "CallAudio": "Recording_URL",
        "AgentID": "Agent_ID",
        "Rating": "Ratings",
        "RatingComments": "Rating_Comments",
        "DynamicDID": "DynamicDid",
        "DID": "DID"
    }
    
    categorical_cols = [
        "Call_Type", "Campaign", "Location", "Skill", "Agent", 
        "Disposition", "Status", "Dial_Status", "Customer_Dial_Status", 
        "Agent_Dial_Status", "Hangup_By", "DID"
    ]

    record_dict = {}
    for oz_key, model_key in mapping.items():
        val = oz_row.get(oz_key)
        if model_key in categorical_cols:
            record_dict[model_key] = normalize_categorical(val)
        else:
            record_dict[model_key] = str(val).strip() if val is not None else ""
    
    record_dict["Call_Date"] = normalized_date
    return record_dict

# ---------------------------------------------------------------------------
# Smart Missing-Dates Detector
# ---------------------------------------------------------------------------

def get_missing_dates(db: Session, base_date: datetime, days: int = 15):
    """
    Returns a list of dates (YYYY-MM-DD) in the past `days` days that
    have NO records for at least one campaign. This allows the bootstrap
    to resume from where it left off rather than always starting fresh.
    """
    all_dates = [
        (base_date - timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(1, days + 1)
    ]

    # Get the set of dates we already have at least one record for
    existing_dates_raw = db.query(models.CallRecord.Call_Date).distinct().all()
    # DB stores as DD-MM-YYYY, convert back for comparison
    existing_dates = set()
    for (d,) in existing_dates_raw:
        if d and len(d) == 10:
            try:
                parts = d.split('-')
                existing_dates.add(f"{parts[2]}-{parts[1]}-{parts[0]}")
            except Exception:
                pass

    missing = [d for d in all_dates if d not in existing_dates]
    print(f"📊 Coverage check: {len(all_dates) - len(missing)}/{len(all_dates)} days covered. "
          f"Missing: {len(missing)} days.")
    return missing

# ---------------------------------------------------------------------------
# Core data ingestion helper (shared by bootstrap and manual run)
# ---------------------------------------------------------------------------

async def ingest_days(db: Session, dates_to_fetch: list, token: str, group, label: str = "Sync"):
    """
    Iterates over dates × sub-campaigns for a SINGLE parent group, fetches data, 
    deduplicates and inserts into the provided Tenant Session (`db`).
    """
    total_inserted = 0
    current_token = token

    for target_date in dates_to_fetch:
        print(f"📅 [{label}] Processing {target_date} ---")
        day_rows = []
        seen_hashes_for_day = set()

        target_campaigns = [sub.ozonetel_name for sub in group.sub_campaigns]
        
        if not target_campaigns:
            print(f"  ⚠️ No sub-campaigns configured for {group.name}.")
            break

        for campaign_name in target_campaigns:
            print(f"  🔍 Fetching {campaign_name} for {target_date}...")
            attempt = 0
            max_attempts = 3

            while attempt < max_attempts:
                try:
                    cdr_data, current_token = fetch_ozonetel_cdrs(
                        current_token,
                        f"{target_date} 00:00:00",
                        f"{target_date} 23:59:59",
                        campaign_name
                    )
                    details = cdr_data.get("details", []) if cdr_data else []
                    
                    campaign_count = 0
                    for row in details:
                        h = get_row_hash(row)
                        if h in seen_hashes_for_day:
                            continue
                        exists = db.query(models.CallRecord).filter(
                            models.CallRecord.row_hash == h
                        ).first()
                        if not exists:
                            record_dict = map_ozonetel_to_model(row)
                            record_dict['row_hash'] = h
                            day_rows.append(record_dict)
                            seen_hashes_for_day.add(h)
                            campaign_count += 1

                    print(f"    ✅ {campaign_name}: {campaign_count} new records "
                          f"(API returned: {len(details)})")
                    await asyncio.sleep(30)  # Rate limit — 2 req/min
                    break  # success

                except RateLimitError as rle:
                    # OzoneTel sends a fresh token in the rate-limit response body
                    if rle.new_token:
                        current_token = rle.new_token
                        _active_token = rle.new_token
                        print(f"    🔄 Rate limit hit for {campaign_name}. "
                              f"Got new token from response. Sleeping 60s then retrying...")
                    else:
                        print(f"    🔄 Rate limit hit for {campaign_name}. "
                              f"Sleeping 60s then retrying...")
                    await asyncio.sleep(60)
                    attempt += 1

                except Exception as e:
                    attempt += 1
                    err_msg = str(e)
                    print(f"    ❌ [{attempt}/{max_attempts}] Error for {campaign_name} "
                          f"on {target_date}: {err_msg}")
                    
                    # Stop immediately if OzoneTel says the campaign name is invalid
                    if "invalid campaignname" in err_msg.lower():
                        print(f"    🚫 Invalid campaign name detected: {campaign_name}. Skipping further attempts.")
                        break

                    if attempt < max_attempts:
                        sleep_time = 30 * attempt
                        print(f"    ⏳ Retrying in {sleep_time}s...")
                        await asyncio.sleep(sleep_time)
                    else:
                        print(f"    🚫 Giving up on {campaign_name}/{target_date} after "
                              f"{max_attempts} attempts.")
                        await asyncio.sleep(30)

        # Bulk insert for entire day across all campaigns
        if day_rows:
            db.execute(models.CallRecord.__table__.insert(), day_rows)
            db.commit()
            total_inserted += len(day_rows)
            print(f"💾 Day Summary [{target_date}]: +{len(day_rows)} records committed. "
                  f"Running total: {total_inserted}")
        else:
            print(f"ℹ️  Day Summary [{target_date}]: No new records.")

    return total_inserted, current_token

# ---------------------------------------------------------------------------
# Bootstrap — Smart Resume
# ---------------------------------------------------------------------------

async def bootstrap_historical_data():
    """
    Multi-tenant bootstraps all active groups:
    - Finds which of the last 15 days have NO records in each respective tenant DB.
    """
    global is_bootstrapping
    from sqlalchemy.orm import joinedload
    master_db = MasterSessionLocal()
    try:
        groups = master_db.query(models.CampaignGroup)\
                         .options(joinedload(models.CampaignGroup.sub_campaigns))\
                         .filter(models.CampaignGroup.status == "Live").all()
    finally:
        master_db.close()
        
    try:
        is_bootstrapping = True
        token = get_or_refresh_token()
        
        for group in groups:
            engine = get_tenant_db_engine(group.name)
            from sqlalchemy.orm import sessionmaker
            TenantSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
            tenant_db = TenantSessionLocal()
            
            try:
                base_date = datetime.now()
                missing_dates = get_missing_dates(tenant_db, base_date, days=15)

                if not missing_dates:
                    print(f"✅ {group.name}: All 15 days covered.")
                    continue

                print(f"🚀 {group.name} Bootstrap — filling {len(missing_dates)} days.")
                total, token = await ingest_days(tenant_db, missing_dates, token, group, label=f"Bootstrap-{group.name}")

                if total > 0:
                    new_sync = models.ProcessedSync(
                        file_id=f"bootstrap_{datetime.now().strftime('%Y%m%d%H%M')}_{group.name}",
                        filename=f"OzoneTel Bootstrap: {group.name}",
                        record_count=total
                    )
                    tenant_db.add(new_sync)
                    tenant_db.commit()
            except Exception as inner_e:
                print(f"💥 Failed to sync group {group.name}: {str(inner_e)}")
            finally:
                tenant_db.close()

    except Exception as e:
        print(f"💥 Bootstrap failed with unrecoverable error: {str(e)}")
    finally:
        is_bootstrapping = False

# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@router.post("/run")
async def run_sync_api(campaign: str, db_master: Session = Depends(get_master_db)):
    """Manual trigger: smart resume for 15 days for a specific tenant campaign."""
    from database import get_tenant_db_engine
    from sqlalchemy.orm import sessionmaker
    
    engine = get_tenant_db_engine(campaign)
    TenantSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db_tenant = TenantSessionLocal()
    
    try:
        base_date = datetime.now()
        missing_dates = get_missing_dates(db_tenant, base_date, days=15)

        if not missing_dates:
            return {"status": "up_to_date", "message": f"All 15 days already covered for {campaign}.", "total_integrated": 0}

        group = db_master.query(models.CampaignGroup).filter(models.CampaignGroup.name == campaign).first()
        if not group:
             raise HTTPException(status_code=404, detail="Campaign group not found in master DB")

        token = get_or_refresh_token()
        total, _ = await ingest_days(db_tenant, missing_dates, token, group, label=f"Manual-Sync-{campaign}")

        if total > 0:
            new_sync = models.ProcessedSync(
                file_id=f"oz_manual_{datetime.now().strftime('%Y%m%d%H%M')}_{campaign}",
                filename=f"OzoneTel Manual Sync: {campaign}",
                record_count=total
            )
            db_tenant.add(new_sync)
            db_tenant.commit()

        return {
            "status": "success",
            "total_integrated": total,
            "dates_synced": missing_dates
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
def get_sync_status(campaign: str = None, db_master: Session = Depends(get_master_db)):
    """Status for a specific campaign tenant DB. If no campaign provided, returns global state."""
    if not campaign:
        return {"status": "operational", "is_bootstrapping": is_bootstrapping, "config": {"userName": OZONETEL_USER_NAME}}
    
    from database import get_tenant_db_engine
    from sqlalchemy.orm import sessionmaker
    
    try:
        engine = get_tenant_db_engine(campaign)
    except Exception:
        return {"status": "error", "message": f"Tenant {campaign} not found", "is_bootstrapping": is_bootstrapping}

    TenantSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db_tenant = TenantSessionLocal()
    
    try:
        last_sync = db_tenant.query(models.ProcessedSync).order_by(
            models.ProcessedSync.synced_at.desc()
        ).first()
        total_records = db_tenant.query(models.CallRecord).count()

        # Coverage summary
        base_date = datetime.now()
        missing_dates = get_missing_dates(db_tenant, base_date, days=15)

        # Config from Master
        group = db_master.query(models.CampaignGroup).filter(models.CampaignGroup.name == campaign).first()
        mapped_campaigns = [sub.ozonetel_name for sub in group.sub_campaigns] if group else []

        return {
            "last_sync": last_sync.synced_at if last_sync else None,
            "total_records": total_records,
            "is_bootstrapping": is_bootstrapping,
            "coverage": {
                "days_covered": 15 - len(missing_dates),
                "days_missing": len(missing_dates),
                "missing_dates": missing_dates
            },
            "config": {
                "userName": OZONETEL_USER_NAME,
                "campaigns": mapped_campaigns
            }
        }
    finally:
        db_tenant.close()

class CampaignAddRequest(BaseModel):
    name: str  
    description: str = ""
    campaigns: str

@router.get("/campaigns")
def get_campaign_groups(db: Session = Depends(get_master_db)):
    """Yields all configured Campaign Groups from the Master Database with sub-campaigns."""
    from sqlalchemy.orm import joinedload
    groups = db.query(models.CampaignGroup).options(joinedload(models.CampaignGroup.sub_campaigns)).all()
    # Pydantic/FastAPI will handle serialization of nested relationships if configured,
    # but we can return raw dicts for safety if needed.
    return {"groups": groups}

@router.post("/campaigns")
def add_campaign_group(payload: CampaignAddRequest, db: Session = Depends(get_master_db)):
    """Dynamically creates or updates a UI Campaign Group and its OzoneTel sub-campaign maps."""
    new_campaigns = [c.strip() for c in payload.campaigns.split(",") if c.strip()]
    if not new_campaigns:
        raise HTTPException(status_code=400, detail="No campaign names provided")
        
    group_name = payload.name.strip()
    if not group_name:
        raise HTTPException(status_code=400, detail="Parent Group Name is required")
        
    group = db.query(models.CampaignGroup).filter(models.CampaignGroup.name == group_name).first()
    if group:
        group.description = payload.description or group.description
        # Clear existing sub-campaigns
        db.query(models.SubCampaign).filter(models.SubCampaign.parent_id == group.id).delete()
    else:
        group = models.CampaignGroup(
            name=group_name,
            description=payload.description or "",
            icon="folder",
            status="Live"
        )
        db.add(group)
        db.flush()

    # Add new sub-campaigns
    for c_name in new_campaigns:
        sub = models.SubCampaign(parent_id=group.id, ozonetel_name=c_name)
        db.add(sub)
    
    db.commit()
            
    return {
        "status": "success", 
        "added": len(new_campaigns), 
        "group": group_name
    }

@router.post("/wipe")
def wipe_database(campaign: str):
    """Deletes all call records and sync history for a specific tenant."""
    from database import get_tenant_db_engine
    from sqlalchemy.orm import sessionmaker
    
    engine = get_tenant_db_engine(campaign)
    TenantSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TenantSessionLocal()
    
    try:
        db.query(models.CallRecord).delete()
        db.query(models.ProcessedSync).delete()
        db.commit()
        return {"status": "ok", "message": f"Database for {campaign} wiped successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


async def background_monitoring_task():
    """Standby — bootstrap handles initial fill; manual trigger for re-runs."""
    print("🚀 OzoneTel Auto-Monitor Standby")
    while True:
        await asyncio.sleep(86400)
