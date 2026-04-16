from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
import pandas as pd
import io
import hashlib
import os

from database import get_db
import models

router = APIRouter(
    prefix="/api/sync",
    tags=["sync"],
)

def get_row_hash(row):
    """Generates a unique hash for a call record to prevent duplicates."""
    unique_str = f"{row.get('Call_Date')}-{row.get('Caller_No')}-{row.get('Start_Time')}-{row.get('Agent')}"
    return hashlib.md5(unique_str.encode()).hexdigest()

@router.post("/upload")
async def upload_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Manually ingest a call report (CSV or Excel)."""
    filename = file.filename
    content = await file.read()
    fh = io.BytesIO(content)

    try:
        if filename.endswith('.csv'):
            df = pd.read_csv(fh)
        elif filename.endswith(('.xls', '.xlsx')):
            df = pd.read_excel(fh)
        else:
            raise HTTPException(status_code=400, detail="Unsupported file format. Use CSV or Excel.")

        if df.empty:
            return {"status": "success", "message": "File is empty", "new_records": 0}

        # Normalize column names
        df.columns = df.columns.str.strip().str.replace(' ', '_').str.replace('-', '_')
        valid_columns = [c.name for c in models.CallRecord.__table__.columns if c.name != 'id']
        
        rows_to_insert = []
        new_records_count = 0

        for _, row in df.iterrows():
            h = get_row_hash(row)
            # Check if record already exists to prevent duplicates
            exists = db.query(models.CallRecord).filter(models.CallRecord.row_hash == h).first()
            if not exists:
                record_dict = {col: row[col] for col in df.columns if col in valid_columns}
                record_dict['row_hash'] = h
                rows_to_insert.append(record_dict)

        if rows_to_insert:
            db.execute(models.CallRecord.__table__.insert(), rows_to_insert)
            new_records_count = len(rows_to_insert)
            
            # Record the sync event
            new_sync = models.ProcessedSync(
                file_id=f"manual_{hashlib.md5(content).hexdigest()[:10]}",
                filename=filename, 
                record_count=new_records_count
            )
            db.add(new_sync)
            db.commit()

        return {
            "status": "success",
            "filename": filename,
            "new_records_integrated": new_records_count,
            "total_rows_read": len(df)
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status")
def get_sync_status(db: Session = Depends(get_db)):
    """Simple status for the manual pipeline."""
    last_sync = db.query(models.ProcessedSync).order_by(models.ProcessedSync.synced_at.desc()).first()
    total_records = db.query(models.CallRecord).count()
    return {
        "last_sync": last_sync.synced_at if last_sync else None,
        "total_records": total_records,
        "mode": "Manual Ingestion"
    }

@router.post("/wipe")
def wipe_database(db: Session = Depends(get_db)):
    """Deletes all call records and sync history."""
    try:
        db.query(models.CallRecord).delete()
        db.query(models.ProcessedSync).delete()
        db.commit()
        return {"message": "Database wiped successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
