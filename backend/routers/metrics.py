from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from typing import Optional
import pandas as pd

from database import get_db, engine
import models

router = APIRouter(
    prefix="/api/metrics",
    tags=["metrics"],
)

def parse_time_to_seconds(time_str):
    """Converts HH:MM:SS or MM:SS strings to total seconds."""
    if not time_str or pd.isna(time_str) or str(time_str).strip() == '':
        return 0
    try:
        parts = str(time_str).strip().split(':')
        if len(parts) == 3: # HH:MM:SS
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2: # MM:SS
            return int(parts[0]) * 60 + int(parts[1])
        return 0
    except:
        return 0

@router.get("/aggregate")
def read_aggregated_metrics(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    agent: Optional[str] = Query(None),
    disposition: Optional[str] = Query(None),
    campaign: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    agent_hc: int = Query(10), # Manual Entry placeholder
    gross_tickets: int = Query(0), # Manual Entry placeholder
    view_type: str = Query("daily"),
    db: Session = Depends(get_db)
):
    query = db.query(models.CallRecord)

    # Load dataset to Pandas
    df = pd.read_sql(query.statement, engine)
    if df.empty:
        return {"summary": {}, "chart_data": [], "distributions": {}, "heatmap_data": []}

    # --- ROBUST NORMALIZATION ---
    # Convert all object columns to lowercase and strip whitespace
    text_cols = ['Agent', 'Status', 'Campaign', 'Disposition', 'Hangup_By', 'DID']
    for col in text_cols:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.lower()
            # Special case: handle 'none' or 'nan' as empty strings
            df.loc[df[col].isin(['nan', 'none', 'null']), col] = ''

    # Date Normalization
    df['Call_Date_DT'] = pd.to_datetime(df['Call_Date'], format='%d-%m-%Y', errors='coerce')
    df = df.dropna(subset=['Call_Date_DT'])

    # Apply date range filtering
    if start_date:
        df = df[df['Call_Date_DT'] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df['Call_Date_DT'] <= pd.to_datetime(end_date)]

    # Apply other filters
    if agent: df = df[df['Agent'] == agent.lower().strip()]
    if disposition: df = df[df['Disposition'] == disposition.lower().strip()]
    if campaign: df = df[df['Campaign'] == campaign.lower().strip()]
    if status: df = df[df['Status'] == status.lower().strip()]

    if df.empty:
        return {"summary": {}, "chart_data": [], "distributions": {}, "heatmap_data": []}

    # Time Normalization (convert to seconds)
    df['TTA_Sec'] = df['Time_to_Answer'].apply(parse_time_to_seconds)
    df['Duration_Sec'] = df['Duration'].apply(parse_time_to_seconds)
    df['Hold_Sec'] = df['Hold_Time'].apply(parse_time_to_seconds)

    # --- METRIC CALCULATIONS ---
    
    # 1. Volume Metrics
    total_calls_offered = len(df)
    calls_answered = int((df['Status'] == 'answered').sum())
    agent_calls_offered = int(((df['Agent'] != '') & df['Status'].isin(['answered', 'unanswered'])).sum())
    
    # WH & Travel Update
    wh_offered = int((df['Campaign'] == 'inbound_cc_womenhelpline').sum())
    wh_answered = int(((df['Campaign'] == 'inbound_cc_womenhelpline') & (df['Status'] == 'answered')).sum())
    travel_update_offered = int((df['Campaign'] == 'inbound_cc_travelupdate').sum())
    inbound_wh_offered = total_calls_offered - travel_update_offered

    # 2. Failure Metrics (Abandonment)
    overall_abn = int((df['Status'] == 'unanswered').sum())
    # Net Abn: Agent assigned, Unanswered, Duration > 5s
    net_abn_calls = int(((df['Agent'] != '') & (df['Status'] == 'unanswered') & (df['Duration_Sec'] > 5)).sum())
    short_abn_calls = int(((df['Agent'] != '') & (df['Status'] == 'unanswered') & (df['Duration_Sec'] <= 5)).sum())
    
    # Queue Level Failure (Placeholder logic based on Agent names containing 'queue')
    queue_fail = int(((df['Agent'].str.contains('queue', na=False)) & (df['Status'] == 'unanswered') & (df['Duration_Sec'] > 5)).sum())

    # 3. Quality & Efficiency Metrics
    sl_calls = int(((df['TTA_Sec'] <= 30) & (df['Status'] == 'answered')).sum())
    on_hold_calls = int((df['Hold_Sec'] > 0).sum())
    long_calls_5m = int(((df['Status'] == 'answered') & (df['Duration_Sec'] > 300)).sum())
    
    # 4. Averages
    avg_wait_time = df['TTA_Sec'].mean() if not df.empty else 0
    avg_hold_time = df[df['Hold_Sec'] > 0]['Hold_Sec'].mean() if (df['Hold_Sec'] > 0).any() else 0
    answered_aht = df[df['Status'] == 'answered']['Duration_Sec'].mean() if calls_answered > 0 else 0

    # 5. Repeat Call Logic
    # Group by Caller No and Day to find repeaters
    df['Day_Key'] = df['Call_Date_DT'].dt.date
    repeat_mask = df.groupby(['Caller_No', 'Day_Key'])['Caller_No'].transform('count') > 1
    repeat_calls_count = int(repeat_mask.sum())
    
    # Same Day Same Disposition Repeat
    disp_repeat_mask = df.groupby(['Caller_No', 'Day_Key', 'Disposition'])['Caller_No'].transform('count') > 1
    same_day_disp_repeat = int(disp_repeat_mask.sum())

    # --- RATIO CALCULATIONS ---
    short_call_pct = (short_abn_calls / calls_answered * 100) if calls_answered > 0 else 0
    gross_abn_pct = ((overall_abn - short_abn_calls) / total_calls_offered * 100) if total_calls_offered > 0 else 0
    net_abn_pct = (net_abn_calls / total_calls_offered * 100) if total_calls_offered > 0 else 0
    sl_pct = (sl_calls / agent_calls_offered * 100) if agent_calls_offered > 0 else 0
    al_pct = (calls_answered / agent_calls_offered * 100) if agent_calls_offered > 0 else 0
    long_call_pct = (long_calls_5m / calls_answered * 100) if calls_answered > 0 else 0
    call_per_agent = (calls_answered / agent_hc) if agent_hc > 0 else 0
    
    # Repeat percentages
    same_day_repeat_pct = (repeat_calls_count / total_calls_offered * 100) if total_calls_offered > 0 else 0
    same_day_disp_repeat_pct = (same_day_disp_repeat / calls_answered * 100) if calls_answered > 0 else 0

    # Journey Metrics (using gross_tickets manual entry)
    intr_journey_pct = ((inbound_wh_offered - gross_tickets) / inbound_wh_offered * 100) if inbound_wh_offered > 0 else 0
    travel_update_util_pct = ((travel_update_offered - gross_tickets) / travel_update_offered * 100) if travel_update_offered > 0 else 0

    # --- DISTRIBUTIONS for Charts ---
    def get_top_dist(col, limit=8):
        return df[col].value_counts().head(limit).to_dict()

    distributions = {
        "dispositions": get_top_dist('Disposition'),
        "campaigns": get_top_dist('Campaign'),
        "hangups": get_top_dist('Hangup_By'),
        "agents": get_top_dist('Agent', limit=10)
    }

    # --- HEATMAP DATA (Day vs Hour) ---
    # Need to extract Hour from Start_Time
    df['Hour'] = pd.to_datetime(df['Start_Time'], format='%H:%M:%S', errors='coerce').dt.hour
    df['DayOfWeek'] = df['Call_Date_DT'].dt.dayofweek # 0=Mon, 6=Sun
    
    heatmap_raw = df.groupby(['DayOfWeek', 'Hour']).size().unstack(fill_value=0)
    # Ensure all days (0-6) and hours (0-23) are present
    for i in range(7):
        if i not in heatmap_raw.index: heatmap_raw.loc[i] = 0
    for j in range(24):
        if j not in heatmap_raw.columns: heatmap_raw[j] = 0
    
    heatmap_data = heatmap_raw.sort_index().sort_index(axis=1).values.tolist()

    # --- TIME SERIES CHART DATA ---
    chart_data = []
    freq_map = {"daily": "D", "weekly": "W", "monthly": "ME", "yearly": "YE"}
    freq = freq_map.get(view_type.lower(), "D")
    
    for timestamp, g_df in df.resample(freq, on='Call_Date_DT'):
        if g_df.empty: continue
        label = timestamp.strftime('%Y-%m-%d')
        chart_data.append({
            "label": label,
            "total": len(g_df),
            "answered": int((g_df['Status'] == 'answered').sum()),
            "abn": int((g_df['Status'] == 'unanswered').sum())
        })

    return {
        "summary": {
            "volume": {
                "total_offered": total_calls_offered,
                "agent_offered": agent_calls_offered,
                "answered": calls_answered,
                "wh_offered": wh_offered,
                "wh_answered": wh_answered,
                "travel_update_offered": travel_update_offered,
                "inbound_wh_offered": inbound_wh_offered
            },
            "service": {
                "sl_calls": sl_calls,
                "sl_pct": round(sl_pct, 2),
                "al_pct": round(al_pct, 2),
                "avg_wait": round(avg_wait_time, 1),
                "on_hold": on_hold_calls,
                "avg_hold": round(avg_hold_time, 1)
            },
            "efficiency": {
                "aht": round(answered_aht, 1),
                "long_calls": long_calls_5m,
                "long_call_pct": round(long_call_pct, 2),
                "call_per_agent": round(call_per_agent, 2),
                "same_day_repeat": repeat_calls_count,
                "repeat_pct": round(same_day_repeat_pct, 2)
            },
            "failure": {
                "overall_abn": overall_abn,
                "net_abn": net_abn_calls,
                "net_abn_pct": round(net_abn_pct, 2),
                "short_abn": short_abn_calls,
                "short_pct": round(short_call_pct, 2),
                "gross_abn_pct": round(gross_abn_pct, 2),
                "queue_level": queue_fail
            },
            "journey": {
                "intr_journey_pct": round(intr_journey_pct, 2),
                "travel_util_pct": round(travel_update_util_pct, 2),
                "same_day_disp_repeat": same_day_disp_repeat,
                "disp_repeat_pct": round(same_day_disp_repeat_pct, 2)
            }
        },
        "distributions": distributions,
        "heatmap": heatmap_data,
        "chart_data": chart_data,
        "raw_count": total_calls_offered
    }

@router.get("/filters")
def get_filter_options(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    query = db.query(models.CallRecord)
    
    # If a date range is provided, pre-filter the options to show only relevant ones
    # We'll use Pandas for consistent date logic across the app
    if start_date or end_date:
        df = pd.read_sql(query.statement, engine)
        if not df.empty and 'Call_Date' in df.columns:
            df['Call_Date_DT'] = pd.to_datetime(df['Call_Date'], format='%d-%m-%Y', errors='coerce')
            if start_date:
                df = df[df['Call_Date_DT'] >= pd.to_datetime(start_date)]
            if end_date:
                df = df[df['Call_Date_DT'] <= pd.to_datetime(end_date)]
        
        agents = [a for a in df['Agent'].unique() if a]
        campaigns = [c for c in df['Campaign'].unique() if c]
        statuses = [s for s in df['Status'].unique() if s]
        
        disp_counts = df['Disposition'].value_counts()
        top_10 = disp_counts.head(10).index.tolist()
        all_dispositions = disp_counts.index.tolist()
    else:
        # Fallback to distinct query if no date range
        agents = [r[0] for r in db.query(models.CallRecord.Agent).distinct().all() if r[0]]
        campaigns = [r[0] for r in db.query(models.CallRecord.Campaign).distinct().all() if r[0]]
        statuses = [r[0] for r in db.query(models.CallRecord.Status).distinct().all() if r[0]]
        
        disp_query = db.query(models.CallRecord.Disposition, func.count(models.CallRecord.Disposition))\
                       .group_by(models.CallRecord.Disposition)\
                       .order_by(func.count(models.CallRecord.Disposition).desc())\
                       .all()
        top_10 = [r[0] for r in disp_query[:10] if r[0]]
        all_dispositions = [r[0] for r in disp_query if r[0]]
    
    return {
        "agents": sorted(agents),
        "campaigns": sorted(campaigns),
        "statuses": sorted(statuses),
        "dispositions": sorted(all_dispositions),
        "top_dispositions": top_10
    }
