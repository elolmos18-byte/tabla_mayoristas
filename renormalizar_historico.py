#!/usr/bin/env python3
"""
renormalizar_historico.py

Los precios CRUDOS (precio_bulto_cerrado, precio_unitario) que ya
tenés en la base de datos son correctos - vinieron directo del sitio.
Lo que estaba mal era el CÁLCULO de los precios normalizados
($/kg, $/L, $/unidad), por dos bugs en precios_normalizar_unidades.py
que ya se arreglaron (ver ese archivo para el detalle).

Este script NO vuelve a pegarle a Maxiconsumo - recalcula, para cada
fila ya guardada, la normalización con la lógica corregida, y
actualiza esa misma fila en la base (no crea filas nuevas, no duplica
historial).

Uso:
    python renormalizar_historico.py
"""

import sqlite3
from pathlib import Path

from mayorista_normalizar import normalizar_producto_mayorista

DB_PATH = Path("historico_mayorista.db")


def main():
    if not DB_PATH.exists():
        print(f"No encontré {DB_PATH}.")
        return

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    filas = cur.execute(
        "SELECT id, nombre, precio_bulto_cerrado, precio_unitario "
        "FROM historico_mayoristas"
    ).fetchall()

    print(f"Total de filas a revisar: {len(filas)}")

    actualizadas = 0
    cambios_de_unidad = 0

    for fila in filas:
        r = normalizar_producto_mayorista(
            fila["nombre"], fila["precio_bulto_cerrado"], fila["precio_unitario"]
        )

        cur.execute(
            """
            UPDATE historico_mayoristas
            SET unidad_detectada = ?,
                cantidad_base = ?,
                precio_bulto_cerrado_normalizado = ?,
                precio_unitario_normalizado = ?
            WHERE id = ?
            """,
            (
                r.unidad_detectada,
                r.cantidad_base,
                r.precio_bulto_cerrado_normalizado,
                r.precio_unitario_normalizado,
                fila["id"],
            ),
        )
        actualizadas += 1

    con.commit()

    normalizados_ahora = cur.execute(
        "SELECT COUNT(*) FROM historico_mayoristas WHERE unidad_detectada IS NOT NULL"
    ).fetchone()[0]

    print(f"Filas actualizadas: {actualizadas}")
    print(f"Filas con normalización válida ahora: {normalizados_ahora} de {len(filas)}")

    con.close()


if __name__ == "__main__":
    main()
