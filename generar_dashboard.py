#!/usr/bin/env python3
"""
generar_dashboard.py

Genera el dashboard HTML público, leyendo de la base de datos SQLite
(historico_mayorista.db) en vez de solo los JSON sueltos - así podemos
calcular la TENDENCIA de precio (subió/bajó/igual) comparando el
último dato contra el anterior de cada producto, y mostrar el estado
de la última actualización de cada rubro (completo vs sin cambios).

Uso:
    python generar_dashboard.py [ruta_salida]

    Si no se pasa ruta_salida, escribe en public/dashboard.html
"""

import json
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path("historico_mayorista.db")
ESTADO_PATH = Path("estado_rubros.json")
TEMPLATE_PATH = Path(__file__).parent / "dashboard_template.html"

NOMBRES_RUBRO = {
    "almacen.html": "Almacén",
    "bebidas.html": "Bebidas",
    "frescos.html": "Frescos",
    "congelados.html": "Congelados",
    "limpieza.html": "Limpieza",
}


def obtener_productos_con_tendencia(con) -> list[dict]:
    """
    Para cada producto (tienda+sku), trae el precio MÁS RECIENTE y lo
    compara contra el ANTERIOR (si existe) para calcular la tendencia.
    Usa una window function de SQLite (ROW_NUMBER) para quedarnos con
    las últimas 2 filas de cada producto en una sola consulta, en vez
    de una consulta por producto (mucho más rápido con miles de filas).
    """
    query = """
    WITH numerado AS (
        SELECT
            *,
            ROW_NUMBER() OVER (
                PARTITION BY tienda, sku
                ORDER BY fecha_scrape DESC
            ) AS orden
        FROM historico_mayoristas
    )
    SELECT
        actual.tienda, actual.sucursal, actual.sku, actual.nombre,
        actual.categoria_raiz, actual.estado_stock,
        actual.precio_bulto_cerrado, actual.precio_unitario,
        actual.unidad_detectada, actual.cantidad_base,
        actual.precio_bulto_cerrado_normalizado,
        actual.precio_unitario_normalizado,
        actual.url_producto, actual.fecha_scrape,
        anterior.precio_bulto_cerrado_normalizado AS precio_anterior_normalizado
    FROM numerado actual
    LEFT JOIN numerado anterior
        ON actual.tienda = anterior.tienda
        AND actual.sku = anterior.sku
        AND anterior.orden = 2
    WHERE actual.orden = 1
    """
    con.row_factory = sqlite3.Row
    filas = con.execute(query).fetchall()

    productos = []
    for fila in filas:
        d = dict(fila)
        actual = d.get("precio_bulto_cerrado_normalizado")
        anterior = d.get("precio_anterior_normalizado")

        tendencia = None  # None = primera vez que vemos este producto, no hay con qué comparar
        if actual is not None and anterior is not None:
            if actual > anterior + 0.01:
                tendencia = "subio"
            elif actual < anterior - 0.01:
                tendencia = "bajo"
            else:
                tendencia = "igual"
        d["tendencia"] = tendencia
        productos.append(d)

    return productos


def cargar_estado_rubros() -> dict:
    if not ESTADO_PATH.exists():
        return {}
    with open(ESTADO_PATH, encoding="utf-8") as f:
        estado = json.load(f)

    resumen = {}
    for nombre_rubro, datos in estado.items():
        resumen[nombre_rubro] = {
            "nombre_legible": NOMBRES_RUBRO.get(nombre_rubro, nombre_rubro),
            "ultima_actualizacion": datos.get("ultima_actualizacion_completa"),
            "ultimo_resultado": datos.get("ultimo_resultado", "desconocido"),
        }
    return resumen


def main():
    ruta_salida = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("public/dashboard.html")
    ruta_salida.parent.mkdir(parents=True, exist_ok=True)

    if not DB_PATH.exists():
        print(f"No encontré {DB_PATH}. Corré primero crear_historico_mayorista.py y cargar datos.")
        sys.exit(1)

    con = sqlite3.connect(DB_PATH)
    productos = obtener_productos_con_tendencia(con)
    con.close()

    if not productos:
        print("La base de datos está vacía, no hay nada que generar.")
        sys.exit(1)

    estado_rubros = cargar_estado_rubros()

    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        template = f.read()

    data_json = json.dumps(productos, ensure_ascii=False, separators=(",", ":"))
    estado_json = json.dumps(estado_rubros, ensure_ascii=False)

    html_final = template.replace("__DATA_JSON__", data_json)
    html_final = html_final.replace("__ESTADO_RUBROS_JSON__", estado_json)

    with open(ruta_salida, "w", encoding="utf-8") as f:
        f.write(html_final)

    con_tendencia = sum(1 for p in productos if p["tendencia"])
    print(f"Total productos: {len(productos)} ({con_tendencia} con tendencia calculable)")
    print(f"Generado: {ruta_salida.resolve()} ({len(html_final) / 1024 / 1024:.2f} MB)")


if __name__ == "__main__":
    main()
