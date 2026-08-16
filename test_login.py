#!/usr/bin/env python3
"""
Script de diagnóstico para calibrar el scraper de Maxiconsumo.

Se usa en DOS PASOS:

PASO 1 - Descubrir categorías y elegir la más chica:
    python test_login.py listar

    Esto lista las categorías/subcategorías que encuentra en la home,
    con la cantidad de productos si Magento la muestra (texto tipo
    "24 Productos"). Elegís la más chica de la lista.

PASO 2 - Probar login + extracción sobre esa categoría:
    python test_login.py probar "https://www.maxiconsumo.com/sucursal_trelew/algo.html"

    Esto:
      1. Intenta loguearse (lee MAXICONSUMO_USER / MAXICONSUMO_PASS del entorno)
      2. Pide esa categoría YA logueado
      3. Guarda el HTML crudo en output/debug_categoria.html para que lo
         abras en el navegador y compares visualmente
      4. Prueba varios selectores CSS candidatos y te dice cuántos
         productos encuentra cada uno, para que sepas cuál usar en
         maxiconsumo_scraper.py

Requiere las mismas dependencias que el scraper principal:
    pip install requests beautifulsoup4 lxml
"""

import os
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from maxiconsumo_scraper import (
    BASE_URL,
    HEADERS,
    LOGIN_URL,
    LOGIN_POST_URL,
    login,
    get_session,
)

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)


def listar_categorias():
    session = get_session()
    print(f"Pidiendo home: {BASE_URL}")
    r = session.get(BASE_URL, timeout=20)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    # Guardamos la home cruda por si hay que inspeccionarla a mano
    (OUTPUT_DIR / "debug_home.html").write_text(r.text, encoding="utf-8")
    print(f"Home guardada en {OUTPUT_DIR / 'debug_home.html'} ({len(r.text)} chars)")

    # Buscamos links del menú de navegación (nav principal de Magento)
    nav_links = soup.select("nav a[href], .navigation a[href], header a[href]")

    candidatos = []
    vistos = set()
    for a in nav_links:
        href = a.get("href", "")
        texto = a.get_text(strip=True)
        if not href or not texto:
            continue
        if href in vistos:
            continue
        if BASE_URL.split("/sucursal")[0] not in href and not href.startswith("/"):
            continue
        vistos.add(href)
        candidatos.append((texto, href))

    print(f"\nEncontré {len(candidatos)} links de navegación con texto. Primeros 40:\n")
    for texto, href in candidatos[:40]:
        print(f"  {texto!r:40s} -> {href}")

    print(
        "\nNo tengo forma de saber la cantidad de productos por categoría "
        "sin visitarlas una por una (Magento no siempre lo muestra en el "
        "menú). Elegí un nombre que suene chico/específico "
        "(ej. una subcategoría tipo 'Cacao' o 'Té' en vez de 'Almacén' "
        "entero) y pasalo como argumento al paso 'probar'."
    )


def probar_categoria(url: str):
    session = get_session()

    usuario = os.environ.get("MAXICONSUMO_USER")
    contrasena = os.environ.get("MAXICONSUMO_PASS")

    if usuario and contrasena:
        ok = login(session, usuario, contrasena)
        print(f"Login: {'OK' if ok else 'FALLÓ (ver logs arriba)'}")
    else:
        print("MAXICONSUMO_USER / MAXICONSUMO_PASS no seteadas - pruebo sin login.")

    print(f"\nPidiendo categoría: {url}")
    try:
        r = session.get(url, timeout=20)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"ERROR pidiendo la categoría: {e}")
        sys.exit(1)

    debug_path = OUTPUT_DIR / "debug_categoria.html"
    debug_path.write_text(r.text, encoding="utf-8")
    print(f"HTML crudo guardado en {debug_path} ({len(r.text)} chars) - abrilo en el navegador")

    soup = BeautifulSoup(r.text, "html.parser")

    # Batería de selectores candidatos, de más específico a más genérico
    candidatos_selector = [
        "li.item.product.product-item",
        "li.product-item",
        "div.product-item",
        "[data-product-sku]",
        ".products-grid .item",
        ".product.product-item",
    ]

    print("\n--- Prueba de selectores CSS ---")
    for sel in candidatos_selector:
        encontrados = soup.select(sel)
        print(f"  {sel!r:40s} -> {len(encontrados)} elementos")

    # Buscamos también evidencia de precio y SKU en el texto plano,
    # para saber si al menos los DATOS están en esta página
    # (a veces Magento carga el grilla de productos vía AJAX/JS y el
    # HTML inicial viene vacío - en ese caso hay que usar otra estrategia,
    # tipo pegarle directo a la API REST de Magento o renderizar con
    # Selenium/Playwright).
    texto_plano = soup.get_text(" ", strip=True)
    tiene_precio = "$" in texto_plano
    tiene_sku = "SKU" in texto_plano or "sku" in texto_plano.lower()

    print(f"\n¿Aparece '$' en el texto de la página? {tiene_precio}")
    print(f"¿Aparece 'SKU' en el texto de la página? {tiene_sku}")

    if not tiene_precio:
        print(
            "\n⚠️  Si no hay '$' en el HTML, es MUY probable que el listado "
            "de productos se cargue vía JavaScript/AJAX después de la carga "
            "inicial, y requests+BeautifulSoup no lo va a ver. En ese caso "
            "el siguiente paso sería revisar la pestaña Network del "
            "navegador buscando una request tipo XHR/fetch que devuelva "
            "JSON con los productos, y pegarle directo a esa API en vez de "
            "parsear HTML."
        )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    comando = sys.argv[1]

    if comando == "listar":
        listar_categorias()
    elif comando == "probar":
        if len(sys.argv) < 3:
            print("Uso: python test_login.py probar <url_categoria>")
            sys.exit(1)
        probar_categoria(sys.argv[2])
    else:
        print(f"Comando desconocido: {comando}")
        print(__doc__)
