import os
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import create_all, Column, Integer, Float, DateTime, create_engine, desc, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import pytz


DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class SensorLog(Base):
    __tablename__ = "sensors"
    id = Column(Integer, primary_key=True, index=True)
    temp = Column(Float)
    hum = Column(Float)
    flame = Column(Float)
    dist = Column(Float)
    timestamp = Column(DateTime, default=lambda: datetime.now(pytz.timezone('Europe/Istanbul')))

Base.metadata.create_all(bind=engine)


app = FastAPI()
live_data = {"temperature": 0.0, "humidity": 0.0, "flame": 0, "distance": 0, "buzzer_status": 0}
data_buffer = [] 

class SensorData(BaseModel):
    temperature: float
    humidity: float
    flame: int
    distance: int


def save_and_prune():
    db = SessionLocal()
    try:
        # 1. Ortalama Hesapla
        if not data_buffer: return
        avg_t = sum(d['t'] for d in data_buffer) / len(data_buffer)
        avg_h = sum(d['h'] for d in data_buffer) / len(data_buffer)
        avg_f = sum(d['f'] for d in data_buffer) / len(data_buffer)
        avg_d = sum(d['d'] for d in data_buffer) / len(data_buffer)
        
        
        new_log = SensorLog(temp=avg_t, hum=avg_h, flame=avg_f, dist=avg_d)
        db.add(new_log)
        db.commit()
        data_buffer.clear() 

        
        count = db.query(SensorLog).count()
        if count > 500000:
            
            oldest_ids = db.query(SensorLog.id).order_by(SensorLog.id).limit(100000).all()
            ids_to_del = [i[0] for i in oldest_ids]
            db.query(SensorLog).filter(SensorLog.id.in_(ids_to_del)).delete(synchronize_session=False)
            db.commit()
    finally:
        db.close()


@app.post("/update")
async def update(data: SensorData, background_tasks: BackgroundTasks):
    global live_data
    # Canlı veriyi güncelle (Flutter'ın anlık izlemesi için)
    live_data.update(data.dict())
    
    # Ortalama için listeye ekle
    data_buffer.append({'t': data.temperature, 'h': data.humidity, 'f': data.flame, 'd': data.distance})
    
    # Yaklaşık 1 dakika olduysa (30 tane 2sn'lik veri) arka planda kaydet
    if len(data_buffer) >= 30:
        background_tasks.add_task(save_and_prune)
    
    return {"buzzer_status": live_data["buzzer_status"]}

@app.get("/status")
async def get_status():
    return live_data

@app.get("/history")
async def get_history(limit: int = 100):
    db = SessionLocal()
    logs = db.query(SensorLog).order_by(desc(SensorLog.id)).limit(limit).all()
    db.close()
    return logs

@app.post("/buzzer/{state}")
async def set_buzzer(state: int):
    live_data["buzzer_status"] = state
    return {"new_state": state}