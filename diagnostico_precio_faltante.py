#!/usr/bin/env python3
"""
diagnostico_precio_faltante.py

Investiga por qué un producto quedó sin precio_bulto_cerrado.
Pide la primera página de Almacén, encuentra los primeros productos
SIN ese precio, y muestra el texto crudo completo de esas tarjetas
(todo lo que item.stripped_strings ve, en orden) para diagnosticar
a ojo si la frase "Precio unitario por bulto cerrado" está o no.

Uso:
    python diagnostico_precio_faltante.py
"""

from bs4 import BeautifulSoup

from maxiconsumo_scraper import get_session, REQUEST_TIMEOUT, _parse_producto


def main():
    session = get_session()
    url = "https://www.maxiconsumo.com/sucursal_trelew/almacen.html?p=1&product_list_limit=96"

    print(f"Pidiendo {url} ...")
    r = session.get(url, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    items = soup.select("li.item.product.product-item, li.product-item")
    print(f"{len(items)} productos en esta página.\n")

    encontrados = 0
    for item in items:
        strings = list(item.stripped_strings)
        tiene_frase = any("bulto cerrado" in s.lower() for s in strings)

        # Corremos el parser REAL, el mismo que usa el scraper de verdad
        p = _parse_producto(item, "diagnostico")

        # El caso que nos interesa: la frase está, pero el parser no
        # logró sacar el precio de bulto cerrado igual
        if tiene_frase and p.precio_bulto_cerrado is None:
            encontrados += 1
            print("=" * 70)
            print(f"PRODUCTO: {p.nombre}  (SKU {p.sku})")
            print(f"tiene_frase='bulto cerrado': {tiene_frase}")
            print(f"parser extrajo precio_bulto_cerrado: {p.precio_bulto_cerrado}")
            print("-" * 70)
            print("Todo el texto de la tarjeta, en orden:")
            print(" | ".join(strings))
            print()

        if encontrados >= 3:
            break

    if encontrados == 0:
        print("No encontré casos de 'frase presente pero precio no extraído' en esta página.")
        print("(el problema de los faltantes puede estar concentrado en otras páginas)")


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()
