#!/usr/bin/env python3
"""
cargar_historico_mayorista.py

Carga los productos de un archivo JSON (el que genera el scraper) a la
tabla historico_mayoristas, como filas NUEVAS - no pisa lo que ya
había, así se va armando el historial en el tiempo.

Uso:
    python cargar_historico_mayorista.py output/rubro_almacen.json
    python cargar_historico_mayorista.py output/maxiconsumo_completo_sucursal_trelew_XXXXXXXX_XXXXXX.json
"""

import json
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path("historico_mayorista.db")

CAMPOS_TABLA = [
    "tienda", "sucursal", "sku", "nombre", "categoria_raiz", "estado_stock",
    "precio_bulto_cerrado", "precio_unitario", "unidad_detectada", "cantidad_base",
    "precio_bulto_cerrado_normalizado", "precio_unitario_normalizado",
    "url_producto", "fecha_scrape",
]


def a_float_o_none(valor):
    """Convierte a float, tolerando que venga como texto vacío, None, o ya numérico."""
    if valor is None or valor == "":
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def fila_desde_producto(p: dict) -> tuple:
    return (
        p.get("tienda", "maxiconsumo"),
        p.get("sucursal", ""),
        p.get("sku", ""),
        p.get("nombre", ""),
        p.get("categoria_raiz", ""),
        p.get("estado_stock", ""),
        a_float_o_none(p.get("precio_bulto_cerrado")),
        a_float_o_none(p.get("precio_unitario")),
        p.get("unidad_detectada") or None,
        a_float_o_none(p.get("cantidad_base")),
        a_float_o_none(p.get("precio_bulto_cerrado_normalizado")),
        a_float_o_none(p.get("precio_unitario_normalizado")),
        p.get("url_producto", ""),
        p.get("fecha_scrape", ""),
    )


def main():
    if len(sys.argv) < 2:
        print("Uso: python cargar_historico_mayorista.py <archivo.json>")
        sys.exit(1)

    ruta_json = Path(sys.argv[1])
    if not ruta_json.exists():
        print(f"No encontré el archivo: {ruta_json}")
        sys.exit(1)

    if not DB_PATH.exists():
        print(f"No encontré {DB_PATH}. Corré primero: python crear_historico_mayorista.py")
        sys.exit(1)

    with open(ruta_json, encoding="utf-8") as f:
        productos = json.load(f)

    filas = [fila_desde_producto(p) for p in productos]

    placeholders = ", ".join(["?"] * len(CAMPOS_TABLA))
    columnas_sql = ", ".join(CAMPOS_TABLA)
    insert_sql = f"INSERT INTO historico_mayoristas ({columnas_sql}) VALUES ({placeholders})"

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.executemany(insert_sql, filas)
    con.commit()

    total_en_tabla = cur.execute("SELECT COUNT(*) FROM historico_mayoristas").fetchone()[0]

    print(f"Cargadas {len(filas)} filas desde {ruta_json.name}")
    print(f"Total acumulado en historico_mayoristas: {total_en_tabla}")

    con.close()


if __name__ == "__main__":
    main()
