#!/usr/bin/env python3
"""
crear_historico_mayorista.py

Crea (si no existe) la base de datos SQLite y la tabla
historico_mayoristas - una sola tabla para TODOS los mayoristas
(Maxiconsumo hoy, Yaguar después), distinguidos por la columna
'tienda'. Mismo espíritu que historico_catalogo_completo de Índice LCV.

Cada corrida del scraper AGREGA filas nuevas (no pisa las viejas), así
se va armando un historial de precios en el tiempo por producto.

Uso:
    python crear_historico_mayorista.py
"""

import sqlite3
from pathlib import Path

DB_PATH = Path("historico_mayorista.db")

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS historico_mayoristas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tienda TEXT NOT NULL,
    sucursal TEXT,
    sku TEXT NOT NULL,
    nombre TEXT NOT NULL,
    categoria_raiz TEXT,
    estado_stock TEXT,
    precio_bulto_cerrado REAL,
    precio_unitario REAL,
    unidad_detectada TEXT,
    cantidad_base REAL,
    precio_bulto_cerrado_normalizado REAL,
    precio_unitario_normalizado REAL,
    url_producto TEXT,
    fecha_scrape TEXT NOT NULL
);
"""

# Índices para las consultas que más vas a hacer: historial de un SKU
# puntual en el tiempo, y comparar precios de un rubro en una fecha dada.
CREATE_INDICES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_sku_tienda ON historico_mayoristas(tienda, sku);",
    "CREATE INDEX IF NOT EXISTS idx_fecha ON historico_mayoristas(fecha_scrape);",
    "CREATE INDEX IF NOT EXISTS idx_categoria ON historico_mayoristas(categoria_raiz);",
]


def main():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    cur.execute(CREATE_TABLE_SQL)
    for sql_indice in CREATE_INDICES_SQL:
        cur.execute(sql_indice)

    con.commit()

    # Confirmamos que la tabla quedó bien armada
    cur.execute("PRAGMA table_info(historico_mayoristas);")
    columnas = cur.fetchall()

    print(f"Base de datos: {DB_PATH.resolve()}")
    print(f"Tabla 'historico_mayoristas' lista, con {len(columnas)} columnas:")
    for col in columnas:
        print(f"  - {col[1]} ({col[2]})")

    con.close()


if __name__ == "__main__":
    main()
