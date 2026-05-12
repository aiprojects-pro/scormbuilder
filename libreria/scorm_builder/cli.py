"""CLI de scorm-builder.

Uso:
    scorm-builder generar curso.docx --output salida/ --tema azul
    scorm-builder validar curso.docx
    scorm-builder paletas
    scorm-builder plantilla --output plantilla.docx
"""
from __future__ import annotations

import sys
import logging
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

from scorm_builder.api import build_complete_course
from scorm_builder.parser import parse_docx
from scorm_builder.themes import list_themes


console = Console()


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Activa logs detallados")
def main(verbose):
    """SCORM Builder · convierte tus DOCX en cursos SCORM con tu marca."""
    if verbose:
        logging.basicConfig(level=logging.INFO, format="%(message)s")


@main.command()
@click.argument("docx_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--output", "-o", type=click.Path(path_type=Path), default="./salida",
              help="Directorio de salida (por defecto: ./salida)")
@click.option("--tema", "-t", default="azul",
              help="Paleta: azul, crimson, teal, verde, morado, naranja")
@click.option("--titulo", default=None, help="Sobrescribe el título del curso")
@click.option("--no-pdf", is_flag=True, help="No generar PDFs descargables")
@click.option("--no-aiken", is_flag=True, help="No generar banco Aiken")
@click.option("--color-deep", default=None, help="Color cabecera personalizado (hex, ej: #0A2540)")
@click.option("--color-primary", default=None, help="Color primario personalizado (hex)")
@click.option("--color-bright", default=None, help="Color brillante personalizado (hex)")
def generar(docx_path, output, tema, titulo, no_pdf, no_aiken,
            color_deep, color_primary, color_bright):
    """Genera el curso SCORM completo desde un DOCX."""

    console.print(Panel.fit(
        f"[bold blue]SCORM Builder[/bold blue]\n[dim]Convirtiendo[/dim] [cyan]{docx_path.name}[/cyan]",
        border_style="blue"
    ))

    # Paleta personalizada si se pasan los 3 colores
    custom_palette = None
    if color_deep and color_primary and color_bright:
        custom_palette = {
            "primary_deep": color_deep,
            "primary": color_primary,
            "primary_bright": color_bright,
        }
        console.print(f"[yellow]Usando paleta personalizada[/yellow]")

    try:
        result = build_complete_course(
            docx_path=docx_path,
            output_dir=output,
            theme=tema,
            custom_palette=custom_palette,
            title_override=titulo,
            generate_pdfs=not no_pdf,
            generate_aiken=not no_aiken,
        )
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)

    # Resumen
    table = Table(title="Resumen del curso generado", show_header=True, header_style="bold blue")
    table.add_column("Métrica")
    table.add_column("Valor", style="cyan")
    table.add_row("Título", result.course.metadata.title)
    table.add_row("Temas", str(result.num_topics))
    table.add_row("Preguntas totales", str(result.num_questions))
    table.add_row("SCORMs generados", str(len(result.scorm_zips)))
    table.add_row("PDFs generados", str(len(result.pdf_files)))
    table.add_row("Bancos Aiken", str(len(result.aiken_files)))
    console.print(table)

    if result.warnings:
        console.print("\n[yellow]Avisos durante el procesamiento:[/yellow]")
        for w in result.warnings:
            console.print(f"  · {w}")

    console.print(f"\n[bold green]✓ Listo.[/bold green] Archivos en: [cyan]{output.absolute()}[/cyan]")
    console.print(f"  · SCORMs:  {output}/scorm/")
    console.print(f"  · PDFs:    {output}/pdfs/")
    console.print(f"  · Aiken:   {output}/aiken/")


@main.command()
@click.argument("docx_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def validar(docx_path):
    """Analiza un DOCX y muestra qué se detectaría sin generar nada."""

    console.print(Panel.fit(
        f"[bold blue]Validando[/bold blue] [cyan]{docx_path.name}[/cyan]",
        border_style="blue"
    ))

    try:
        course = parse_docx(docx_path)
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)

    table = Table(title="Estructura detectada", show_header=True, header_style="bold blue")
    table.add_column("#", justify="center")
    table.add_column("Tema")
    table.add_column("Subapartados", justify="center")
    table.add_column("Preguntas", justify="center")
    for t in course.topics:
        table.add_row(
            str(t.number),
            t.title[:50],
            str(len(t.subsections)),
            str(len(t.quiz)),
        )
    console.print(table)

    console.print(f"\n[bold]Metadatos:[/bold]")
    console.print(f"  · Título:  {course.metadata.title}")
    console.print(f"  · Autor:   {course.metadata.author or '(no especificado)'}")
    console.print(f"  · Paleta:  {course.metadata.palette}")
    console.print(f"  · Mastery: {course.metadata.mastery}%")

    if course.warnings:
        console.print("\n[yellow]Avisos:[/yellow]")
        for w in course.warnings:
            console.print(f"  · {w}")
    else:
        console.print("\n[green]✓ Sin avisos. El documento sigue la convención correctamente.[/green]")


@main.command()
def paletas():
    """Lista las paletas disponibles."""
    table = Table(title="Paletas predefinidas", show_header=True, header_style="bold blue")
    table.add_column("Nombre", style="cyan")
    table.add_column("Descripción")
    for name, label in list_themes().items():
        table.add_row(name, label)
    console.print(table)
    console.print("\n[dim]También puedes pasar colores personalizados con --color-deep, --color-primary, --color-bright[/dim]")


@main.command()
@click.option("--output", "-o", type=click.Path(path_type=Path),
              default="./Plantilla_Curso_SCORM.docx",
              help="Ruta donde guardar la plantilla")
def plantilla(output):
    """Copia la plantilla DOCX rellenable a la ruta indicada."""
    import importlib.resources
    try:
        # Buscar la plantilla embebida en el paquete
        with importlib.resources.path("scorm_builder.assets", "Plantilla_Curso_SCORM.docx") as src:
            import shutil
            shutil.copy2(src, output)
            console.print(f"[bold green]✓[/bold green] Plantilla guardada en [cyan]{output.absolute()}[/cyan]")
    except (FileNotFoundError, ModuleNotFoundError):
        console.print(f"[yellow]La plantilla no está incluida en este paquete. Descárgala del repositorio.[/yellow]")


if __name__ == "__main__":
    main()
