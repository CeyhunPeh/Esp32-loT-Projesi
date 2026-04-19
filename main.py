import os
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import Column, Integer, Float, DateTime, create_engine, desc
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
    return {"status": "V2 Aktif", "message": "Yaşam-Devlet Kontrol Merkezi"}

@app.post("/update")
async def update(data: UpdateData, background_tasks: BackgroundTasks):
    global state
    # Sensörleri güncelle
    state["temperature"] = data.temperature
    state["humidity"] = data.humidity
    state["flame"] = data.flame
    state["distance"] = data.distance
    
    # Ortalama için biriktir
    data_buffer.append({'t': data.temperature, 'h': data.humidity, 'f': data.flame, 'd': data.distance})
    
    # 30 veri (1 dakika) olduysa kaydet
    if len(data_buffer) >= 30:
        background_tasks.add_task(save_and_prune)
    
    # ESP32'ye actuator komutlarını dön
    return {
        "buzzer_status": state["buzzer_status"],
        "led_status": state["led_status"],
        "servo_pos": state["servo_pos"]
    }

def save_and_prune():
    db = SessionLocal()
    try:
        avg_t = sum(d['t'] for d in data_buffer) / len(data_buffer)
        avg_h = sum(d['h'] for d in data_buffer) / len(data_buffer)
        avg_f = sum(d['f'] for d in data_buffer) / len(data_buffer)
        avg_d = sum(d['d'] for d in data_buffer) / len(data_buffer)
        
        db.add(SensorLog(temp=avg_t, hum=avg_h, flame=avg_f, dist=avg_d))
        db.commit()
        data_buffer.clear()

        # Pruning (500k kontrolü)
        count = db.query(SensorLog).count()
        if count > 500000:
            oldest_ids = db.query(SensorLog.id).order_by(SensorLog.id).limit(100000).all()
            db.query(SensorLog).filter(SensorLog.id.in_([i[0] for i in oldest_ids])).delete(synchronize_session=False)
            db.commit()
    finally:
        db.close()


@app.get("/status")
def get_status():
    return state

@app.post("/control/{device}/{value}")
def control(device: str, value: int):
    if device in ["buzzer_status", "led_status", "servo_pos"]:
        if device == "servo_pos":
            value = max(0, min(180, value)) # Dereceyi 0-180 arası kısıtla
        state[device] = value
        return {"target": device, "new_value": value}
    return {"error": "Cihaz bulunamadı"}