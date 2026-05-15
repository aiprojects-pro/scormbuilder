"""Paletas de color y configuración visual del curso."""
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class Theme:
    """Define los colores y la tipografía de un curso."""
    name: str
    label: str
    # Colores principales
    ink: str = "#0F172A"
    ink_soft: str = "#1E293B"
    ink_mute: str = "#475569"
    paper: str = "#F8FAFC"
    paper_warm: str = "#F1F5F9"
    paper_deep: str = "#E2E8F0"
    primary_deep: str = "#0A2540"  # cabecera
    primary: str = "#1D4ED8"        # acento principal
    primary_bright: str = "#2563EB"
    primary_pale: str = "#DBEAFE"
    primary_mist: str = "#EFF6FF"
    accent: str = "#B8893A"          # color de detalle
    alert: str = "#DC2626"
    warn: str = "#D97706"
    ok: str = "#059669"
    # Tipografía
    serif_font: str = "Fraunces"
    sans_font: str = "Plus Jakarta Sans"
    mono_font: str = "JetBrains Mono"


# Paletas predefinidas
THEMES: Dict[str, Theme] = {
    "azul": Theme(
        name="azul",
        label="Azul corporativo",
        primary_deep="#0A2540",
        primary="#1D4ED8",
        primary_bright="#2563EB",
        primary_pale="#DBEAFE",
        primary_mist="#EFF6FF",
        accent="#B8893A",
    ),
    "crimson": Theme(
        name="crimson",
        label="Crimson editorial",
        primary_deep="#1A0A0A",
        primary="#A8201A",
        primary_bright="#C8261F",
        primary_pale="#FCE8E6",
        primary_mist="#FFF8F8",
        paper="#FAF6EF",
        paper_warm="#F2EBDF",
        paper_deep="#E8DFCE",
        accent="#B8893A",
    ),
    "teal": Theme(
        name="teal",
        label="Teal sereno",
        primary_deep="#143534",
        primary="#1F4E4D",
        primary_bright="#2D7B79",
        primary_pale="#CCEAE9",
        primary_mist="#E6F0EF",
        paper="#FAF6EF",
        paper_warm="#F2EBDF",
        paper_deep="#E8DFCE",
        accent="#B8893A",
    ),
    "verde": Theme(
        name="verde",
        label="Verde naturaleza",
        primary_deep="#064E3B",
        primary="#047857",
        primary_bright="#10B981",
        primary_pale="#D1FAE5",
        primary_mist="#ECFDF5",
        accent="#B45309",
    ),
    "morado": Theme(
        name="morado",
        label="Morado creativo",
        primary_deep="#3B0764",
        primary="#6D28D9",
        primary_bright="#8B5CF6",
        primary_pale="#EDE9FE",
        primary_mist="#F5F3FF",
        accent="#D97706",
    ),
    "naranja": Theme(
        name="naranja",
        label="Naranja vital",
        primary_deep="#7C2D12",
        primary="#C2410C",
        primary_bright="#EA580C",
        primary_pale="#FFEDD5",
        primary_mist="#FFF7ED",
        accent="#1E40AF",
    ),
    # v0.5.10: paletas nuevas
    "amarillo": Theme(
        name="amarillo",
        label="Amarillo solar",
        primary_deep="#713F12",      # ámbar muy oscuro
        primary="#A16207",            # ámbar 700
        primary_bright="#EAB308",     # amarillo 500
        primary_pale="#FEF9C3",
        primary_mist="#FEFCE8",
        accent="#0E7490",             # complementario cian para acentos
    ),
    "negro": Theme(
        name="negro",
        label="Negro carbón",
        primary_deep="#0A0A0A",
        primary="#262626",
        primary_bright="#525252",
        primary_pale="#E5E5E5",
        primary_mist="#F5F5F5",
        accent="#B91C1C",             # acento rojo cuidado
    ),
    "magenta": Theme(
        name="magenta",
        label="Magenta vibrante",
        primary_deep="#500724",
        primary="#BE185D",
        primary_bright="#EC4899",
        primary_pale="#FCE7F3",
        primary_mist="#FDF2F8",
        accent="#0E7490",
    ),
    "cian": Theme(
        name="cian",
        label="Cian eléctrico",
        primary_deep="#083344",
        primary="#0E7490",
        primary_bright="#06B6D4",
        primary_pale="#CFFAFE",
        primary_mist="#ECFEFF",
        accent="#C2410C",
    ),
    "terracota": Theme(
        name="terracota",
        label="Terracota cálido",
        primary_deep="#431407",
        primary="#9A3412",
        primary_bright="#C2410C",
        primary_pale="#FED7AA",
        primary_mist="#FFEDD5",
        paper="#FAF6EF",
        paper_warm="#F2EBDF",
        paper_deep="#E8DFCE",
        accent="#365314",
    ),
    "oliva": Theme(
        name="oliva",
        label="Oliva clásico",
        primary_deep="#1A2E05",
        primary="#365314",
        primary_bright="#65A30D",
        primary_pale="#ECFCCB",
        primary_mist="#F7FEE7",
        paper="#FAF6EF",
        paper_warm="#F2EBDF",
        paper_deep="#E8DFCE",
        accent="#9A3412",
    ),
}


def list_themes() -> Dict[str, str]:
    """Lista todas las paletas disponibles {nombre: etiqueta}."""
    return {name: theme.label for name, theme in THEMES.items()}


def get_theme(name: str) -> Theme:
    """Obtiene una paleta por su nombre. Lanza ValueError si no existe."""
    if name not in THEMES:
        available = ", ".join(THEMES.keys())
        raise ValueError(f"Paleta '{name}' no encontrada. Disponibles: {available}")
    return THEMES[name]


def make_custom_theme(
    primary_deep: str,
    primary: str,
    primary_bright: str,
    primary_pale: str = "#DBEAFE",
    primary_mist: str = "#EFF6FF",
    accent: str = "#B8893A",
    name: str = "personalizada",
) -> Theme:
    """Crea una paleta personalizada a partir de los colores que dé el cliente."""
    return Theme(
        name=name,
        label="Personalizada",
        primary_deep=primary_deep,
        primary=primary,
        primary_bright=primary_bright,
        primary_pale=primary_pale,
        primary_mist=primary_mist,
        accent=accent,
    )


def theme_to_css_vars(theme: Theme) -> str:
    """Convierte un Theme en variables CSS listas para inyectar en el HTML."""
    return f""":root {{
  --ink: {theme.ink};
  --ink-soft: {theme.ink_soft};
  --ink-mute: {theme.ink_mute};
  --paper: {theme.paper};
  --paper-warm: {theme.paper_warm};
  --paper-deep: {theme.paper_deep};
  --primary-deep: {theme.primary_deep};
  --primary: {theme.primary};
  --primary-bright: {theme.primary_bright};
  --primary-pale: {theme.primary_pale};
  --primary-mist: {theme.primary_mist};
  --accent: {theme.accent};
  --alert: {theme.alert};
  --warn: {theme.warn};
  --ok: {theme.ok};
  --serif: '{theme.serif_font}', 'Georgia', serif;
  --sans: '{theme.sans_font}', -apple-system, system-ui, sans-serif;
  --mono: '{theme.mono_font}', 'Courier New', monospace;
}}"""
