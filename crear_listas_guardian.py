#!/usr/bin/env python3
"""
crear_listas_guardian.py

Crea (si no existen) las tablas de la lista de compras persistida por
Guardián:
  - listas_guardian: el estado ACTUAL de la lista de cada Guardián
    (un producto por fila, se actualiza o se borra según lo que haga).
  - movimientos_lista: el HISTORIAL completo, nunca se borra - cada
    agregado/sacado/cambio de cantidad o modo queda como fila nueva,
    con el nombre y precio del producto en ese momento (para no
    depender de que el SKU siga existiendo en el catálogo más
    adelante, y para poder analizar a qué precio se tocó cada vez).

Mismo espíritu que crear_historico_mayorista.py: vive en la misma base
(historico_mayorista.db), corré esto una sola vez antes de usar la
API nueva.

Uso:
    python crear_listas_guardian.py
"""

import sqlite3
from pathlib import Path

DB_PATH = Path("historico_mayorista.db")

CREATE_LISTAS_GUARDIAN_SQL = """
CREATE TABLE IF NOT EXISTS listas_guardian (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    sku TEXT NOT NULL,
    cantidad INTEGER NOT NULL DEFAULT 1,
    modo TEXT NOT NULL DEFAULT 'unitario',
    actualizado_en TEXT NOT NULL,
    UNIQUE(telegram_id, sku)
);
"""

CREATE_MOVIMIENTOS_LISTA_SQL = """
CREATE TABLE IF NOT EXISTS movimientos_lista (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    sku TEXT NOT NULL,
    producto_nombre TEXT,
    accion TEXT NOT NULL,
    cantidad INTEGER,
    modo TEXT,
    precio_unitario_momento REAL,
    precio_bulto_momento REAL,
    creado_en TEXT NOT NULL
);
"""

# Índices para las consultas que más se van a hacer: la lista de UN
# Guardián puntual (tanto estado actual como historial), y el
# historial ordenado por fecha (para reportes de hábitos de consumo).
CREATE_INDICES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_listas_guardian_telegram ON listas_guardian(telegram_id);",
    "CREATE INDEX IF NOT EXISTS idx_movimientos_telegram ON movimientos_lista(telegram_id);",
    "CREATE INDEX IF NOT EXISTS idx_movimientos_fecha ON movimientos_lista(creado_en);",
]


def main():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    cur.execute(CREATE_LISTAS_GUARDIAN_SQL)
    cur.execute(CREATE_MOVIMIENTOS_LISTA_SQL)
    for sql_indice in CREATE_INDICES_SQL:
        cur.execute(sql_indice)

    con.commit()

    # Confirmamos que las dos tablas quedaron bien armadas - mismo
    # chequeo visual que ya hace crear_historico_mayorista.py.
    print(f"Base de datos: {DB_PATH.resolve()}")

    for nombre_tabla in ("listas_guardian", "movimientos_lista"):
        cur.execute(f"PRAGMA table_info({nombre_tabla});")
        columnas = cur.fetchall()
        print(f"\nTabla '{nombre_tabla}' lista, con {len(columnas)} columnas:")
        for col in columnas:
            print(f"  - {col[1]} ({col[2]})")

    con.close()


if __name__ == "__main__":
    main()
