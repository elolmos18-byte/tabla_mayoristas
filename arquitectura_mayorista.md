# Arquitectura de Índice Mayorista

> Este documento explica QUÉ hace y POR QUÉ el sistema de scraping de
> mayoristas (Maxiconsumo por ahora), para que se pueda diseñar su
> integración con LCdV (Guardianes, canasta personalizada, bot) sin
> tener que reconstruir el razonamiento desde cero.
>
> Repo: `github.com/elolmos18-byte/tabla_mayoristas`
> Vive en el VPS: `/home/lcv/tabla_mayoristas`
> Dashboard público: `guardianesdelviento.com/mayorista/`

---

## 1. Por qué existe esto

Agustín compra 1 vez al mes en mayorista (Maxiconsumo) para la familia
(6 personas) y refuerza con compras chicas en supermercados normales
durante el mes. La hipótesis a validar: ese approach ahorra plata
respecto a comprar todo en super, aunque el gasto grande de una sola
vez "se sienta" más caro en el momento.

Índice Mayorista es la mitad de mayoristas de esa comparación. La otra
mitad ya existe: **Índice LCV** (La Anónima, Carrefour, Changomas,
Vea), con su propia tabla `historico_catalogo_completo`. La idea final
es poder comparar ambas tablas para saber, producto por producto,
dónde conviene comprar cada cosa - y algún día, detectar "ofertas
imperdibles" (precio muy por debajo del resto del mercado) y armar una
canasta personalizada por Guardián (ver sección 9, pendiente de
diseño).

---

## 2. La fuente de datos: Maxiconsumo

- Plataforma: **Magento 2** (a diferencia de Vea que es VTEX).
- Sucursal scrapeada: **Trelew** (`sucursal_trelew` en la URL).
- **Sin login**: el scraper corre como invitado (precio público), NO
  con la cuenta de cliente registrado de Agustín. Esto es una decisión
  consciente tomada por ahora - los precios de invitado y de cliente
  logueado ("categorizado", según la cookie `customer_type`) podrían
  diferir, pero implementar el login agrega complejidad y por ahora no
  se activó. **Si en algún momento se necesita el precio real de
  cliente, hay que revisar esto.**
- Cada producto tiene **DOS precios**, no uno:
  - `precio_unitario`: precio comprando de a 1, sin condiciones.
  - `precio_bulto_cerrado`: precio MÁS BARATO por unidad, pero **solo
    válido si comprás el pack cerrado completo** (ej. el "Cacao Toddy
    800gr" tiene bulto cerrado de 8 unidades - comprar 3 sueltas NO te
    da ese precio).
- **Limitación conocida**: no se pudo extraer cuántas unidades trae
  cada pack cerrado (el dato "Presentación: 1 / 8 / 12 / 18" no está
  en el HTML como texto, se arma con JavaScript a partir de un JSON
  embebido en un `<script>` - parsearlo bien requeriría más trabajo,
  se dejó pendiente). Por eso el dashboard NUNCA asume automáticamente
  que vas a conseguir el precio de bulto - siempre hay que confirmar
  la cantidad mínima en la ficha real del producto antes de comprar.

---

## 3. Los 5 rubros scrapeados (y por qué esos 5)

Maxiconsumo tiene 9 categorías raíz. Se scrapean solo 5, relevantes
para gasto familiar de comida/limpieza:

- ✅ Almacén, Bebidas, Frescos, Congelados, Limpieza
- ❌ Perfumería, Mascotas, Hogar y Bazar, Electro (descartados a
  propósito, no aportan al objetivo del proyecto)

Volumen real (a la fecha de este documento): **7.308 productos**
totales entre los 5 rubros. Almacén solo tiene 3.674 (la mitad del
catálogo).

---

## 4. Por qué NO se re-scrapea todo el catálogo todos los días

Este es el punto que más confunde, así que va con detalle.

**El costo real de un scrape completo**: Magento devuelve hasta 96
productos por request (`product_list_limit=96`). Almacén con 3.674
productos necesita solo **39 requests** para traerse TODO. Cada
request tarda ~20-25 segundos en responder (el servidor de
Maxiconsumo es lento calculando precios de 96 productos a la vez) -
por eso un scrape completo de Almacén tarda **~17-20 minutos**. Los 5
rubros juntos: **~40 minutos a 1 hora**.

Hacer esto todos los días, para los 5 rubros, sería: (a) pesado para
el servidor de Maxiconsumo (mala práctica de scraping, riesgo de que
nos bloqueen), y (b) probablemente innecesario, porque los precios
mayoristas no cambian todos los días.

**La solución: chequeo barato antes del trabajo caro.**

En vez de scrapear todo, cada rubro guarda una "muestra" de sus
**primeras 2 páginas de categoría** (hasta 192 productos, el orden de
"Posición" de Maxiconsumo es estable así que son siempre los mismos
productos). Para chequear si algo cambió, alcanza con pedir esas 2
páginas de vuelta (**2 requests**, no 39) y comparar los precios
contra los guardados.

- Si **ningún precio cambió** en la muestra → se asume que el rubro
  entero no tuvo actualizaciones, y NO se dispara el scrape completo.
- Si **algún precio cambió** → SÍ se dispara el scrape completo de ESE
  rubro (y solo ese), para traer los datos reales actualizados.

**Por qué 2 páginas de categoría y no productos individuales**: se
evaluó chequear productos sueltos por su ficha individual, pero eso
hubiera necesitado **más requests** que el scrape completo (192
fichas individuales > 39 páginas de categoría) - contraproducente. Por
eso el chequeo usa páginas de categoría (que traen 96 productos de un
solo request), no fichas de producto sueltas.

**Por qué solo 1 rubro por día**: para repartir la carga en el
tiempo, cada corrida diaria (cron a las 3am) elige el rubro **más
atrasado** (el que hace más tiempo no se actualiza, o nunca) y solo
chequea/actualiza ESE. En ~5 días se completa un ciclo por los 5
rubros. Esto significa que un cambio de precio en un rubro puede
tardar hasta varios días en detectarse, dependiendo de cuándo le toque
el turno - trade-off aceptado a cambio de no sobrecargar el sitio.

---

## 5. Archivos del repo y qué hace cada uno

### Scraping core
- **`maxiconsumo_scraper.py`**: el módulo base. Login opcional
  (actualmente sin usar), `fetch_pagina_categoria()` (pide 1 página),
  `scrape_category()` (pagina hasta el final, usa la anterior en
  loop), `_parse_producto()` (extrae SKU/nombre/precio/stock de una
  tarjeta de categoría por texto, con selectores CSS y fallbacks),
  `parsear_precio_ficha_individual()` (mismo parseo pero para la
  ficha de UN producto, usado en chequeos puntuales).
- **`precios_normalizar_unidades.py`**: **clon** del mismo archivo
  que usa Índice LCV (no está sincronizado, es una copia
  independiente). Extrae gramos/ml/unidades del nombre de un
  producto vía regex, para poder comparar precios entre presentaciones
  distintas.
- **`mayorista_normalizar.py`**: wrapper específico de mayoristas
  sobre el archivo anterior. Auto-detecta si un producto se mide en
  kg/L/unidad (sin necesitar el diccionario de "rubro por categoría"
  que sí usa Índice LCV) y normaliza LOS DOS precios (bulto y
  unitario) a la misma unidad.

### Scripts de corrida
- **`scraper_por_rubro.py`**: scrapea cada rubro por separado,
  guardando cada uno en su propio archivo (`output/rubro_<nombre>.csv`
  y `.json`) apenas termina - así una falla en un rubro no hace
  perder el trabajo de los demás. Soporta `--solo <rubro>` para
  reintentar uno puntual.
- **`scraper_completo.py`**: versión más vieja, scrapea los 5 rubros
  en una sola corrida larga y guarda todo junto al final (menos
  resiliente a fallas que `scraper_por_rubro.py` - se mantiene por
  compatibilidad pero no es la forma recomendada de correrlo hoy).
- **`elegir_referencias.py`**: arma `estado_rubros.json` tomando los
  primeros 192 productos de los datos ya scrapeados de cada rubro,
  como la "muestra" de comparación (ver sección 4).
- **`main_actualizar.py`**: el orquestador diario. Elige el rubro
  más atrasado, chequea su muestra de 2 páginas, decide si dispara
  scrape completo o no, y actualiza `estado_rubros.json` con el
  resultado (`completo` / `sin_cambios` / `incompleto`).

### Base de datos
- **`crear_historico_mayorista.py`**: crea `historico_mayorista.db`
  (SQLite) y la tabla `historico_mayoristas` (una sola tabla para
  TODOS los mayoristas, distinguidos por columna `tienda` - así Yaguar
  entra sin cambiar el esquema). Cada corrida AGREGA filas nuevas, no
  pisa las viejas - se acumula el historial de precios en el tiempo,
  mismo espíritu que `historico_catalogo_completo` de Índice LCV.
- **`cargar_historico_mayorista.py`**: toma un JSON de rubro y lo
  inserta en la tabla.

### Dashboard
- **`generar_dashboard.py`**: lee de SQLite (no de los JSON sueltos),
  calcula la TENDENCIA de precio de cada producto (subió/bajó/igual,
  comparando la fila más reciente contra la anterior de ese SKU vía
  window function SQL), lee `estado_rubros.json` para armar un banner
  de estado por rubro, y genera el HTML final embebiendo todo.
- **`dashboard_template.html`**: la plantilla - buscador con
  tolerancia a errores de tipeo (distancia de Levenshtein), filtro por
  rubro, filtro de "ocultar sin precio", lista de compras con
  selector "Suelto" vs "Pack cerrado" por producto (nunca asume el
  precio de bulto por defecto, hay que elegirlo a propósito), links de
  búsqueda robustos a Maxiconsumo (ver sección 8).

### Automatización
- **`corrida_diaria_mayorista.sh`**: wrapper de cron. Activa el venv,
  corre `main_actualizar.py`, y si generó algún `rubro_*.json` nuevo
  en las últimas 24hs, lo carga a SQLite automáticamente.
- **Cron en el VPS**: `0 3 * * *` (todos los días a las 3am).

---

## 6. Campos de datos relevantes

| Campo | Qué es |
|---|---|
| `sku` | Código interno de Maxiconsumo - **NO sirve para comparar entre tiendas distintas** (cada una tiene su propio sistema de códigos). Solo sirve para trackear el mismo producto en el tiempo dentro de Maxiconsumo. |
| `estado_stock` | Texto literal: `"En stock"`, `"Sin stock"`, o `"Disponibilidad Critica"`. Este último es importante: quiere decir que Maxiconsumo **no publica precio** para ese producto (confirmado a mano contra varios casos reales) - no es un bug del scraper. |
| `precio_bulto_cerrado` / `precio_unitario` | Ver sección 2. |
| `precio_bulto_cerrado_normalizado` / `precio_unitario_normalizado` | Los mismos precios pero en $/kg, $/L o $/unidad, para comparar entre presentaciones distintas del mismo producto (o contra otras tiendas, en el futuro). |
| `categoria_raiz` | El rubro (`"almacen.html"`, etc.) |

**Dato de negocio importante**: aproximadamente el **58% del catálogo
de Maxiconsumo no tiene precio publicado** ahora mismo (mayormente por
"Disponibilidad Crítica"). No es un problema de nuestro scraper, es un
estado real del catálogo del proveedor.

---

## 7. Estructura del estado (`estado_rubros.json`)

```json
{
  "almacen.html": {
    "paginas_muestra": 2,
    "precios_muestra": { "4427": 6399.90, "12532": 16999.90, ... },
    "ultima_actualizacion_completa": "2026-08-22T03:00:00+00:00",
    "ultimo_resultado": "completo"  // o "sin_cambios" o "incompleto"
  },
  ...
}
```

---

## 8. Problema conocido: links directos a productos se rompen

Cuando Maxiconsumo reorganiza categorías (mueve un producto de lugar),
la URL guardada en el scrape queda apuntando a un 404. El sistema de
chequeo por muestra (sección 4) solo mira **precio**, no detecta estos
movimientos de categoría - así que un link puede quedar roto bastante
tiempo sin que nada lo note automáticamente.

**Mitigación actual**: el dashboard prioriza un link de **búsqueda por
nombre** (`catalogsearch/result/?q=...`) sobre el link directo, porque
ese no depende de la categoría y no se rompe con estos movimientos.

---

## 9. Pendiente de diseñar (motivo de este documento)

- **Canasta personalizada por Guardián**: usar el Telegram ID
  existente de Guardianes (no login nuevo) para que cada familia
  guarde su lista de productos habituales, y el sistema muestre la
  mejor opción cruzando Índice LCV (supers) + Índice Mayorista.
- **Detector de "ofertas imperdibles"**: producto cuyo precio
  normalizado está muy por debajo del promedio/mediana del resto de
  tiendas para ese mismo producto en ese momento (no comparado con su
  propio historial, sino contra el resto del mercado).
- **Botón del bot**: "Ver precios" desplegándose en "Precios Super"
  (ya existe, va a `precios.html`) y "Precios Mayorista" (nuevo, va a
  `/mayorista/`).
- **Yaguar**: segundo mayorista, WordPress con login de "Acceso
  Comerciantes" - todavía sin empezar, estructura del HTML sin
  explorar.
- **Diarco**: descartado, no tiene tienda online navegable.
- **Login con precio de cliente real**: pendiente de decidir si vale
  la pena vs. seguir con precio de invitado.
