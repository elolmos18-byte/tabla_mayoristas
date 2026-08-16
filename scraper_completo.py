#!/usr/bin/env python3
"""
scraper_completo.py

Corrida completa del catálogo de Maxiconsumo (sucursal Trelew):
  1. Scrapea las categorías definidas en CATEGORIAS_RAIZ
     (maxiconsumo_scraper.py) - actualmente: Almacén, Bebidas, Frescos,
     Congelados, Limpieza.
  2. A cada producto le aplica la normalización ($/kg, $/L o $/unidad)
  3. Guarda TODO en un único CSV + JSON con timestamp
  4. Imprime un resumen general (por categoría y total)

Tiempo estimado: 40 min - 1 hora (Almacén solo ya tarda ~17-20 min).

Uso:
    python scraper_completo.py
"""

import csv
import json
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

from maxiconsumo_scraper import (
    BASE_URL,
    CATEGORIAS_RAIZ,
    STORE_SLUG,
    get_session,
    scrape_category,
)
from mayorista_normalizar import normalizar_producto_mayorista

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)


def main():
    inicio = time.time()
    session = get_session()

    categorias = [urljoin(BASE_URL, c) for c in CATEGORIAS_RAIZ]
    print(f"Categorías a scrapear ({len(categorias)}): {CATEGORIAS_RAIZ}")
    print("Esto puede tardar 40 min - 1 hora. Paciencia.\n")

    todas_las_filas = []
    resumen_por_categoria = {}

    for i, cat_url in enumerate(categorias, 1):
        nombre_cat = cat_url.rstrip("/").split("/")[-1]
        print(f"\n[{i}/{len(categorias)}] Categoría: {nombre_cat}")
        productos = scrape_category(session, cat_url)
        resumen_por_categoria[nombre_cat] = len(productos)

        for p in productos:
            r = normalizar_producto_mayorista(p.nombre, p.precio_bulto_cerrado, p.precio_unitario)
            fila = asdict(p)
            fila["categoria_raiz"] = nombre_cat
            fila["unidad_detectada"] = r.unidad_detectada
            fila["cantidad_base"] = r.cantidad_base
            fila["precio_bulto_cerrado_normalizado"] = r.precio_bulto_cerrado_normalizado
            fila["precio_unitario_normalizado"] = r.precio_unitario_normalizado
            fila["presentaciones"] = "|".join(str(x) for x in (fila["presentaciones"] or []))
            todas_las_filas.append(fila)

    # --- Guardar CSV + JSON final ---
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if todas_las_filas:
        campos = list(todas_las_filas[0].keys())
        ruta_csv = OUTPUT_DIR / f"maxiconsumo_completo_{STORE_SLUG}_{timestamp}.csv"
        with open(ruta_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=campos)
            writer.writeheader()
            writer.writerows(todas_las_filas)
        print(f"\nGuardado CSV: {ruta_csv} ({len(todas_las_filas)} productos)")

        ruta_json = OUTPUT_DIR / f"maxiconsumo_completo_{STORE_SLUG}_{timestamp}.json"
        with open(ruta_json, "w", encoding="utf-8") as f:
            json.dump(todas_las_filas, f, ensure_ascii=False, indent=2)
        print(f"Guardado JSON: {ruta_json}")

    # --- Resumen ---
    duracion_min = (time.time() - inicio) / 60
    total = len(todas_las_filas)
    normalizados = sum(1 for f in todas_las_filas if f["unidad_detectada"] is not None)

    print("\n" + "=" * 60)
    print("RESUMEN FINAL")
    print("=" * 60)
    print(f"Duración total: {duracion_min:.1f} minutos")
    print(f"\nProductos por categoría:")
    for cat, cantidad in resumen_por_categoria.items():
        print(f"  {cat:20s} {cantidad}")
    print(f"\nTotal productos:      {total}")
    print(f"Normalizados OK:      {normalizados} ({100*normalizados/total:.1f}%)" if total else "")
    print("=" * 60)


if __name__ == "__main__":
    main()
