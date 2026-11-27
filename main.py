"""
main.py - Servidor Web Oficial JIN.COM.MX
Despliegue optimizado para Render con Uvicorn / FastAPI / Jinja2
Sincronización en vivo con Mercado Libre México (OAuth2 + Paginación + Caché TTL + Geolocalización)
"""

import os
import io
import csv
import html
import json
import time
import hashlib
import asyncio
import logging
import smtplib
import urllib.request
from email.message import EmailMessage
from contextlib import asynccontextmanager
from urllib.parse import quote
from typing import Optional, List, Dict, Any, Tuple, Set
import requests
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

try:
    from fastapi.templating import Jinja2Templates
except ImportError:
    Jinja2Templates = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("jin.com.mx")

# Directorios del proyecto
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
IMAGES_DIR = os.path.join(BASE_DIR, "images")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

KEEP_ALIVE_URL = "https://www.jin.com.mx/health"
KEEP_ALIVE_INTERVAL_SECONDS = 600  # 10 minutos


def _perform_keep_alive_ping() -> None:
    """Realiza un GET ligero hacia https://www.jin.com.mx/health de forma silenciosa."""
    try:
        req = urllib.request.Request(
            KEEP_ALIVE_URL,
            headers={"User-Agent": "jin.com.mx-keepalive/1.0"}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            resp.read()
    except Exception:
        pass


async def _keep_alive_ping_loop() -> None:
    """Bucle asíncrono en segundo plano que ejecuta auto-ping cada 10 minutos."""
    while True:
        await asyncio.sleep(KEEP_ALIVE_INTERVAL_SECONDS)
        try:
            await asyncio.to_thread(_perform_keep_alive_ping)
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicia la tarea de Keep-Alive al arrancar FastAPI para evitar suspensión en Render."""
    keep_alive_task = asyncio.create_task(_keep_alive_ping_loop())
    try:
        yield
    finally:
        keep_alive_task.cancel()


app = FastAPI(
    title="JIN.COM.MX Catálogo 3D",
    description="Aplicación web www.jin.com.mx con estética Y2K 3D Glossy, Menú Orbital y Catálogo Interactivo",
    version="2.2.0",
    lifespan=lifespan
)


@app.middleware("http")
async def redirect_non_www_to_www(request: Request, call_next):
    """
    Redirige peticiones entrantes desde jin.com.mx (sin www) hacia https://www.jin.com.mx
    con código HTTP 301, respetando localhost y 127.0.0.1 en entorno local.
    """
    host_header = request.headers.get("host", "")
    hostname = host_header.split(":")[0].lower().strip()
    if hostname == "jin.com.mx":
        path = request.url.path or "/"
        query = f"?{request.url.query}" if request.url.query else ""
        return RedirectResponse(url=f"https://www.jin.com.mx{path}{query}", status_code=301)
    return await call_next(request)

# Montaje de archivos estáticos e imágenes
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
if os.path.exists(IMAGES_DIR):
    app.mount("/images", StaticFiles(directory=IMAGES_DIR), name="images")

# Configuración opcional del motor de plantillas Jinja2
templates = Jinja2Templates(directory=TEMPLATES_DIR) if (Jinja2Templates and os.path.exists(TEMPLATES_DIR)) else None

# ==============================================================================
# 1. CREDENCIALES, TOKENS Y CONSTANTES OAUTH2 MERCADO LIBRE
# ==============================================================================
CLIENT_ID = os.getenv("MELI_CLIENT_ID", "4303420568939896")
CLIENT_SECRET = os.getenv("MELI_CLIENT_SECRET", "VUnYfpH5rp9LM090hc7N36wzcnHcpBL5")
TOKEN_FILE = os.path.join(BASE_DIR, "tokens.json")
BLACKLIST_KEYWORDS = ["aromatizante frech"]

BASE_URL = os.environ.get("NGROK_URL", "https://www.jin.com.mx").rstrip("/")
NGROK_URL = BASE_URL
REDIRECT_URI = f"{BASE_URL}/webhook/mercadolibre"

MELI_SELLER_ID = os.getenv("MELI_SELLER_ID", "491131225")
WHATSAPP_NUMBER = "524771230000"

# Configuración de Facebook Graph API y Autopublicación desde Mercado Libre
FB_PAGE_ID = os.environ.get("FB_PAGE_ID", "").strip()
FB_PAGE_ACCESS_TOKEN = os.environ.get("FB_PAGE_ACCESS_TOKEN", "").strip()
FB_AUTO_POST_ENABLED = os.environ.get("FB_AUTO_POST_ENABLED", "true").lower() == "true"
POSTED_FB_ITEMS_FILE = os.path.join(BASE_DIR, "posted_fb_items.json")
POSTED_FB_ITEMS_MEM: Set[str] = set()

# Sesión del Panel Privado (/privado)
PRIVATE_SESSION_COOKIE = "jin_private_session"
PRIVATE_PANEL_PASSWORD = os.environ.get("PRIVATE_PANEL_PASSWORD", os.environ.get("ADMIN_PASSWORD", "jin2026"))
PRIVATE_SESSION_TOKEN = hashlib.sha256(f"jin.com.mx:{PRIVATE_PANEL_PASSWORD}".encode("utf-8")).hexdigest()

# URL CSV de Google Sheets para ruta /acumuladores
GOOGLE_SHEET_CSV_URL = os.getenv(
    "GOOGLE_SHEET_CSV_URL",
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vR9_acumuladores_lth_jin/pub?output=csv"
)

# Caché en memoria diferenciada por "local" y "national" (TTL: 15 minutos = 900s)
CACHE_TTL_SECONDS = 900
CACHE_PRODUCTS: Dict[str, Dict[str, Any]] = {
    "local": {"data": None, "products": [], "timestamp": 0, "source": "uninitialized"},
    "national": {"data": None, "products": [], "timestamp": 0, "source": "uninitialized"}
}

# Catálogo de Respaldo Híbrido de Alta Fidelidad (cuando no hay tokens.json activo o ML falla)
LOCAL_FALLBACK_PRODUCTS: List[Dict[str, Any]] = [
    {
        "id": "MLM21848544",
        "title": "Capitán América 15 Cm Marvel Avengers Hasbro",
        "category": "colecciones",
        "brand": "marvel",
        "price": 180.00,
        "original_price": 220.00,
        "discount": "-18%",
        "available_quantity": 3,
        "stock": "3 disp.",
        "is_last": False,
        "is_battery": False,
        "installments": "Hasta 12 MSI",
        "image_url": "https://http2.mlstatic.com/D_NQ_NP_2X_795646-MLM51761611099_092022-F.webp",
        "permalink": "https://www.mercadolibre.com.mx/capitan-america-15-cm-marvel-avengers/p/MLM21848544?pdp_filters=seller_id%3A491131225",
        "description": "Figura de acción original Marvel Avengers Hasbro con escudo desmontable y articulación premium."
    },
    {
        "id": "MLM-BATMAN-15",
        "title": "Batman Missions 15 Cm DC Comics Mattel",
        "category": "colecciones",
        "brand": "dc",
        "price": 150.00,
        "original_price": 190.00,
        "discount": "-21%",
        "available_quantity": 1,
        "stock": "1 pieza",
        "is_last": True,
        "is_battery": False,
        "installments": "Hasta 3 MSI",
        "image_url": "https://http2.mlstatic.com/D_NQ_NP_2X_616188-MLM43555364132_092020-F.webp",
        "permalink": f"https://listado.mercadolibre.com.mx/_CustId_{MELI_SELLER_ID}",
        "description": "Figura articulada oficial de colección DC Comics Mattel. Entregas en zona Arbide o envíos."
    },
    {
        "id": "MLM-SPIDER-30",
        "title": "Spider-Man Titan Hero Series 30 Cm Marvel Hasbro",
        "category": "toy",
        "brand": "marvel",
        "price": 299.00,
        "original_price": 360.00,
        "discount": "-17%",
        "available_quantity": 4,
        "stock": "Disponible",
        "is_last": False,
        "is_battery": False,
        "installments": "Hasta 12 MSI",
        "image_url": "https://http2.mlstatic.com/D_NQ_NP_2X_792370-MLM46882672722_072021-F.webp",
        "permalink": f"https://listado.mercadolibre.com.mx/_CustId_{MELI_SELLER_ID}",
        "description": "Gran tamaño de 30 cm con articulación premium Marvel Hasbro y diseño clásico Spider-Man."
    },
    {
        "id": "MLM-MANDO-01",
        "title": "Star Wars The Mandalorian & Grogu Figura Colección",
        "category": "colecciones",
        "brand": "star wars",
        "price": 340.00,
        "original_price": 420.00,
        "discount": "-19%",
        "available_quantity": 2,
        "stock": "2 piezas",
        "is_last": False,
        "is_battery": False,
        "installments": "Hasta 12 MSI",
        "image_url": "https://http2.mlstatic.com/D_NQ_NP_2X_910776-MLM48384218765_112021-F.webp",
        "permalink": f"https://listado.mercadolibre.com.mx/_CustId_{MELI_SELLER_ID}",
        "description": "Auténtico coleccionable de la saga Star Wars con accesorios de batalla y figura de Grogu."
    },
    {
        "id": "MLM-HW-PACK5",
        "title": "Hot Wheels 5-Pack Vehículos Escala 1:64 Mattel",
        "category": "toy",
        "brand": "hot wheels",
        "price": 195.00,
        "original_price": 240.00,
        "discount": "-18%",
        "available_quantity": 5,
        "stock": "Disponible",
        "is_last": False,
        "is_battery": False,
        "installments": "Meses sin Intereses",
        "image_url": "https://http2.mlstatic.com/D_NQ_NP_2X_985556-MLM51893322047_102022-F.webp",
        "permalink": f"https://listado.mercadolibre.com.mx/_CustId_{MELI_SELLER_ID}",
        "description": "Modelos clásicos y deportivos en metal die-cast Mattel a escala 1:64."
    },
    {
        "id": "MLM-LTH-L42",
        "title": "Batería Acumulador LTH L-42-500 Automotriz",
        "category": "battery",
        "brand": "lth",
        "price": 2150.00,
        "original_price": 2450.00,
        "discount": "-12%",
        "available_quantity": 3,
        "stock": "Local Arbide",
        "is_last": False,
        "is_battery": True,
        "installments": "48 Meses Garantía",
        "image_url": "https://http2.mlstatic.com/D_NQ_NP_2X_899203-MLM44976766461_022021-F.webp",
        "permalink": f"https://listado.mercadolibre.com.mx/_CustId_{MELI_SELLER_ID}",
        "description": "Acumulador automotriz LTH L-42-500. Entrega e instalación en zona Arbide (León, Gto)."
    }
]


# ==============================================================================
# 2. GESTIÓN DE TOKENS OAUTH2 Y REFRESCO AUTOMÁTICO
# ==============================================================================
def load_tokens() -> Optional[Dict[str, Any]]:
    """Carga los tokens de Mercado Libre desde tokens.json o variables de entorno."""
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data and data.get("access_token"):
                    return data
        except Exception as e:
            logger.error(f"Error al leer {TOKEN_FILE}: {e}")

    env_access = os.getenv("MELI_ACCESS_TOKEN", "")
    env_refresh = os.getenv("MELI_REFRESH_TOKEN", "")
    if env_access:
        return {"access_token": env_access, "refresh_token": env_refresh}
    return None


def save_tokens(tokens: Dict[str, Any]) -> None:
    """Guarda los tokens actualizados en tokens.json."""
    try:
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            json.dump(tokens, f, indent=4, ensure_ascii=False)
        logger.info("Tokens de Mercado Libre guardados exitosamente en tokens.json.")
    except Exception as e:
        logger.error(f"Error al guardar {TOKEN_FILE}: {e}")


def refresh_access_token(refresh_token: str) -> Optional[str]:
    """Renueva automáticamente el access_token ante respuestas 401 o 403."""
    if not refresh_token:
        logger.warning("No hay refresh_token disponible para renovar la sesión de Mercado Libre.")
        return None

    url = "https://api.mercadolibre.com/oauth/token"
    payload = {
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    try:
        logger.info("Intentando refrescar access_token de Mercado Libre...")
        res = requests.post(url, data=payload, headers=headers, timeout=10)
        if res.status_code == 200:
            new_tokens = res.json()
            save_tokens(new_tokens)
            logger.info("¡Token de Mercado Libre renovado con éxito!")
            return new_tokens.get("access_token")
        else:
            logger.error(f"Error al refrescar token ML ({res.status_code}): {res.text[:200]}")
    except Exception as e:
        logger.error(f"Excepción durante refresh_access_token: {e}")
    return None


def invalidate_product_cache() -> None:
    """Invalida la caché de productos tanto local como nacional."""
    for k in ("local", "national"):
        CACHE_PRODUCTS[k]["data"] = None
        CACHE_PRODUCTS[k]["products"] = []
        CACHE_PRODUCTS[k]["timestamp"] = 0


# ==============================================================================
# 2.5 CONTROL ANTI-DUPLICADOS Y AUTOPUBLICACIÓN EN FACEBOOK GRAPH API
# ==============================================================================
def load_posted_fb_items() -> Set[str]:
    """Carga el registro de IDs (MLM...) ya publicados en Facebook desde memoria y posted_fb_items.json."""
    global POSTED_FB_ITEMS_MEM
    if os.path.exists(POSTED_FB_ITEMS_FILE):
        try:
            with open(POSTED_FB_ITEMS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    POSTED_FB_ITEMS_MEM.update(str(x).strip() for x in data if x)
                elif isinstance(data, dict) and isinstance(data.get("posted_ids"), list):
                    POSTED_FB_ITEMS_MEM.update(str(x).strip() for x in data["posted_ids"] if x)
        except Exception as e:
            logger.warning(f"No se pudo leer {POSTED_FB_ITEMS_FILE}: {e}")
    return POSTED_FB_ITEMS_MEM


def save_posted_fb_item(item_id: str) -> None:
    """Registra un ID de Mercado Libre como publicado en memoria y en posted_fb_items.json."""
    clean_id = str(item_id or "").strip()
    if not clean_id:
        return
    posted = load_posted_fb_items()
    posted.add(clean_id)
    try:
        with open(POSTED_FB_ITEMS_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(list(posted)), f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"No se pudo guardar {POSTED_FB_ITEMS_FILE}: {e}")


def get_high_res_image_url(item_data: Dict[str, Any]) -> str:
    """Garantiza URL HTTPS absoluta de alta resolución (-O.jpg o secure_url) para Meta Commerce / Graph API."""
    img = str(item_data.get("image_url") or item_data.get("thumbnail_url") or "").strip()
    if not img:
        pictures = item_data.get("pictures") or []
        if pictures and isinstance(pictures, list) and isinstance(pictures[0], dict):
            img = str(pictures[0].get("secure_url") or pictures[0].get("url") or "").strip()
    if not img:
        img = str(item_data.get("thumbnail") or "").strip()

    if img:
        img = (
            img.replace("http://", "https://")
            .replace("-I.jpg", "-O.jpg")
            .replace("-V.jpg", "-O.jpg")
            .replace("-S.jpg", "-O.jpg")
        )
        if img.startswith("/"):
            img = f"https://www.jin.com.mx{img}"
        elif not img.startswith("http"):
            img = f"https://www.jin.com.mx/{img.lstrip('/')}"
        return img
    return "https://www.jin.com.mx/static/img/logo_jin_3d.png"


def build_facebook_post_caption(item_data: Dict[str, Any]) -> str:
    """
    Construye un copy comercial limpio y persuasivo en español para el muro de Facebook
    (facebook.com/jin.com.mx) con título, precio, descuento/MSI, condición, stock y enlaces.
    """
    item_id = str(item_data.get("id") or "").strip()
    title = str(item_data.get("title") or "Artículo Disponible en jin.com.mx").strip()
    price = float(item_data.get("price") or 0)
    orig_price_raw = item_data.get("original_price")
    orig_price = float(orig_price_raw) if orig_price_raw else None
    cond_raw = str(item_data.get("condition") or "new").lower()
    cond_label = "Usado / Bazar Seleccionado" if cond_raw == "used" else "Nuevo"
    avail_qty = int(item_data.get("available_quantity", 1) or 1)
    stock_label = "¡Última pieza disponible!" if avail_qty == 1 else f"Disponible ({avail_qty} pzas en stock)"
    installments = item_data.get("installments")

    price_line = f"💰 Precio: ${price:,.2f} MXN"
    if orig_price and orig_price > price > 0:
        disc_pct = int(round(((orig_price - price) / orig_price) * 100))
        if disc_pct > 0:
            price_line += f" (🔥 -{disc_pct}% de descuento, antes ${orig_price:,.2f} MXN)"
    if installments:
        price_line += f"\n💳 {installments}"

    direct_web_link = f"https://www.jin.com.mx/?q={quote(item_id)}" if item_id else "https://www.jin.com.mx"
    ml_permalink = str(item_data.get("permalink") or f"https://listado.mercadolibre.com.mx/_CustId_{MELI_SELLER_ID}").strip()

    caption = (
        f"✨ ¡NUEVO EN CATÁLOGO JIN.COM.MX! ✨\n\n"
        f"📦 {title}\n"
        f"{price_line}\n"
        f"🏷️ Condición: {cond_label} | {stock_label}\n\n"
        f"🌐 Ver en nuestro catálogo 3D: {direct_web_link}\n"
        f"🛒 Compra protegida en Mercado Libre: {ml_permalink}\n"
        f"📲 Atención directa y entregas en León, Gto. por WhatsApp: https://wa.me/{WHATSAPP_NUMBER}\n\n"
        f"#jincommx #CatalogoEnLinea #MercadoLibreMexico #Juguetes #Coleccionables #Refacciones #LeonGto"
    )
    return caption


async def publish_item_to_facebook(item_data: Dict[str, Any], force: bool = False) -> Dict[str, Any]:
    """
    Publica un artículo de Mercado Libre con su fotografía en alta resolución (-O.jpg)
    en el muro de la página oficial de Facebook (https://www.facebook.com/jin.com.mx)
    usando Meta Graph API v21.0 (/{FB_PAGE_ID}/photos).
    """
    if not item_data or not isinstance(item_data, dict):
        return {"status": "error", "ok": False, "message": "Datos del artículo inválidos."}

    item_id = str(item_data.get("id") or "").strip()
    title = str(item_data.get("title") or "").strip()
    posted_ids = load_posted_fb_items()

    if item_id and (item_id in posted_ids) and not force:
        msg = f"El artículo {item_id} ('{title}') ya fue publicado previamente en Facebook (control anti-duplicados)."
        logger.info(msg)
        return {
            "status": "already_posted",
            "ok": False,
            "item_id": item_id,
            "title": title,
            "message": msg
        }

    image_url = get_high_res_image_url(item_data)
    caption = build_facebook_post_caption(item_data)

    if not FB_PAGE_ID or not FB_PAGE_ACCESS_TOKEN:
        warn_msg = (
            f"Autopublicación Facebook omitida para {item_id or title}: "
            "FB_PAGE_ID o FB_PAGE_ACCESS_TOKEN aún no están configurados en las variables de entorno."
        )
        logger.warning(warn_msg)
        return {
            "status": "missing_credentials",
            "ok": False,
            "item_id": item_id,
            "title": title,
            "image_url": image_url,
            "caption_preview": caption,
            "message": warn_msg
        }

    graph_url = f"https://graph.facebook.com/v21.0/{FB_PAGE_ID}/photos"
    payload = {
        "url": image_url,
        "caption": caption,
        "access_token": FB_PAGE_ACCESS_TOKEN
    }

    def _post_to_graph() -> requests.Response:
        return requests.post(graph_url, data=payload, timeout=15)

    try:
        res = await asyncio.to_thread(_post_to_graph)
        res_data = res.json() if res.content else {}
        if res.status_code in (200, 201) and (res_data.get("id") or res_data.get("post_id")):
            fb_post_id = res_data.get("post_id") or res_data.get("id")
            if item_id:
                save_posted_fb_item(item_id)
            logger.info(f"Artículo {item_id} publicado con éxito en Facebook Page {FB_PAGE_ID} (post_id={fb_post_id}).")
            return {
                "status": "published",
                "ok": True,
                "item_id": item_id,
                "title": title,
                "fb_post_id": fb_post_id,
                "image_url": image_url,
                "caption_preview": caption,
                "message": f"Artículo {item_id} ('{title}') publicado con éxito en Facebook."
            }
        else:
            err_detail = res_data.get("error", {}).get("message") if isinstance(res_data, dict) else res.text[:250]
            logger.error(f"Error de Facebook Graph API ({res.status_code}) para {item_id}: {err_detail}")
            return {
                "status": "graph_api_error",
                "ok": False,
                "item_id": item_id,
                "title": title,
                "image_url": image_url,
                "caption_preview": caption,
                "message": f"Facebook Graph API respondió ({res.status_code}): {err_detail}"
            }
    except Exception as e:
        logger.error(f"Excepción al publicar {item_id} en Facebook Graph API: {e}")
        return {
            "status": "exception",
            "ok": False,
            "item_id": item_id,
            "title": title,
            "image_url": image_url,
            "caption_preview": caption,
            "message": f"Error de conexión con Facebook Graph API: {str(e)}"
        }


def fetch_single_ml_item_by_resource(resource_or_id: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene y normaliza un artículo individual desde la API de Mercado Libre a partir de
    un resource de webhook (ej. '/items/MLM123456') o un ID ('MLM123456').
    """
    raw = str(resource_or_id or "").strip()
    if not raw:
        return None
    item_id = raw.split("/")[-1].split("?")[0].strip().upper()
    if not item_id.startswith("MLM"):
        return None

    headers = {"Accept": "application/json"}
    tokens = load_tokens()
    if tokens and tokens.get("access_token"):
        headers["Authorization"] = f"Bearer {tokens['access_token']}"

    url = f"https://api.mercadolibre.com/items/{item_id}"
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code in (401, 403) and tokens and tokens.get("refresh_token"):
            new_token = refresh_access_token(tokens["refresh_token"])
            if new_token:
                headers["Authorization"] = f"Bearer {new_token}"
                res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            raw_item = res.json()
            return normalize_ml_item(raw_item)
    except Exception as e:
        logger.error(f"Error al consultar item individual {item_id} desde Mercado Libre: {e}")
    return None


async def process_ml_webhook_facebook_autopost(body: Dict[str, Any]) -> None:
    """
    Tarea en segundo plano disparada por POST /webhook/mercadolibre:
    Verifica si la notificación corresponde a un artículo activo nuevo o reactivado que aún no
    se ha publicado en Facebook y lo publica automáticamente sin bloquear al webhook.
    """
    if not FB_AUTO_POST_ENABLED:
        logger.info("FB_AUTO_POST_ENABLED está desactivado; omitiendo autopublicación desde webhook.")
        return

    topic = str(body.get("topic") or "").lower().strip()
    resource = str(body.get("resource") or "").strip()
    if topic not in ("items", "created_item", "") and not resource.startswith("/items/"):
        return

    item_id = resource.split("/")[-1].split("?")[0].strip().upper()
    if not item_id.startswith("MLM"):
        return

    if item_id in load_posted_fb_items():
        logger.info(f"Webhook ML: {item_id} ya figura en posted_fb_items.json; no se republica en Facebook.")
        return

    norm_item = await asyncio.to_thread(fetch_single_ml_item_by_resource, item_id)
    if norm_item:
        await publish_item_to_facebook(norm_item, force=False)


# ==============================================================================
# 3. CLASIFICACIÓN INTELIGENTE MULTI-ETIQUETA, GEOLOCALIZACIÓN Y TARJETAS 3D
# ==============================================================================
def is_battery_product(title: str) -> bool:
    """Detecta si un producto corresponde a batería o acumulador."""
    t = title.lower()
    return any(w in t for w in ["bateria", "batería", "acumulador", "lth"])


def extract_attributes_text(attributes: Optional[List[Dict[str, Any]]]) -> Dict[str, str]:
    """Extrae un diccionario de atributos clave de Mercado Libre (BRAND, LINE, CHARACTER, FRANCHISE, etc.)."""
    attr_map: Dict[str, str] = {}
    if not attributes or not isinstance(attributes, list):
        return attr_map
    for attr in attributes:
        if not isinstance(attr, dict):
            continue
        attr_id = (attr.get("id") or attr.get("name") or "").upper()
        val_name = str(attr.get("value_name") or "").strip()
        if attr_id and val_name:
            attr_map[attr_id] = val_name
    return attr_map


def classify_item_detailed(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analiza todos los campos de la publicación de Mercado Libre (title, condition, price,
    original_price, category_id, attributes, tags, available_quantity) y asigna etiquetas
    múltiples de categorías (cats) y subcategorías (subs) para los menús y nodos orbitales.
    """
    title = str(item.get("title") or "")
    t = title.lower()
    attr_map = extract_attributes_text(item.get("attributes"))
    all_attr_text = " ".join(v.lower() for v in attr_map.values())
    combined_text = f"{t} {all_attr_text}"

    raw_cond = str(item.get("condition") or "").lower()
    cond_attr = attr_map.get("ITEM_CONDITION", "").lower()
    is_used = (
        raw_cond == "used"
        or "usado" in cond_attr
        or any(w in t for w in ["usado", "usada", "segunda mano", "exhibición", "exhibicion", "seminuevo", "preowned"])
    )
    condition = "used" if is_used else "new"

    price = float(item.get("price") or 0)
    orig_price_raw = item.get("original_price")
    orig_price = float(orig_price_raw) if orig_price_raw else None
    avail_qty = int(item.get("available_quantity", 1) or 1)
    category_id = str(item.get("category_id") or "").upper()

    tags_raw = item.get("tags") or []
    tags_lower = [str(tg).lower() for tg in tags_raw if tg]
    deal_ids = item.get("deal_ids") or []

    # Cálculo de descuento real o detección de promoción ML
    discount_pct = 0
    if orig_price and orig_price > price > 0:
        discount_pct = int(round(((orig_price - price) / orig_price) * 100))
    has_promo_tag = any(
        k in tg for tg in tags_lower
        for k in ["deal_of_the_day", "lightning", "promotion", "discount", "campaign"]
    ) or bool(deal_ids)

    # Detección de ramas principales
    is_battery = is_battery_product(combined_text)

    refa_keywords = [
        "refaccion", "refacción", "autoparte", "bujia", "bujía", "bobina", "encendido",
        "banda", "polea", "tensor", "distribucion", "distribución", "alternador",
        "filtro", "sensor", "oxigeno", "oxígeno", "maf", "map", "tps", "inyector",
        "amortiguador", "balata", "freno", "disco de freno", "rotula", "rótula",
        "horquilla", "terminal", "bieleta", "maza", "balero", "suspensión", "suspension",
        "embrague", "clutch", "radiador", "termostato", "bomba de agua", "bomba de gasolina",
        "faro", "calavera", "espejo lateral", "parrilla automotriz", "junta homocinetica"
    ]
    is_refaccion = (not is_battery) and (
        any(k in combined_text for k in refa_keywords)
        or category_id.startswith("MLM1747")
    )

    toy_keywords = [
        "juguete", "figura", "colección", "coleccion", "coleccionable", "muñeco", "muñeca",
        "marvel", "spider", "avengers", "capitán", "capitan", "iron man", "thor", "hulk",
        "wolverine", "deadpool", "venom", "x-men", "star wars", "mandalorian", "grogu",
        "yoda", "vader", "jedi", "stormtrooper", "kenner", "batman", "superman", "dc comics",
        "joker", "flash", "justice league", "wonder woman", "aquaman", "pokemon", "pokémon",
        "pikachu", "charizard", "pokebola", "mewtwo", "trolls", "mattel", "hasbro",
        "hot wheels", "barbie", "funko", "lego", "max steel", "nerf", "transformers",
        "jurassic", "he-man", "masters of the universe", "toy story", "disney", "pixar",
        "bandai", "neca", "mcfarlane", "playmobil", "peluche", "escala 1:"
    ]
    is_toy = (not is_battery and not is_refaccion) and (
        any(k in combined_text for k in toy_keywords)
        or category_id.startswith("MLM1132")
    )

    cats: List[str] = []
    subs: List[str] = []
    brand = (attr_map.get("BRAND") or "").lower()

    # 1. BATERÍAS PARA AUTO LTH
    if is_battery:
        cats.append("battery")
        subs.append("bat_all")
        subs.append("bat_aplicacion")
        brand = "lth"
        if any(k in combined_text for k in ["hi-tec", "hitec", "agm", "evolution", "protect", "optima", "gel", "start-stop"]):
            subs.append("bat_hitec_agm")
        else:
            subs.append("bat_convencional")

    # 2. REFA EN LÍNEA (REFACCIONES AUTOMOTRICES)
    if is_refaccion:
        cats.append("refacciones")
        subs.append("refa_all")
        matched_refa_sub = False
        if any(k in combined_text for k in ["bujia", "bujía", "bobina", "cable", "encendido", "ngk", "champion", "bosch", "denso", "autolite", "distribuidor"]):
            subs.append("refa_bujias")
            matched_refa_sub = True
        if any(k in combined_text for k in ["banda", "polea", "tensor", "distribucion", "distribución", "alternador", "tiempo", "gates", "continental", "dayco"]):
            subs.append("refa_bandas")
            matched_refa_sub = True
        if any(k in combined_text for k in ["filtro", "sensor", "oxigeno", "oxígeno", "maf", "map", "tps", "aceite", "aire", "gasolina", "cabina", "fram", "gonher", "interfil", "inyector", "valvula", "válvula"]):
            subs.append("refa_filtros_sensores")
            matched_refa_sub = True
        if any(k in combined_text for k in ["amortiguador", "balata", "freno", "disco", "rotula", "rótula", "terminal", "horquilla", "buje", "bieleta", "maza", "balero", "soporte", "suspension", "suspensión", "embrague", "clutch", "bomba"]):
            subs.append("refa_suspension_frenos")
            matched_refa_sub = True
        if not matched_refa_sub:
            subs.append("refa_otras")

    # 3. JUGUETES Y COLECCIONES + OUTLET DEL JUGUETE
    if is_toy:
        cats.extend(["toy", "colecciones"])
        subs.extend(["col_all", "outlet_baratos"])

        # Subcategorías Outlet del Juguete por rango de precio
        if price < 300:
            subs.append("outlet_menos_300")
        if 300 <= price <= 600:
            subs.append("outlet_300_600")
        if discount_pct > 0 or price <= 220 or avail_qty == 1:
            subs.append("outlet_remates")

        # Subcategorías Juguetes y Colecciones por franquicia / marca
        if any(k in combined_text for k in ["star wars", "mandalorian", "grogu", "yoda", "vader", "jedi", "stormtrooper", "boba fett", "kenner"]):
            subs.append("col_star_wars")
            brand = brand or "star wars"
        if any(k in combined_text for k in ["marvel", "spider", "avengers", "capitán", "capitan", "iron man", "thor", "hulk", "x-men", "wolverine", "deadpool", "venom"]):
            subs.append("col_marvel_dc")
            brand = brand or "marvel"
        if any(k in combined_text for k in ["batman", "superman", "dc", "joker", "flash", "justice league", "wonder woman", "aquaman"]):
            if "col_marvel_dc" not in subs:
                subs.append("col_marvel_dc")
            brand = brand or "batman"
        if any(k in combined_text for k in ["pokemon", "pokémon", "pikachu", "charizard", "pokebola", "mewtwo", "eevee"]):
            subs.append("col_pokemon")
            brand = brand or "pokemon"
        if any(k in combined_text for k in ["trolls", "mattel", "hasbro", "hot wheels", "barbie", "max steel", "nerf", "transformers", "my little pony", "jurassic", "he-man", "masters of the universe"]):
            subs.append("col_trolls_mattel_hasbro")
            if "hot wheels" in combined_text:
                brand = "hot wheels"
            elif "barbie" in combined_text or "muñeca" in combined_text:
                brand = "barbie"
            elif "hasbro" in combined_text and not brand:
                brand = "hasbro"
            elif "mattel" in combined_text and not brand:
                brand = "mattel"
        if "funko" in combined_text:
            brand = "funko"
        if "lego" in combined_text:
            brand = "lego"
        if any(k in combined_text for k in ["figura", "colección", "coleccion", "collector", "funko", "lego", "escala", "die-cast", "titan hero", "missions"]):
            subs.append("col_figuras_accion")

    # 4. BAZAR (USADOS / SEGUNDA MANO)
    if is_used:
        cats.append("bazar")
        subs.append("bazar_usados_all")
        if is_toy:
            subs.append("bazar_usados_juguetes")
        elif any(k in combined_text for k in ["electr", "hogar", "cocina", "audio", "bocina", "tv", "pantalla", "consola", "celular", "comput", "lámpara", "lampara", "mueble"]):
            subs.append("bazar_usados_electronica_hogar")
        else:
            subs.append("bazar_usados_otros")

    # 5. BAZAR 2 / VARIEDADES Y MISCELÁNEA (No juguetes, no baterías, no refacciones)
    if not is_toy and not is_battery and not is_refaccion:
        cats.append("bazar_2")
        subs.append("bazar2_all")
        matched_b2 = False
        if any(k in combined_text for k in ["hogar", "oficina", "cocina", "decoracion", "decoración", "organizador", "mueble", "baño", "jardín", "jardin", "termo", "taza"]):
            subs.append("bazar2_hogar")
            matched_b2 = True
        if any(k in combined_text for k in ["herramienta", "llave", "pinza", "desarmador", "taladro", "cinta", "accesorio", "candado", "linterna", "multimetro"]):
            subs.append("bazar2_herramientas")
            matched_b2 = True
        if any(k in combined_text for k in ["electr", "gadget", "cable", "bocina", "audifono", "audífono", "cargador", "usb", "led", "camara", "cámara", "bluetooth", "adaptador"]):
            subs.append("bazar2_electronica")
            matched_b2 = True
        if not matched_b2:
            subs.append("bazar2_variedades")

    # 6. OFERTAS ESPECIALES (DESCUENTOS, RELÁMPAGO, MSI, ÚLTIMAS PIEZAS)
    has_installments = bool(item.get("installments") or item.get("accepts_mercadopago"))
    if discount_pct > 0 or has_promo_tag:
        subs.append("oferta_mayores")
    if has_promo_tag or discount_pct >= 15:
        subs.append("oferta_relampago")
    if has_installments:
        subs.append("oferta_msi")
    if avail_qty == 1 or bool(item.get("is_last")):
        subs.append("oferta_ultimas")

    # Categoría primaria para data-type
    if is_battery:
        primary_cat = "battery"
    elif is_refaccion:
        primary_cat = "refacciones"
    elif is_used and not is_toy:
        primary_cat = "bazar"
    elif is_toy:
        primary_cat = "colecciones" if "col_figuras_accion" in subs else "toy"
    else:
        primary_cat = "bazar_2"

    # Deduplicar manteniendo orden
    cats_unique = list(dict.fromkeys(cats))
    subs_unique = list(dict.fromkeys(subs))

    return {
        "category": primary_cat,
        "brand": brand,
        "condition": condition,
        "discount_pct": discount_pct,
        "has_promo_tag": has_promo_tag,
        "cats": cats_unique,
        "subs": subs_unique
    }


def classify_category(title: str) -> Dict[str, str]:
    """Wrapper compatible con llamadas simples por título."""
    res = classify_item_detailed({"title": title})
    return {"category": res["category"], "brand": res["brand"]}


def detect_client_is_local(request: Request) -> bool:
    """
    Determina por IP usando GeoJS si el visitante se encuentra en León / Guanajuato (is-local)
    o en el resto del país (is-national).
    """
    # Soporte para parámetro de prueba manual (?loc=local o ?loc=national)
    loc_override = request.query_params.get("loc", "").lower()
    if loc_override == "local":
        return True
    if loc_override == "national":
        return False

    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "127.0.0.1"

    if client_ip == "testclient":
        return False

    # Si se ejecuta en localhost, consultar GeoJS sin IP para detectar ubicación real de la red local
    geo_url = (
        "https://get.geojs.io/v1/ip/geo.json"
        if client_ip in ("127.0.0.1", "::1", "localhost")
        else f"https://get.geojs.io/v1/ip/geo/{client_ip}.json"
    )

    try:
        geo_res = requests.get(geo_url, timeout=(2.0, 2.0))
        if geo_res.status_code == 200:
            geo_data = geo_res.json()
            city = (geo_data.get("city") or "").lower()
            region = (geo_data.get("region") or "").lower()
            if any(loc in city or loc in region for loc in ["leon", "león", "guanajuato"]):
                return True
    except Exception as e:
        logger.debug(f"No se pudo verificar geolocalización IP ({client_ip}): {e}")

    return False


def build_card_html(p: Dict[str, Any], is_local: bool) -> str:
    """
    Construye el HTML de cada tarjeta flip-card 3D respetando la estética Y2K de JIN.COM.MX,
    pantalla de precio LCD digital (#88c599), link directo a Mercado Libre y botón de WhatsApp.
    """
    item_id = p.get("id", "")
    title = p.get("title", "Producto JIN.COM.MX")
    category = p.get("category", "toy")
    is_battery = bool(p.get("is_battery") or category == "battery")
    price = float(p.get("price", 0))
    original_price = p.get("original_price")
    discount = p.get("discount", "")
    is_last = bool(p.get("is_last"))
    stock_text = p.get("stock", "Disponible")
    installments = p.get("installments")
    img_url = p.get("image_url") or "static/img/logo_jin_3d.png"
    thumb_url = p.get("thumbnail_url") or img_url
    permalink = p.get("permalink", "")

    battery_class = "battery-link" if is_battery else ""

    if is_last:
        stock_badge_html = '<span class="stock-badge last-piece">⚡ ¡ÚLTIMA PIEZA!</span>'
    else:
        stock_badge_html = f'<span class="stock-badge">Stock: {stock_text}</span>'

    discount_badge_html = f'<span class="discount-badge">{discount}</span>' if discount else ""

    orig_price_html = ""
    if original_price and float(original_price) > price:
        orig_price_html = (
            f'<div style="font-size: 11px; text-decoration: line-through; color: #888; font-weight: 700;">'
            f'${float(original_price):,.2f} MXN</div>'
        )

    installments_html = f'<div class="installments">{installments}</div>' if installments else ""

    if is_local:
        desc_text = p.get("description") or "📍 Entrega personal en zona Arbide (León, Gto.) o compra protegida por Mercado Libre."
    else:
        desc_text = p.get("description") or "🚚 Publicación oficial con envío seguro a todo México por Mercado Libre."

    ml_btn_html = ""
    if permalink:
        ml_btn_html = f"""
                                    <a href="{permalink}" target="_blank" rel="noopener" class="glass-btn ml-btn">
                                        🛒 Comprar en Mercado Libre
                                    </a>"""

    wa_msg = quote(f"Hola JIN.COM.MX, me interesa el producto: {title} (Ref: {item_id}) de ${price:,.2f} MXN")
    wa_btn_html = f"""
                                    <a href="https://wa.me/{WHATSAPP_NUMBER}?text={wa_msg}" target="_blank" rel="noopener" class="glass-btn wa-btn">
                                        💬 Pedir por WhatsApp
                                    </a>"""

    # Asegurar clasificación detallada para atributos data-* del DOM
    if "cats" not in p or "subs" not in p:
        detailed = classify_item_detailed(p)
        cats_str = ",".join(detailed["cats"])
        subs_str = ",".join(detailed["subs"])
        cond_str = detailed["condition"]
        disc_pct = detailed["discount_pct"]
        brand_str = p.get("brand") or detailed["brand"]
    else:
        cats_str = ",".join(p.get("cats") or [category])
        subs_str = ",".join(p.get("subs") or [])
        cond_str = p.get("condition") or "new"
        disc_pct = int(p.get("discount_pct") or 0)
        brand_str = p.get("brand") or ""

    return f"""
                <div class="product-card flip-card {battery_class}"
                     data-id="{item_id}"
                     data-title="{title}"
                     data-type="{category}"
                     data-cats="{cats_str}"
                     data-subs="{subs_str}"
                     data-condition="{cond_str}"
                     data-price="{price:.2f}"
                     data-discount-pct="{disc_pct}"
                     data-brand="{brand_str}">
                    <div class="flip-card-inner">
                        <div class="flip-card-front">
                            {stock_badge_html}
                            {discount_badge_html}
                            <div class="card-image-area">
                                <img src="{img_url}" 
                                     data-fallback="{thumb_url}"
                                     alt="{title}" 
                                     loading="lazy"
                                     onerror="if(this.dataset.fallback && this.src !== this.dataset.fallback){{this.src=this.dataset.fallback;}}else{{this.onerror=null;this.src='static/img/logo_jin_3d.png';}}">
                            </div>
                            <div class="card-info-area">
                                <h3 class="card-title">{title}</h3>
                                <div class="ref-id">REF: {item_id}</div>
                                {orig_price_html}
                                <div class="front-price">${price:,.2f} MXN</div>
                                {installments_html}
                                <div class="tap-hint">👆 Toca para ver opciones</div>
                            </div>
                        </div>
                        <div class="flip-card-back">
                            <div class="back-content">
                                <img src="static/img/logo_jin_3d.png" alt="JIN.COM.MX" class="back-logo-img">
                                <h4 class="back-title">{title}</h4>
                                <div class="back-price">${price:,.2f} MXN</div>
                                <p style="font-size: 11px; color: #555; font-weight: 600;">{desc_text}</p>
                                <div class="action-buttons-group">{ml_btn_html}{wa_btn_html}
                                    <button class="return-btn" type="button">Volver al frente ↩</button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>"""


# ==============================================================================
# 4. EXTRACCIÓN PAGINADA MERCADO LIBRE + CACHÉ TTL + OPTIMIZACIÓN DE RAM
# ==============================================================================
def normalize_ml_item(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Procesa y filtra un item individual devuelto por la API de Mercado Libre.
    Retorna None si no está activo, sin stock o en la lista negra.
    """
    status = item.get("status", "active")
    avail_qty = int(item.get("available_quantity", 0) or 0)
    if status != "active" or avail_qty <= 0:
        return None

    title = item.get("title") or ""
    title_lower = title.lower()

    # Excluir palabras de BLACKLIST_KEYWORDS
    if any(bad.lower() in title_lower for bad in BLACKLIST_KEYWORDS):
        return None

    # Fotografía en máxima resolución desde pictures[0]["url"] con fallback a thumbnail original HTTPS
    raw_thumb = (item.get("thumbnail") or "").replace("http://", "https://")
    pictures = item.get("pictures") or []
    if pictures and isinstance(pictures, list) and (pictures[0].get("secure_url") or pictures[0].get("url")):
        high_res_img = pictures[0].get("secure_url") or pictures[0].get("url")
    else:
        high_res_img = (
            raw_thumb.replace("-I.jpg", "-O.jpg")
            .replace("-V.jpg", "-O.jpg")
            .replace("-S.jpg", "-O.jpg")
        )
    high_res_img = high_res_img.replace("http://", "https://") if high_res_img else (raw_thumb or "static/img/logo_jin_3d.png")
    fallback_thumb = raw_thumb if raw_thumb else high_res_img

    price = float(item.get("price") or 0)
    orig_price = item.get("original_price")
    discount_badge = ""
    if orig_price and float(orig_price) > price:
        pct = int(round(((float(orig_price) - price) / float(orig_price)) * 100))
        if pct > 0:
            discount_badge = f"-{pct}%"

    # Meses sin intereses (installments)
    inst_data = item.get("installments")
    installments_str = None
    if isinstance(inst_data, dict):
        qty = inst_data.get("quantity")
        amount = inst_data.get("amount")
        rate = inst_data.get("rate", 0)
        if qty and qty > 1:
            if rate == 0 and amount:
                installments_str = f"Hasta {qty}x ${float(amount):,.2f} sin intereses"
            else:
                installments_str = f"Hasta {qty} MSI"
    elif item.get("accepts_mercadopago"):
        installments_str = "Meses sin Intereses"

    detailed = classify_item_detailed(item)
    is_battery = is_battery_product(title) or ("battery" in detailed["cats"])
    date_created = item.get("date_created") or item.get("start_time") or ""
    last_updated = item.get("last_updated") or date_created or ""
    disc_pct = detailed["discount_pct"]
    if not discount_badge and detailed.get("has_promo_tag"):
        discount_badge = "OFERTA"

    return {
        "id": item.get("id", ""),
        "title": title,
        "category": detailed["category"],
        "brand": detailed["brand"],
        "condition": detailed["condition"],
        "cats": detailed["cats"],
        "subs": detailed["subs"],
        "price": price,
        "original_price": float(orig_price) if orig_price else None,
        "discount": discount_badge,
        "discount_pct": disc_pct,
        "available_quantity": avail_qty,
        "stock": "1 pieza" if avail_qty == 1 else f"{avail_qty} disp.",
        "is_last": avail_qty == 1,
        "is_battery": is_battery,
        "installments": installments_str,
        "image_url": high_res_img,
        "thumbnail_url": fallback_thumb,
        "permalink": item.get("permalink") or f"https://listado.mercadolibre.com.mx/_CustId_{MELI_SELLER_ID}",
        "description": "Publicación oficial en Mercado Libre México con garantía y envío protegido.",
        "date_created": date_created,
        "last_updated": last_updated
    }


def get_recent_products(products: List[Dict[str, Any]], is_local: bool = False, max_items: int = 5) -> List[Dict[str, Any]]:
    """
    Selecciona los 5 artículos más recientes obtenidos del catálogo en vivo de Mercado Libre
    ordenados por fecha de publicación más reciente.
    """
    eligible = [
        p for p in products
        if is_local or not (p.get("is_battery") or p.get("category") == "battery")
    ]
    if not eligible:
        eligible = list(products)

    has_timestamps = any(p.get("date_created") or p.get("last_updated") for p in eligible)
    if has_timestamps:
        eligible = sorted(
            eligible,
            key=lambda x: (x.get("date_created") or x.get("last_updated") or ""),
            reverse=True
        )

    return eligible[:max_items]


def build_recent_slider_html(recent_products: List[Dict[str, Any]], is_local: bool = False) -> str:
    """
    Construye los slides horizontales del Banner Carrusel de los 5 Artículos Más Recientes
    manteniendo la estética Y2K 3D Glossy de JIN.COM.MX.
    """
    slides_html: List[str] = []
    for idx, p in enumerate(recent_products[:5]):
        item_id = p.get("id", "")
        title = p.get("title", "Producto JIN.COM.MX")
        price = float(p.get("price", 0))
        original_price = p.get("original_price")
        discount = p.get("discount", "")
        is_last = bool(p.get("is_last"))
        installments = p.get("installments") or "Compra 100% Protegida"
        img_url = p.get("image_url") or "static/img/logo_jin_3d.png"
        thumb_url = p.get("thumbnail_url") or img_url
        permalink = p.get("permalink") or f"https://listado.mercadolibre.com.mx/_CustId_{MELI_SELLER_ID}"

        active_cls = "is-active" if idx == 0 else ""
        tag_label = "RECIÉN PUBLICADO" if idx % 2 == 0 else "NUEVO INGRESO"

        extra_badge = ""
        if is_last:
            extra_badge = '<span class="recent-slide-pill pill-alert">¡ÚLTIMA PIEZA!</span>'
        elif discount:
            extra_badge = f'<span class="recent-slide-pill pill-discount">{discount} OFF</span>'

        orig_html = ""
        if original_price and float(original_price) > price:
            orig_html = f'<span class="recent-orig-price">${float(original_price):,.2f} MXN</span>'

        wa_msg = quote(f"Hola JIN.COM.MX, vi en Nuevos Artículos el producto: {title} (Ref: {item_id}) de ${price:,.2f} MXN")

        slides_html.append(f"""
                        <div class="recent-slide {active_cls}" data-slide-index="{idx}">
                            <a href="{permalink}" target="_blank" rel="noopener noreferrer" class="recent-slide-media" title="Ver publicación en Mercado Libre">
                                <img src="{img_url}"
                                     data-fallback="{thumb_url}"
                                     alt="{title}"
                                     loading="lazy"
                                     onerror="if(this.dataset.fallback && this.src !== this.dataset.fallback){{this.src=this.dataset.fallback;}}else{{this.onerror=null;this.src='static/img/logo_jin_3d.png';}}">
                            </a>
                            <div class="recent-slide-content">
                                <div class="recent-slide-badges">
                                    <span class="recent-slide-pill pill-new">{tag_label}</span>
                                    {extra_badge}
                                    <span class="recent-slide-ref">REF: {item_id}</span>
                                </div>
                                <h3 class="recent-slide-title">
                                    <a href="{permalink}" target="_blank" rel="noopener noreferrer" class="recent-title-link">{title}</a>
                                </h3>
                                <div class="recent-slide-pricing">
                                    <div class="front-price recent-lcd-price">${price:,.2f} MXN</div>
                                    {orig_html}
                                    <span class="recent-slide-msi">{installments}</span>
                                </div>
                                <div class="recent-slide-actions">
                                    <a href="{permalink}" target="_blank" rel="noopener noreferrer" class="glass-btn ml-btn recent-cta-btn">
                                        Ver / Comprar en Mercado Libre
                                    </a>
                                    <a href="https://wa.me/{WHATSAPP_NUMBER}?text={wa_msg}" target="_blank" rel="noopener noreferrer" class="glass-btn wa-btn recent-cta-btn">
                                        Pedir por WhatsApp
                                    </a>
                                </div>
                            </div>
                        </div>""")

    return "\n".join(slides_html)


def fetch_mercadolibre_catalog(is_local: bool = False) -> Tuple[List[Dict[str, Any]], str]:
    """
    Obtiene los productos activos desde Mercado Libre usando:
    1) Caché en memoria diferenciada por "local" y "national" (TTL = 900s)
    2) Flujo OAuth2 paginado: /users/me -> /users/{user_id}/items/search?status=active (50 en 50)
       -> /items?ids={ids_str}&attributes={fields} (en bloques de 20 para cuidar la RAM en Render)
    3) Fallback a búsqueda pública o catálogo de respaldo si no hay token configurado.
    """
    cache_key = "local" if is_local else "national"
    now = time.time()

    cached_entry = CACHE_PRODUCTS[cache_key]
    if cached_entry["data"] is not None and (now - cached_entry["timestamp"] < CACHE_TTL_SECONDS):
        logger.info(f"Sirviendo catálogo '{cache_key}' desde caché en memoria.")
        return cached_entry["products"], cached_entry["data"]

    tokens = load_tokens()
    fetched_products: List[Dict[str, Any]] = []
    source_used = "fallback"

    # A. Flujo OAuth2 autenticado (/users/me -> /users/{user_id}/items/search -> /items?ids=...)
    if tokens and tokens.get("access_token"):
        access_token = tokens.get("access_token")
        refresh_token = tokens.get("refresh_token", "")
        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}

        try:
            me_res = requests.get("https://api.mercadolibre.com/users/me", headers=headers, timeout=8)
            if me_res.status_code in (401, 403) and refresh_token:
                new_access = refresh_access_token(refresh_token)
                if new_access:
                    access_token = new_access
                    headers["Authorization"] = f"Bearer {access_token}"
                    me_res = requests.get("https://api.mercadolibre.com/users/me", headers=headers, timeout=8)

            if me_res.status_code == 200:
                user_id = me_res.json().get("id", MELI_SELLER_ID)
                item_ids: List[str] = []
                offset = 0
                limit = 50

                while True:
                    search_url = (
                        f"https://api.mercadolibre.com/users/{user_id}/items/search"
                        f"?status=active&orders=start_time_desc&offset={offset}&limit={limit}"
                    )
                    s_res = requests.get(search_url, headers=headers, timeout=8)
                    if s_res.status_code != 200:
                        break

                    s_data = s_res.json()
                    batch_ids = s_data.get("results") or []
                    if not batch_ids:
                        break

                    item_ids.extend(batch_ids)
                    total = int(s_data.get("paging", {}).get("total", 0))
                    offset += limit
                    if offset >= total:
                        break

                # Consulta multiget /items?ids= en bloques de 20 (chunk_size = 20) para optimizar RAM
                chunk_size = 20
                fields = (
                    "id,title,condition,price,original_price,category_id,available_quantity,status,"
                    "permalink,thumbnail,pictures,installments,shipping,attributes,tags,deal_ids,"
                    "accepts_mercadopago,date_created,last_updated,start_time"
                )

                for i in range(0, len(item_ids), chunk_size):
                    chunk = item_ids[i:i + chunk_size]
                    ids_str = ",".join(chunk)
                    items_url = f"https://api.mercadolibre.com/items?ids={ids_str}&attributes={fields}"
                    items_res = requests.get(items_url, headers=headers, timeout=10)

                    if items_res.status_code == 200:
                        for wrapper in items_res.json():
                            if wrapper.get("code") == 200 and wrapper.get("body"):
                                norm = normalize_ml_item(wrapper["body"])
                                if norm:
                                    if norm["is_battery"] and not is_local:
                                        # En modo nacional se conserva marcado como battery para filtrado pero no se expone por defecto
                                        pass
                                    fetched_products.append(norm)

                if fetched_products:
                    source_used = "live_oauth"
                    logger.info(f"Sincronización OAuth2 exitosa: {len(fetched_products)} productos activos obtenidos.")
            else:
                logger.warning(f"No se pudo autenticar /users/me (status {me_res.status_code}).")
        except Exception as e:
            logger.error(f"Error en sincronización OAuth2 con Mercado Libre: {e}")

    # B. Intento de búsqueda pública si OAuth2 no devolvió resultados
    if not fetched_products:
        pub_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json"
        }
        if tokens and tokens.get("access_token"):
            pub_headers["Authorization"] = f"Bearer {tokens['access_token']}"

        try:
            pub_url = f"https://api.mercadolibre.com/sites/MLM/search?seller_id={MELI_SELLER_ID}"
            pub_res = requests.get(pub_url, headers=pub_headers, timeout=6)
            if pub_res.status_code == 200:
                for raw_item in pub_res.json().get("results", []):
                    raw_item.setdefault("status", "active")
                    raw_item.setdefault("available_quantity", 1)
                    norm = normalize_ml_item(raw_item)
                    if norm:
                        fetched_products.append(norm)
                if fetched_products:
                    source_used = "live_public"
        except Exception as e:
            logger.debug(f"Búsqueda pública ML no disponible: {e}")

    # C. Respaldo local garantizado si no hay conexión o tokens activos
    if not fetched_products:
        fetched_products = []
        for raw_fb in LOCAL_FALLBACK_PRODUCTS:
            p_copy = dict(raw_fb)
            detailed = classify_item_detailed(p_copy)
            p_copy.setdefault("cats", detailed["cats"])
            p_copy.setdefault("subs", detailed["subs"])
            p_copy.setdefault("condition", detailed["condition"])
            p_copy.setdefault("discount_pct", detailed["discount_pct"])
            fetched_products.append(p_copy)
        source_used = "fallback"

    # Construir el HTML de las tarjetas (filtrando baterías en vista nacional por defecto en el HTML renderizado)
    cards_html_list: List[str] = []
    for prod in fetched_products:
        cards_html_list.append(build_card_html(prod, is_local=is_local))

    cards_html = "\n".join(cards_html_list)

    # Guardar en caché por 15 minutos
    CACHE_PRODUCTS[cache_key] = {
        "data": cards_html,
        "products": fetched_products,
        "timestamp": now,
        "source": source_used
    }

    return fetched_products, cards_html


# ==============================================================================
# 5. ENDPOINTS PRINCIPALES, WEBHOOKS Y RUTAS ESPECIALES
# ==============================================================================
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """
    Ruta Principal: Detecta ubicación (is-local / is-national), sincroniza catálogo de Mercado Libre
    e inyecta los productos en <!-- PRODUCTOS_AQUI --> y la clase en <!-- BODY_CLASS --> manteniendo
    intacto el diseño 3D Y2K de index.html.
    """
    is_local = detect_client_is_local(request)
    body_class = "is-local" if is_local else "is-national"
    products, cards_html = fetch_mercadolibre_catalog(is_local=is_local)

    root_html_path = os.path.join(BASE_DIR, "index.html")
    template_html_path = os.path.join(TEMPLATES_DIR, "index.html")
    target_path = root_html_path if os.path.exists(root_html_path) else template_html_path

    if os.path.exists(target_path):
        with open(target_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        # Inyectar clase de geolocalización (is-local / is-national)
        html_content = html_content.replace(
            'class="is-national <!-- BODY_CLASS -->"',
            f'class="{body_class}"'
        ).replace(
            'class="{{ body_class or \'is-national\' }} <!-- BODY_CLASS -->"',
            f'class="{body_class}"'
        ).replace(
            "<!-- BODY_CLASS -->",
            body_class
        )

        # Inyectar slider de recientes en <!-- SLIDER_RECIENTES_AQUI -->
        recent_items = get_recent_products(products, is_local=is_local, max_items=5)
        recent_slider_html = build_recent_slider_html(recent_items, is_local=is_local)
        slider_start = "<!-- SLIDER_RECIENTES_AQUI -->"
        slider_end = "<!-- FIN_SLIDER_RECIENTES_AQUI -->"
        if slider_start in html_content and slider_end in html_content:
            s_before = html_content.split(slider_start)[0]
            s_after = html_content.split(slider_end)[1]
            html_content = f"{s_before}{slider_start}\n{recent_slider_html}\n{slider_end}{s_after}"
        elif slider_start in html_content:
            html_content = html_content.replace(slider_start, recent_slider_html)

        # Inyectar tarjetas en <!-- PRODUCTOS_AQUI -->
        start_marker = "<!-- PRODUCTOS_AQUI -->"
        end_marker = "<!-- FIN_PRODUCTOS_AQUI -->"
        if start_marker in html_content and end_marker in html_content:
            before = html_content.split(start_marker)[0]
            after = html_content.split(end_marker)[1]
            html_content = f"{before}{start_marker}\n{cards_html}\n{end_marker}{after}"
        elif start_marker in html_content:
            html_content = html_content.replace(start_marker, cards_html)

        return HTMLResponse(content=html_content, status_code=200)

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "seller_id": MELI_SELLER_ID,
            "body_class": body_class,
            "products": products,
            "recent_products": get_recent_products(products, is_local=is_local, max_items=5)
        }
    )


@app.get("/auth/mercadolibre")
@app.get("/login")
async def mercadolibre_auth_redirect():
    """
    Redirige al flujo de autorización OAuth2 de Mercado Libre México para conceder permisos
    con la cuenta oficial (jinfbventas@gmail.com).
    """
    auth_url = (
        f"https://auth.mercadolibre.com.mx/authorization"
        f"?response_type=code&client_id={CLIENT_ID}&redirect_uri={quote(REDIRECT_URI, safe='')}"
    )
    return RedirectResponse(url=auth_url, status_code=302)


@app.get("/webhook/mercadolibre")
async def mercadolibre_oauth_callback(code: Optional[str] = None):
    """
    Endpoint OAuth2 Redirect URI: Recibe el parámetro ?code=... de Mercado Libre,
    genera y guarda tokens.json e invalida la caché de productos.
    """
    if not code:
        return JSONResponse({
            "status": "active",
            "message": "Webhook OAuth2 de Mercado Libre activo en JIN.COM.MX.",
            "redirect_uri": REDIRECT_URI
        })

    token_url = "https://api.mercadolibre.com/oauth/token"
    payload = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "redirect_uri": REDIRECT_URI
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    try:
        res = requests.post(token_url, data=payload, headers=headers, timeout=10)
        if res.status_code == 200:
            token_data = res.json()
            save_tokens(token_data)
            invalidate_product_cache()
            return JSONResponse({
                "status": "success",
                "message": "Autorización exitosa. tokens.json generado y caché actualizada.",
                "user_id": token_data.get("user_id")
            })
        return JSONResponse(
            status_code=res.status_code,
            content={"status": "error", "detail": res.text}
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "detail": str(e)})


@app.post("/webhook/mercadolibre")
async def mercadolibre_webhook_notification(request: Request, background_tasks: BackgroundTasks):
    """
    Recibe notificaciones en tiempo real de Mercado Libre (cambios de stock, precio o publicaciones),
    invalida la caché en memoria y dispara en segundo plano (BackgroundTasks) la autopublicación
    hacia la página oficial de Facebook (facebook.com/jin.com.mx) si es un artículo nuevo/reactivado.
    """
    try:
        body = await request.json()
        logger.info(f"Notificación Webhook ML recibida: {body.get('topic')} - {body.get('resource')}")
    except Exception:
        body = {}

    invalidate_product_cache()
    if body:
        background_tasks.add_task(process_ml_webhook_facebook_autopost, body)

    return JSONResponse({"status": "received", "cache_cleared": True, "fb_autopost_queued": bool(body and FB_AUTO_POST_ENABLED)})


@app.get("/api/facebook-catalog.xml")
@app.get("/feed-facebook.xml")
async def facebook_catalog_xml_feed():
    """
    Feed XML RSS 2.0 en vivo compatible con el estándar de Meta Commerce Manager
    (xmlns:g="http://base.google.com/ns/1.0") para sincronizar automáticamente todo
    el inventario activo de Mercado Libre con la Tienda de Facebook e Instagram.
    """
    products, _ = fetch_mercadolibre_catalog(is_local=True)
    items_xml_list: List[str] = []

    for prod in products:
        item_id = str(prod.get("id") or "").strip()
        if not item_id:
            continue

        title = str(prod.get("title") or "Producto Oficial jin.com.mx").strip()
        cond_raw = str(prod.get("condition") or "new").lower().strip()
        condition = "used" if cond_raw == "used" else "new"
        cond_es = "Usado / Bazar" if condition == "used" else "Nuevo"

        avail_qty = int(prod.get("available_quantity", 1) or 0)
        availability = "in stock" if avail_qty > 0 else "out of stock"

        price = float(prod.get("price") or 0)
        price_formatted = f"{price:.2f} MXN"

        brand_raw = str(prod.get("brand") or "").strip()
        brand = brand_raw.upper() if brand_raw in ("lth", "dc", "ngk") else (brand_raw.title() if brand_raw else "JIN.COM.MX")

        base_desc = str(prod.get("description") or "Artículo disponible en el catálogo oficial de jin.com.mx.").strip()
        description = (
            f"{title}. Condición: {cond_es}. Marca: {brand}. "
            f"Disponibilidad inmediata en jin.com.mx ({avail_qty} disponibles). {base_desc}"
        )

        link = f"https://www.jin.com.mx/?q={quote(item_id)}"
        image_link = get_high_res_image_url(prod)

        items_xml_list.append(
            f"""    <item>
      <g:id>{html.escape(item_id)}</g:id>
      <g:title>{html.escape(title)}</g:title>
      <g:description>{html.escape(description)}</g:description>
      <g:availability>{availability}</g:availability>
      <g:condition>{condition}</g:condition>
      <g:price>{price_formatted}</g:price>
      <g:link>{html.escape(link)}</g:link>
      <g:image_link>{html.escape(image_link)}</g:image_link>
      <g:brand>{html.escape(brand)}</g:brand>
    </item>"""
        )

    items_xml = "\n".join(items_xml_list)
    rss_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">
  <channel>
    <title>Catálogo Oficial jin.com.mx</title>
    <link>https://www.jin.com.mx/</link>
    <description>Feed oficial en vivo sincronizado con Mercado Libre México para Meta Commerce Manager (facebook.com/jin.com.mx).</description>
{items_xml}
  </channel>
</rss>"""
    return Response(content=rss_xml, media_type="application/xml", status_code=200)


def _is_private_session_authenticated(request: Request) -> bool:
    """Valida si la petición cuenta con la cookie de sesión privada jin_private_session."""
    cookie_val = (request.cookies.get(PRIVATE_SESSION_COOKIE) or "").strip()
    if not cookie_val:
        return False
    return cookie_val in (PRIVATE_SESSION_TOKEN, "authenticated", "1", "true", PRIVATE_PANEL_PASSWORD)


@app.get("/privado", response_class=HTMLResponse)
async def private_panel_page(request: Request):
    """Panel privado (/privado) con tarjeta modular de Sincronización en Vivo con Facebook."""
    is_auth = _is_private_session_authenticated(request)
    products, _ = fetch_mercadolibre_catalog(is_local=True)
    posted_ids = load_posted_fb_items()

    context = {
        "request": request,
        "authenticated": is_auth,
        "error_msg": "",
        "seller_id": MELI_SELLER_ID,
        "product_count": len(products),
        "catalog_source": CACHE_PRODUCTS["local"].get("source", "cache"),
        "fb_auto_post_enabled": FB_AUTO_POST_ENABLED,
        "fb_credentials_configured": bool(FB_PAGE_ID and FB_PAGE_ACCESS_TOKEN),
        "posted_fb_count": len(posted_ids),
    }
    if templates and os.path.exists(os.path.join(TEMPLATES_DIR, "privado.html")):
        return templates.TemplateResponse("privado.html", context)
    return HTMLResponse(content="Panel privado disponible en templates/privado.html", status_code=200)


@app.post("/privado/login")
async def private_panel_login(request: Request):
    """Inicia sesión en /privado y establece la cookie jin_private_session."""
    password = ""
    try:
        form = await request.form()
        password = str(form.get("password") or "").strip()
    except Exception:
        try:
            data = await request.json()
            password = str(data.get("password") or "").strip()
        except Exception:
            password = ""

    if password == PRIVATE_PANEL_PASSWORD:
        resp = RedirectResponse(url="/privado", status_code=303)
        resp.set_cookie(
            key=PRIVATE_SESSION_COOKIE,
            value=PRIVATE_SESSION_TOKEN,
            httponly=True,
            max_age=86400 * 7,
            samesite="lax"
        )
        return resp

    products, _ = fetch_mercadolibre_catalog(is_local=True)
    context = {
        "request": request,
        "authenticated": False,
        "error_msg": "Contraseña incorrecta. Verifica PRIVATE_PANEL_PASSWORD.",
        "seller_id": MELI_SELLER_ID,
        "product_count": len(products),
        "catalog_source": CACHE_PRODUCTS["local"].get("source", "cache"),
        "fb_auto_post_enabled": FB_AUTO_POST_ENABLED,
        "fb_credentials_configured": bool(FB_PAGE_ID and FB_PAGE_ACCESS_TOKEN),
        "posted_fb_count": len(load_posted_fb_items()),
    }
    if templates and os.path.exists(os.path.join(TEMPLATES_DIR, "privado.html")):
        return templates.TemplateResponse("privado.html", context, status_code=401)
    return JSONResponse(status_code=401, content={"status": "error", "message": "No autorizado"})


@app.get("/privado/logout")
async def private_panel_logout():
    """Cierra la sesión privada eliminando la cookie jin_private_session."""
    resp = RedirectResponse(url="/privado", status_code=303)
    resp.delete_cookie(PRIVATE_SESSION_COOKIE)
    return resp


@app.post("/api/facebook/publish-latest", response_class=JSONResponse)
async def publish_latest_items_to_facebook(request: Request):
    """
    Endpoint protegido por la cookie jin_private_session que dispara manualmente la publicación
    en Facebook de los últimos N artículos activos (por defecto 1) desde el panel privado.
    """
    if not _is_private_session_authenticated(request):
        return JSONResponse(
            status_code=401,
            content={
                "status": "unauthorized",
                "ok": False,
                "message": "Sesión privada no válida. Inicia sesión en /privado para publicar en Facebook."
            }
        )

    limit = 1
    force = False
    try:
        if "application/json" in (request.headers.get("content-type") or "").lower():
            payload = await request.json()
            if isinstance(payload, dict):
                limit = int(payload.get("limit") or payload.get("n") or 1)
                force = bool(payload.get("force", False))
    except Exception:
        pass

    if request.query_params.get("limit"):
        try:
            limit = int(request.query_params["limit"])
        except ValueError:
            limit = 1
    limit = max(1, min(limit, 10))

    products, _ = fetch_mercadolibre_catalog(is_local=True)
    recent_items = get_recent_products(products, is_local=True, max_items=max(limit, 5))
    target_items = recent_items[:limit]

    if not target_items:
        return JSONResponse(
            status_code=404,
            content={
                "status": "no_products",
                "ok": False,
                "message": "No se encontraron artículos activos en el catálogo para publicar."
            }
        )

    results: List[Dict[str, Any]] = []
    for item in target_items:
        res = await publish_item_to_facebook(item, force=force)
        results.append(res)

    first = results[0]
    any_ok = any(r.get("ok") for r in results)
    return JSONResponse(
        status_code=200,
        content={
            "status": first.get("status", "processed"),
            "ok": any_ok,
            "count": len(results),
            "item_id": first.get("item_id"),
            "title": first.get("title"),
            "fb_post_id": first.get("fb_post_id"),
            "caption_preview": first.get("caption_preview"),
            "message": first.get("message"),
            "results": results
        }
    )


@app.get("/api/productos-ml", response_class=JSONResponse)
@app.get("/api/products", response_class=JSONResponse)
async def get_products_api(request: Request):
    """
    API JSON para hidratación asíncrona de catalog.js.
    """
    is_local = detect_client_is_local(request)
    cache_key = "local" if is_local else "national"
    products, _ = fetch_mercadolibre_catalog(is_local=is_local)
    recent_products = get_recent_products(products, is_local=is_local, max_items=5)
    return {
        "status": "success",
        "source": CACHE_PRODUCTS[cache_key].get("source", "cache"),
        "body_class": "is-local" if is_local else "is-national",
        "is_local": is_local,
        "seller_id": MELI_SELLER_ID,
        "count": len(products),
        "products": products,
        "recent_products": recent_products
    }


@app.get("/acumuladores", response_class=HTMLResponse)
async def acumuladores_page():
    """
    Vista especializada de Acumuladores / Baterías LTH sincronizada con GOOGLE_SHEET_CSV_URL
    y respaldo automático.
    """
    rows_html = ""
    batteries: List[Dict[str, str]] = []

    try:
        res = requests.get(GOOGLE_SHEET_CSV_URL, timeout=6)
        if res.status_code == 200 and "text/csv" in res.headers.get("content-type", "text/csv"):
            reader = csv.DictReader(io.StringIO(res.text))
            for row in reader:
                modelo = row.get("Modelo") or row.get("MODELO") or row.get("Codigo") or ""
                marca = row.get("Marca") or row.get("MARCA") or "LTH"
                precio = row.get("Precio") or row.get("PRECIO") or "2150.00"
                garantia = row.get("Garantia") or row.get("GARANTIA") or "48 Meses"
                cca = row.get("CCA") or row.get("Amperaje") or "500 CCA"
                if modelo:
                    batteries.append({
                        "modelo": modelo,
                        "marca": marca,
                        "precio": precio,
                        "garantia": garantia,
                        "cca": cca
                    })
    except Exception as e:
        logger.debug(f"Usando catálogo base para /acumuladores ({e})")

    if not batteries:
        batteries = [
            {"modelo": "L-42-500", "marca": "LTH", "precio": "2,150.00", "garantia": "48 Meses", "cca": "500 CCA"},
            {"modelo": "L-47-600", "marca": "LTH", "precio": "2,490.00", "garantia": "48 Meses", "cca": "600 CCA"},
            {"modelo": "L-58-575", "marca": "LTH", "precio": "2,380.00", "garantia": "48 Meses", "cca": "575 CCA"},
            {"modelo": "L-65-650", "marca": "LTH", "precio": "2,890.00", "garantia": "48 Meses", "cca": "650 CCA"},
        ]

    for b in batteries:
        wa_link = f"https://wa.me/{WHATSAPP_NUMBER}?text=" + quote(
            f"Hola JIN.COM.MX, solicito cotización e instalación del acumulador {b['marca']} {b['modelo']} (${b['precio']} MXN)"
        )
        rows_html += f"""
        <div class="product-card flip-card" style="aspect-ratio: 0.72;">
            <div class="flip-card-inner">
                <div class="flip-card-front">
                    <span class="stock-badge">Local Arbide</span>
                    <span class="discount-badge">{b['garantia']}</span>
                    <div class="card-image-area">
                        <img src="static/img/acumuladores.png" alt="{b['marca']} {b['modelo']}">
                    </div>
                    <div class="card-info-area">
                        <h3 class="card-title">Acumulador {b['marca']} {b['modelo']}</h3>
                        <div class="ref-id">Potencia: {b['cca']}</div>
                        <div class="front-price">${b['precio']} MXN</div>
                        <div class="installments">Entrega e Instalación Local</div>
                        <div class="tap-hint">👆 Toca para pedir</div>
                    </div>
                </div>
                <div class="flip-card-back">
                    <div class="back-content">
                        <img src="static/img/logo_jin_3d.png" alt="JIN.COM.MX" class="back-logo-img">
                        <h4 class="back-title">{b['marca']} {b['modelo']}</h4>
                        <div class="back-price">${b['precio']} MXN</div>
                        <p style="font-size: 11px; color: #555; font-weight: 600;">Precio con entrega en Zona Arbide (León, Gto). Garantía oficial {b['garantia']}.</p>
                        <div class="action-buttons-group">
                            <a href="{wa_link}" target="_blank" rel="noopener" class="glass-btn wa-btn">
                                💬 Cotizar por WhatsApp
                            </a>
                            <button class="return-btn" type="button">Volver al frente ↩</button>
                        </div>
                    </div>
                </div>
            </div>
        </div>"""

    html_page = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Acumuladores LTH | JIN.COM.MX</title>
    <link rel="icon" href="static/img/favicon.png" type="image/png">
    <link rel="stylesheet" href="static/css/style.css">
</head>
<body class="is-local">
    <header class="header-wrapper">
        <div class="header-top">
            <a href="/" class="header-brand">
                <img src="static/img/logo_jin_3d.png" alt="JIN.COM.MX Logo" class="brand-icon">
                <span class="brand-text">jin<span class="rgb-split-text">.com.mx</span></span>
            </a>
            <div class="header-actions">
                <a href="/" class="header-cta-btn">⬅ Volver al Catálogo Principal</a>
            </div>
        </div>
    </header>
    <main class="catalog-section" style="margin-top: 30px;">
        <div class="catalog-header-bar">
            <div class="catalog-title-group">
                <h2>Baterías para Auto <span class="rgb-split-text">LTH</span></h2>
                <p>Entrega e instalación en Zona Arbide (León, Guanajuato)</p>
            </div>
        </div>
        <div class="gallery">
            {rows_html}
        </div>
    </main>
    <script src="static/js/background3d.js"></script>
    <script src="static/js/catalog.js"></script>
</body>
</html>"""
    return HTMLResponse(content=html_page, status_code=200)


@app.post("/api/contact", response_class=JSONResponse)
async def send_corporate_contact_email(request: Request):
    """
    Recibe mensajes dirigidos a ale@jin.com.mx o contacto@jin.com.mx (vía JSON o Form)
    y los envía mediante SMTP_SSL de Gmail hacia casillas.alejo@gmail.com con Reply-To al cliente.
    """
    content_type = (request.headers.get("content-type") or "").lower()
    payload: Dict[str, Any] = {}

    try:
        if "application/json" in content_type:
            payload = await request.json()
        else:
            form_data = await request.form()
            payload = dict(form_data)
    except Exception:
        try:
            payload = await request.json()
        except Exception:
            payload = {}

    nombre = str(payload.get("nombre") or "").strip()
    email_cliente = str(payload.get("email_cliente") or "").strip()
    destinatario_raw = str(payload.get("destinatario") or "contacto@jin.com.mx").strip().lower()
    asunto = str(payload.get("asunto") or "Consulta desde JIN.COM.MX").strip()
    mensaje = str(payload.get("mensaje") or "").strip()

    allowed_recipients = ("ale@jin.com.mx", "contacto@jin.com.mx")
    destinatario = destinatario_raw if destinatario_raw in allowed_recipients else "contacto@jin.com.mx"

    if not nombre or not email_cliente or not mensaje:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "ok": False,
                "message": "Por favor completa tu nombre, correo electrónico y mensaje."
            }
        )

    gmail_user = os.environ.get("GMAIL_USER", "casillas.alejo@gmail.com").strip()
    gmail_app_password = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    target_inbox = "casillas.alejo@gmail.com"

    if not gmail_app_password:
        logger.warning("Intento de envío en /api/contact sin GMAIL_APP_PASSWORD configurado en variables de entorno.")
        return JSONResponse(
            status_code=200,
            content={
                "status": "missing_config",
                "ok": False,
                "destinatario": destinatario,
                "message": (
                    "Falta configurar la variable de entorno GMAIL_APP_PASSWORD en Render para el envío SMTP automático. "
                    f"Puedes escribir directamente a {destinatario}."
                )
            }
        )

    dept_label = (
        "Atención Directa / Cotizaciones Especiales (ale@jin.com.mx)"
        if destinatario == "ale@jin.com.mx"
        else "Atención General y Ventas (contacto@jin.com.mx)"
    )

    msg = EmailMessage()
    msg["From"] = f"JIN.COM.MX Web <{gmail_user}>"
    msg["To"] = target_inbox
    msg["Reply-To"] = email_cliente
    msg["Subject"] = f"[JIN.COM.MX -> {destinatario}] {asunto} - de {nombre}"

    email_body = (
        f"Nuevo mensaje recibido desde el formulario oficial de JIN.COM.MX\n"
        f"{'=' * 64}\n"
        f"• Dirigido a: {destinatario} ({dept_label})\n"
        f"• Nombre del cliente: {nombre}\n"
        f"• Correo del cliente (Reply-To): {email_cliente}\n"
        f"• Asunto: {asunto}\n"
        f"{'=' * 64}\n\n"
        f"Mensaje:\n{mensaje}\n\n"
        f"{'-' * 64}\n"
        f"Tip: Al presionar 'Responder' en Gmail, contestarás directamente a {email_cliente}."
    )
    msg.set_content(email_body)

    def _send_smtp() -> None:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=12) as server:
            server.login(gmail_user, gmail_app_password)
            server.send_message(msg)

    try:
        await asyncio.to_thread(_send_smtp)
        logger.info(f"Correo enviado con éxito desde /api/contact hacia {target_inbox} (destinatario: {destinatario})")
        return JSONResponse(
            status_code=200,
            content={
                "status": "sent",
                "ok": True,
                "destinatario": destinatario,
                "message": f"¡Mensaje enviado con éxito a {destinatario}! Te responderemos a {email_cliente} a la brevedad."
            }
        )
    except Exception as e:
        logger.error(f"Error SMTP al enviar correo desde /api/contact: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "smtp_error",
                "ok": False,
                "destinatario": destinatario,
                "message": f"No se pudo enviar el correo vía SMTP ({str(e)}). Por favor contáctanos en {destinatario}."
            }
        )


@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt():
    """Archivo robots.txt para motores de búsqueda y rastreadores de Meta Commerce Manager."""
    content = (
        "User-agent: *\n"
        "Allow: /\n"
        "Allow: /api/facebook-catalog.xml\n"
        "Allow: /feed-facebook.xml\n"
        "Disallow: /auth/\n"
        "Disallow: /webhook/\n"
        "Disallow: /privado\n"
        "Disallow: /api/\n"
        "Sitemap: https://www.jin.com.mx/sitemap.xml\n"
    )
    return PlainTextResponse(content=content, status_code=200)


@app.get("/sitemap.xml")
async def sitemap_xml():
    """Mapa del sitio XML oficial para indexación SEO."""
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://www.jin.com.mx/</loc>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>"""
    return Response(content=xml_content, media_type="application/xml", status_code=200)


@app.get("/health", response_class=JSONResponse)
@app.get("/ping", response_class=JSONResponse)
@app.get("/healthz", response_class=JSONResponse)
async def health_check():
    """
    Endpoint ultraligero de salud (/health, /ping, /healthz) para monitores externos y Keep-Alive.
    Responde inmediatamente HTTP 200 sin consultar Mercado Libre ni procesar plantillas HTML.
    """
    return {"status": "ok", "service": "jin.com.mx"}


@app.get("/logo_cabecera_jinfbventas.png")
@app.get("/static/images/logo_cabecera_jinfbventas.png")
async def legacy_logo():
    logo_path = os.path.join(STATIC_DIR, "img", "logo_jin_3d.png")
    if os.path.exists(logo_path):
        return FileResponse(logo_path, media_type="image/png")
    return RedirectResponse(url="/static/img/logo_jin_3d.png")


@app.get("/favicon.ico")
async def favicon():
    favicon_path = os.path.join(STATIC_DIR, "img", "favicon.png")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path, media_type="image/png")
    return RedirectResponse(url="/static/img/favicon.png")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
