#!/usr/bin/env bash
set -euo pipefail

echo "======================================================"
echo " SISTEMA CONTABLE FF - ARRANQUE LIMPIO STREAMLIT"
echo "======================================================"

echo ""
echo "=== DIRECTORIO ACTUAL ==="
pwd

echo ""
echo "=== GIT STATUS ==="
git status --short || true

echo ""
echo "=== ÚLTIMO COMMIT ==="
git log --oneline -5 || true

echo ""
echo "=== MATANDO STREAMLIT VIEJO ==="
pkill -f "streamlit" || true
sleep 2

echo ""
echo "=== PROCESOS STREAMLIT LUEGO DE MATAR ==="
ps aux | grep "streamlit" | grep -v grep || echo "No hay procesos Streamlit activos."

echo ""
echo "=== LIMPIANDO CACHES PYTHON ==="
find . -type d -name "__pycache__" -prune -exec rm -rf {} +
rm -rf .pytest_cache

echo ""
echo "=== HUELLA DEL MÓDULO BANCOS ==="
python3 - <<'PY'
from pathlib import Path
import hashlib
import importlib
import inspect

import modulos.bancos as bancos

ruta = Path(inspect.getfile(bancos)).resolve()
contenido = ruta.read_text(encoding="utf-8")
sha = hashlib.sha256(contenido.encode("utf-8")).hexdigest()[:16]

print("Archivo importado:", ruta)
print("SHA256 corto:", sha)
print("Tiene 'Resumen / Estadísticas de Ventas':", "Resumen / Estadísticas de Ventas" in contenido)
print("Tiene 'Libro IVA Ventas':", "Libro IVA Ventas" in contenido)
print("Tiene 'Asientos propuestos de Banco / Caja':", "Asientos propuestos de Banco / Caja" in contenido)
print("Tiene 'Vista por asiento agrupado':", "Vista por asiento agrupado" in contenido)
PY

echo ""
echo "=== BASE DE DATOS REAL ==="
python3 - <<'PY'
from database import conectar

conn = conectar()
cur = conn.cursor()

cur.execute("PRAGMA database_list")
for row in cur.fetchall():
    print(row)

for tabla in [
    "bancos_importaciones",
    "bancos_movimientos",
    "bancos_asientos_propuestos",
    "bancos_grupos_fiscales",
    "bancos_conciliaciones",
    "bancos_conciliaciones_detalle",
]:
    try:
        cur.execute(f"SELECT COUNT(*) FROM {tabla}")
        print(f"{tabla}: {cur.fetchone()[0]}")
    except Exception as e:
        print(f"{tabla}: ERROR {e}")

conn.close()
PY

echo ""
echo "=== VALIDACIÓN PY_COMPILE ==="
python3 -m py_compile main.py core/ui.py modulos/bancos.py services/bancos_operaciones_service.py tests/test_bancos.py

echo ""
echo "=== VALIDACIÓN PYTEST ==="
python3 -m pytest tests -q

echo ""
echo "=== LEVANTANDO STREAMLIT ÚNICO ==="
nohup python3 -m streamlit run main.py \
  --server.port 8501 \
  --server.address 0.0.0.0 \
  --browser.gatherUsageStats false \
  > /tmp/sistema_contable_streamlit.log 2>&1 &

sleep 5

echo ""
echo "=== PROCESO STREAMLIT ACTIVO ==="
ps aux | grep "streamlit run main.py" | grep -v grep || true

echo ""
echo "=== PUERTO 8501 ==="
ss -ltnp | grep ':8501' || echo "NO HAY NADA ESCUCHANDO EN 8501"

echo ""
echo "=== RESPUESTA LOCAL ==="
curl -I http://127.0.0.1:8501 || true

echo ""
echo "=== LOG STREAMLIT ==="
tail -n 30 /tmp/sistema_contable_streamlit.log || true

echo ""
echo "======================================================"
echo " ARRANQUE FINALIZADO"
echo " Abrí nuevamente el puerto 8501 desde Codespaces."
echo " Si el navegador seguía abierto, cerrá esa pestaña y abrí una nueva."
echo "======================================================"
