from fastapi import FastAPI
from pydantic import BaseModel
from typing import Dict

app = FastAPI()

# Verilerin ve cihaz durumunun tutulduğu değişken
# Render uyuduğunda bu veriler sıfırlanır (bizim için sorun değil)
db = {
    "temperature": 0.0,
    "humidity": 0.0,
    "flame": 0,
    "distance": 0,
    "buzzer_status": 0  # 0: Kapalı, 1: Açık
}

class SensorUpdate(BaseModel):
    temperature: float
    humidity: float
    flame: int
    distance: int

@app.get("/")
def read_root():
    return {"message": "ESP32-Flutter Bridge Sistemi Aktif!"}

# ESP32'nin veri göndereceği endpoint
@app.post("/update")
async def update_sensor_data(data: SensorUpdate):
    global db
    db["temperature"] = data.temperature
    db["humidity"] = data.humidity
    db["flame"] = data.flame
    db["distance"] = data.distance
    
    # ESP32'ye yanıt olarak buzzer'ın durumunu dönüyoruz
    return {"buzzer_status": db["buzzer_status"]}

# Flutter'ın anlık verileri göreceği endpoint
@app.get("/status")
async def get_status():
    return db

# Flutter'ın buzzer'ı kontrol edeceği endpoint (0 veya 1)
@app.post("/buzzer/{state}")
async def set_buzzer(state: int):
    global db
    if state in [0, 1]:
        db["buzzer_status"] = state
        return {"status": "success", "new_state": state}
    return {"status": "error", "message": "Geçersiz değer (0 veya 1 olmalı)"}