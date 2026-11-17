# CONTEXTO DEL PROYECTO: JIN.COM.MX (Remasterización Y2K / 3D Glossy)

Este documento define la arquitectura técnica, identidad visual, reglas de interacción y lógica de integración en vivo de **JIN.COM.MX**. Debe consultarse antes de realizar cualquier modificación en el repositorio.

---

## 1. Arquitectura Actual y Estructura de Directorios

El proyecto opera bajo un **modelo híbrido dual**: permite previsualización estática directa en local y ejecución dinámica completa en la nube (Render) mediante **FastAPI / Uvicorn**.

### Árbol de Directorios
```text
jin.com.mx/
├── main.py                  # Backend FastAPI (endpoints de catálogo, caché ML y servidor de estáticos/templates)
├── Procfile                 # Comando de arranque en producción (web: uvicorn main:app --host 0.0.0.0 --port $PORT)
├── render.yaml              # Configuración de infraestructura como código para despliegue automático en Render
├── requirements.txt         # Dependencias Python (fastapi, uvicorn, httpx/requests, jinja2, etc.)
├── abrir_web_local.bat      # Script de lanzamiento rápido en Windows
├── CONTEXTO_PROYECTO.md     # Este documento de referencia
├── static/
│   ├── css/                 # Hojas de estilo Y2K, variables HEX, Glassmorphism y animaciones 3D
│   ├── js/
│   │   ├── orbital.js       # Cálculo de órbita elíptica, giroscopio reactivo al mouse y responsividad
│   │   └── catalog.js       # Hidratación asíncrona de productos, buscador en vivo, slider de escala y card-flip 3D
│   └── img/
│       └── logo_jin_3d.png  # Logotipo oficial 3D optimizado para rutas web/Linux (copia limpia de ᒎᎥᑎ孩子 _ jin.png)
├── templates/
│   └── index.html           # Plantilla principal en UTF-8 sin BOM
└── images/                  # Recursos gráficos y respaldos locales del catálogo