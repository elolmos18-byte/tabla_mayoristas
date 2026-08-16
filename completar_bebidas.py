#!/usr/bin/env python3
"""
completar_bebidas.py

La corrida de scraper_completo.py se cortó en Bebidas (falló en la
página 7 tras 3 reintentos). Este script:
  1. Vuelve a scrapear SOLO Bebidas, de punta a punta
  2. Toma el CSV completo más reciente ya generado
  3. Saca las filas viejas e incompletas de Bebidas
  4. Agrega las filas nuevas y completas
  5. Guarda un CSV/JSON actualizado (con timestamp nuevo)

Uso:
    python completar_bebidas.py
"""

import csv
import json
from dataclasses import asdict
from datetime import datetime
from glob import glob
from pathlib import Path
from urllib.parse import urljoin

from maxiconsumo_scraper import BASE_URL, STORE_SLUG, get_session, scrape_category
from mayorista_normalizar import normalizar_producto_mayorista

OUTPUT_DIR = Path("output")


def encontrar_csv_completo_mas_reciente() -> Path:
    candidatos = sorted(glob(str(OUTPUT_DIR / "maxiconsumo_completo_*.csv")))
    if not candidatos:
        raise FileNotFoundError(
            "No encontré ningún CSV completo previo en output/. "
            "Corré primero scraper_completo.py."
        )
    return Path(candidatos[-1])  # el último por orden alfabético = más reciente (timestamp en el nombre)


def main():
    session = get_session()

    print("Scrapeando Bebidas completo...")
    url_bebidas = urljoin(BASE_URL, "bebidas.html")
    productos, completo = scrape_category(session, url_bebidas)
    if not completo:
        print("⚠️  Bebidas volvió a quedar incompleta - probá correr este script de nuevo")
    print(f"Bebidas: {len(productos)} productos encontrados (corrida nueva).\n")

    filas_bebidas_nuevas = []
    for p in productos:
        r = normalizar_producto_mayorista(p.nombre, p.precio_bulto_cerrado, p.precio_unitario)
        fila = asdict(p)
        fila["categoria_raiz"] = "bebidas.html"
        fila["unidad_detectada"] = r.unidad_detectada
        fila["cantidad_base"] = r.cantidad_base
        fila["precio_bulto_cerrado_normalizado"] = r.precio_bulto_cerrado_normalizado
        fila["precio_unitario_normalizado"] = r.precio_unitario_normalizado
        fila["presentaciones"] = "|".join(str(x) for x in (fila["presentaciones"] or []))
        filas_bebidas_nuevas.append(fila)

    # --- Cargar el CSV completo previo y sacar las filas viejas de Bebidas ---
    ruta_previa = encontrar_csv_completo_mas_reciente()
    print(f"Cargando CSV previo: {ruta_previa}")

    with open(ruta_previa, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        filas_previas = list(reader)

    cantidad_bebidas_vieja = sum(1 for f in filas_previas if f.get("categoria_raiz") == "bebidas.html")
    print(f"Filas viejas de Bebidas (incompletas) a reemplazar: {cantidad_bebidas_vieja}")

    filas_sin_bebidas = [f for f in filas_previas if f.get("categoria_raiz") != "bebidas.html"]

    # Los campos numéricos del CSV vienen como texto (por ser CSV) - las
    # filas nuevas de Bebidas tienen tipos nativos (float/None). Para que
    # el archivo final sea consistente, convertimos las filas nuevas a
    # texto también antes de mezclar.
    filas_bebidas_texto = []
    for fila in filas_bebidas_nuevas:
        fila_texto = {k: ("" if v is None else str(v)) for k, v in fila.items()}
        filas_bebidas_texto.append(fila_texto)

    filas_finales = filas_sin_bebidas + filas_bebidas_texto

    # --- Guardar el CSV/JSON actualizado ---
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    campos = list(filas_finales[0].keys())

    ruta_csv = OUTPUT_DIR / f"maxiconsumo_completo_{STORE_SLUG}_{timestamp}.csv"
    with open(ruta_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        writer.writerows(filas_finales)

    ruta_json = OUTPUT_DIR / f"maxiconsumo_completo_{STORE_SLUG}_{timestamp}.json"
    with open(ruta_json, "w", encoding="utf-8") as f:
        json.dump(filas_finales, f, ensure_ascii=False, indent=2)

    print(f"\nGuardado CSV actualizado: {ruta_csv} ({len(filas_finales)} productos totales)")
    print(f"Guardado JSON actualizado: {ruta_json}")
    print(f"\nBebidas: {cantidad_bebidas_vieja} (viejo, incompleto) -> {len(filas_bebidas_texto)} (nuevo, completo)")


if __name__ == "__main__":
    main()
