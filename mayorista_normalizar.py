"""
mayorista_normalizar.py

Normaliza los precios de mayoristas (Maxiconsumo, y despues Yaguar) a
un precio por unidad estandar ($/kg o $/L), para poder comparar contra
el catalogo de supermercados de Indice LCV.

Reusa las funciones de extraccion de precios_normalizar_unidades.py
(el mismo modulo que ya usa Indice LCV), pero con una diferencia de
enfoque importante:

- En Indice LCV, la unidad (kg/L/unidad/m/panos) viene de un diccionario
  "rubro" armado a mano por categoria de super (ej. "Aceites" -> L).
- Aca en mayoristas NO tenemos ese mapeo armado todavia, asi que en vez
  de clasificar por categoria, auto-detectamos POR PRODUCTO: probamos
  extraer gramos primero, despues mililitros, despues cantidad de
  unidades (ej. "196 UN", "20 sobres"). Si ninguna de las tres aplica,
  el producto queda sin normalizar. Es menos preciso en casos ambiguos
  (ej. un producto que por error tiene tanto "500ml" como "20un" en el
  nombre), pero no requiere categorizar a mano cada subcategoria de
  Maxiconsumo antes de poder normalizar nada.

Cada producto de mayorista tiene DOS precios (precio_bulto_cerrado y
precio_unitario - ver maxiconsumo_scraper.py). Ambos representan el
precio de UNA unidad del producto (ej. una bolsa de 800gr), solo que
a tarifas distintas segun si comprás por bulto o suelto - no son
"precio del pack" vs "precio de 1 unidad del pack". Por eso a los dos
se les aplica la MISMA cantidad extraida del nombre.
"""

from dataclasses import dataclass
from typing import Optional

from precios_normalizar_unidades import (
    normalizar,
    extraer_gramos,
    extraer_mililitros,
    extraer_unidades,
)


@dataclass
class ResultadoNormalizacion:
    unidad_detectada: Optional[str]  # "kg", "L", "unidad", o None si no se pudo detectar
    cantidad_base: Optional[float]   # gramos, ml, o cantidad de unidades extraidas del nombre
    precio_bulto_cerrado_normalizado: Optional[float]  # $/kg, $/L o $/unidad
    precio_unitario_normalizado: Optional[float]        # $/kg, $/L o $/unidad


def normalizar_producto_mayorista(
    nombre: str,
    precio_bulto_cerrado: Optional[float],
    precio_unitario: Optional[float],
) -> ResultadoNormalizacion:
    """
    Auto-detecta si el producto se mide en peso, volumen, o cantidad de
    unidades a partir del nombre, y normaliza ambos precios (bulto y
    unitario) a $/kg, $/L o $/unidad.

    Prioridad de deteccion: gramos primero, despues mililitros, despues
    unidades. Un producto no deberia matchear mas de una categoria en
    la practica (no vimos ningun caso asi en las pruebas contra
    Maxiconsumo), pero si llegara a pasar, gramos gana, despues ml.
    """
    nombre_norm = normalizar(nombre)

    gramos = extraer_gramos(nombre_norm)
    if gramos and gramos > 0:
        return ResultadoNormalizacion(
            unidad_detectada="kg",
            cantidad_base=gramos,
            precio_bulto_cerrado_normalizado=_normalizar_por_cantidad(precio_bulto_cerrado, gramos, escala=1000),
            precio_unitario_normalizado=_normalizar_por_cantidad(precio_unitario, gramos, escala=1000),
        )

    ml = extraer_mililitros(nombre_norm)
    if ml and ml > 0:
        return ResultadoNormalizacion(
            unidad_detectada="L",
            cantidad_base=ml,
            precio_bulto_cerrado_normalizado=_normalizar_por_cantidad(precio_bulto_cerrado, ml, escala=1000),
            precio_unitario_normalizado=_normalizar_por_cantidad(precio_unitario, ml, escala=1000),
        )

    unidades = extraer_unidades(nombre_norm)
    if unidades and unidades > 0:
        return ResultadoNormalizacion(
            unidad_detectada="unidad",
            cantidad_base=float(unidades),
            precio_bulto_cerrado_normalizado=_normalizar_por_cantidad(precio_bulto_cerrado, unidades, escala=1),
            precio_unitario_normalizado=_normalizar_por_cantidad(precio_unitario, unidades, escala=1),
        )

    # No se pudo detectar peso, volumen, ni cantidad de unidades - queda sin normalizar
    return ResultadoNormalizacion(
        unidad_detectada=None,
        cantidad_base=None,
        precio_bulto_cerrado_normalizado=None,
        precio_unitario_normalizado=None,
    )


def _normalizar_por_cantidad(precio: Optional[float], cantidad_base: float, escala: float) -> Optional[float]:
    """
    precio del envase -> precio normalizado.
    escala=1000 para kg/L (cantidad_base viene en gramos/ml, precio por
    cada 1000 de esas unidades). escala=1 para "unidad" (cantidad_base
    ya es la cantidad de unidades, precio simplemente se divide).
    """
    if precio is None:
        return None
    return precio / cantidad_base * escala
