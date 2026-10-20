import json
import re
from curl_cffi import requests
from fastapi import FastAPI, HTTPException

app = FastAPI()


def extraer_de_json(data):
  views, followers = None, None

  def buscar(obj):
    nonlocal views, followers
    if isinstance(obj, dict):
      if "playCount" in obj and views is None:
        try:
          views = int(obj["playCount"])
        except:
          pass
      if "followerCount" in obj and followers is None:
        try:
          followers = int(obj["followerCount"])
        except:
          pass
      for k, v in obj.items():
        if views is not None and followers is not None:
          break
        buscar(v)
    elif isinstance(obj, list):
      for item in obj:
        if views is not None and followers is not None:
          break
        buscar(item)

  buscar(data)
  return views, followers


def obtener_datos_tiktok(url: str):
  try:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    respuesta = requests.get(
        url, impersonate="chrome110", headers=headers, timeout=12
    )
    html = respuesta.text

    # Captcha REAL solo si la página es reducida (< 20KB) y pide verificación explícita
    if len(html) < 20000 and "verify to continue" in html.lower():
      return {
          "url": url,
          "error": "TikTok solicitó verificación Captcha real",
          "status": "error",
      }

    views, followers = None, None

    # 1. Búsqueda en bloques JSON embebidos
    m_json = re.search(
        r'<script\s+id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not m_json:
      m_json = re.search(
          r'<script\s+id="SIGI_STATE"[^>]*>(.*?)</script>', html, re.DOTALL
      )

    if m_json:
      try:
        datos_json = json.loads(m_json.group(1))
        views, followers = extraer_de_json(datos_json)
      except Exception:
        pass

    # 2. Búsqueda secundaria por Regex alternativos
    if views is None:
      m_views = re.search(
          r'"(?:playCount|play_count|views)"\s*:\s*"?(\d+)"?', html
      )
      if m_views:
        views = int(m_views.group(1))

    if followers is None:
      m_followers = re.search(
          r'"(?:followerCount|follower_count)"\s*:\s*"?(\d+)"?', html
      )
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


@app.get("/api/diag")
def diagnostico(url: str):
  try:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    r = requests.get(url, impersonate="chrome110", headers=headers, timeout=12)
    html = r.text
    return {
        "status_code": r.status_code,
        "len_html": len(html),
        "has_universal_data": "__UNIVERSAL_DATA_FOR_REHYDRATION__" in html,
        "has_sigi_state": "SIGI_STATE" in html,
        "has_play_count": "playCount" in html or "play_count" in html,
        "has_follower_count": (
            "followerCount" in html or "follower_count" in html
        ),
        "is_captcha": "verify to continue" in html.lower()
        and len(html) < 20000,
        "snippet": html[:250].replace("\n", " "),
    }
  except Exception as e:
    return {"error": str(e)}


# ---------------------------------------------------------------
# NEW (additive): /api/status -> OK / TAKEN_DOWN / UNKNOWN
# Does not touch /api/tiktok or /api/diag.
# ---------------------------------------------------------------
def _scope_video_detail(html):
  m = re.search(
      r'<script\s+id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
      html,
      re.DOTALL,
  )
  if not m:
    return None, None
  try:
    data = json.loads(m.group(1))
  except Exception:
    return None, None
  scope = data.get("__DEFAULT_SCOPE__", {}) or {}
  return scope.get("webapp.video-detail"), list(scope.keys())


@app.get("/api/status")
def estado(url: str):
  if not url:
    raise HTTPException(status_code=400, detail="Se requiere una URL")
  try:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    r = requests.get(url, impersonate="chrome110", headers=headers, timeout=12)
    html = r.text

    # Infra / anti-bot problems are NEVER treated as "taken down"
    if r.status_code in (403, 429) or r.status_code >= 500:
      return {"estado": "UNKNOWN", "motivo": f"http_{r.status_code}"}
    if len(html) < 20000 and "verify to continue" in html.lower():
      return {"estado": "UNKNOWN", "motivo": "captcha"}

    detail, scope_keys = _scope_video_detail(html)
    if detail is None:
      return {
          "estado": "UNKNOWN",
          "motivo": "sin_video_detail",
          "scope": scope_keys,
      }

    code = detail.get("statusCode")
    item = (detail.get("itemInfo") or {}).get("itemStruct")

    if item:
      return {"estado": "OK", "statusCode": code}
    # Taken down only if TikTok explicitly says so (non-zero code, no item)
    if code not in (None, 0):
      return {
          "estado": "TAKEN_DOWN",
          "statusCode": code,
          "statusMsg": detail.get("statusMsg"),
      }
    return {"estado": "UNKNOWN", "motivo": "sin_item_ni_codigo", "statusCode": code}
  except Exception as e:
    return {"estado": "UNKNOWN", "motivo": f"exc_{type(e).__name__}"}
