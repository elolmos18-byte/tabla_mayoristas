# Diseño: Lista de compras persistida por Guardián

> Documento de trabajo para la funcionalidad "Mi lista Maxiconsumo"
> atada al `telegram_id`. Vive en la base SQLite de `tabla_mayoristas`
> (`historico_mayorista.db`), separada de la Postgres de LCdV a
> propósito. Complementa `arquitectura_mayorista.md`.

---

## Decisiones ya tomadas

- Se guarda con **historial completo de movimientos**, no solo el
  estado actual — para poder analizar hábitos de consumo más adelante
  (ver sección "Motivación" abajo).
- Arquitectura elegida: **Opción A** — una API nueva corriendo 24/7 en
  el VPS (no un botón "guardar todo junto"), para edición fluida en
  tiempo real desde el HTML.
- Identidad del Guardián: se valida con el mecanismo **seguro** de
  Telegram (WebApp con `initData` firmado), no con el `telegram_id`
  pegado sin protección en la URL.
- `telegram_id` es la llave — no hace falta conectar Postgres (LCdV)
  con SQLite (`tabla_mayoristas`), cada sistema lo usa de forma
  independiente.

---

## Motivación (por qué guardamos historial)

Más allá de que el Guardián pueda editar su lista cómodo, esta data
sirve para conocer hábitos de consumo reales de la comunidad y
eventualmente sacarle valor:

- Qué productos se repiten más entre familias (canasta básica real de
  Puerto Madryn, no la oficial genérica).
- Frecuencia de armado/actualización de listas.
- Preferencia bulto vs. suelto (sensibilidad al precio, tamaño de
  familia implícito).
- A futuro, cruzado con Índice LCV: cuánta gente aprovecha realmente
  la comparación mayorista vs. súper, y cuánto ahorra en la práctica.

Posibles líneas de monetización (sin definir todavía, quedan
anotadas): reportes agregados/anónimos vendidos a mayoristas o
proveedores, comercios patrocinados como alternativa recomendada,
compra colectiva negociada por volumen detectado, índice de costo de
vida público con valor de prensa/sponsors.

**Importante:** son datos de consumo de familias reales. Antes de
compartir o vender cualquier cosa (aunque sea agregada/anónima),
conviene ser transparente con los Guardianes sobre este uso — por
ejemplo en los términos de uso del bot. No es asesoría legal, es un
tema de confianza con la comunidad a resolver antes de que sea
problema.

---

## Diseño de tablas (en `historico_mayorista.db`)

### `listas_guardian` — estado actual

| Columna | Tipo | Qué guarda |
|---|---|---|
| `id` | INTEGER PK | — |
| `telegram_id` | INTEGER | quién es el Guardián |
| `sku` | TEXT | qué producto |
| `cantidad` | INTEGER | cuántas unidades |
| `modo` | TEXT | `unitario` \| `bulto` |
| `actualizado_en` | TEXT | último cambio en esta fila |

`UNIQUE(telegram_id, sku)` — no se duplica el mismo producto para el
mismo Guardián. Agregar un producto que ya estaba = update, no insert
nuevo. Sacar un producto = se borra la fila.

### `movimientos_lista` — historial, nunca se borra

| Columna | Tipo | Qué guarda |
|---|---|---|
| `id` | INTEGER PK | — |
| `telegram_id` | INTEGER | quién hizo la acción |
| `sku` | TEXT | sobre qué producto |
| `producto_nombre` | TEXT | nombre del producto en el momento (ver debilidad sobre SKUs que desaparecen del catálogo) |
| `accion` | TEXT | `agregado` \| `quitado` \| `cantidad_cambiada` \| `modo_cambiado` |
| `cantidad` | INTEGER | cantidad en el momento de la acción |
| `modo` | TEXT | modo en el momento de la acción |
| `precio_unitario_momento` | REAL | precio unitario vigente al momento de la acción (nullable) |
| `precio_bulto_momento` | REAL | precio de bulto vigente al momento de la acción (nullable) |
| `creado_en` | TEXT | cuándo pasó |

Guardar `producto_nombre` y los precios del momento resuelve dos de
las debilidades detectadas (ver abajo): que el SKU deje de existir en
el catálogo más adelante, y que se pierda la noción de a qué precio
compró/consideró comprar el Guardián en ese instante.

---

## Debilidades detectadas (a tener en cuenta al programar)

Ninguna bloquea el arranque, pero hay que decidir a propósito qué se
resuelve ahora y qué se pospone — no dejar pasar por descuido.

1. **Escritura concurrente en SQLite.** SQLite bloquea la base entera
   en cada escritura. Con poco uso no se nota; si crece mucho (muchos
   Guardianes tocando la lista a la vez, o al mismo tiempo que corre
   el cron de scraping de madrugada), puede dar errores de "database
   is locked". Aceptable por ahora, vigilar si el uso crece.

2. **Precio del momento no capturado (RESUELTO en el diseño de
   arriba)** — se agregaron `precio_unitario_momento` y
   `precio_bulto_momento` a `movimientos_lista`.

3. **Productos que desaparecen del catálogo (RESUELTO en el diseño de
   arriba)** — se agregó `producto_nombre` a `movimientos_lista`, para
   no depender de que el SKU siga existiendo en `historico_mayoristas`.

4. **Crecimiento sin límite de `movimientos_lista`.** Nunca se borra.
   No es problema inmediato (SQLite aguanta millones de filas), pero
   revisar en 1-2 años si hace falta archivar o resumir datos viejos.

5. **La API nueva es superficie de ataque nueva.** Hoy
   `tabla_mayoristas` es de solo lectura hacia afuera. Al sumar una
   API que ACEPTA cambios, hay que: validar el `initData` de Telegram
   en CADA pedido (no solo una vez), poner límite de pedidos por
   minuto por Guardián, y loguear errores desde el día uno.

6. **Sin backup de `historico_mayorista.db`.** Hoy si se pierde, "solo"
   se pierde histórico de precios (recuperable re-scrapeando). Con
   las listas de compra reales de familias ahí adentro, ya no es
   recuperable. Pendiente: sumar backup periódico simple del archivo
   `.db` antes de poner esto en producción de verdad.

---

## Próximos pasos (orden acordado)

1. ~~Diseño de tablas~~ ✅ (este documento)
2. Script SQL para crear las tablas (`crear_listas_guardian.py`,
   mismo estilo que `crear_historico_mayorista.py`)
3. API (endpoints: traer lista, agregar, sacar, cambiar cantidad,
   cambiar modo) + validación de `initData` de Telegram
4. Conectar `dashboard_template.html` a la API en vez de memoria
5. Bot de LCdV: pantalla nueva + botón que abre la WebApp
6. Prueba de punta a punta

---

*Armado: 17/ago/2026.*
