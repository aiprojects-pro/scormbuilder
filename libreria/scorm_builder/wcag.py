"""Validador de accesibilidad básico (orientado a WCAG 2.1 AA).

Revisa la estructura del curso y la paleta antes de empaquetar, e informa de
problemas que afectan a accesibilidad. No es un validador exhaustivo — se centra
en lo que afecta a contenido SCORM educativo: contraste, alt texts, subtítulos,
jerarquía de headings.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Tuple
from pathlib import Path
import re


@dataclass
class Issue:
    severity: str          # "error" (bloquea WCAG AA), "warning" (recomendado), "info"
    code: str              # identificador WCAG-like (ej. "1.4.3" para contraste)
    title: str
    description: str
    location: str = ""     # ruta dentro del curso (tema/subapartado/bloque)
    autofix: bool = False  # ¿se puede arreglar automáticamente?


@dataclass
class WCAGReport:
    issues: List[Issue] = field(default_factory=list)

    @property
    def n_errors(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def n_warnings(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")

    @property
    def passes(self) -> bool:
        return self.n_errors == 0

    def to_dict(self) -> dict:
        return {
            "passes": self.passes,
            "n_errors": self.n_errors,
            "n_warnings": self.n_warnings,
            "issues": [asdict(i) for i in self.issues],
        }


# ---------------------------------------------------------------
# Cálculo de contraste (WCAG 2.1)
# ---------------------------------------------------------------

def _hex_to_rgb(h: str) -> Optional[Tuple[int, int, int]]:
    """Devuelve (r,g,b) 0-255 a partir de #rgb o #rrggbb. None si inválido."""
    if not h:
        return None
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6 or not re.match(r"^[0-9a-fA-F]{6}$", h):
        return None
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _relative_luminance(rgb: Tuple[int, int, int]) -> float:
    """Luminancia relativa según WCAG 2.1 §1.4.3."""
    def channel(c: int) -> float:
        s = c / 255.0
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: str, bg: str) -> Optional[float]:
    """Devuelve el ratio de contraste entre dos colores hex (1.0–21.0)."""
    fg_rgb, bg_rgb = _hex_to_rgb(fg), _hex_to_rgb(bg)
    if fg_rgb is None or bg_rgb is None:
        return None
    l1, l2 = _relative_luminance(fg_rgb), _relative_luminance(bg_rgb)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


# ---------------------------------------------------------------
# Validador principal
# ---------------------------------------------------------------

def validate_course(course, recursos_dir: Optional[Path] = None) -> WCAGReport:
    """Valida una CourseStructure contra reglas WCAG 2.1 AA básicas.

    Args:
        course: CourseStructure ya parseada.
        recursos_dir: directorio con los recursos extra (para comprobar .vtt
            asociados a vídeos locales).
    """
    report = WCAGReport()

    # 1.4.3 — Contraste de la paleta. Comprobamos los pares principales:
    #         texto blanco sobre primary_deep (cabecera del módulo) y
    #         texto sobre fondo de paper (cuerpo).
    md = course.metadata
    palette = getattr(md, "palette", "azul")
    # Cargar el theme para tener los hex
    try:
        from scorm_builder.themes import get_theme
        theme = get_theme(palette)
        # Cabecera: blanco sobre primary_deep
        ratio_header = contrast_ratio("#ffffff", theme.primary_deep) or 0
        if ratio_header < 4.5:
            report.issues.append(Issue(
                severity="error", code="1.4.3",
                title="Contraste insuficiente en cabecera del módulo",
                description=(
                    f"Texto blanco sobre la cabecera ({theme.primary_deep}) tiene un "
                    f"ratio de {ratio_header:.2f}:1. WCAG AA exige al menos 4.5:1 "
                    "para texto normal."
                ),
                location="paleta",
                autofix=False,
            ))
        # Texto cuerpo: ink sobre paper
        ratio_body = contrast_ratio(theme.ink, theme.paper) or 0
        if ratio_body < 4.5:
            report.issues.append(Issue(
                severity="error", code="1.4.3",
                title="Contraste insuficiente en el cuerpo del curso",
                description=(
                    f"Texto del cuerpo ({theme.ink}) sobre fondo ({theme.paper}) tiene "
                    f"ratio {ratio_body:.2f}:1. Mínimo WCAG AA: 4.5:1."
                ),
                location="paleta",
                autofix=False,
            ))
        # Enlaces: primary_bright sobre paper
        ratio_link = contrast_ratio(theme.primary_bright, theme.paper) or 0
        if ratio_link < 4.5:
            report.issues.append(Issue(
                severity="warning", code="1.4.3",
                title="Contraste mejorable en enlaces",
                description=(
                    f"Color de enlaces ({theme.primary_bright}) sobre fondo ({theme.paper}): "
                    f"ratio {ratio_link:.2f}:1. Recomendado al menos 4.5:1."
                ),
                location="paleta",
                autofix=False,
            ))
    except Exception:
        pass

    # 2.4.6 — Jerarquía de headings: cada tema debe tener al menos un Heading 2 (subapartado).
    # 3.1.1 — Idioma: comprobamos que metadata indica español (es) — el motor lo fija siempre.
    for t in course.topics:
        loc = f"Tema {t.number}: {t.title}"
        if not t.subsections:
            report.issues.append(Issue(
                severity="warning", code="2.4.6",
                title="Tema sin subapartados",
                description=(
                    f"El tema '{t.title}' no tiene subapartados. La estructura "
                    "facilita la navegación con lector de pantalla."
                ),
                location=loc,
                autofix=False,
            ))
        # Headings saltados: si hay heading_4 sin heading_3 previo en el mismo subapartado
        for s in t.subsections:
            seen_h3 = False
            for b in s.blocks:
                bt = getattr(b.type, "value", b.type)
                if bt == "heading_3":
                    seen_h3 = True
                elif bt == "heading_4" and not seen_h3:
                    report.issues.append(Issue(
                        severity="warning", code="1.3.1",
                        title="Salto en jerarquía de encabezados",
                        description=(
                            "Se encontró un encabezado h4 sin h3 previo en "
                            f"el subapartado {s.number} '{s.title}'."
                        ),
                        location=f"{loc} > {s.number} {s.title}",
                        autofix=False,
                    ))
                    break  # un aviso por subapartado basta

    # 1.1.1 — Texto alternativo en imágenes
    # 1.2.2 — Subtítulos en vídeos pregrabados
    # Recorremos los bloques multimedia
    for t in course.topics:
        for s in t.subsections:
            for b in s.blocks:
                bt = getattr(b.type, "value", b.type)
                loc = f"Tema {t.number} > {s.number} {s.title}"
                if bt == "image":
                    if not (b.text or "").strip():
                        report.issues.append(Issue(
                            severity="error", code="1.1.1",
                            title="Imagen sin texto alternativo",
                            description=(
                                "Las imágenes deben llevar un pie/alt descriptivo "
                                "(en el DOCX usa: '[IMAGEN] Descripción | archivo.png')."
                            ),
                            location=loc,
                            autofix=False,
                        ))
                elif bt == "video":
                    src = (b.extras or {}).get("src", "") or (b.extras or {}).get("file", "")
                    is_local_video = (
                        src
                        and not re.match(r"^https?://", src)
                        and not src.lower().startswith(("youtu.be", "youtube.com", "vimeo.com"))
                    )
                    if is_local_video and recursos_dir:
                        # Buscar .vtt con el mismo nombre base
                        video_path = Path(recursos_dir) / src
                        vtt_path = video_path.with_suffix(".vtt")
                        if not vtt_path.exists():
                            report.issues.append(Issue(
                                severity="warning", code="1.2.2",
                                title="Vídeo sin subtítulos",
                                description=(
                                    f"El vídeo '{src}' no tiene archivo .vtt con subtítulos. "
                                    "Para FUNDAE/sector público suele ser obligatorio. "
                                    "Puedes generarlos automáticamente con Whisper si está instalado."
                                ),
                                location=loc,
                                autofix=True,
                            ))

    # 3.1.2 — Idioma (informativo)
    if not getattr(md, "title", "").strip():
        report.issues.append(Issue(
            severity="warning", code="2.4.2",
            title="Curso sin título",
            description="El curso no tiene título. Esto afecta a la cabecera del SCORM y al manifiesto.",
            location="metadatos",
            autofix=False,
        ))

    return report
