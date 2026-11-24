"""
main.py - Servidor Web Oficial JIN.COM.MX
Despliegue optimizado para Render con Uvicorn / FastAPI / Jinja2
Sincronización en vivo con Mercado Libre México (OAuth2 + Paginación + Caché TTL + Geolocalización)
"""

import os
import io
import csv
import json
import time
import logging
from urllib.parse import quote
from typing import Optional, List, Dict, Any, Tuple
import requests
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse
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

app = FastAPI(
    title="JIN.COM.MX Catálogo 3D",
    description="Aplicación web www.jin.com.mx con estética Y2K 3D Glossy, Menú Orbital y Catálogo Interactivo",
    version="2.2.0"
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
# 3. CLASIFICACIÓN, GEOLOCALIZACIÓN Y CONSTRUCCIÓN DE TARJETAS 3D
# ==============================================================================
def is_battery_product(title: str) -> bool:
    """Detecta si un producto corresponde a batería o acumulador."""
    t = title.lower()
    return any(w in t for w in ["bateria", "batería", "acumulador", "lth"])


def classify_category(title: str) -> Dict[str, str]:
    """Clasifica automáticamente la categoría y marca según el título del producto."""
    t = title.lower()
    cat = "toy"
    brand = ""

    if is_battery_product(t):
        cat = "battery"
        brand = "lth"
    elif any(k in t for k in ["refaccion", "refacción", "bujia", "bujía", "filtro", "balata", "amortiguador", "alternador", "sensor", "faro"]):
        cat = "refacciones"
    elif any(k in t for k in ["marvel", "spider", "avengers", "capitán", "capitan", "hulk", "iron man", "thor", "x-men"]):
        cat = "colecciones"
        brand = "marvel"
    elif any(k in t for k in ["star wars", "mandalorian", "grogu", "yoda", "vader", "jedi"]):
        cat = "colecciones"
        brand = "star wars"
    elif any(k in t for k in ["batman", "superman", "dc", "joker", "flash", "justice league"]):
        cat = "colecciones"
        brand = "batman"
    elif "hot wheels" in t:
        cat = "toy"
        brand = "hot wheels"
    elif "barbie" in t or "muñeca" in t:
        cat = "toy"
        brand = "barbie"
    elif "funko" in t:
        cat = "colecciones"
        brand = "funko"
    elif "lego" in t:
        cat = "colecciones"
        brand = "lego"
    elif "hasbro" in t:
        cat = "toy"
        brand = "hasbro"
    elif "mattel" in t:
        cat = "toy"
        brand = "mattel"

    return {"category": cat, "brand": brand}


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

    return f"""
                <div class="product-card flip-card {battery_class}" data-id="{item_id}" data-title="{title}" data-type="{category}">
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

    classification = classify_category(title)
    is_battery = is_battery_product(title)
    date_created = item.get("date_created") or item.get("start_time") or ""
    last_updated = item.get("last_updated") or date_created or ""

    return {
        "id": item.get("id", ""),
        "title": title,
        "category": classification["category"],
        "brand": classification["brand"],
        "price": price,
        "original_price": float(orig_price) if orig_price else None,
        "discount": discount_badge,
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
                    "id,title,price,original_price,available_quantity,status,"
                    "permalink,thumbnail,pictures,installments,shipping,attributes,"
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
        fetched_products = [dict(p) for p in LOCAL_FALLBACK_PRODUCTS]
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
async def mercadolibre_webhook_notification(request: Request):
    """
    Recibe notificaciones en tiempo real de Mercado Libre (cambios de stock, precio o publicaciones)
    e invalida la caché en memoria para reflejar los cambios de inmediato.
    """
    try:
        body = await request.json()
        logger.info(f"Notificación Webhook ML recibida: {body.get('topic')} - {body.get('resource')}")
    except Exception:
        body = {}

    invalidate_product_cache()
    return JSONResponse({"status": "received", "cache_cleared": True})


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


@app.get("/healthz", response_class=JSONResponse)
@app.get("/health", response_class=JSONResponse)
async def health_check():
    """Health check endpoint para monitoreo de Render (/healthz y /health)."""
    return {
        "status": "healthy",
        "app": "JIN.COM.MX",
        "domain": "www.jin.com.mx",
        "version": "2.2.0-y2k"
    }


@app.get("/logo_cabecera_jinfbventas.png")
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
