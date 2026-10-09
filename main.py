from fastapi import FastAPI, HTTPException
from curl_cffi import requests
import re

app = FastAPI()

def obtener_datos_tiktok(url: str):
    try:
        # Simulamos ser un navegador Chrome real para saltar el bloqueo
        respuesta = requests.get(url, impersonate="chrome110", timeout=10)
        html = respuesta.text
        
        # Buscamos las views (playCount)
        views = None
        m_views = re.search(r'"playCount"\s*:\s*"?(\d+)"?', html)
        if m_views:
            views = int(m_views.group(1))
            
        # Buscamos los followers (followerCount)
        followers = None
        m_followers = re.search(r'"followerCount"\s*:\s*"?(\d+)"?', html)
        if m_followers:
            followers = int(m_followers.group(1))
            
        return {"url": url, "views": views, "followers": followers, "status": "ok"}
    except Exception as e:
        return {"url": url, "error": str(e), "status": "error"}

@app.get("/")
def inicio():
    return {"mensaje": "API de TikTok funcionando"}

@app.get("/api/tiktok")
def extraer(url: str):
    if not url:
        raise HTTPException(status_code=400, detail="Se requiere una URL")
    return obtener_datos_tiktok(url)
