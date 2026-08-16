#!/usr/bin/env python3
"""
scraper_por_rubro.py

A diferencia de scraper_completo.py (que scrapea las 5 categorías en
una sola corrida larga y guarda todo junto al final), este script:

  1. Scrapea CADA rubro por separado
  2. Guarda cada rubro en su PROPIO archivo apenas termina (no espera
     a que terminen los demás) - así si algo falla a mitad de camino,
     no perdés el trabajo ya hecho de los rubros anteriores
  3. Si un rubro se corta por error de red (queda incompleto), lo
     AVISA claramente al final, para que sepas cuál volver a correr
     (podés usar --solo <rubro> para reintentar uno puntual sin
     tener que correr todo de nuevo)

Uso:
    python scraper_por_rubro.py                  # corre los 5 rubros
    python scraper_por_rubro.py --solo bebidas    # corre solo Bebidas
"""

import csv
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

from maxiconsumo_scraper import BASE_URL, CATEGORIAS_RAIZ, get_session, scrape_category
from mayorista_normalizar import normalizar_producto_mayorista

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)


def scrapear_un_rubro(session, nombre_rubro: str) -> tuple[int, bool, Path]:
    """
    Scrapea un rubro puntual, lo normaliza, y lo guarda en su propio
    archivo. Devuelve (cantidad_productos, completo, ruta_del_archivo).
    """
    url = urljoin(BASE_URL, nombre_rubro)
    print(f"\n{'=' * 60}")
    print(f"Rubro: {nombre_rubro}")
    print(f"{'=' * 60}")

    productos, completo = scrape_category(session, url)

    filas = []
    for p in productos:
        r = normalizar_producto_mayorista(p.nombre, p.precio_bulto_cerrado, p.precio_unitario)
        fila = asdict(p)
        fila["categoria_raiz"] = nombre_rubro
        fila["unidad_detectada"] = r.unidad_detectada
        fila["cantidad_base"] = r.cantidad_base
        fila["precio_bulto_cerrado_normalizado"] = r.precio_bulto_cerrado_normalizado
        fila["precio_unitario_normalizado"] = r.precio_unitario_normalizado
        fila["presentaciones"] = "|".join(str(x) for x in (fila["presentaciones"] or []))
        filas.append(fila)

    # Nombre de archivo SIN timestamp variable - siempre pisa el mismo
    # archivo para ese rubro (así "completar solo bebidas" reemplaza
    # limpiamente el archivo de bebidas anterior, sin ir acumulando
    # versiones viejas incompletas dando vueltas).
    nombre_base = nombre_rubro.replace(".html", "")
    ruta_csv = OUTPUT_DIR / f"rubro_{nombre_base}.csv"

    if filas:
        campos = list(filas[0].keys())
        with open(ruta_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=campos)
            writer.writeheader()
            writer.writerows(filas)

        ruta_json = OUTPUT_DIR / f"rubro_{nombre_base}.json"
        with open(ruta_json, "w", encoding="utf-8") as f:
            json.dump(filas, f, ensure_ascii=False, indent=2)

    estado = "COMPLETO" if completo else "INCOMPLETO (error de red)"
    print(f"\n{nombre_rubro}: {len(filas)} productos - {estado}")
    print(f"Guardado: {ruta_csv}")

    return len(filas), completo, ruta_csv


def main():
    session = get_session()

    # --solo <rubro> permite reintentar UN rubro puntual sin correr todo
    if "--solo" in sys.argv:
        idx = sys.argv.index("--solo")
        nombre_pedido = sys.argv[idx + 1]
        rubros_a_correr = [r for r in CATEGORIAS_RAIZ if nombre_pedido in r]
        if not rubros_a_correr:
            print(f"No encontré ningún rubro que coincida con '{nombre_pedido}'.")
            print(f"Rubros disponibles: {CATEGORIAS_RAIZ}")
            sys.exit(1)
    else:
        rubros_a_correr = CATEGORIAS_RAIZ

    resultados = {}
    for nombre_rubro in rubros_a_correr:
        cantidad, completo, ruta = scrapear_un_rubro(session, nombre_rubro)
        resultados[nombre_rubro] = (cantidad, completo)

    # --- Resumen final ---
    print("\n" + "=" * 60)
    print("RESUMEN")
    print("=" * 60)

    incompletos = []
    for nombre_rubro, (cantidad, completo) in resultados.items():
        marca = "✅" if completo else "❌"
        print(f"  {marca} {nombre_rubro:20s} {cantidad} productos" + ("" if completo else "  <- INCOMPLETO"))
        if not completo:
            incompletos.append(nombre_rubro)

    if incompletos:
        print("\n⚠️  Los siguientes rubros quedaron INCOMPLETOS y hay que repetirlos:")
        for r in incompletos:
            nombre_sin_html = r.replace(".html", "")
            print(f"    python scraper_por_rubro.py --solo {nombre_sin_html}")
    else:
        print("\n✅ Todos los rubros terminaron completos.")

    print("=" * 60)


if __name__ == "__main__":
    main()
