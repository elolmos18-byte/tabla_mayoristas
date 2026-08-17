#!/bin/bash
# corrida_diaria_mayorista.sh
#
# Wrapper para el cron diario de Índice Mayorista. Mismo espíritu que
# precios_corrida_diaria.sh de Índice LCV: activa el venv, corre el
# script de Python, y deja todo logueado para poder revisar después
# si algo falló.
#
# Se asume que este script vive en la raíz del proyecto (junto a
# main_actualizar.py), y que ya existe:
#   - el venv armado (python3 -m venv venv && pip install -r requirements.txt)
#   - la base de datos creada (python crear_historico_mayorista.py)
#   - el estado inicial armado (python elegir_referencias.py)
#
# Instalación en el cron (crontab -e):
#   0 3 * * * /home/lcv/tabla_mayoristas/corrida_diaria_mayorista.sh >> /home/lcv/tabla_mayoristas/cron.log 2>&1

set -e  # si algo falla, cortamos - no seguimos con pasos que dependen del anterior

cd "$(dirname "$0")"  # nos aseguramos de estar parados en la carpeta del proyecto

source venv/bin/activate

echo "=========================================="
echo "Corrida: $(date -Iseconds)"
echo "=========================================="

python main_actualizar.py

# Si main_actualizar.py generó un rubro_*.json NUEVO en las últimas 24hs
# (señal de que sí hubo scrape completo, no solo el chequeo de muestra),
# lo cargamos al historial de SQLite.
ARCHIVOS_NUEVOS=$(find output -name "rubro_*.json" -mtime -1 2>/dev/null || true)

if [ -n "$ARCHIVOS_NUEVOS" ]; then
  echo ""
  echo "Archivos actualizados en las últimas 24hs, cargando a SQLite:"
  for archivo in $ARCHIVOS_NUEVOS; do
    echo "  -> $archivo"
    python cargar_historico_mayorista.py "$archivo"
  done
else
  echo ""
  echo "No hubo scrapes completos nuevos hoy (probablemente sin cambios de precio) - nada para cargar a SQLite."
fi

# Regeneramos el dashboard público SIEMPRE, haya habido cambios de
# precio o no - porque también hay que reflejar cambios en la
# plantilla (dashboard_template.html) aunque los datos no se hayan
# movido. Es una operación barata: solo lee la base SQLite local, no
# pide nada a Maxiconsumo, así que no complica correrla todos los días.
# Escribe en public/dashboard.html por defecto, que es la ruta que
# sirve Nginx (alias /home/lcv/tabla_mayoristas/public/).
echo ""
echo "Regenerando dashboard público..."
python generar_dashboard.py

echo ""
echo "Corrida terminada: $(date -Iseconds)"
echo ""
