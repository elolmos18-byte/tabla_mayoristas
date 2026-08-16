#!/usr/bin/env python3
"""
analizar_almacen.py

Pipeline completo de prueba sobre la categoria Almacen de Maxiconsumo:
  1. Scrapea la categoria completa (~3674 productos, ~17 min - ya
     confirmado en corridas anteriores)
  2. A cada producto le aplica la normalizacion ($/kg o $/L) via
     mayorista_normalizar.py
  3. Guarda un CSV enriquecido con todos los campos + los normalizados
  4. Imprime un resumen: cuantos se pudieron normalizar, cuantos no
     (y por que), y una muestra ordenada por precio normalizado para
     detectar outliers raros (precios absurdos por typos, etc.)

Uso:
    python analizar_almacen.py
"""

import csv
from dataclasses import asdict
from pathlib import Path

from maxiconsumo_scraper import get_session, scrape_category
from mayorista_normalizar import normalizar_producto_mayorista

CATEGORIA_URL = "https://www.maxiconsumo.com/sucursal_trelew/almacen.html"
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)


def main():
    print(f"Scrapeando {CATEGORIA_URL} ...")
    print("(esto tarda ~15-20 minutos, es la categoria mas grande - paciencia)")
    print()

    session = get_session()
    productos = scrape_category(session, CATEGORIA_URL)

    print(f"\nScraping terminado: {len(productos)} productos encontrados.\n")
    print("Aplicando normalización ($/kg o $/L) a cada producto...")

    filas = []
    for p in productos:
        r = normalizar_producto_mayorista(p.nombre, p.precio_bulto_cerrado, p.precio_unitario)
        fila = asdict(p)
        fila["unidad_detectada"] = r.unidad_detectada
        fila["cantidad_base"] = r.cantidad_base
        fila["precio_bulto_cerrado_normalizado"] = r.precio_bulto_cerrado_normalizado
        fila["precio_unitario_normalizado"] = r.precio_unitario_normalizado
        # el campo presentaciones queda como lista vacia por ahora (ver
        # maxiconsumo_scraper.py) - lo pasamos a texto para el CSV
        fila["presentaciones"] = "|".join(str(x) for x in (fila["presentaciones"] or []))
        filas.append(fila)

    # --- Guardar CSV enriquecido ---
    ruta_csv = OUTPUT_DIR / "almacen_normalizado.csv"
    if filas:
        campos = list(filas[0].keys())
        with open(ruta_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=campos)
            writer.writeheader()
            writer.writerows(filas)
        print(f"\nGuardado: {ruta_csv} ({len(filas)} productos)")

    # --- Resumen estadístico ---
    print("\n" + "=" * 60)
    print("RESUMEN")
    print("=" * 60)

    total = len(filas)
    normalizados = [f for f in filas if f["unidad_detectada"] is not None]
    sin_normalizar = [f for f in filas if f["unidad_detectada"] is None]
    en_kg = [f for f in filas if f["unidad_detectada"] == "kg"]
    en_l = [f for f in filas if f["unidad_detectada"] == "L"]

    print(f"Total productos:            {total}")
    print(f"Normalizados OK:            {len(normalizados)} ({100*len(normalizados)/total:.1f}%)")
    print(f"  - en kg:                  {len(en_kg)}")
    print(f"  - en L:                   {len(en_l)}")
    print(f"Sin normalizar (sin match): {len(sin_normalizar)} ({100*len(sin_normalizar)/total:.1f}%)")

    sin_sku = [f for f in filas if not f["sku"]]
    sin_precio = [f for f in filas if f["precio_bulto_cerrado"] is None]
    print(f"\nSin SKU:                    {len(sin_sku)}")
    print(f"Sin precio_bulto_cerrado:   {len(sin_precio)}")

    skus = [f["sku"] for f in filas if f["sku"]]
    duplicados = len(skus) - len(set(skus))
    print(f"SKUs duplicados:            {duplicados}")

    # Muestra de productos SIN normalizar, para ver qué tipo de nombre
    # se nos está escapando (útil para decidir si vale la pena mejorar
    # el extractor, o si son casos legítimamente raros)
    if sin_normalizar:
        print("\n--- Muestra de productos SIN normalizar (primeros 15) ---")
        for f in sin_normalizar[:15]:
            print(f"  {f['nombre']}")

    # Outliers: productos normalizados con precio por kg/L absurdamente
    # alto o bajo, señal de un typo en el catálogo o un error de parseo
    if normalizados:
        con_precio = [
            f for f in normalizados
            if f["precio_bulto_cerrado_normalizado"] is not None
        ]
        con_precio.sort(key=lambda f: f["precio_bulto_cerrado_normalizado"])

        print("\n--- 5 más BARATOS por kg/L (revisar si tiene sentido) ---")
        for f in con_precio[:5]:
            print(f"  ${f['precio_bulto_cerrado_normalizado']:.2f}/{f['unidad_detectada']}  -  {f['nombre']}")

        print("\n--- 5 más CAROS por kg/L (revisar si tiene sentido) ---")
        for f in con_precio[-5:]:
            print(f"  ${f['precio_bulto_cerrado_normalizado']:.2f}/{f['unidad_detectada']}  -  {f['nombre']}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
