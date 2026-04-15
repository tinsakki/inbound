from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import Optional
import pandas as pd

from database import get_db, engine
import models

router = APIRouter(
    prefix="/api/metrics",
    tags=["metrics"],
)

@router.get("/aggregate")
def read_aggregated_metrics(
    agent: Optional[str] = Query(None),
    disposition: Optional[str] = Query(None),
    campaign: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    hangup_by: Optional[str] = Query(None),
    did: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    query = db.query(models.CallRecord)

    # Apply extensive filtering dynamically
    if agent: query = query.filter(models.CallRecord.Agent == agent)
    if disposition: query = query.filter(models.CallRecord.Disposition == disposition)
    if campaign: query = query.filter(models.CallRecord.Campaign == campaign)
    if status: query = query.filter(models.CallRecord.Status == status)
    if hangup_by: query = query.filter(models.CallRecord.Hangup_By == hangup_by)
    if did: query = query.filter(models.CallRecord.DID == did)
    
    # Load the filtered dataset to Pandas for quick calculations of derived metrics
    df = pd.read_sql(query.statement, engine)

    # Default metrics
    total_calls_offered = 0
    agent_calls_offered = 0
    calls_answered = 0
    sl_calls = 0
    wh_total_calls = 0
    wh_answered = 0
    overall_abn = 0
    net_abn = 0
    short_abn = 0
    short_abn_pct = 0.0
    gross_abn_pct = 0.0

    if not df.empty:
        total_calls_offered = len(df)
        
        if 'Agent' in df.columns and 'Status' in df.columns:
            agents_valid = df['Agent'].notna() & (df['Agent'].astype(str).str.strip() != '')
            status_valid = df['Status'].astype(str).str.strip().str.lower().isin(['answered', 'unanswered'])
            agent_calls_offered = int((agents_valid & status_valid).sum())
            
        if 'Status' in df.columns:
            calls_answered = int((df['Status'].astype(str).str.strip().str.lower() == 'answered').sum())

        if 'Time_to_Answer' in df.columns and 'Status' in df.columns:
            try:
                sec = pd.to_timedelta(df['Time_to_Answer']).dt.total_seconds()
                status_answered = df['Status'].astype(str).str.strip().str.lower() == 'answered'
                sl_calls = int(((sec <= 30) & status_answered).sum())
            except Exception:
                pass

        if 'Campaign' in df.columns:
            wh_total_calls = int((df['Campaign'].astype(str).str.strip() == 'Inbound_CC_WomenHelpline').sum())
            if 'Status' in df.columns:
                wh_answered = int(((df['Campaign'].astype(str).str.strip() == 'Inbound_CC_WomenHelpline') & (df['Status'].astype(str).str.strip().str.lower() == 'answered')).sum())
                
        if 'Status' in df.columns:
            overall_abn = int((df['Status'].astype(str).str.strip().str.lower() == 'unanswered').sum())

        if 'Agent' in df.columns and 'Status' in df.columns and 'Duration' in df.columns:
            try:
                dur_sec = pd.to_timedelta(df['Duration']).dt.total_seconds()
                v_agents = df['Agent'].notna() & (df['Agent'].astype(str).str.strip() != '')
                v_unanswered = df['Status'].astype(str).str.strip().str.lower() == 'unanswered'
                
                net_abn = int((v_agents & v_unanswered & (dur_sec > 5)).sum())
                short_abn = int((v_agents & v_unanswered & (dur_sec <= 5)).sum())
            except Exception:
                pass
                
        if calls_answered > 0:
            short_abn_pct = (short_abn / calls_answered) * 100
            
        if total_calls_offered > 0:
            gross_abn_pct = ((overall_abn - short_abn) / total_calls_offered) * 100

    # Group by Call Date for chart Data
    grouped = []
    if not df.empty and 'Call_Date' in df.columns:
        date_groups = df.groupby('Call_Date')
        for call_date, g_df in date_groups:
            c_agents_valid = g_df['Agent'].notna() & (g_df['Agent'].astype(str).str.strip() != '')
            c_status_valid = g_df['Status'].astype(str).str.strip().str.lower().isin(['answered', 'unanswered'])
            g_agent_calls = int((c_agents_valid & c_status_valid).sum())
            g_answered = int((g_df['Status'].astype(str).str.strip().str.lower() == 'answered').sum())
            
            grouped.append({
                "call_date": call_date,
                "total_calls": len(g_df),
                "agent_calls": g_agent_calls,
                "answered_calls": g_answered
            })
            
    return {
        "summary": {
            "Total Calls Offered": total_calls_offered,
            "Agent Calls Offered": agent_calls_offered,
            "Calls Answered": calls_answered,
            "SL Calls": sl_calls,
            "WH Total Calls Offered": wh_total_calls,
            "WH Calls Answered": wh_answered,
            "Overall Abn": overall_abn,
            "Net Abandoned": net_abn,
            "Short Call Abn": short_abn,
            "Short Call %": round(short_abn_pct, 2),
            "Gross Abn %": round(gross_abn_pct, 2)
        },
        "chart_data": grouped,
        "raw_count": total_calls_offered
    }

@router.get("/filters")
def get_filter_options(db: Session = Depends(get_db)):
    agents = [r[0] for r in db.query(models.CallRecord.Agent).distinct().all() if r[0]]
    campaigns = [r[0] for r in db.query(models.CallRecord.Campaign).distinct().all() if r[0]]
    statuses = [r[0] for r in db.query(models.CallRecord.Status).distinct().all() if r[0]]
    dispositions = [r[0] for r in db.query(models.CallRecord.Disposition).distinct().all() if r[0]]
    
    return {
        "agents": agents,
        "campaigns": campaigns,
        "statuses": statuses,
        "dispositions": dispositions
    }
