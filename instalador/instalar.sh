#!/bin/bash
# ===================================================================
# SCORM Builder · Instalador automático para Linux
# ===================================================================
# Este script:
#   1. Comprueba que tienes Python 3.10+
#   2. Crea un entorno aislado para no ensuciar tu sistema
#   3. Instala el motor scorm-builder
#   4. Instala la mini-app web
#   5. Crea un lanzador en el escritorio
#   6. Te da las instrucciones finales
# ===================================================================

set -e  # parar al primer error

# Colores para que se vea bonito
ROJO='\033[0;31m'
VERDE='\033[0;32m'
AZUL='\033[0;34m'
AMARILLO='\033[1;33m'
SIN_COLOR='\033[0m'
NEGRITA='\033[1m'

echo ""
echo -e "${AZUL}${NEGRITA}╔══════════════════════════════════════════════════════════╗${SIN_COLOR}"
echo -e "${AZUL}${NEGRITA}║                                                          ║${SIN_COLOR}"
echo -e "${AZUL}${NEGRITA}║      SCORM Builder · Instalador automático               ║${SIN_COLOR}"
echo -e "${AZUL}${NEGRITA}║                                                          ║${SIN_COLOR}"
echo -e "${AZUL}${NEGRITA}╚══════════════════════════════════════════════════════════╝${SIN_COLOR}"
echo ""

# Detectar la carpeta del script (donde está el proyecto)
PROYECTO_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
echo -e "${AMARILLO}→${SIN_COLOR} Detectado proyecto en: ${PROYECTO_DIR}"
echo ""

# ===================================================================
# 1. Comprobar Python
# ===================================================================
echo -e "${AMARILLO}→${SIN_COLOR} Comprobando Python..."

if command -v python3 &> /dev/null; then
    PYTHON=python3
elif command -v python &> /dev/null; then
    PYTHON=python
else
    echo ""
    echo -e "${ROJO}✗ ERROR:${SIN_COLOR} No tienes Python instalado."
    echo ""
    echo "Para instalarlo, abre una terminal y ejecuta:"
    echo -e "  ${NEGRITA}sudo apt install python3 python3-venv python3-pip${SIN_COLOR}"
    echo ""
    echo "Cuando lo tengas, vuelve a ejecutar este instalador."
    echo ""
    read -p "Pulsa Enter para cerrar..."
    exit 1
fi

VERSION=$($PYTHON --version 2>&1 | awk '{print $2}')
MAJOR=$(echo $VERSION | cut -d. -f1)
MINOR=$(echo $VERSION | cut -d. -f2)

if [ "$MAJOR" -lt 3 ] || ([ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 10 ]); then
    echo ""
    echo -e "${ROJO}✗ ERROR:${SIN_COLOR} Tu Python es la versión ${VERSION}, pero necesitamos 3.10 o superior."
    echo ""
    echo "Para actualizarlo:"
    echo -e "  ${NEGRITA}sudo apt install python3.12 python3.12-venv${SIN_COLOR}"
    echo ""
    read -p "Pulsa Enter para cerrar..."
    exit 1
fi

echo -e "  ${VERDE}✓${SIN_COLOR} Python $VERSION encontrado"
echo ""

# ===================================================================
# 2. Crear entorno virtual
# ===================================================================
echo -e "${AMARILLO}→${SIN_COLOR} Creando entorno aislado (no afecta a tu sistema)..."

VENV_DIR="$PROYECTO_DIR/.venv"

if [ -d "$VENV_DIR" ]; then
    echo -e "  ${AMARILLO}!${SIN_COLOR} Ya existía. Lo borramos y recreamos."
    rm -rf "$VENV_DIR"
fi

# Verificar que python3-venv está disponible
if ! $PYTHON -c "import venv" &> /dev/null; then
    echo ""
    echo -e "${ROJO}✗ ERROR:${SIN_COLOR} Falta el módulo venv de Python."
    echo ""
    echo "Instálalo con:"
    echo -e "  ${NEGRITA}sudo apt install python3-venv${SIN_COLOR}"
    echo ""
    read -p "Pulsa Enter para cerrar..."
    exit 1
fi

$PYTHON -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

echo -e "  ${VERDE}✓${SIN_COLOR} Entorno creado en .venv/"
echo ""

# ===================================================================
# 3. Actualizar pip
# ===================================================================
echo -e "${AMARILLO}→${SIN_COLOR} Actualizando herramientas de instalación..."
pip install --quiet --upgrade pip setuptools wheel
echo -e "  ${VERDE}✓${SIN_COLOR} Listo"
echo ""

# ===================================================================
# 4. Instalar el motor
# ===================================================================
echo -e "${AMARILLO}→${SIN_COLOR} Instalando el motor scorm-builder (esto tarda 1-2 minutos)..."
cd "$PROYECTO_DIR/libreria"
pip install --quiet -e .
echo -e "  ${VERDE}✓${SIN_COLOR} Motor instalado"
echo ""

# ===================================================================
# 5. Instalar la mini-app web
# ===================================================================
echo -e "${AMARILLO}→${SIN_COLOR} Instalando la mini-app web..."
pip install --quiet flask
echo -e "  ${VERDE}✓${SIN_COLOR} Mini-app instalada"
echo ""

# ===================================================================
# 6. Crear lanzador en el escritorio (si hay entorno gráfico)
# ===================================================================
if [ -d "$HOME/Escritorio" ] || [ -d "$HOME/Desktop" ]; then
    if [ -d "$HOME/Escritorio" ]; then
        DESKTOP="$HOME/Escritorio"
    else
        DESKTOP="$HOME/Desktop"
    fi

    LAUNCHER="$DESKTOP/SCORM Builder.desktop"

    cat > "$LAUNCHER" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=SCORM Builder
Comment=Convierte Word en SCORM
Exec=bash -c "cd '$PROYECTO_DIR' && source .venv/bin/activate && python instalador/app_local.py"
Icon=$PROYECTO_DIR/instalador/icono.png
Terminal=false
Categories=Office;Education;
EOF
    chmod +x "$LAUNCHER"

    # Marcar como confiable (necesario en GNOME modernos)
    gio set "$LAUNCHER" metadata::trusted true 2>/dev/null || true

    echo -e "${AMARILLO}→${SIN_COLOR} Lanzador creado en el escritorio"
    echo -e "  ${VERDE}✓${SIN_COLOR} Busca el icono ${NEGRITA}'SCORM Builder'${SIN_COLOR} en tu escritorio"
    echo ""
fi

# ===================================================================
# 7. Crear comando rápido `scorm-app`
# ===================================================================
LAUNCH_SCRIPT="$PROYECTO_DIR/abrir_app.sh"
cat > "$LAUNCH_SCRIPT" << EOF
#!/bin/bash
cd "$PROYECTO_DIR"
source .venv/bin/activate
python instalador/app_local.py
EOF
chmod +x "$LAUNCH_SCRIPT"

# ===================================================================
# Final
# ===================================================================
echo ""
echo -e "${VERDE}${NEGRITA}╔══════════════════════════════════════════════════════════╗${SIN_COLOR}"
echo -e "${VERDE}${NEGRITA}║                                                          ║${SIN_COLOR}"
echo -e "${VERDE}${NEGRITA}║   ✓ Instalación completada                               ║${SIN_COLOR}"
echo -e "${VERDE}${NEGRITA}║                                                          ║${SIN_COLOR}"
echo -e "${VERDE}${NEGRITA}╚══════════════════════════════════════════════════════════╝${SIN_COLOR}"
echo ""
echo -e "${NEGRITA}Cómo usar la app:${SIN_COLOR}"
echo ""
echo -e "  ${AZUL}OPCIÓN 1 (más fácil):${SIN_COLOR}"
echo -e "  Haz doble clic en el icono ${NEGRITA}'SCORM Builder'${SIN_COLOR} de tu escritorio."
echo ""
echo -e "  ${AZUL}OPCIÓN 2:${SIN_COLOR}"
echo -e "  Haz doble clic en el archivo ${NEGRITA}abrir_app.sh${SIN_COLOR} de la carpeta del proyecto."
echo ""
echo -e "  ${AZUL}OPCIÓN 3 (terminal):${SIN_COLOR}"
echo -e "  ${NEGRITA}cd '$PROYECTO_DIR'${SIN_COLOR}"
echo -e "  ${NEGRITA}./abrir_app.sh${SIN_COLOR}"
echo ""
echo -e "Cuando se abra, el navegador mostrará la app en ${AZUL}http://localhost:5000${SIN_COLOR}"
echo ""

read -p "Pulsa Enter para cerrar este instalador..."
