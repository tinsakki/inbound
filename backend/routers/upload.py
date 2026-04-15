from fastapi import APIRouter, File, UploadFile, Depends, HTTPException, Form
from sqlalchemy.orm import Session
import pandas as pd
import io
import traceback

from database import get_db, engine
import models

router = APIRouter(
    prefix="/api/upload",
    tags=["upload"],
)

@router.delete("/clear")
def clear_database(db: Session = Depends(get_db)):
    try:
        db.query(models.CallRecord).delete()
        db.query(models.UploadManifest).delete()
        db.commit()
        return {"message": "Database wiped successfully."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error clearing data: {str(e)}")

@router.post("/")
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    if not file.filename.endswith(('.xls', '.xlsx', '.csv')):
        raise HTTPException(status_code=400, detail="Invalid file format.")

    try:
        contents = await file.read()
        if file.filename.endswith('.csv'):
            try:
                df = pd.read_csv(io.BytesIO(contents), sep='\t')
                if df.shape[1] == 1:
                    df = pd.read_csv(io.BytesIO(contents))
            except Exception:
                df = pd.read_csv(io.BytesIO(contents))
        else:
            df = pd.read_excel(io.BytesIO(contents))
        
        # Format columns to match SQLAlchemy CallRecord model exact field names
        df.columns = df.columns.str.strip().str.replace(' ', '_').str.replace('-', '_')

        # Drop any columns that don't belong to the schema
        valid_columns = [c.name for c in models.CallRecord.__table__.columns]
        df = df[[col for col in df.columns if col in valid_columns]]

        call_date_str = "Unknown Date"
        if 'Call_Date' in df.columns and not df['Call_Date'].empty:
            call_date_str = str(df['Call_Date'].iloc[0]).strip()

        # Save manifest
        manifest = models.UploadManifest(
            filename=file.filename,
            call_date=call_date_str
        )
        db.add(manifest)
        db.commit()

        # Push to Data Warehouse via Pandas
        df.to_sql('call_records', con=engine, if_exists='append', index=False)
        
        return {"message": "Data processed in warehouse successfully", "metrics_saved": len(df)}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error processing data: {str(e)}")
