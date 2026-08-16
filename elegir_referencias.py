#!/usr/bin/env python3
"""
elegir_referencias.py

Arma el archivo de estado inicial (estado_rubros.json) con una MUESTRA
de 2 páginas (hasta 192 productos) por rubro, tomando los primeros
productos de los datos ya scrapeados (el orden en que Maxiconsumo los
lista - "Posición" - es estable entre corridas, así que estos mismos
productos deberían seguir en la página 1 y 2 la próxima vez).

Por qué 2 páginas y no productos individuales sueltos: pedir 2 páginas
de categoría (192 productos de un saque, 2 requests) es MUCHO más
liviano que pedir 192 fichas de producto individuales (192 requests) -
de hecho, scrapear el catálogo COMPLETO de una categoría chica puede
necesitar menos requests que eso.

El main_actualizar.py después vuelve a pedir esas mismas 2 páginas en
vivo, compara los precios contra esta muestra guardada, y si varios
cambiaron, dispara el scrape completo del rubro.

Uso:
    python elegir_referencias.py
"""

import csv
import json
from glob import glob
from pathlib import Path

from maxiconsumo_scraper import CATEGORIAS_RAIZ, PRODUCTS_PER_PAGE

OUTPUT_DIR = Path("output")
ESTADO_PATH = Path("estado_rubros.json")
PAGINAS_MUESTRA = 2  # cuántas páginas de categoría se usan como muestra


def cargar_filas_de_rubro(nombre_rubro: str) -> list[dict]:
    """Busca datos ya scrapeados para este rubro (mismo criterio que antes)."""
    nombre_base = nombre_rubro.replace(".html", "")
    ruta_propia = OUTPUT_DIR / f"rubro_{nombre_base}.csv"

    if ruta_propia.exists():
        with open(ruta_propia, encoding="utf-8") as f:
            return list(csv.DictReader(f))

    candidatos = sorted(glob(str(OUTPUT_DIR / "maxiconsumo_completo_*.csv")))
    if not candidatos:
        return []

    with open(candidatos[-1], encoding="utf-8") as f:
        filas = list(csv.DictReader(f))

    return [f for f in filas if f.get("categoria_raiz") == nombre_rubro]


def main():
    estado = {}

    if ESTADO_PATH.exists():
        with open(ESTADO_PATH, encoding="utf-8") as f:
            estado = json.load(f)
        print(f"Estado previo encontrado en {ESTADO_PATH}, lo conservamos y solo completamos lo que falte.\n")

    tamano_muestra_max = PAGINAS_MUESTRA * PRODUCTS_PER_PAGE  # 2 x 96 = 192

    for nombre_rubro in CATEGORIAS_RAIZ:
        if nombre_rubro in estado and estado[nombre_rubro].get("precios_muestra"):
            print(f"{nombre_rubro}: ya tiene muestra guardada, no la piso.")
            continue

        filas = cargar_filas_de_rubro(nombre_rubro)
        if not filas:
            print(f"{nombre_rubro}: no encontré datos scrapeados todavía - correr el scraper primero para este rubro.")
            continue

        muestra = filas[:tamano_muestra_max]

        precios_muestra = {}
        for fila in muestra:
            precio = fila.get("precio_bulto_cerrado") or fila.get("precio_unitario")
            sku = fila.get("sku")
            if sku and precio:
                precios_muestra[sku] = float(precio)

        estado[nombre_rubro] = {
            "paginas_muestra": PAGINAS_MUESTRA,
            "precios_muestra": precios_muestra,
            "ultima_actualizacion_completa": None,
        }
        print(f"{nombre_rubro}: muestra armada -> {len(precios_muestra)} productos con precio de {len(muestra)} tomados.")

    with open(ESTADO_PATH, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)

    print(f"\nGuardado: {ESTADO_PATH}")


if __name__ == "__main__":
    main()
