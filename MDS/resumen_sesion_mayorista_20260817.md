# Resumen de sesión — Índice Mayorista (17/ago/2026)

> Repaso de todo lo que se charló y cambió hoy, para retomar mañana sin
> tener que reconstruir el contexto de nuevo. Complementa (no
> reemplaza) `arquitectura_mayorista.md`, que sigue siendo el
> documento de referencia de cómo funciona el sistema en general.

---

## 1. Qué se hizo hoy (cerrado y funcionando en producción)

### 1.1 Buscador con Fuse.js
**Problema:** el buscador viejo (`distanciaEdicion` + `palabraCoincide` en
`dashboard_template.html`) exigía que TODAS las palabras escritas
matchearan, palabra por palabra, en el nombre del producto. Buscar
"galletitas dulces rumba" no encontraba nada si el producto no tenía
literalmente la palabra "dulces".

**Solución aplicada:** se reemplazó por [Fuse.js](https://www.fusejs.io/)
(cargado por CDN), que compara la frase completa contra el nombre
completo con un puntaje de similitud, tolerando palabras de más/de
menos, orden distinto, y errores de tipeo.

- `threshold: 0.4` — umbral acordado (0 = exige match perfecto, 1 =
  deja pasar cualquier cosa). Se puede ajustar si en el uso real deja
  pasar ruido o tapa resultados válidos.
- `ignoreLocation: true` — no importa en qué parte del nombre esté la
  coincidencia.
- Se borraron `distanciaEdicion` y `palabraCoincide`, ya sin uso.
- Cuando hay búsqueda activa, la tabla respeta el orden por relevancia
  de Fuse (mejor match primero) en vez del combo de ordenar por
  precio/nombre.

**Estado:** probado y funcionando en producción.

---

### 1.2 Gap descubierto: el cron nunca regeneraba el dashboard público
**Problema:** `corrida_diaria_mayorista.sh` (cron diario, 3am) corría
`main_actualizar.py` y `cargar_historico_mayorista.py`, pero **nunca
llamaba a `generar_dashboard.py`** — el único script que arma el HTML
público leyendo de `historico_mayorista.db`. Resultado: la base de
datos se actualizaba sola todos los días, pero el dashboard que ve la
gente podía quedar desactualizado por tiempo indefinido sin que nada
lo notara.

**Solución aplicada:** se agregó `python generar_dashboard.py` como
último paso del script, corriendo **siempre** (no solo cuando hubo
scrape completo nuevo) — porque también hace falta regenerar cuando
lo que cambió es la plantilla (`dashboard_template.html`), no los
datos. Es una operación barata (solo lee SQLite local, no pide nada a
Maxiconsumo).

**Estado:** probado con una corrida manual completa en el servidor,
terminó bien y regeneró `public/dashboard.html` (7.305 productos,
3.98 MB).

---

### 1.3 Links de producto poco confiables
**Problema real (no cosmético):** el Guardián necesita entrar a la
ficha del producto en Maxiconsumo para confirmar cuántas unidades trae
el pack cerrado (dato que el scraper no puede extraer — ver
`arquitectura_mayorista.md` sección 2). El link que existía para eso
podía romper de dos formas distintas:
- **Link directo** (`url_producto`, viene del scraping): rompe con 404
  si Maxiconsumo reorganizó categorías después del scrape.
- **Búsqueda por nombre completo** (la que se usaba antes): rompió con
  **HTTP 500 del lado de Maxiconsumo** al mandarle una query larga y
  rara (nombre + peso, ej. "GALLETITAS SONRISAS 118 GR").

**Solución aplicada (decisión final, después de varias vueltas):**
- Se sacó el link directo (`url_producto`) por completo.
- Se sacó la búsqueda por nombre completo por completo.
- Queda **solo un link**: búsqueda por SKU (`urlBusquedaSku(sku)`) —
  un solo token numérico, mucho menos propenso a romper el buscador de
  Maxiconsumo que una frase larga, y preciso (identifica un único
  producto).
- Texto del link: **"Confirmar en página ↗"** (se descartaron "Buscar
  por SKU", "Ver ficha en Maxiconsumo", etc. — se buscó algo más
  ligado al tono del juego/personaje, pero quedó pendiente esa parte
  del lore, ver sección 3).
- Se aplicó en los dos lugares del HTML: la columna "Producto" de la
  tabla, y el aviso de "pack cerrado" en el panel de "Mi lista".

**Estado:** probado con el caso real que había fallado (SKU 4699,
Galletitas Sonrisas) — encontró el producto exacto, con precio de
bulto/unitario y la info de "Presentación 1/36". Confirmado por
Agustín como funcionando.

---

## 2. Hallazgo importante de infraestructura (para tener siempre presente)

`tabla_mayoristas` es un **proyecto completamente aparte** de LCdV:
- Repo propio: `github.com/elolmos18-byte/tabla_mayoristas`
- Vive en el VPS en `/home/lcv/tabla_mayoristas` (LCdV vive en
  `/home/lcv/La-comunidad-del-Viento`)
- Base de datos propia: **SQLite** (`historico_mayorista.db`) — LCdV
  usa **PostgreSQL**. Son dos motores distintos, a propósito, para que
  no se toquen entre sí fácilmente.
- Dashboard servido por Nginx desde `alias
  /home/lcv/tabla_mayoristas/public/` → `guardianesdelviento.com/mayorista/`
- Hoy es un sistema **100% estático**: un cron nocturno genera un HTML
  y no hay ningún servidor corriendo que reciba pedidos en vivo (no
  hay una API tipo `lcv_api`/`lcv_bot` para este proyecto).

Documentado a fondo en `arquitectura_mayorista.md` (que además quedó
con una parte desactualizada: la sección 5 todavía describe el
buscador viejo por distancia de Levenshtein — hay que actualizarla la
próxima vez que se toque ese documento).

---

## 3. Pendientes para retomar

### 3.1 Subir el último cambio (texto del link)
Falta el ciclo completo de despliegue del cambio "Confirmar en
página":
```powershell
# en la PC, carpeta tabla_mayoristas
git add .
git commit -m "Texto del link a Maxiconsumo: Confirmar en pagina"
git push
```
```bash
# en el VPS
cd /home/lcv/tabla_mayoristas
git pull
source venv/bin/activate
python generar_dashboard.py
```

### 3.2 Texto del link — posible ajuste de tono con lore del juego
Se había planteado usar algo relacionado a un personaje del juego (el
"Señor del Viento" o similar) para el texto del link, en vez de algo
genérico. Quedó sin resolver por falta de contexto sobre ese
personaje — no hay ningún `.md` subido todavía que lo describa. Si
existe un documento de lore/personajes, subirlo la próxima vez para
poder ajustar el texto con ese tono si se quiere.

### 3.3 Lista de compras persistente atada al `telegram_id` (el pendiente grande)

**Lo que ya se acordó:**
- Nueva pantalla en el bot dentro de "Ver precios Madryn": botón al
  Índice (4 súper) y botón a "Mi lista Maxiconsumo".
- El `telegram_id` es la llave para identificar al Guardián — **sin
  necesidad de conectar Postgres con SQLite**, porque el `telegram_id`
  es un dato universal que ambos sistemas pueden usar de forma
  independiente. Confirmado como el enfoque correcto.
- La lista se guardaría en una tabla nueva **dentro de la base SQLite
  de `tabla_mayoristas`** (no en la Postgres de LCdV), con columnas
  tipo: `telegram_id`, `sku`, `cantidad`, `modo` (unitario/bulto).

**Lo que falta decidir (quedó como pregunta abierta):**
`tabla_mayoristas` hoy no tiene ningún servidor corriendo en vivo —
solo el cron nocturno que genera un HTML estático. Para que el
Guardián pueda agregar/sacar productos de su lista personal y que
quede guardado, hacen falta dos caminos posibles, y hay que elegir
uno:

- **Opción A — API liviana nueva, corriendo 24/7 en el VPS** (tipo
  FastAPI, gestionada con `supervisorctl` igual que `lcv_api`): el
  HTML llama a esta API en cada cambio (agregar, sacar, cambiar
  cantidad) y se guarda al instante. Más cómodo de usar día a día,
  pero es infraestructura nueva que hay que levantar y mantener.
- **Opción B — botón "Guardar mi lista" desde el HTML actual**: la
  lista se sigue armando en memoria como hoy (se pierde al recargar),
  pero en vez de solo "Copiar lista", un botón manda TODA la lista de
  una sola vez al bot (por ejemplo con un link que abre Telegram con
  un mensaje prearmado, o algo similar). Mucho más simple de construir
  hoy, pero menos fluido — no permite edición incremental día a día
  sin volver a mandar todo.

**Próximo paso:** decidir entre A y B (o algo intermedio) antes de
diseñar el detalle técnico.

---

## 4. Archivos tocados hoy (todos en el repo `tabla_mayoristas`)

| Archivo | Cambios |
|---|---|
| `dashboard_template.html` | Buscador (Fuse.js), links de producto (solo SKU, texto "Confirmar en página") |
| `corrida_diaria_mayorista.sh` | Se agregó el paso final `python generar_dashboard.py` |
| `arquitectura_mayorista.md` | Sin cambios hoy (aportado por el chat anterior) — pendiente actualizar la sección del buscador |

---

*Armado: 17/ago/2026, sesión de trabajo sobre Índice Mayorista.*
