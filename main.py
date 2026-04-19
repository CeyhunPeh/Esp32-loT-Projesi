import os
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import Column, Integer, Float, DateTime, create_engine, desc
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import pytz

# --- VERİTABANI AYARLARI ---
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class SensorLog(Base):
    __tablename__ = "sensors_v2"
    id = Column(Integer, primary_key=True, index=True)
    temp = Column(Float)
    hum = Column(Float)
    flame = Column(Float)
    dist = Column(Float)
    timestamp = Column(DateTime, default=lambda: datetime.now(pytz.timezone('Europe/Istanbul')))

Base.metadata.create_all(bind=engine)

app = FastAPI()

# --- SİSTEM DURUMU ---
state = {
    "temperature": 0.0,
    "humidity": 0.0,
    "flame": 0,
    "distance": 0,
    "buzzer_status": 0,
    "led_status": 0,
    "servo_pos": 0
}
data_buffer = []

class UpdateData(BaseModel):
    temperature: float
    humidity: float
    flame: int
    distance: int

@app.get("/")
def read_root():
    return {"status": "V2.1 Aktif", "info": "History rotası eklendi."}

# --- VERİ GÖNDERME (ESP32) ---
@app.post("/update")
async def update(data: UpdateData, background_tasks: BackgroundTasks):
    global state
    state.update(data.dict())
    data_buffer.append({'t': data.temperature, 'h': data.humidity, 'f': data.flame, 'd': data.distance})
    
    if len(data_buffer) >= 30:
        background_tasks.add_task(save_to_db)
    
    return {
        "buzzer_status": state["buzzer_status"],
        "led_status": state["led_status"],
        "servo_pos": state["servo_pos"]
    }

def save_to_db():
    db = SessionLocal()
    try:
        avg = {k: sum(d[k] for d in data_buffer)/len(data_buffer) for k in ['t','h','f','d']}
        new_log = SensorLog(temp=avg['t'], hum=avg['h'], flame=avg['f'], dist=avg['d'])
        db.add(new_log)
        db.commit()
        data_buffer.clear()
    finally:
        db.close()

# --- VERİ ÇEKME VE KONTROL (FLUTTER) ---

@app.get("/status")
def get_status():
    return state

# EKSİK OLAN VE 404 HATASI VEREN KISIM BURASIYDI
@app.get("/history")
def get_history(limit: int = 100):
    """Veritabanındaki geçmiş verileri liste halinde döner."""
    db = SessionLocal()
    try:
        # En yeni kayıtları en üstte olacak şekilde getirir
        logs = db.query(SensorLog).order_by(desc(SensorLog.timestamp)).limit(limit).all()
        return logs
    except Exception as e:
        return {"error": str(e)}
    finally:
        db.close()

@app.post("/control/{device}/{value}")
def control(device: str, value: int):
    if device in ["buzzer_status", "led_status", "servo_pos"]:
        if device == "servo_pos":
            value = max(0, min(180, value))
        state[device] = value
        return {"target": device, "new_value": value}
    return {"error": "Cihaz bulunamadı"}