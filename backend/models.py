from sqlalchemy import Column, Integer, String, Float, JSON, DateTime
from sqlalchemy.sql import func
from database import Base

class UploadManifest(Base):
    __tablename__ = "upload_manifests"
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String)
    call_date = Column(String)
    gross_tickets = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class CallRecord(Base):
    __tablename__ = "call_records"
    id = Column(Integer, primary_key=True, index=True)
    
    # Unique identifier to prevent double counting
    row_hash = Column(String, unique=True, index=True)
    
    Call_ID = Column(String, index=True)
    Call_Type = Column(String)
    Campaign = Column(String, index=True)
    Location = Column(String)
    Caller_No = Column(String)
    Caller_E164 = Column(String)
    Skill = Column(String)
    Call_Date = Column(String, index=True)
    Queue_Time = Column(String)
    Start_Time = Column(String)
    Time_to_Answer = Column(String)
    End_Time = Column(String)
    Talk_Time = Column(String)
    Hold_Time = Column(String)
    Duration = Column(String)
    Call_Flow = Column(String)
    Dialed_Number = Column(String)
    Agent = Column(String, index=True)
    Disposition = Column(String, index=True)
    Wrapup_Duration = Column(String)
    Handling_Time = Column(String)
    Status = Column(String, index=True)
    Dial_Status = Column(String)
    Customer_Dial_Status = Column(String)
    Agent_Dial_Status = Column(String)
    Hangup_By = Column(String, index=True)
    Transfer_Details = Column(String)
    UUI = Column(String)
    Comments = Column(String)
    Feedback = Column(String)
    Customer_Ring_Time = Column(String)
    Recording_URL = Column(String)
    Agent_ID = Column(String)
    Ratings = Column(String)
    Rating_Comments = Column(String)
    DynamicDid = Column(String)
    DID = Column(String, index=True)

class ProcessedSync(Base):
    __tablename__ = "processed_syncs"
    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(String, unique=True, index=True) # Google Drive File ID
    filename = Column(String)
    record_count = Column(Integer)
    synced_at = Column(DateTime(timezone=True), server_default=func.now())
