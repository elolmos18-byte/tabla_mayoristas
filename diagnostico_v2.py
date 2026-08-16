#!/usr/bin/env python3
"""
diagnostico_v2.py

A diferencia de diagnostico_precio_faltante.py (que solo miraba la
página 1 de la categoría), este script usa el CSV que ya generó
analizar_almacen.py para encontrar productos REALES sin
precio_bulto_cerrado - de cualquier página - y pide su ficha
individual para ver qué pasa ahí.

Uso:
    python diagnostico_v2.py
"""

import csv

from maxiconsumo_scraper import get_session, REQUEST_TIMEOUT

CSV_PATH = "output/almacen_normalizado.csv"


def main():
    # Leemos el CSV ya generado y buscamos productos sin precio de bulto
    faltantes = []
    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row.get("precio_bulto_cerrado"):
                faltantes.append(row)

    print(f"Total productos sin precio_bulto_cerrado en el CSV: {len(faltantes)}")
    print()

    session = get_session()

    for row in faltantes[:3]:
        url = row["url_producto"]
        nombre = row["nombre"]
        print("=" * 70)
        print(f"PRODUCTO: {nombre}")
        print(f"URL: {url}")
        print("-" * 70)

        if not url:
            print("(sin URL guardada, no puedo pedir la ficha)")
            continue

        try:
            r = session.get(url, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
        except Exception as e:
            print(f"Error pidiendo la ficha: {e}")
            continue

        # Buscamos el fragmento de texto alrededor de '$' (signo de pesos)
        # para ver los NÚMEROS reales de precio, en vez de la palabra
        # "Precio" que también aparece en banners y texto legal sin
        # ningún numero cerca.
        texto = r.text
        idx = 0
        encontrados_precio = 0
        while True:
            idx = texto.find("$", idx)
            if idx == -1 or encontrados_precio >= 6:
                break
            # Un poco de contexto ANTES también, para ver qué etiqueta
            # acompaña a ese precio puntual
            inicio = max(0, idx - 80)
            fragmento = texto[inicio:idx + 60]
            import re
            fragmento_limpio = re.sub(r"<[^>]+>", " ", fragmento)
            fragmento_limpio = re.sub(r"\s+", " ", fragmento_limpio).strip()
            print(f"  ...{fragmento_limpio}...")
            idx += 1
            encontrados_precio += 1

        print()


if __name__ == "__main__":
    main()
