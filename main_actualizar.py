#!/usr/bin/env python3
"""
main_actualizar.py

Orquestador principal - pensado para correr una vez por día (a mano
por ahora, después como cron en el VPS):

  1. Elige el rubro MÁS ATRASADO (el que hace más tiempo no se
     actualiza completo - o nunca, si es la primera vez)
  2. Pide las 2 páginas de MUESTRA de ese rubro (2 requests, rápido -
     ver elegir_referencias.py) y compara los precios de esos ~192
     productos contra los últimos conocidos
  3. Si HAY CAMBIOS en la muestra (o es la primera vez que se corre
     este rubro): dispara el scrape COMPLETO de ese rubro, guarda los
     datos, y actualiza el estado con la fecha de hoy
  4. Si NO hay cambios: no hace nada más, evitando un scrape completo
     innecesario

Requiere haber corrido antes:
    python elegir_referencias.py

Uso:
    python main_actualizar.py
"""

import csv
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

from maxiconsumo_scraper import (
    BASE_URL,
    get_session,
    fetch_pagina_categoria,
    scrape_category,
)
from mayorista_normalizar import normalizar_producto_mayorista

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)
ESTADO_PATH = Path("estado_rubros.json")


def cargar_estado() -> dict:
    if not ESTADO_PATH.exists():
        raise FileNotFoundError(
            f"No encontré {ESTADO_PATH}. Corré primero: python elegir_referencias.py"
        )
    with open(ESTADO_PATH, encoding="utf-8") as f:
        return json.load(f)


def guardar_estado(estado: dict):
    with open(ESTADO_PATH, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)


def elegir_rubro_mas_atrasado(estado: dict) -> str:
    """El más atrasado: fecha más vieja, o nunca corrido (None) primero."""
    def clave_orden(item):
        _, datos = item
        fecha = datos.get("ultima_actualizacion_completa")
        return fecha if fecha is not None else ""

    rubros_ordenados = sorted(estado.items(), key=clave_orden)
    return rubros_ordenados[0][0]


def chequear_muestra_paginas(session, nombre_rubro: str, datos_rubro: dict) -> tuple[bool, dict, int]:
    """
    Pide las N páginas de muestra EN VIVO, compara sus precios contra
    los guardados en precios_muestra. Devuelve (hay_cambios,
    precios_muestra_nuevos, cantidad_de_productos_que_cambiaron).
    """
    url = urljoin(BASE_URL, nombre_rubro)
    n_paginas = datos_rubro.get("paginas_muestra", 2)
    precios_previos = datos_rubro.get("precios_muestra", {})

    productos_muestra = []
    for pagina in range(1, n_paginas + 1):
        productos_pagina, ok = fetch_pagina_categoria(session, url, pagina)
        if not ok:
            print(f"  No pude pedir la página {pagina} de la muestra - por las dudas, actualizo completo.")
            return True, precios_previos, -1
        productos_muestra.extend(productos_pagina)
        if len(productos_pagina) < 96:
            break  # la categoría es más chica que la muestra completa

    precios_nuevos = {}
    cantidad_cambios = 0
    for p in productos_muestra:
        precio_actual = p.precio_bulto_cerrado or p.precio_unitario
        if not p.sku or precio_actual is None:
            continue
        precios_nuevos[p.sku] = precio_actual

        precio_anterior = precios_previos.get(p.sku)
        if precio_anterior is None or abs(precio_actual - precio_anterior) > 0.01:
            cantidad_cambios += 1

    hay_cambios = cantidad_cambios > 0
    return hay_cambios, precios_nuevos, cantidad_cambios


def scrapear_rubro_completo(session, nombre_rubro: str) -> tuple[int, bool]:
    url = urljoin(BASE_URL, nombre_rubro)
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

    if filas:
        nombre_base = nombre_rubro.replace(".html", "")
        campos = list(filas[0].keys())

        ruta_csv = OUTPUT_DIR / f"rubro_{nombre_base}.csv"
        with open(ruta_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=campos)
            writer.writeheader()
            writer.writerows(filas)

        ruta_json = OUTPUT_DIR / f"rubro_{nombre_base}.json"
        with open(ruta_json, "w", encoding="utf-8") as f:
            json.dump(filas, f, ensure_ascii=False, indent=2)

    return len(filas), completo


def main():
    estado = cargar_estado()
    session = get_session()

    nombre_rubro = elegir_rubro_mas_atrasado(estado)
    datos_rubro = estado[nombre_rubro]
    ultima_actualizacion = datos_rubro.get("ultima_actualizacion_completa") or "nunca"
    cantidad_muestra = len(datos_rubro.get("precios_muestra", {}))

    print(f"Rubro elegido (el más atrasado): {nombre_rubro}")
    print(f"Última actualización completa: {ultima_actualizacion}")
    print(f"Muestra guardada: {cantidad_muestra} productos ({datos_rubro.get('paginas_muestra', 2)} páginas)")
    print()

    print(f"Chequeando muestra ({datos_rubro.get('paginas_muestra', 2)} páginas, pocos requests)...")
    hay_cambios, precios_nuevos, cantidad_cambios = chequear_muestra_paginas(session, nombre_rubro, datos_rubro)

    if not hay_cambios:
        print(f"\n✅ Sin cambios en la muestra ({len(precios_nuevos)} productos revisados, 0 cambiaron). No hace falta actualizar {nombre_rubro} hoy.")
        datos_rubro["precios_muestra"] = precios_nuevos
        datos_rubro["ultima_actualizacion_completa"] = datetime.now(timezone.utc).isoformat()
        datos_rubro["ultimo_resultado"] = "sin_cambios"
        guardar_estado(estado)
        return

    print(f"\n🔄 Cambios detectados en la muestra ({cantidad_cambios} de {len(precios_nuevos)} productos). Actualizando {nombre_rubro} completo...")
    cantidad, completo = scrapear_rubro_completo(session, nombre_rubro)

    estado_txt = "COMPLETO" if completo else "INCOMPLETO (error de red - reintentar)"
    print(f"\n{nombre_rubro}: {cantidad} productos - {estado_txt}")

    if completo:
        datos_rubro["precios_muestra"] = precios_nuevos
        datos_rubro["ultima_actualizacion_completa"] = datetime.now(timezone.utc).isoformat()
        datos_rubro["ultimo_resultado"] = "completo"
        guardar_estado(estado)
        print(f"Estado actualizado en {ESTADO_PATH}")
    else:
        datos_rubro["ultimo_resultado"] = "incompleto"
        guardar_estado(estado)
        print("Como quedó incompleto, NO actualizo la fecha - va a reintentarse en la próxima corrida.")


if __name__ == "__main__":
    main()
