#!/usr/bin/env python3
"""
Scraper de Maxiconsumo para Índice LCV.

Maxiconsumo corre en Magento. El catálogo se ve público (sin login),
navegable por categoría, con precio "por bulto cerrado" (mayorista) y
"unitario" (individual) mostrados juntos en cada ficha de producto.

IMPORTANTE - cosas a verificar/ajustar antes de correr en serio:
  1. STORE_SLUG: confirmá que "sucursal_trelew" responde 200 con:
       curl -s -o /dev/null -w "%{http_code}\n" https://www.maxiconsumo.com/sucursal_trelew/ofertas
     Si no, mirá el selector de sucursal en la web (Network tab) para
     sacar el slug real.
  2. Los selectores CSS de abajo son la estructura típica de Magento 2
     (product-item / product-item-link / price-box), pero Maxiconsumo
     puede tener el theme customizado. Corré scrape_category() contra
     UNA categoría chica primero y revisá con print(soup.prettify())
     si no trae nada, antes de lanzar la corrida completa.
  3. No pude probar esto contra el sitio real desde acá (mi sandbox no
     tiene salida de red a maxiconsumo.com). Este script es la
     estructura y lógica; el ajuste fino de selectores lo hacés vos
     con el sitio real delante.
"""

import csv
import json
import os
import sys
import time
import random
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# --------------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------------

STORE_SLUG = "sucursal_trelew"          # <-- confirmar/ajustar
BASE_URL = f"https://www.maxiconsumo.com/{STORE_SLUG}/"
SITEMAP_URL = "https://www.maxiconsumo.com/sitemap.xml"  # fallback para descubrir categorías

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "es-AR,es;q=0.9",
}

REQUEST_DELAY_RANGE = (1.0, 2.5)  # segundos entre requests, para no reventar el sitio
REQUEST_TIMEOUT = 45  # segundos - las categorías grandes (Almacén, Bebidas) tardan más en renderizar
MAX_REINTENTOS = 3
PRODUCTS_PER_PAGE_PARAM = "product_list_limit"
PRODUCTS_PER_PAGE = 96  # Magento suele soportar 12/24/36/48/96

# Credenciales de cuenta - NUNCA hardcodear acá. Se leen de variables de entorno:
#   export MAXICONSUMO_USER="tu_email@ejemplo.com"
#   export MAXICONSUMO_PASS="tu_contraseña"
LOGIN_URL = urljoin(BASE_URL, "customer/account/login/")
LOGIN_POST_URL = urljoin(BASE_URL, "customer/account/loginPost/")

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("maxiconsumo")

# Categorías raíz conocidas por la nav pública (fallback si no usás sitemap)
CATEGORIAS_RAIZ = [
    "almacen.html",
    "bebidas.html",
    "frescos.html",
    "congelados.html",
    "limpieza.html",
]
# Categorías excluidas a propósito (no relevantes para comparar gasto
# familiar de comida/limpieza del hogar): perfumeria.html, mascotas.html,
# hogar-y-bazar.html, electro.html. Si en algún momento hace falta
# sumarlas, es solo agregarlas de nuevo a la lista de arriba.


@dataclass
class Producto:
    tienda: str = "maxiconsumo"
    sucursal: str = STORE_SLUG
    sku: str = ""
    nombre: str = ""
    categoria_url: str = ""
    en_stock: Optional[bool] = None
    # Texto literal tal como aparece en el sitio (ej. "En stock",
    # "Disponibilidad crítica"). Util porque "Disponibilidad crítica"
    # es un estado intermedio (ni confirmado en stock ni confirmado sin
    # stock) donde Maxiconsumo directamente NO PUBLICA precio - saber
    # esto explica por qué precio_bulto_cerrado/precio_unitario pueden
    # venir vacíos sin que sea un error de parseo.
    estado_stock: str = ""
    # "Precio unitario por bulto cerrado" - precio final mostrado (puede incluir descuento)
    precio_bulto_cerrado: Optional[float] = None
    # Si el bulto tiene descuento, el precio de lista tachado aparece acá; si no hay
    # descuento, queda en None y precio_bulto_cerrado es el único precio de bulto.
    precio_bulto_cerrado_lista: Optional[float] = None
    # "Precio unitario" - precio de la unidad individual (no el bulto)
    precio_unitario: Optional[float] = None
    # Opciones de presentación que ofrece el producto, ej. [1, 8] o [1, 12, 18].
    # PENDIENTE: este dato NO está en el HTML como texto plano, viene de un
    # bloque JSON embebido en un <script> que arma el widget de "swatches"
    # con JS (confirmado inspeccionando debug_categoria.html). Parsearlo
    # bien requeriría cruzar ese JSON con el producto de la tarjeta - se
    # deja afuera por ahora, el precio ya capturado (bulto/unitario) es el
    # dato esencial y sigue siendo válido sin esto.
    presentaciones: list = None
    url_producto: str = ""
    fecha_scrape: str = ""


def get_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def login(session: requests.Session, username: str, password: str) -> bool:
    """
    Login estilo Magento 2: GET a la página de login para sacar el form_key
    (token anti-CSRF que Magento exige en el POST), después POST con
    usuario/contraseña + ese token.

    OJO: los nombres exactos de los campos del form (login[username],
    login[password], form_key) son los estándar de Magento 2, pero
    Maxiconsumo puede tener el formulario customizado. Si el login falla,
    lo primero es abrir las devtools del navegador (pestaña Network),
    loguearte a mano, mirar el POST real que se manda y ajustar
    `payload` acá abajo con los nombres de campo que veas ahí.
    """
    try:
        r = session.get(LOGIN_URL, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
    except requests.RequestException as e:
        log.error("No se pudo cargar la página de login: %s", e)
        return False

    soup = BeautifulSoup(r.text, "html.parser")
    form_key_input = soup.select_one('input[name="form_key"]')
    if not form_key_input:
        log.error(
            "No encontré el input form_key en la página de login. "
            "Puede que el HTML sea distinto al Magento 2 estándar - "
            "revisá manualmente con devtools."
        )
        return False
    form_key = form_key_input.get("value", "")

    payload = {
        "form_key": form_key,
        "login[username]": username,
        "login[password]": password,
    }

    try:
        r = session.post(LOGIN_POST_URL, data=payload, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        r.raise_for_status()
    except requests.RequestException as e:
        log.error("Error en el POST de login: %s", e)
        return False

    # Chequeo básico de éxito: buscamos algo que solo aparece logueado
    # (típicamente un link de "Cerrar sesión" / "Mi cuenta" / "Logout").
    texto = r.text.lower()
    logueado = any(
        marcador in texto
        for marcador in ("cerrar sesión", "logout", "mi cuenta", "customer-name")
    )

    if logueado:
        log.info("Login OK como %s", username)
    else:
        log.warning(
            "El login no dio error HTTP pero no encontré señales claras de "
            "sesión iniciada en la respuesta. Verificá a mano si funcionó "
            "(por ejemplo pidiendo una página de categoría y viendo si el "
            "precio cambió respecto a la versión sin loguear)."
        )

    return logueado


def sleep_politely():
    time.sleep(random.uniform(*REQUEST_DELAY_RANGE))


def parse_precio_ar(texto: str) -> Optional[float]:
    """Convierte '$ 1.949,90' -> 1949.90"""
    if not texto:
        return None
    limpio = (
        texto.replace("$", "")
        .replace(".", "")
        .replace(",", ".")
        .strip()
    )
    try:
        return float(limpio)
    except ValueError:
        return None


def descubrir_categorias_via_sitemap(session: requests.Session) -> list[str]:
    """
    Intenta sacar URLs de categoría del sitemap.xml. Más robusto y completo
    que mantener a mano la lista de categorías/subcategorías del menú.
    Devuelve URLs completas (no relativas).
    """
    try:
        r = session.get(SITEMAP_URL, timeout=15)
        r.raise_for_status()
    except requests.RequestException as e:
        log.warning("No se pudo bajar sitemap.xml (%s). Uso lista de categorías fija.", e)
        return []

    soup = BeautifulSoup(r.content, "xml")
    urls = [loc.text for loc in soup.find_all("loc")]
    # Filtramos: nos interesan páginas de categoría (terminan en .html y NO son
    # fichas de producto individuales; en Magento las fichas suelen tener
    # patrón distinto, pero esto hay que afinarlo mirando el sitemap real).
    categorias = [u for u in urls if u.endswith(".html") and "/sucursal_" not in u]
    log.info("Sitemap: %d URLs candidatas a categoría encontradas", len(categorias))
    return categorias


def fetch_pagina_categoria(session: requests.Session, category_url: str, pagina: int) -> tuple[list["Producto"], bool]:
    """
    Pide UNA sola página de una categoría (sin recorrer todas las
    páginas siguientes) y devuelve los productos de esa página.

    Devuelve (productos, ok):
    - ok=True: la página respondió bien (haya o no productos - una
      página vacía más allá del final del catálogo también es "ok",
      simplemente no tiene productos).
    - ok=False: se agotaron los reintentos por error de red.

    Usada por scrape_category() (que la llama en loop para traer todas
    las páginas) y por chequear_muestra_paginas() en main_actualizar.py
    (que solo pide 1-2 páginas puntuales como muestra rápida, sin
    recorrer la categoría entera).
    """
    sep = "&" if "?" in category_url else "?"
    url = f"{category_url}{sep}p={pagina}&{PRODUCTS_PER_PAGE_PARAM}={PRODUCTS_PER_PAGE}"

    r = None
    for intento in range(1, MAX_REINTENTOS + 1):
        try:
            r = session.get(url, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            break
        except requests.RequestException as e:
            if intento < MAX_REINTENTOS:
                espera = 5 * intento
                log.warning(
                    "Intento %d/%d falló para %s (%s) - reintentando en %ds",
                    intento, MAX_REINTENTOS, url, e, espera,
                )
                time.sleep(espera)
            else:
                log.error("Se agotaron los %d reintentos para %s: %s", MAX_REINTENTOS, url, e)

    if r is None:
        return [], False

    soup = BeautifulSoup(r.text, "html.parser")
    items = soup.select("li.item.product.product-item, li.product-item")
    productos = [_parse_producto(item, category_url) for item in items]
    return productos, True


def scrape_category(session: requests.Session, category_url: str) -> tuple[list[Producto], bool]:
    """
    Scrapea una categoría completa, paginando hasta que no haya más productos.

    Devuelve (productos, completo):
    - completo=True: la categoría se recorrió hasta el final con normalidad
      (la última página trajo menos productos que el límite pedido, señal
      natural de fin de catálogo).
    - completo=False: se cortó ANTES de tiempo por un error de red que
      agotó los reintentos. Los productos ya juntados hasta ese punto SÍ
      se devuelven (no se pierden), pero la categoría quedó INCOMPLETA -
      hay que volver a correrla.
    """
    productos: list[Producto] = []
    page = 1
    completo = True

    while True:
        productos_pagina, ok = fetch_pagina_categoria(session, category_url, page)

        if not ok:
            completo = False  # se cortó por error de red, NO por fin natural
            break

        if not productos_pagina:
            # No hay más productos -> fin de la paginación (o selector mal)
            if page == 1:
                log.warning(
                    "0 productos en la primera página de %s. "
                    "Revisá el selector CSS contra el HTML real.",
                    category_url,
                )
            break

        productos.extend(productos_pagina)
        log.info("Categoría %s - página %d: %d productos", category_url, page, len(productos_pagina))

        # Si trajo menos que el límite pedido, asumimos que es la última página
        if len(productos_pagina) < PRODUCTS_PER_PAGE:
            break

        page += 1
        sleep_politely()

    return productos, completo


def _parse_producto(item, category_url: str) -> Producto:
    """
    Extracción basada en TEXTO de las etiquetas confirmadas contra el sitio
    real (ver captura de pantalla de referencia):
        SKU <numero>
        Precio unitario por bulto cerrado:
        $ X.XXX,XX
        Precio unitario:
        $ X.XXX,XX
        PRESENTACIÓN
        1  8   (o 1 12, 1 18, etc. - varía por producto)

    Se usa item.stripped_strings (lista ordenada de textos limpios, en el
    orden en que aparecen en el HTML) en vez de selectores CSS, porque no
    conocemos los nombres de clase exactos del theme y el texto es estable.
    """
    p = Producto(categoria_url=category_url, fecha_scrape=datetime.now().isoformat())
    p.presentaciones = []

    # Nombre + URL del producto. OJO: el primer <a> de la tarjeta suele ser
    # el que envuelve la IMAGEN (sin texto) - hay que recorrer todos los
    # <a> y quedarnos con el primero que tenga texto real.
    p.nombre = ""
    for a in item.select("a[href]"):
        texto_link = a.get_text(strip=True)
        if texto_link:
            p.nombre = texto_link
            href = a.get("href", "")
            if href and ".html" in href:
                p.url_producto = href
            break

    # SKU vía atributo data-product-sku (confirmado que existe en el diagnóstico)
    sku_el = item.select_one("[data-product-sku]")
    if sku_el:
        p.sku = sku_el.get("data-product-sku", "")

    strings = list(item.stripped_strings)

    for i, texto in enumerate(strings):
        low = texto.lower()

        if low == "en stock":
            p.en_stock = True
            p.estado_stock = "En stock"
        elif low in ("sin stock", "agotado"):
            p.en_stock = False
            p.estado_stock = texto  # guardamos tal cual apareció (mayúsculas originales)
        elif "disponibilidad critica" in low or "disponibilidad crítica" in low:
            # Ni confirmado en stock ni confirmado sin stock - estado
            # intermedio donde Maxiconsumo no publica precio (confirmado
            # a mano contra 3 productos reales de este tipo).
            p.en_stock = None
            p.estado_stock = texto

        # SKU como fallback si el atributo data-product-sku no estaba
        if not p.sku and low == "sku" and i + 1 < len(strings):
            p.sku = strings[i + 1].strip()

        # "Precio unitario por bulto cerrado:" seguido del precio en el
        # siguiente string. Puede venir con o sin ":" al final según el HTML.
        if "precio unitario por bulto cerrado" in low:
            precio = _siguiente_precio(strings, i + 1)
            if precio is not None:
                p.precio_bulto_cerrado = precio

        # "Precio unitario:" a secas (sin "por bulto cerrado") es el precio
        # individual. Ojo: NO debe matchear la línea anterior, por eso
        # chequeamos que "bulto" no esté en este texto puntual.
        elif low.startswith("precio unitario") and "bulto" not in low:
            precio = _siguiente_precio(strings, i + 1)
            if precio is not None:
                p.precio_unitario = precio

    # --- FALLBACK ---
    # Si el parseo por etiqueta de texto no logró completar alguno (o
    # los dos) de los precios, probamos algo más tosco pero efectivo:
    # buscamos TODOS los números con forma de precio en toda la tarjeta.
    # Si encontramos exactamente 2 valores distintos, asumimos que el
    # MAYOR es el precio unitario (comprando de a 1) y el MENOR es el
    # precio por bulto cerrado - esto vale porque en Maxiconsumo el
    # bulto SIEMPRE sale más barato por unidad que comprar suelto
    # (confirmado en todos los ejemplos vistos hasta ahora). No pisa
    # valores que ya se hayan extraído bien por etiqueta.
    if p.precio_bulto_cerrado is None or p.precio_unitario is None:
        precios_encontrados = []
        for texto in strings:
            # Solo consideramos textos que EMPIEZAN con '$' - así evitamos
            # que números sueltos (ej. los botones de presentación "1",
            # "8", "12", o el contador de cantidad) se cuelen como si
            # fueran precios válidos (parse_precio_ar("1") da 1.0, que
            # es un float válido pero NO es un precio real).
            if not texto.strip().startswith("$"):
                continue
            precio = parse_precio_ar(texto)
            if precio is not None and precio not in precios_encontrados:
                precios_encontrados.append(precio)

        if len(precios_encontrados) == 2:
            mayor = max(precios_encontrados)
            menor = min(precios_encontrados)
            if p.precio_unitario is None:
                p.precio_unitario = mayor
            if p.precio_bulto_cerrado is None:
                p.precio_bulto_cerrado = menor

    return p


def parsear_precio_ficha_individual(html_text: str) -> dict:
    """
    Parsea el precio de la FICHA INDIVIDUAL de un producto (no un listado
    de categoría - es la página a la que se llega clickeando un producto,
    ej. .../cacao-toddy-extremo-800-gr-4427.html).

    Usa la misma estrategia de buscar por texto de etiqueta que
    _parse_producto(), porque la estructura de precios es la misma
    ("Precio unitario por bulto cerrado" / "Precio unitario"),
    confirmado contra capturas reales de fichas individuales.

    Devuelve un dict: {"precio_bulto_cerrado": float|None,
                        "precio_unitario": float|None,
                        "estado_stock": str}
    """
    soup = BeautifulSoup(html_text, "html.parser")
    strings = list(soup.stripped_strings)

    resultado = {
        "precio_bulto_cerrado": None,
        "precio_unitario": None,
        "estado_stock": "",
    }

    for i, texto in enumerate(strings):
        low = texto.lower()

        if low == "en stock":
            resultado["estado_stock"] = "En stock"
        elif low in ("sin stock", "agotado"):
            resultado["estado_stock"] = texto
        elif "disponibilidad critica" in low or "disponibilidad crítica" in low:
            resultado["estado_stock"] = texto

        if "precio unitario por bulto cerrado" in low:
            precio = _siguiente_precio(strings, i + 1)
            if precio is not None:
                resultado["precio_bulto_cerrado"] = precio
        elif low.startswith("precio unitario") and "bulto" not in low:
            precio = _siguiente_precio(strings, i + 1)
            if precio is not None:
                resultado["precio_unitario"] = precio

    return resultado


def _siguiente_precio(strings: list, start_idx: int, max_lookahead: int = 2) -> Optional[float]:
    """
    Busca un precio parseable en los próximos `max_lookahead` strings a
    partir de start_idx (por si el '$' y el número vienen en textos
    separados, cosa común en Magento).
    """
    for k in range(start_idx, min(start_idx + max_lookahead, len(strings))):
        precio = parse_precio_ar(strings[k])
        if precio is not None:
            return precio
    return None


def guardar_csv(productos: list[Producto], nombre_archivo: str):
    if not productos:
        log.warning("No hay productos para guardar en %s", nombre_archivo)
        return

    ruta = OUTPUT_DIR / nombre_archivo
    campos = list(asdict(productos[0]).keys())

    with open(ruta, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        for p in productos:
            fila = asdict(p)
            # Las presentaciones son una lista (ej. [1, 8]) - en CSV la
            # dejamos como texto separado por "|" para que sea legible en Excel
            fila["presentaciones"] = "|".join(str(x) for x in (fila["presentaciones"] or []))
            writer.writerow(fila)

    log.info("Guardado: %s (%d productos)", ruta, len(productos))


def main():
    session = get_session()

    usuario = os.environ.get("MAXICONSUMO_USER")
    contrasena = os.environ.get("MAXICONSUMO_PASS")

    if usuario and contrasena:
        ok = login(session, usuario, contrasena)
        if not ok:
            log.error(
                "El login falló. Corriendo igual, pero probablemente vas a "
                "ver precios de invitado en vez de precios de cliente. "
                "Revisá LOGIN_URL/LOGIN_POST_URL y los nombres de campo."
            )
    else:
        log.info(
            "MAXICONSUMO_USER / MAXICONSUMO_PASS no están seteadas - "
            "scrapeando como invitado (precios públicos)."
        )

    categorias = descubrir_categorias_via_sitemap(session)
    if not categorias:
        categorias = [urljoin(BASE_URL, c) for c in CATEGORIAS_RAIZ]

    log.info("Arrancando scraping de %d categorías en %s", len(categorias), STORE_SLUG)

    todos_los_productos: list[Producto] = []
    for i, cat_url in enumerate(categorias, 1):
        log.info("[%d/%d] %s", i, len(categorias), cat_url)
        productos, completo = scrape_category(session, cat_url)
        if not completo:
            log.warning("Categoría %s quedó INCOMPLETA (se cortó por error de red)", cat_url)
        todos_los_productos.extend(productos)
        sleep_politely()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    guardar_csv(todos_los_productos, f"maxiconsumo_{STORE_SLUG}_{timestamp}.csv")

    # También un JSON crudo por si preferís post-procesar con pandas
    ruta_json = OUTPUT_DIR / f"maxiconsumo_{STORE_SLUG}_{timestamp}.json"
    with open(ruta_json, "w", encoding="utf-8") as f:
        json.dump([asdict(p) for p in todos_los_productos], f, ensure_ascii=False, indent=2)

    log.info("Listo. Total productos: %d", len(todos_los_productos))


if __name__ == "__main__":
    main()
