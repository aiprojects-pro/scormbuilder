"""Renderer: convierte una CourseStructure en HTML.

Cada tema se convierte en un HTML completo con:
- Cabecera coloreada con título del tema
- Sidebar lateral con subapartados (sticky)
- Cuerpo con bloques renderizados según su tipo
- Quiz interactivo con feedback automático y reporte SCORM
- Botón flotante "subir al inicio"
- Botón final "Completar tema" que notifica setCompleted al LMS
"""
from __future__ import annotations

import html
import re
from typing import List, Dict, Optional
from pathlib import Path

from scorm_builder.parser import (
    CourseStructure, Topic, Subsection, Block, BlockType, Question,
)
from scorm_builder.themes import Theme, theme_to_css_vars


# ============================================================
# CSS COMPLETO DEL CURSO
# ============================================================

def get_full_css(theme: Theme) -> str:
    """Devuelve el CSS completo del curso con la paleta aplicada."""
    css_vars = theme_to_css_vars(theme)
    return css_vars + """

/* === IMPORT FUENTES === */
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,700;9..144,900&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

* { box-sizing: border-box; margin: 0; padding: 0; }
html { scroll-behavior: smooth; }
body {
  font-family: var(--sans);
  background: var(--paper);
  color: var(--ink);
  line-height: 1.65;
  font-size: 17px;
  -webkit-font-smoothing: antialiased;
  min-height: 100vh;
}

.module-header {
  background: var(--primary-deep);
  color: white;
  padding: 2.5rem 0 3.5rem;
  position: relative;
  overflow: hidden;
  border-bottom: 4px solid var(--primary-bright);
}
.module-header::before {
  content: '';
  position: absolute;
  top: -50%; left: -10%;
  width: 600px; height: 600px;
  background: radial-gradient(circle, rgba(255,255,255,0.07) 0%, transparent 65%);
  pointer-events: none;
}
.module-header-inner {
  width: min(1100px, 92vw);
  margin: 0 auto;
  position: relative;
  z-index: 2;
}
.crumb {
  font-family: var(--mono);
  font-size: 0.78rem;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: var(--primary-pale);
  margin-bottom: 1.2rem;
  display: flex;
  align-items: center;
  gap: 0.7rem;
}
.crumb .dot { width: 6px; height: 6px; background: var(--primary-bright); border-radius: 50%; }
.module-number {
  font-family: var(--serif);
  font-weight: 900;
  font-style: italic;
  font-size: clamp(3rem, 8vw, 5.5rem);
  line-height: 1;
  color: var(--primary-bright);
  margin-bottom: 0.3rem;
  letter-spacing: -0.02em;
}
.module-title {
  font-family: var(--serif);
  font-weight: 500;
  font-size: clamp(1.8rem, 4vw, 2.8rem);
  line-height: 1.15;
  letter-spacing: -0.015em;
  margin-bottom: 1rem;
  max-width: 800px;
}
.module-meta {
  display: flex;
  gap: 2rem;
  flex-wrap: wrap;
  margin-top: 1.5rem;
  font-size: 0.88rem;
  color: var(--primary-pale);
}
.module-meta strong { color: white; font-weight: 600; }

.module-layout {
  display: grid;
  grid-template-columns: 260px 1fr;
  gap: 2.5rem;
  width: min(1100px, 92vw);
  margin: 0 auto;
  padding: 3rem 0 5rem;
  align-items: start;
}
.module-sidebar {
  position: sticky;
  top: 1.5rem;
  background: white;
  border-radius: 14px;
  padding: 1.4rem 1.2rem;
  box-shadow: 0 4px 18px rgba(0,0,0,0.06);
  max-height: calc(100vh - 3rem);
  overflow-y: auto;
  border-top: 4px solid var(--primary);
}
.sidebar-title {
  font-family: var(--mono);
  font-size: 0.7rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--ink-mute);
  font-weight: 700;
  margin-bottom: 0.9rem;
  padding-bottom: 0.7rem;
  border-bottom: 1px solid var(--paper-deep);
}
.sidebar-nav { list-style: none; counter-reset: sb; }
.sidebar-nav li { counter-increment: sb; }
.sidebar-nav a {
  display: flex;
  align-items: flex-start;
  gap: 0.6rem;
  padding: 0.55rem 0.6rem;
  border-radius: 6px;
  text-decoration: none;
  color: var(--ink-soft);
  font-size: 0.88rem;
  line-height: 1.35;
  font-weight: 500;
  transition: all 0.15s;
  border-left: 3px solid transparent;
  margin-bottom: 0.15rem;
}
.sidebar-nav a::before {
  content: counter(sb, decimal-leading-zero);
  font-family: var(--mono);
  font-size: 0.72rem;
  color: var(--primary-bright);
  font-weight: 700;
  flex-shrink: 0;
}
.sidebar-nav a:hover { background: var(--primary-mist); color: var(--ink); }
.sidebar-nav a.active {
  background: var(--primary-mist);
  color: var(--ink);
  border-left-color: var(--primary-bright);
  font-weight: 600;
}

.module-main { min-width: 0; }
.module-main h2 { scroll-margin-top: 1.5rem; }
.module-main h2:not(:first-of-type) { margin-top: 4rem; }

h2 {
  font-family: var(--serif);
  font-weight: 700;
  font-size: clamp(1.5rem, 3vw, 2.1rem);
  line-height: 1.2;
  margin: 3rem 0 1rem;
  color: var(--ink);
}
h2::before {
  content: '';
  display: block;
  width: 40px; height: 3px;
  background: var(--primary);
  margin-bottom: 0.8rem;
}
h3 { font-family: var(--sans); font-weight: 700; font-size: 1.2rem; margin: 2rem 0 0.8rem; color: var(--ink); }
h4 { font-family: var(--sans); font-weight: 600; font-size: 1rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--primary-deep); margin: 1.5rem 0 0.5rem; }

p { margin-bottom: 1rem; color: var(--ink-soft); }
p.lead {
  font-family: var(--serif);
  font-size: 1.25rem;
  line-height: 1.5;
  color: var(--ink);
  margin: 1.5rem 0 2rem;
  border-left: 3px solid var(--primary-bright);
  padding-left: 1.2rem;
  font-style: italic;
}
ul, ol { margin: 1rem 0 1.5rem 1.5rem; color: var(--ink-soft); }
li { margin-bottom: 0.5rem; }
strong { color: var(--ink); font-weight: 700; }
em { color: var(--primary-deep); font-style: italic; }
a { color: var(--primary); text-decoration: underline; text-underline-offset: 3px; }
a:hover { color: var(--primary-deep); }

.callout {
  margin: 1.8rem 0;
  padding: 1.3rem 1.5rem;
  border-radius: 14px;
  display: grid;
  grid-template-columns: 40px 1fr;
  gap: 1rem;
}
.callout-icon {
  width: 40px; height: 40px;
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-family: var(--serif);
  font-weight: 900;
  font-size: 1.4rem;
  color: white;
}
.callout-key { background: var(--primary-mist); border: 1px solid var(--primary-pale); }
.callout-key .callout-icon { background: var(--primary); }
.callout-alert { background: #FEF2F2; border: 1px solid #FCA5A5; }
.callout-alert .callout-icon { background: var(--alert); }
.callout-success { background: #ECFDF5; border: 1px solid #6EE7B7; }
.callout-success .callout-icon { background: var(--ok); }
.callout-warn { background: #FFFBEB; border: 1px solid #FCD34D; }
.callout-warn .callout-icon { background: var(--warn); }
.callout p { margin: 0; }
.callout-title { font-weight: 700; color: var(--ink); margin-bottom: 0.3rem; }

.concept-box {
  background: var(--paper-warm);
  border-left: 4px solid var(--primary);
  padding: 1.4rem 1.6rem;
  margin: 1.8rem 0;
  border-radius: 0 6px 6px 0;
}
.concept-tag {
  font-family: var(--mono);
  font-size: 0.7rem;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: var(--primary-deep);
  font-weight: 600;
  margin-bottom: 0.5rem;
  display: block;
}
.concept-box p:last-child { margin-bottom: 0; }
.concept-box .quote { font-family: var(--serif); color: var(--ink); font-size: 1.02rem; font-style: italic; }

.edit-table {
  width: 100%;
  border-collapse: collapse;
  margin: 1.5rem 0;
  font-size: 0.95rem;
}
.edit-table thead { background: var(--primary-deep); color: white; }
.edit-table th {
  text-align: left;
  padding: 0.9rem 1rem;
  font-family: var(--sans);
  font-weight: 600;
  font-size: 0.82rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.edit-table td {
  padding: 0.9rem 1rem;
  border-bottom: 1px solid var(--paper-deep);
  vertical-align: top;
}
.edit-table tr:nth-child(even) td { background: var(--paper-warm); }

.downloads {
  background: white;
  border-radius: 14px;
  padding: 1.8rem 2rem;
  margin: 2.5rem 0;
  border: 1px dashed var(--primary);
}
.downloads h3 { margin-top: 0; font-family: var(--serif); font-style: italic; color: var(--primary-deep); }
.download-item {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.9rem 0;
  border-bottom: 1px solid var(--paper-deep);
  text-decoration: none;
  color: var(--ink);
  transition: transform 0.15s;
}
.download-item:last-child { border-bottom: none; }
.download-item:hover { transform: translateX(4px); color: var(--primary); }
.download-item .icon {
  width: 38px; height: 38px;
  background: var(--primary);
  color: white;
  border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
  font-family: var(--mono);
  font-size: 0.7rem;
  font-weight: 700;
}
.download-item .label { font-weight: 600; flex: 1; }
.download-item .meta { font-size: 0.82rem; color: var(--ink-mute); font-family: var(--mono); }

/* === MEDIA: imágenes, vídeos, audios, embeds === */
.media {
  margin: 2rem 0;
  background: var(--paper-warm);
  border-radius: 14px;
  overflow: hidden;
  border: 1px solid var(--paper-deep);
}
.media img,
.media video {
  display: block;
  width: 100%;
  height: auto;
  background: #000;
}
.media-image img { background: var(--paper-warm); }
.media figcaption {
  padding: 0.85rem 1.1rem;
  font-size: 0.88rem;
  color: var(--ink-mute);
  font-style: italic;
  border-top: 1px solid var(--paper-deep);
  background: white;
}
.media-audio {
  background: white;
  padding: 1.2rem 1.4rem;
}
.media-audio audio {
  width: 100%;
  display: block;
}
.media-audio figcaption {
  border-top: none;
  padding: 0.6rem 0 0;
  background: transparent;
}
.video-wrapper {
  position: relative;
  width: 100%;
  padding-bottom: 56.25%; /* 16:9 */
  height: 0;
  overflow: hidden;
  background: #000;
}
.video-wrapper iframe {
  position: absolute;
  top: 0; left: 0;
  width: 100%;
  height: 100%;
  border: 0;
}

.quiz {
  background: white;
  border: 2px solid var(--ink);
  border-radius: 14px;
  padding: 1.8rem 2rem;
  margin: 2rem 0;
  position: relative;
}
.quiz-tag {
  position: absolute;
  top: -12px; left: 1.5rem;
  background: var(--primary);
  color: white;
  padding: 0.25rem 0.8rem;
  border-radius: 100px;
  font-family: var(--mono);
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.1em;
}
.quiz-question {
  font-family: var(--serif);
  font-size: 1.15rem;
  font-weight: 500;
  margin: 0.5rem 0 1.3rem;
  color: var(--ink);
}
.quiz-options { display: flex; flex-direction: column; gap: 0.7rem; }
.quiz-option {
  display: flex;
  align-items: center;
  gap: 0.9rem;
  padding: 0.85rem 1.1rem;
  border: 1.5px solid var(--paper-deep);
  border-radius: 6px;
  cursor: pointer;
  background: var(--paper);
}
.quiz-option:hover { border-color: var(--primary-bright); background: var(--primary-mist); }
.quiz-option input { accent-color: var(--primary); width: 18px; height: 18px; }
.quiz-option.correct { border-color: var(--ok); background: #ECFDF5; }
.quiz-option.wrong { border-color: var(--alert); background: #FEF2F2; }
.quiz-feedback {
  margin-top: 1rem;
  padding: 1rem 1.2rem;
  border-radius: 6px;
  font-size: 0.95rem;
  display: none;
}
.quiz-feedback.show { display: block; }
.quiz-feedback.ok { background: #ECFDF5; border-left: 3px solid var(--ok); }
.quiz-feedback.ko { background: #FEF2F2; border-left: 3px solid var(--alert); }

.btn {
  background: var(--ink);
  color: white;
  border: none;
  padding: 0.8rem 1.6rem;
  border-radius: 6px;
  font-family: var(--sans);
  font-weight: 600;
  font-size: 0.95rem;
  cursor: pointer;
  margin-top: 1.2rem;
}
.btn:hover { background: var(--primary); }

.section-end {
  display: flex;
  justify-content: flex-end;
  margin: 1.8rem 0 0.5rem;
}
.section-end a {
  font-size: 0.82rem;
  color: var(--ink-mute);
  text-decoration: none;
  padding: 0.4rem 0.9rem;
  border-radius: 100px;
  border: 1px solid var(--paper-deep);
}
.section-end a:hover { background: var(--primary-mist); color: var(--ink); border-color: var(--primary-bright); }

.scroll-top {
  position: fixed;
  bottom: 1.8rem;
  right: 1.8rem;
  width: 48px; height: 48px;
  border-radius: 50%;
  background: var(--primary-deep);
  color: white;
  border: none;
  cursor: pointer;
  font-size: 1.4rem;
  font-weight: 700;
  display: flex;
  align-items: center; justify-content: center;
  box-shadow: 0 4px 16px rgba(0,0,0,0.25);
  opacity: 0; visibility: hidden;
  transform: translateY(10px);
  transition: all 0.25s;
  z-index: 1000;
}
.scroll-top.visible { opacity: 1; visibility: visible; transform: translateY(0); }
.scroll-top:hover { background: var(--primary); transform: translateY(-3px); }

.nav-bottom {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 4rem;
  padding-top: 2rem;
  border-top: 1px solid var(--paper-deep);
  gap: 1rem;
  flex-wrap: wrap;
}
.nav-btn {
  background: transparent;
  color: var(--ink);
  text-decoration: none;
  padding: 0.6rem 1.2rem;
  border: 1.5px solid var(--ink);
  border-radius: 6px;
  font-weight: 600;
  cursor: pointer;
  font-family: var(--sans);
}
.nav-btn:hover { background: var(--ink); color: white; }
.nav-btn.primary { background: var(--primary); border-color: var(--primary); color: white; }
.nav-btn.primary:hover { background: var(--primary-deep); }

.module-footer {
  background: var(--ink);
  color: var(--paper-deep);
  padding: 2rem 0;
  margin-top: 3rem;
  font-size: 0.85rem;
}
.module-footer-inner {
  width: min(1100px, 92vw);
  margin: 0 auto;
  display: flex;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 1rem;
}
.module-footer .brand {
  font-family: var(--serif);
  font-weight: 700;
  font-style: italic;
  color: white;
}

@media (max-width: 900px) {
  .module-layout { grid-template-columns: 1fr; }
  .module-sidebar { position: static; max-height: none; }
}
@media print {
  .module-header, .module-footer, .nav-bottom, .module-sidebar, .scroll-top, .section-end, #progress-tracker { display: none; }
  .module-layout { grid-template-columns: 1fr; }
}

/* === Barra de progreso ponderado (sticky arriba) === */
#progress-tracker {
  position: sticky;
  top: 0;
  z-index: 50;
  background: var(--paper-warm);
  border-bottom: 1px solid var(--paper-deep);
  padding: 0.7rem 2rem 0.6rem;
  font-family: var(--sans);
  font-size: 0.82rem;
}
#progress-tracker .pt-row {
  display: grid;
  grid-template-columns: 100px 1fr 50px;
  gap: 0.7rem;
  align-items: center;
  margin-bottom: 0.25rem;
}
#progress-tracker .pt-row.pt-final {
  margin-top: 0.4rem;
  padding-top: 0.4rem;
  border-top: 1px dashed var(--paper-deep);
  font-weight: 600;
}
#progress-tracker .pt-label {
  color: var(--ink-mute);
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
#progress-tracker .pt-bar {
  height: 8px;
  background: var(--paper-deep);
  border-radius: 999px;
  overflow: hidden;
  position: relative;
}
#progress-tracker .pt-fill {
  position: absolute;
  top: 0; left: 0;
  height: 100%;
  background: var(--primary-bright);
  border-radius: 999px;
  width: 0%;
  transition: width 0.4s ease;
}
#progress-tracker .pt-fill-quiz { background: var(--primary); }
#progress-tracker .pt-fill-final { background: var(--ink); }
#progress-tracker .pt-fill-final.passed { background: var(--ok); }
#progress-tracker .pt-pct {
  text-align: right;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  color: var(--ink-soft);
  font-size: 0.85rem;
}
#progress-tracker .pt-pct.passed { color: var(--ok); }
#progress-tracker .pt-info {
  color: var(--ink-mute);
  font-size: 0.72rem;
  margin-top: 0.5rem;
  padding-top: 0.4rem;
  border-top: 1px dotted var(--paper-deep);
  text-align: center;
}
@media (max-width: 600px) {
  #progress-tracker { padding: 0.5rem 1rem; }
  #progress-tracker .pt-row { grid-template-columns: 80px 1fr 40px; gap: 0.4rem; }
  #progress-tracker .pt-label { font-size: 0.7rem; }
  #progress-tracker .pt-info { font-size: 0.68rem; }
}

/* =============================================================
   ACCESIBILIDAD WCAG 2.1 AA (v0.5)
   ============================================================= */

/* Salto al contenido — invisible hasta tabular */
.skip-link {
  position: absolute;
  top: -100px;
  left: 0;
  background: var(--primary-deep);
  color: white;
  padding: 0.8rem 1.2rem;
  text-decoration: none;
  font-weight: 700;
  z-index: 10000;
  border-radius: 0 0 6px 0;
  transition: top 0.15s ease-in-out;
}
.skip-link:focus {
  top: 0;
  outline: 3px solid var(--primary-bright);
  outline-offset: 2px;
}

/* Foco visible reforzado para todos los elementos interactivos */
:focus-visible {
  outline: 3px solid var(--primary-bright);
  outline-offset: 3px;
  border-radius: 3px;
}
button:focus-visible,
.btn:focus-visible,
.nav-btn:focus-visible {
  outline: 3px solid var(--primary-deep);
  outline-offset: 3px;
}

/* Solo lectores de pantalla */
.sr-only {
  position: absolute;
  width: 1px; height: 1px;
  padding: 0; margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

/* main programáticamente enfocable sin contorno raro al hacer clic */
main:focus { outline: none; }

/* Botón de descarga del PDF en la cabecera */
.pdf-download-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.6rem;
  margin-top: 1.5rem;
  padding: 0.7rem 1.2rem;
  background: rgba(255,255,255,0.12);
  border: 2px solid rgba(255,255,255,0.5);
  border-radius: 8px;
  color: white;
  text-decoration: none;
  font-weight: 600;
  font-size: 0.95rem;
  transition: background 0.15s ease, border-color 0.15s ease, transform 0.1s ease;
}
.pdf-download-btn:hover {
  background: rgba(255,255,255,0.22);
  border-color: white;
}
.pdf-download-btn:active { transform: translateY(1px); }
.pdf-download-btn:focus-visible {
  outline: 3px solid white;
  outline-offset: 3px;
}
.pdf-download-btn .pdf-icon { font-size: 1.2rem; }

/* Enlaces dentro del cuerpo (los preservados desde el Word) */
.module-main a,
.module-main p a {
  color: var(--primary-deep);
  text-decoration: underline;
  text-decoration-thickness: 1.5px;
  text-underline-offset: 3px;
}
.module-main a:hover {
  color: var(--primary-bright);
}
.module-main a:focus-visible {
  background: var(--primary-pale, #DBEAFE);
  text-decoration-thickness: 2px;
}

/* Feedback de quiz: aria-live region anunciado por lectores de pantalla */
[aria-live] { /* asegurar que tenga al menos contenedor accesible */ }

/* Animaciones reducidas para usuarios con prefers-reduced-motion */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.001ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.001ms !important;
    scroll-behavior: auto !important;
  }
}

/* Modo alto contraste forzado de Windows: asegurar bordes */
@media (forced-colors: active) {
  .callout, .concept-box, .pdf-download-btn, .btn, .nav-btn {
    border: 1px solid CanvasText;
  }
}

/* =============================================================
   CHIPS DE TAGS / ETIQUETAS (v0.5 Fase 2)
   ============================================================= */
.tag-chips {
  list-style: none;
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin: 1.2rem 0 0;
  padding: 0;
}
.tag-chip {
  display: inline-block;
  padding: 0.3rem 0.8rem;
  background: rgba(255,255,255,0.15);
  border: 1px solid rgba(255,255,255,0.45);
  border-radius: 999px;
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: white;
}

/* =============================================================
   QUIZZES INTERCALADOS POR SUBAPARTADO (v0.5 Fase 2)
   ============================================================= */
.inline-quiz {
  margin: 2rem 0;
  padding: 1.5rem;
  background: var(--paper-deep, #F1F5F9);
  border-left: 4px solid var(--primary-bright);
  border-radius: 6px;
}
.inline-quiz .inline-quiz-tag {
  display: inline-block;
  font-family: var(--mono);
  font-size: 0.72rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--primary-deep);
  margin-bottom: 0.6rem;
  font-weight: 700;
}
.inline-quiz .quiz-options { margin-top: 0.8rem; }
.inline-quiz .quiz-feedback {
  margin-top: 1rem;
  padding: 0.8rem 1rem;
  border-radius: 6px;
  display: none;
}
.inline-quiz .quiz-feedback.correct {
  display: block;
  background: rgba(16, 185, 129, 0.12);
  border-left: 4px solid #10B981;
  color: #064E3B;
}
.inline-quiz .quiz-feedback.wrong {
  display: block;
  background: rgba(239, 68, 68, 0.12);
  border-left: 4px solid #EF4444;
  color: #7F1D1D;
}

/* Estilos específicos por tipo de pregunta */
fieldset.quiz[data-qtype="true_false"] .quiz-options,
.inline-quiz[data-qtype="true_false"] .quiz-options {
  display: flex;
  gap: 1rem;
}
fieldset.quiz[data-qtype="true_false"] .quiz-option,
.inline-quiz[data-qtype="true_false"] .quiz-option {
  flex: 1;
  text-align: center;
  font-weight: 600;
}

/* Hueco visible en preguntas fill_in */
.quiz-question .fill-blank {
  display: inline-block;
  min-width: 80px;
  border-bottom: 2px solid var(--primary-deep);
  margin: 0 0.3rem;
}

.btn-inline-check {
  margin-top: 0.8rem;
  padding: 0.5rem 1rem;
  background: var(--primary);
  color: white;
  border: none;
  border-radius: 6px;
  font-weight: 600;
  font-size: 0.9rem;
  cursor: pointer;
  transition: background 0.15s;
}
.btn-inline-check:hover:not(:disabled) { background: var(--primary-deep); }
.btn-inline-check:disabled {
  background: #94A3B8;
  cursor: not-allowed;
}
"""


# ============================================================
# JS COMPLETO DEL CURSO
# ============================================================

JS_BLOCK = """
(function() {
  // Botón scroll-top
  var btn = document.createElement('button');
  btn.className = 'scroll-top';
  btn.setAttribute('aria-label', 'Subir al inicio');
  btn.innerHTML = '↑';
  btn.onclick = function() { window.scrollTo({top:0, behavior:'smooth'}); };
  document.body.appendChild(btn);
  function toggleBtn() {
    if (window.scrollY > 300) btn.classList.add('visible');
    else btn.classList.remove('visible');
  }
  window.addEventListener('scroll', toggleBtn, {passive:true});
  toggleBtn();

  // Scroll-spy
  var links = document.querySelectorAll('.sidebar-nav a');
  var sections = [];
  links.forEach(function(a) {
    var id = a.getAttribute('href').replace('#','');
    var el = document.getElementById(id);
    if (el) sections.push({id:id, el:el, link:a});
  });
  function updateActive() {
    var pos = window.scrollY + 120;
    var current = sections[0];
    for (var i = 0; i < sections.length; i++) {
      if (sections[i].el.offsetTop <= pos) current = sections[i];
    }
    links.forEach(function(a) { a.classList.remove('active'); });
    if (current) current.link.classList.add('active');
  }
  window.addEventListener('scroll', updateActive, {passive:true});
  updateActive();
})();

// =====================================================================
// SISTEMA DE PUNTUACIÓN PONDERADA (v0.3)
// Variables globales inyectadas desde renderer.py:
//   MASTERY_SCORE       (int)   - umbral de aprobado (0-100)
//   WEIGHT_VIEW         (int)   - peso de la visualización (0-100)
//   WEIGHT_QUIZ         (int)   - peso del quiz (0-100). Suma 100 con WEIGHT_VIEW.
//   VIEW_MIN_SECONDS    (int)   - segundos mínimos por subapartado
//   VIEW_STRATEGY       (str)   - "scroll" | "time" | "both"
//   HAS_QUIZ            (bool)  - si este tema tiene quiz
//   SUBSECTION_IDS      (array) - ids de los subapartados (para tracking)
// =====================================================================

var ProgresoVista = (function() {
  // Estado de visualización por subapartado
  var seenScroll = {};      // id -> bool: ¿ha hecho scroll hasta el final?
  var seenTime = {};        // id -> bool: ¿ha permanecido el tiempo mínimo?
  var timeOnSection = {};   // id -> ms acumulados
  var currentSection = null;
  var lastTickTime = Date.now();
  var quizScore = null;     // null hasta que el alumno haga el quiz, luego 0-100

  // Estrategia efectiva: si no hay quiz, todo el peso va a visualización
  var effectiveWeightView = HAS_QUIZ ? WEIGHT_VIEW : 100;
  var effectiveWeightQuiz = HAS_QUIZ ? WEIGHT_QUIZ : 0;

  function isSectionDone(id) {
    if (VIEW_STRATEGY === "scroll") return !!seenScroll[id];
    if (VIEW_STRATEGY === "time")   return !!seenTime[id];
    // "both" (recomendado)
    return !!seenScroll[id] && !!seenTime[id];
  }

  function viewPercent() {
    if (!SUBSECTION_IDS.length) return 0;
    var done = 0;
    for (var i = 0; i < SUBSECTION_IDS.length; i++) {
      if (isSectionDone(SUBSECTION_IDS[i])) done++;
    }
    return Math.round((done / SUBSECTION_IDS.length) * 100);
  }

  function finalScore() {
    var v = viewPercent();
    var q = (quizScore == null) ? 0 : quizScore;
    var raw = (effectiveWeightView * v + effectiveWeightQuiz * q) / 100;
    return Math.round(raw);
  }

  function passed() {
    return finalScore() >= MASTERY_SCORE;
  }

  // Persistencia entre sesiones via cmi.suspend_data
  function serialize() {
    return JSON.stringify({
      ss: seenScroll, st: seenTime, t: timeOnSection,
      q: quizScore, v: 1
    });
  }
  function deserialize(str) {
    if (!str) return;
    try {
      var data = JSON.parse(str);
      if (data && data.v === 1) {
        seenScroll = data.ss || {};
        seenTime = data.st || {};
        timeOnSection = data.t || {};
        quizScore = (typeof data.q === "number") ? data.q : null;
      }
    } catch(e) {}
  }

  // Tracker de tiempo: sumar ms al subapartado activo
  function tick() {
    var now = Date.now();
    var dt = Math.min(2000, now - lastTickTime);  // cap para evitar saltos al volver de pestaña
    lastTickTime = now;
    if (currentSection && document.visibilityState === "visible") {
      timeOnSection[currentSection] = (timeOnSection[currentSection] || 0) + dt;
      if (timeOnSection[currentSection] >= VIEW_MIN_SECONDS * 1000) {
        if (!seenTime[currentSection]) {
          seenTime[currentSection] = true;
          actualizarUI();
          guardarSCORM();
        }
      }
    }
  }
  setInterval(tick, 1000);

  // IntersectionObserver para detectar scroll-hasta-el-final de cada subapartado
  function setupObserver() {
    if (!('IntersectionObserver' in window)) {
      // Fallback: marcar todo como visto al hacer scroll cerca del final del documento
      window.addEventListener('scroll', function() {
        if (window.scrollY + window.innerHeight >= document.body.scrollHeight - 50) {
          SUBSECTION_IDS.forEach(function(id) { seenScroll[id] = true; });
          actualizarUI();
        }
      }, {passive:true});
      return;
    }
    // Sentinela invisible al final de cada subapartado
    SUBSECTION_IDS.forEach(function(id) {
      var sec = document.getElementById(id);
      if (!sec) return;
      // Buscar el siguiente <h2> o el final del main
      var sentinel = document.createElement('div');
      sentinel.className = 'view-sentinel';
      sentinel.dataset.sectionId = id;
      sentinel.style.cssText = 'height:1px;width:100%;';
      var next = sec.nextElementSibling;
      while (next && next.tagName !== 'H2') {
        var sib = next.nextElementSibling;
        if (!sib || sib.tagName === 'H2') break;
        next = sib;
      }
      if (next) {
        next.parentNode.insertBefore(sentinel, next);
      } else {
        sec.parentNode.appendChild(sentinel);
      }
    });
    // Observar también qué <h2> está en pantalla para saber el "current"
    var hObserver = new IntersectionObserver(function(entries) {
      entries.forEach(function(e) {
        if (e.isIntersecting && e.target.id) {
          currentSection = e.target.id;
        }
      });
    }, { rootMargin: '-20% 0px -60% 0px' });
    SUBSECTION_IDS.forEach(function(id) {
      var sec = document.getElementById(id);
      if (sec) hObserver.observe(sec);
    });
    // Observar las sentinelas para marcar scroll-completo
    var sObserver = new IntersectionObserver(function(entries) {
      entries.forEach(function(e) {
        if (e.isIntersecting) {
          var id = e.target.dataset.sectionId;
          if (id && !seenScroll[id]) {
            seenScroll[id] = true;
            actualizarUI();
            guardarSCORM();
          }
        }
      });
    }, { threshold: 0.1 });
    document.querySelectorAll('.view-sentinel').forEach(function(s) {
      sObserver.observe(s);
    });
  }

  // ----- UI: barrita de progreso fija arriba -----
  var progressBar = null;
  function ensureUI() {
    if (progressBar) return progressBar;
    var bar = document.createElement('div');
    bar.id = 'progress-tracker';
    bar.innerHTML =
      '<div class="pt-row">' +
      '  <div class="pt-label">Visualización</div>' +
      '  <div class="pt-bar"><div class="pt-fill" id="pt-fill-view"></div></div>' +
      '  <div class="pt-pct" id="pt-pct-view">0%</div>' +
      '</div>' +
      (HAS_QUIZ ?
      '<div class="pt-row">' +
      '  <div class="pt-label">Quiz</div>' +
      '  <div class="pt-bar"><div class="pt-fill pt-fill-quiz" id="pt-fill-quiz"></div></div>' +
      '  <div class="pt-pct" id="pt-pct-quiz">—</div>' +
      '</div>' : '') +
      '<div class="pt-row pt-final">' +
      '  <div class="pt-label">Nota final</div>' +
      '  <div class="pt-bar"><div class="pt-fill pt-fill-final" id="pt-fill-final"></div></div>' +
      '  <div class="pt-pct" id="pt-pct-final">0%</div>' +
      '</div>' +
      '<div class="pt-info" id="pt-info"></div>';
    document.body.insertBefore(bar, document.body.firstChild);
    progressBar = bar;
    actualizarInfoTexto();
    return bar;
  }

  function actualizarInfoTexto() {
    var info = document.getElementById('pt-info');
    if (!info) return;
    var txt = 'Aprobado a partir del ' + MASTERY_SCORE + '%. ';
    if (HAS_QUIZ) {
      txt += 'Visualización pesa ' + WEIGHT_VIEW + '% y quiz ' + WEIGHT_QUIZ + '%.';
    } else {
      txt += 'Este tema no tiene quiz: la nota es 100% por visualización.';
    }
    info.textContent = txt;
  }

  function actualizarUI() {
    ensureUI();
    var v = viewPercent();
    var q = quizScore;
    var f = finalScore();
    var fillView = document.getElementById('pt-fill-view');
    var pctView = document.getElementById('pt-pct-view');
    if (fillView) fillView.style.width = v + '%';
    if (pctView) pctView.textContent = v + '%';
    if (HAS_QUIZ) {
      var fillQuiz = document.getElementById('pt-fill-quiz');
      var pctQuiz = document.getElementById('pt-pct-quiz');
      if (fillQuiz) fillQuiz.style.width = (q == null ? 0 : q) + '%';
      if (pctQuiz) pctQuiz.textContent = (q == null ? '—' : q + '%');
    }
    var fillFinal = document.getElementById('pt-fill-final');
    var pctFinal = document.getElementById('pt-pct-final');
    if (fillFinal) {
      fillFinal.style.width = f + '%';
      fillFinal.classList.toggle('passed', passed());
    }
    if (pctFinal) {
      pctFinal.textContent = f + '%';
      pctFinal.classList.toggle('passed', passed());
    }
  }

  // ----- SCORM: enviar score, status y location -----
  function guardarSCORM() {
    if (typeof SCORM === 'undefined' || !SCORM) return;
    try {
      var f = finalScore();
      SCORM.setScore && SCORM.setScore(f);
      if (passed()) {
        SCORM.setPassed && SCORM.setPassed();
        SCORM.setCompleted && SCORM.setCompleted();
      } else {
        // Aún no aprobado: no marcamos failed para que pueda seguir; solo incompleto
        SCORM.setIncomplete && SCORM.setIncomplete();
      }
      SCORM.setSuspendData && SCORM.setSuspendData(serialize());
      // location: id del subapartado actual, para que el LMS pueda reabrir donde lo dejó
      if (currentSection && SCORM.setLocation) SCORM.setLocation(currentSection);
      SCORM.commit && SCORM.commit();
    } catch(e) {}
  }

  function setQuizScore(pct) {
    quizScore = pct;
    actualizarUI();
    guardarSCORM();
  }

  // Restaurar estado al cargar
  function init() {
    if (typeof SCORM !== 'undefined' && SCORM) {
      try {
        if (SCORM.init) SCORM.init();
        var prev = SCORM.getSuspendData && SCORM.getSuspendData();
        if (prev) deserialize(prev);
      } catch(e) {}
    }
    setupObserver();
    ensureUI();
    actualizarUI();
    // Guardar periódicamente
    setInterval(guardarSCORM, 30000);
    window.addEventListener('beforeunload', guardarSCORM);
  }

  return {
    init: init,
    setQuizScore: setQuizScore,
    finalScore: finalScore,
    viewPercent: viewPercent,
    passed: passed,
    save: guardarSCORM
  };
})();

window.addEventListener('load', function() { ProgresoVista.init(); });

// =====================================================================
// QUIZ
// =====================================================================

function checkQuiz(qid, correct) {
  var quiz = document.getElementById(qid);
  if (!quiz) return;
  var inputs = quiz.querySelectorAll('input[type=radio]');
  var selected = -1;
  inputs.forEach(function(i, idx) { if (i.checked) selected = idx; });
  if (selected < 0) return;
  var options = quiz.querySelectorAll('.quiz-option');
  options.forEach(function(opt, idx) {
    opt.classList.remove('correct','wrong');
    if (idx === correct) opt.classList.add('correct');
    else if (idx === selected) opt.classList.add('wrong');
  });
  var fb = quiz.querySelector('.quiz-feedback');
  if (fb) {
    fb.classList.add('show');
    fb.classList.add(selected === correct ? 'ok' : 'ko');
  }
}

// Evaluación final completa
function evaluarFinal() {
  var quizs = document.querySelectorAll('#quiz-final .quiz');
  var aciertos = 0, total = quizs.length, pendientes = 0;
  // Recolectamos las respuestas para enviarlas al LMS como interactions
  var interacciones = [];
  quizs.forEach(function(q) {
    var idx = q.getAttribute('data-q');
    var correcto = parseInt(q.getAttribute('data-a'));
    var seleccionado = q.querySelector('input[name="qf'+idx+'"]:checked');
    if (!seleccionado) { pendientes++; return; }
    var valor = parseInt(seleccionado.value);
    var opciones = q.querySelectorAll('.quiz-option');
    opciones.forEach(function(opt, i) {
      opt.classList.remove('correct','wrong');
      if (i === correcto) opt.classList.add('correct');
      if (i === valor && i !== correcto) opt.classList.add('wrong');
    });
    var ok = (valor === correcto);
    if (ok) aciertos++;
    // Texto del enunciado (para que en informes del LMS aparezca legible)
    var stem = q.querySelector('.quiz-question');
    interacciones.push({
      id: 'q' + idx,
      type: 'choice',
      response: String(valor),
      correct: String(correcto),
      isCorrect: ok,
      description: stem ? stem.textContent.trim().substring(0, 250) : ''
    });
  });
  var out = document.getElementById('resultado-final');
  if (!out) return;
  out.style.display = 'block';
  if (pendientes > 0) {
    out.innerHTML = '<div class="callout callout-alert"><div class="callout-icon">!</div><div><div class="callout-title">Te quedan '+pendientes+' preguntas por responder</div></div></div>';
    return;
  }
  var pctQuiz = total > 0 ? Math.round((aciertos/total)*100) : 0;

  // Reportar cada interacción al LMS (sólo si está disponible)
  if (typeof SCORM !== 'undefined' && SCORM && SCORM.isAvailable && SCORM.isAvailable()) {
    try {
      interacciones.forEach(function(it) { SCORM.setInteraction(it); });
      SCORM.commit && SCORM.commit();
    } catch(e) {}
  }

  // Guardar puntuación del quiz en el tracker (recalcula la nota ponderada)
  if (typeof ProgresoVista !== 'undefined') {
    ProgresoVista.setQuizScore(pctQuiz);
  }

  var notaFinal = (typeof ProgresoVista !== 'undefined') ? ProgresoVista.finalScore() : pctQuiz;
  var aprobado = (typeof ProgresoVista !== 'undefined') ? ProgresoVista.passed() : (pctQuiz >= MASTERY_SCORE);
  var clase = aprobado ? 'callout-success' : 'callout-alert';
  var icono = aprobado ? '✓' : '!';
  var titulo = 'Quiz: '+aciertos+' / '+total+' ('+pctQuiz+'%) — Nota final ponderada: '+notaFinal+'% — '+(aprobado ? 'APROBADO' : 'NO SUPERADO');
  var msg;
  if (aprobado) {
    msg = '<p>Has superado el tema. Puedes pulsar el botón de abajo para finalizar y registrar tu progreso.</p>';
  } else if (pctQuiz < MASTERY_SCORE && (typeof ProgresoVista !== 'undefined') && ProgresoVista.viewPercent() < 100) {
    msg = '<p>Necesitas un mínimo del '+MASTERY_SCORE+'% en la nota final ponderada. Sigue revisando los subapartados que te falten y/o repite el quiz.</p>';
  } else {
    msg = '<p>Necesitas un mínimo del '+MASTERY_SCORE+'% en la nota final ponderada. Revisa las preguntas erróneas y vuelve a intentarlo.</p>';
  }
  out.innerHTML = '<div class="callout '+clase+'"><div class="callout-icon">'+icono+'</div><div><div class="callout-title">'+titulo+'</div>'+msg+'</div></div>';
  out.scrollIntoView({behavior:'smooth', block:'center'});
}

function finalizarTema() {
  if (typeof ProgresoVista !== 'undefined') {
    ProgresoVista.save();
    var f = ProgresoVista.finalScore();
    var passed = ProgresoVista.passed();
    alert('Tema completado.\\n\\nNota final ponderada: ' + f + '%\\nEstado: ' + (passed ? 'APROBADO' : 'NO SUPERADO') + '\\n\\nTu progreso ha sido guardado. Puedes cerrar esta ventana cuando quieras.');
  } else {
    alert('Tema completado. Tu progreso ha sido guardado.\\n\\nPuedes cerrar esta ventana cuando quieras.');
  }
}

// Evaluación de preguntas de repaso intercaladas (v0.5 Fase 2).
// No afectan a la nota final, solo dan feedback inmediato al alumno.
function evaluarInline(btn) {
  var quiz = btn.closest('.inline-quiz');
  if (!quiz) return;
  var idx = quiz.getAttribute('data-q');
  var correcto = parseInt(quiz.getAttribute('data-a'));
  var seleccionado = quiz.querySelector('input[type="radio"]:checked');
  var fb = quiz.querySelector('.quiz-feedback');
  if (!seleccionado) {
    if (fb) {
      fb.className = 'quiz-feedback wrong';
      fb.textContent = '⚠ Selecciona una opción antes de comprobar.';
    }
    return;
  }
  var valor = parseInt(seleccionado.value);
  var opciones = quiz.querySelectorAll('.quiz-option');
  opciones.forEach(function(opt, i) {
    opt.classList.remove('correct','wrong');
    if (i === correcto) opt.classList.add('correct');
    if (i === valor && i !== correcto) opt.classList.add('wrong');
  });
  var ok = (valor === correcto);
  var explanation = fb.getAttribute('data-explanation') || '';
  if (fb) {
    fb.className = 'quiz-feedback ' + (ok ? 'correct' : 'wrong');
    var prefix = ok ? '✓ ¡Correcto! ' : '✗ Respuesta incorrecta. ';
    fb.textContent = prefix + explanation;
  }
  // Deshabilitar el botón tras la primera comprobación
  btn.disabled = true;
  btn.textContent = 'Comprobado';
}
"""


SCORM_API_JS = r"""
// =====================================================================
// SCORM API Wrapper UNIVERSAL — soporta tanto SCORM 1.2 como 2004
// Detecta automáticamente la versión del LMS y traduce las llamadas.
// =====================================================================
var SCORM = (function() {
  var api = null;
  var version = null;          // "2004" | "1.2" | null
  var initialized = false;
  var terminated = false;
  var startTime = null;        // ms desde inicialización
  var interactionIdx = 0;      // contador de interacciones (quiz)

  // ---------- 1. Localizar la API del LMS ----------
  // En 2004 el objeto se llama API_1484_11; en 1.2 se llama API.
  // El SCO puede estar en un iframe anidado: hay que subir por window.parent
  // y también mirar en window.opener.
  function findInWindow(win) {
    var n = 0;
    while (win && n < 500) {
      if (win.API_1484_11) { version = "2004"; return win.API_1484_11; }
      if (win.API)         { version = "1.2";  return win.API; }
      if (!win.parent || win.parent === win) break;
      win = win.parent;
      n++;
    }
    return null;
  }
  function getAPI() {
    if (api) return api;
    api = findInWindow(window);
    if (!api && window.opener && !window.opener.closed) {
      try { api = findInWindow(window.opener); } catch(e) {}
    }
    if (!api && window.top && window.top !== window) {
      try { api = findInWindow(window.top); } catch(e) {}
    }
    return api;
  }

  // ---------- 2. Llamadas de bajo nivel (mapeadas por versión) ----------
  function _initialize() {
    if (!api) return "false";
    return version === "2004" ? api.Initialize("") : api.LMSInitialize("");
  }
  function _set(k, v) {
    if (!api || !initialized) return "false";
    return version === "2004"
      ? api.SetValue(k, String(v))
      : api.LMSSetValue(k, String(v));
  }
  function _get(k) {
    if (!api || !initialized) return "";
    return version === "2004" ? api.GetValue(k) : api.LMSGetValue(k);
  }
  function _commit() {
    if (!api || !initialized) return "false";
    return version === "2004" ? api.Commit("") : api.LMSCommit("");
  }
  function _terminate() {
    if (!api || !initialized) return "false";
    return version === "2004" ? api.Terminate("") : api.LMSFinish("");
  }
  function _lastError() {
    if (!api) return "0";
    return version === "2004" ? api.GetLastError() : api.LMSGetLastError();
  }

  // ---------- 3. Formato de tiempo ----------
  // 1.2 usa HHHH:MM:SS.ss   ·   2004 usa ISO 8601 duration PT#H#M#S
  function pad(n, w) { var s = String(Math.floor(n)); while (s.length < w) s = "0" + s; return s; }
  function fmtTime12(sec) {
    var h = Math.floor(sec / 3600);
    var m = Math.floor((sec % 3600) / 60);
    var s = sec - h*3600 - m*60;
    var cs = Math.round((s - Math.floor(s)) * 100);
    return pad(h,4) + ":" + pad(m,2) + ":" + pad(Math.floor(s),2) + "." + pad(cs,2);
  }
  function fmtTime2004(sec) {
    var h = Math.floor(sec / 3600);
    var m = Math.floor((sec % 3600) / 60);
    var s = sec - h*3600 - m*60;
    var out = "PT";
    if (h) out += h + "H";
    if (m) out += m + "M";
    out += s.toFixed(2) + "S";
    return out;
  }

  // ---------- 4. API pública ----------
  function init() {
    if (initialized) return true;
    if (!getAPI()) {
      // No hay LMS: el contenido sigue funcionando offline, sin reportar
      return false;
    }
    initialized = (_initialize() === "true");
    if (initialized) {
      startTime = new Date().getTime();
    } else {
      // Diagnóstico útil en consola si el LMS rechaza Initialize
      try { console.warn("SCORM Initialize falló. LastError:", _lastError()); } catch(e) {}
    }
    return initialized;
  }

  function setCompleted() {
    if (!init()) return false;
    if (version === "2004") {
      _set("cmi.completion_status", "completed");
    } else {
      _set("cmi.core.lesson_status", "completed");
    }
    return _commit() === "true";
  }

  function setPassed() {
    if (!init()) return false;
    if (version === "2004") {
      _set("cmi.completion_status", "completed");
      _set("cmi.success_status", "passed");
    } else {
      _set("cmi.core.lesson_status", "passed");
    }
    return _commit() === "true";
  }

  function setFailed() {
    if (!init()) return false;
    if (version === "2004") {
      _set("cmi.success_status", "failed");
    } else {
      _set("cmi.core.lesson_status", "failed");
    }
    return _commit() === "true";
  }

  function setIncomplete() {
    if (!init()) return false;
    if (version === "2004") {
      _set("cmi.completion_status", "incomplete");
    } else {
      _set("cmi.core.lesson_status", "incomplete");
    }
    return _commit() === "true";
  }

  // score: número 0–100
  function setScore(score) {
    if (!init()) return false;
    score = Math.max(0, Math.min(100, Number(score) || 0));
    if (version === "2004") {
      // En 2004 el score relevante es scaled (0.0–1.0)
      _set("cmi.score.scaled", String(score / 100));
      _set("cmi.score.raw", String(score));
      _set("cmi.score.min", "0");
      _set("cmi.score.max", "100");
    } else {
      _set("cmi.core.score.raw", String(score));
      _set("cmi.core.score.min", "0");
      _set("cmi.core.score.max", "100");
    }
    return _commit() === "true";
  }

  // progress: 0.0 a 1.0  (sólo SCORM 2004)
  function setProgress(p) {
    if (!init()) return false;
    if (version !== "2004") return false;
    p = Math.max(0, Math.min(1, Number(p) || 0));
    _set("cmi.progress_measure", String(p));
    return _commit() === "true";
  }

  function setSuspendData(s) {
    if (!init()) return false;
    return _set("cmi.suspend_data", s) === "true";
  }
  function getSuspendData() {
    if (!init()) return "";
    return _get("cmi.suspend_data") || "";
  }

  function setLocation(loc) {
    if (!init()) return false;
    var key = version === "2004" ? "cmi.location" : "cmi.core.lesson_location";
    return _set(key, loc) === "true";
  }
  function getLocation() {
    if (!init()) return "";
    var key = version === "2004" ? "cmi.location" : "cmi.core.lesson_location";
    return _get(key) || "";
  }

  // Reportar una interacción del quiz (pregunta-respuesta).
  // q = { id, type, response, correct, isCorrect, weighting, description }
  function setInteraction(q) {
    if (!init()) return false;
    var i = interactionIdx++;
    var p = "cmi.interactions." + i;
    _set(p + ".id", q.id || ("q_" + i));
    _set(p + ".type", q.type || "choice");
    if (version === "2004") {
      _set(p + ".timestamp", new Date().toISOString().replace(/\.\d{3}Z$/, "Z"));
      _set(p + ".learner_response", q.response != null ? String(q.response) : "");
      _set(p + ".result", q.isCorrect ? "correct" : "incorrect");
      if (q.correct != null) {
        _set(p + ".correct_responses.0.pattern", String(q.correct));
      }
      if (q.weighting != null) _set(p + ".weighting", String(q.weighting));
      if (q.description) _set(p + ".description", q.description);
    } else {
      // SCORM 1.2: vocabulario ligeramente distinto
      var d = new Date();
      var hh = pad(d.getHours(),2), mm = pad(d.getMinutes(),2), ss = pad(d.getSeconds(),2);
      _set(p + ".time", hh + ":" + mm + ":" + ss);
      _set(p + ".student_response", q.response != null ? String(q.response) : "");
      _set(p + ".result", q.isCorrect ? "correct" : "wrong");
      if (q.correct != null) {
        _set(p + ".correct_responses.0.pattern", String(q.correct));
      }
      if (q.weighting != null) _set(p + ".weighting", String(q.weighting));
    }
    return true;
  }

  function commit() { return _commit() === "true"; }

  // Cierre del SCO: muy importante hacerlo bien para que el LMS guarde
  function finish(asSuspend) {
    if (!initialized || terminated) return false;
    try {
      // Tiempo de sesión
      if (startTime) {
        var elapsed = (new Date().getTime() - startTime) / 1000;
        if (version === "2004") {
          _set("cmi.session_time", fmtTime2004(elapsed));
        } else {
          _set("cmi.core.session_time", fmtTime12(elapsed));
        }
      }
      // Modo de salida: "suspend" si el alumno aún no ha terminado, para
      // que el LMS reabra el SCO desde donde lo dejó.
      var statusKey = version === "2004" ? "cmi.completion_status" : "cmi.core.lesson_status";
      var status = _get(statusKey);
      var done = (status === "completed" || status === "passed");
      var exitKey = version === "2004" ? "cmi.exit" : "cmi.core.exit";
      _set(exitKey, (!done || asSuspend) ? "suspend" : (version === "2004" ? "normal" : ""));
      _commit();
    } catch(e) {}
    var ok = (_terminate() === "true");
    terminated = true;
    initialized = false;
    return ok;
  }

  return {
    version: function(){ return version; },
    isAvailable: function(){ return getAPI() !== null; },
    init: init,
    setCompleted: setCompleted,
    setPassed: setPassed,
    setFailed: setFailed,
    setIncomplete: setIncomplete,
    setScore: setScore,
    setProgress: setProgress,
    setSuspendData: setSuspendData,
    getSuspendData: getSuspendData,
    setLocation: setLocation,
    getLocation: getLocation,
    setInteraction: setInteraction,
    commit: commit,
    finish: finish,
    lastError: _lastError
  };
})();

// Cierre seguro en cualquier evento de descarga (escritorio + móvil)
(function() {
  function safeFinish() { try { SCORM.finish(); } catch(e) {} }
  window.addEventListener("beforeunload", safeFinish);
  window.addEventListener("pagehide", safeFinish);
  window.addEventListener("unload", safeFinish);
})();
"""


# ============================================================
# FUNCIONES DE RENDERIZADO
# ============================================================

def _h(text: str) -> str:
    """Escapa texto para HTML."""
    return html.escape(text or "", quote=True)


def _h_or_html(block: Block) -> str:
    """Devuelve `block.text_html` si está definido (HTML inline preservado),
    o el texto escapado si no. Centraliza la decisión en el renderer."""
    if block.text_html is not None:
        return block.text_html
    return _h(block.text)


def _items_or_html(block: Block) -> List[str]:
    """Devuelve los items renderizados como HTML, preservando inline si está disponible."""
    if block.items_html is not None and len(block.items_html) == len(block.items):
        return [
            h if h is not None else _h(t)
            for h, t in zip(block.items_html, block.items)
        ]
    return [_h(it) for it in block.items]


def _render_block(block: Block) -> str:
    """Renderiza un bloque individual."""
    bt = block.type
    if isinstance(bt, str):
        bt = BlockType(bt)

    if bt == BlockType.PARAGRAPH:
        return f"<p>{_h_or_html(block)}</p>"

    if bt == BlockType.HEADING_3:
        return f"<h3>{_h_or_html(block)}</h3>"

    if bt == BlockType.HEADING_4:
        return f"<h4>{_h_or_html(block)}</h4>"

    if bt == BlockType.LIST_BULLET:
        items_html = "\n".join(f"  <li>{it}</li>" for it in _items_or_html(block))
        return f"<ul>\n{items_html}\n</ul>"

    if bt == BlockType.LIST_NUMBER:
        items_html = "\n".join(f"  <li>{it}</li>" for it in _items_or_html(block))
        return f"<ol>\n{items_html}\n</ol>"

    if bt == BlockType.TABLE:
        if not block.rows:
            return ""
        # v0.5: si hay rows_html (celdas con enlaces/negritas), las usamos.
        if block.rows_html and len(block.rows_html) == len(block.rows):
            rows_data = block.rows_html
            cell_render = lambda c: c  # ya viene como HTML
        else:
            rows_data = block.rows
            cell_render = _h
        header = rows_data[0]
        body = rows_data[1:]
        thead = "<thead><tr>" + "".join(f"<th scope=\"col\">{cell_render(c)}</th>" for c in header) + "</tr></thead>"
        tbody = "<tbody>" + "".join(
            "<tr>" + "".join(f"<td>{cell_render(c)}</td>" for c in row) + "</tr>"
            for row in body
        ) + "</tbody>"
        return f'<table class="edit-table">{thead}{tbody}</table>'

    if bt == BlockType.CALLOUT_KEY:
        return f'''<aside class="callout callout-key" role="note" aria-label="Concepto clave">
  <div class="callout-icon" aria-hidden="true">i</div>
  <div><p>{_h_or_html(block)}</p></div>
</aside>'''

    if bt == BlockType.CALLOUT_ALERT:
        return f'''<aside class="callout callout-alert" role="note" aria-label="Aviso importante">
  <div class="callout-icon" aria-hidden="true">!</div>
  <div><p>{_h_or_html(block)}</p></div>
</aside>'''

    if bt == BlockType.CALLOUT_SUCCESS:
        return f'''<aside class="callout callout-success" role="note" aria-label="Buena práctica">
  <div class="callout-icon" aria-hidden="true">✓</div>
  <div><p>{_h_or_html(block)}</p></div>
</aside>'''

    if bt == BlockType.CALLOUT_WARN:
        return f'''<aside class="callout callout-warn" role="note" aria-label="Precaución">
  <div class="callout-icon" aria-hidden="true">⚠</div>
  <div><p>{_h_or_html(block)}</p></div>
</aside>'''

    if bt == BlockType.QUOTE:
        # Si el texto empieza con "FUENTE:", separamos
        text = block.text
        source = ""
        if text.upper().startswith("FUENTE:"):
            parts = text.split("\n", 1)
            source = parts[0].replace("FUENTE:", "", 1).strip().replace("FUENTE:", "")
            text = parts[1] if len(parts) > 1 else ""
        source_html = f'<cite class="concept-tag">{_h(source)}</cite>' if source else ""
        return f'''<blockquote class="concept-box">
  {source_html}
  <p class="quote">{_h(text)}</p>
</blockquote>'''

    if bt == BlockType.DOWNLOAD:
        filename = block.extras.get("file", "") or block.extras.get("src", "")
        ext = Path(filename).suffix.upper().lstrip(".") or "FILE"
        return f'''<a class="download-item" href="recursos/{_h(filename)}" target="_blank" download>
  <span class="icon">{_h(ext)}</span>
  <span class="label">{_h(block.text)}</span>
  <span class="meta">{_h(filename)}</span>
</a>'''

    # ---- BLOQUES MULTIMEDIA (v0.2 / v0.5) ----
    if bt == BlockType.IMAGE:
        src = block.extras.get("src", "") or block.extras.get("file", "")
        if not src:
            return ""
        # Si es URL absoluta, dejar tal cual; si no, prefijar carpeta recursos
        url = src if src.startswith(("http://", "https://", "data:")) else f"recursos/{src}"
        # Alt text WCAG 1.1.1: usamos block.text si lo hay, si no un genérico
        # (la validación previa habrá avisado de que falta).
        alt = (block.text or "").strip()
        if not alt:
            alt = "Imagen sin descripción"
        caption = f'<figcaption>{_h(block.text)}</figcaption>' if block.text else ""
        return f'''<figure class="media media-image">
  <img src="{_h(url)}" alt="{_h(alt)}" loading="lazy">
  {caption}
</figure>'''

    if bt == BlockType.VIDEO:
        src = block.extras.get("src", "") or block.extras.get("file", "")
        if not src:
            return ""
        is_url = src.startswith(("http://", "https://"))
        # YouTube / Vimeo → iframe
        if is_url and ("youtube.com" in src or "youtu.be" in src or "vimeo.com" in src):
            embed_url = _to_embed_url(src)
            iframe_title = (block.text or "Vídeo del tema").strip()
            caption = f'<figcaption>{_h(block.text)}</figcaption>' if block.text else ""
            return f'''<figure class="media media-video media-embed">
  <div class="video-wrapper">
    <iframe src="{_h(embed_url)}" title="{_h(iframe_title)}" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>
  </div>
  {caption}
</figure>'''
        url = src if is_url else f"recursos/{src}"
        caption = f'<figcaption>{_h(block.text)}</figcaption>' if block.text else ""
        # Si hay archivo .vtt con el mismo nombre base, lo añadimos como pista de subtítulos
        track_html = ""
        if not is_url and src:
            # El nombre base sin extensión
            base = src.rsplit(".", 1)[0] if "." in src else src
            vtt_url = f"recursos/{base}.vtt"
            track_html = (
                f'\n    <track kind="captions" srclang="es" '
                f'label="Español" src="{_h(vtt_url)}" default>'
            )
        return f'''<figure class="media media-video">
  <video controls preload="metadata" playsinline>
    <source src="{_h(url)}">{track_html}
    Tu navegador no soporta la etiqueta de vídeo.
  </video>
  {caption}
</figure>'''

    if bt == BlockType.AUDIO:
        src = block.extras.get("src", "") or block.extras.get("file", "")
        if not src:
            return ""
        url = src if src.startswith(("http://", "https://")) else f"recursos/{src}"
        caption = f'<figcaption>{_h(block.text)}</figcaption>' if block.text else ""
        return f'''<figure class="media media-audio">
  <audio controls preload="metadata">
    <source src="{_h(url)}">
    Tu navegador no soporta la etiqueta de audio.
  </audio>
  {caption}
</figure>'''

    if bt == BlockType.EMBED:
        src = block.extras.get("src", "") or block.extras.get("file", "")
        if not src:
            return ""
        embed_url = _to_embed_url(src)
        iframe_title = (block.text or "Contenido incrustado").strip()
        caption = f'<figcaption>{_h(block.text)}</figcaption>' if block.text else ""
        return f'''<figure class="media media-embed">
  <div class="video-wrapper">
    <iframe src="{_h(embed_url)}" title="{_h(iframe_title)}" frameborder="0" allow="autoplay; encrypted-media" allowfullscreen></iframe>
  </div>
  {caption}
</figure>'''

    if bt == BlockType.RESOURCE:
        filename = block.extras.get("file", "") or block.extras.get("src", "")
        if not filename:
            return ""
        ext = Path(filename).suffix.upper().lstrip(".") or "FILE"
        is_url = filename.startswith(("http://", "https://"))
        href = filename if is_url else f"recursos/{filename}"
        target_attr = ' target="_blank" rel="noopener"' if is_url else ' download'
        return f'''<a class="download-item"{target_attr} href="{_h(href)}">
  <span class="icon">{_h(ext)}</span>
  <span class="label">{_h(block.text or filename)}</span>
  <span class="meta">{_h(filename)}</span>
</a>'''

    return ""


def _to_embed_url(url: str) -> str:
    """Convierte URLs de YouTube y Vimeo a su versión embebible.

    Si ya es una URL embed o no es de YouTube/Vimeo, se devuelve tal cual.
    """
    if not url:
        return url
    # YouTube watch?v=
    m = re.search(r"youtube\.com/watch\?v=([A-Za-z0-9_\-]+)", url)
    if m:
        return f"https://www.youtube.com/embed/{m.group(1)}"
    # YouTube shorts
    m = re.search(r"youtube\.com/shorts/([A-Za-z0-9_\-]+)", url)
    if m:
        return f"https://www.youtube.com/embed/{m.group(1)}"
    # YouTube short link
    m = re.search(r"youtu\.be/([A-Za-z0-9_\-]+)", url)
    if m:
        return f"https://www.youtube.com/embed/{m.group(1)}"
    # Vimeo
    m = re.search(r"vimeo\.com/(\d+)", url)
    if m:
        return f"https://player.vimeo.com/video/{m.group(1)}"
    return url


def _render_subsection(sub: Subsection, inline_questions: Optional[List[Question]] = None) -> str:
    """Renderiza un subapartado completo, con quiz inline opcional al final."""
    blocks_html = "\n".join(_render_block(b) for b in sub.blocks)
    inline_html = _render_inline_quiz(inline_questions, sub.id) if inline_questions else ""
    return f'''<h2 id="{sub.id}">{_h(sub.number)} {_h(sub.title)}</h2>
{blocks_html}
{inline_html}
'''


def _render_question_options(q: Question, name_prefix: str, q_idx: int) -> str:
    """Renderiza las opciones de una pregunta según su qtype."""
    opts_html_parts: List[str] = []
    qtype = getattr(q, "qtype", "multiple_choice")
    # Para fill_in renderizamos el enunciado con el hueco (lo hace _render_question_stem),
    # las opciones se muestran abajo como en multiple_choice.
    for opt_idx, opt in enumerate(q.options):
        input_id = f"{name_prefix}{q_idx}_opt{opt_idx}"
        if qtype == "true_false":
            label = _h(opt)  # "Verdadero" / "Falso"
        else:
            letter = chr(ord("A") + opt_idx)
            label = f"{letter}. {_h(opt)}"
        opts_html_parts.append(
            f'<label class="quiz-option" for="{input_id}"><input id="{input_id}" '
            f'type="radio" name="{name_prefix}{q_idx}" value="{opt_idx}"> {label}</label>'
        )
    return "\n".join(opts_html_parts)


def _render_question_stem(q: Question) -> str:
    """Renderiza el enunciado de una pregunta. Para fill_in marca el hueco."""
    qtype = getattr(q, "qtype", "multiple_choice")
    if qtype == "fill_in" and "___" in q.text:
        parts = q.text.split("___", 1)
        return f'{_h(parts[0])}<span class="fill-blank" aria-label="hueco a completar"></span>{_h(parts[1]) if len(parts) > 1 else ""}'
    return _h(q.text)


def _render_quiz(topic: Topic, mastery: int) -> str:
    """Renderiza el quiz final de un tema con cálculo de score y reporte SCORM."""
    if not topic.quiz:
        return ""

    questions_html = []
    for idx, q in enumerate(topic.quiz):
        qtype = getattr(q, "qtype", "multiple_choice")
        opts_html = _render_question_options(q, "qf", idx)
        stem_html = _render_question_stem(q)
        questions_html.append(f'''<fieldset class="quiz" data-q="{idx}" data-a="{q.correct_index}" data-qtype="{qtype}">
  <legend class="sr-only">Pregunta {idx+1} de {len(topic.quiz)}</legend>
  <span class="quiz-tag" aria-hidden="true">PREGUNTA {idx+1} / {len(topic.quiz)}</span>
  <p class="quiz-question">{stem_html}</p>
  <div class="quiz-options" role="radiogroup" aria-label="Opciones de respuesta">
    {opts_html}
  </div>
</fieldset>''')

    questions_block = "\n".join(questions_html)

    return f'''<h2 id="evaluacion">Evaluación final</h2>
<p>Responde a las {len(topic.quiz)} preguntas siguientes. Necesitas un <strong>{mastery}%</strong> de aciertos para superar el tema. Puedes repetir el test las veces que necesites.</p>

<form id="quiz-final" onsubmit="event.preventDefault(); evaluarFinal();">
{questions_block}

<button type="submit" class="btn" style="font-size:1.05rem; padding:1rem 2rem;">Comprobar mis respuestas</button>
</form>

<div id="resultado-final" role="status" aria-live="polite" aria-atomic="true" style="display:none; margin-top:2rem;"></div>
'''


def _render_inline_quiz(questions: List[Question], sub_id: str) -> str:
    """Renderiza preguntas intercaladas tras un subapartado (no evaluables,
    son de repaso). Se evalúan en el cliente con feedback inmediato."""
    if not questions:
        return ""
    parts: List[str] = ['<div class="inline-quiz-group">']
    for idx, q in enumerate(questions):
        qtype = getattr(q, "qtype", "multiple_choice")
        name_prefix = f"iq_{sub_id}_"
        opts_html = _render_question_options(q, name_prefix, idx)
        stem_html = _render_question_stem(q)
        feedback_id = f"{name_prefix}{idx}_fb"
        explanation = (q.explanation or "").strip()
        parts.append(f'''<div class="inline-quiz" data-q="{idx}" data-a="{q.correct_index}" data-qtype="{qtype}" data-feedback="{feedback_id}">
  <span class="inline-quiz-tag">💡 Pregunta de repaso</span>
  <p class="quiz-question">{stem_html}</p>
  <div class="quiz-options" role="radiogroup" aria-label="Opciones de respuesta">
    {opts_html}
  </div>
  <button type="button" class="btn-inline-check" onclick="evaluarInline(this)">Comprobar</button>
  <div id="{feedback_id}" class="quiz-feedback" role="status" aria-live="polite"
       data-explanation="{_h(explanation)}"></div>
</div>''')
    parts.append("</div>")
    return "\n".join(parts)


def render_topic(
    topic: Topic,
    course: CourseStructure,
    theme: Theme,
    pdf_filename: Optional[str] = None,
) -> str:
    """Renderiza un tema completo como HTML standalone.

    Args:
        topic: el tema a renderizar
        course: el curso completo (para metadata)
        theme: paleta visual
        pdf_filename: si se pasa, se añade un botón "Descargar PDF" en la
            cabecera que apunta a `recursos/<pdf_filename>`. v0.5.
    """
    # Sidebar items: subapartados + evaluación si hay quiz
    sidebar_items = []
    for sub in topic.subsections:
        sidebar_items.append(f'<li><a href="#{sub.id}">{_h(sub.number)} {_h(sub.title)}</a></li>')
    if topic.quiz:
        sidebar_items.append('<li><a href="#evaluacion">Evaluación final</a></li>')
    sidebar_html = "\n".join(sidebar_items)

    # Cuerpo: intro + subapartados + quiz
    body_parts = []
    if topic.intro:
        body_parts.append(f'<p class="lead">{_h(topic.intro)}</p>')
    for sub in topic.subsections:
        # v0.5 Fase 2: si hay preguntas intercaladas para este subapartado, las insertamos
        inline_qs = topic.inline_quiz.get(sub.id) if topic.inline_quiz else None
        body_parts.append(_render_subsection(sub, inline_questions=inline_qs))
        body_parts.append('<div class="section-end"><a href="#top">↑ Subir al inicio del módulo</a></div>')

    if topic.quiz:
        body_parts.append(_render_quiz(topic, course.metadata.mastery))

    body_html = "\n".join(body_parts)

    css = get_full_css(theme)
    js_full = SCORM_API_JS + "\n" + JS_BLOCK
    mastery = course.metadata.mastery
    weight_view = course.metadata.weight_view
    weight_quiz = course.metadata.weight_quiz
    view_min_seconds = course.metadata.view_min_seconds
    view_strategy = course.metadata.view_strategy
    has_quiz = bool(topic.quiz)
    # Lista de ids de los subapartados, para que el JS sepa cuáles trackear
    subsection_ids_json = "[" + ",".join(f'"{s.id}"' for s in topic.subsections) + "]"

    # v0.5: botón de descarga del PDF en la cabecera (si está disponible)
    pdf_btn_html = ""
    if pdf_filename:
        pdf_btn_html = f'''
    <a class="pdf-download-btn" href="recursos/{_h(pdf_filename)}" download
       aria-label="Descargar apuntes del tema en PDF">
      <span class="pdf-icon" aria-hidden="true">📄</span>
      <span class="pdf-label">Descargar apuntes (PDF)</span>
    </a>'''

    # v0.5 Fase 2: chips de tags bajo el título
    tags_html = ""
    if topic.tags:
        chip_items = "\n".join(
            f'<li class="tag-chip">{_h(t)}</li>' for t in topic.tags
        )
        tags_html = f'''
    <ul class="tag-chips" aria-label="Etiquetas del tema">
{chip_items}
    </ul>'''

    return f'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_h(course.metadata.title)} · {_h(topic.title)}</title>
<style>
{css}
</style>
</head>
<body>

<a class="skip-link" href="#contenido">Saltar al contenido</a>

<header class="module-header" role="banner">
  <div class="module-header-inner">
    <div class="crumb"><span class="dot" aria-hidden="true"></span> {_h(course.metadata.title.upper())}</div>
    <div class="module-number" aria-hidden="true">{topic.number:02d}</div>
    <h1 class="module-title">{_h(topic.title)}</h1>
    {tags_html}
    <div class="module-meta">
      <span><strong>Subapartados:</strong> {len(topic.subsections)}</span>
      <span><strong>Preguntas:</strong> {len(topic.quiz)}</span>
      {f'<span><strong>Aprobado:</strong> {mastery}%</span>' if topic.quiz else ''}
    </div>
    {pdf_btn_html}
  </div>
</header>

<div class="module-layout">

  <nav class="module-sidebar" aria-label="Índice del tema">
    <div class="sidebar-title">En este tema</div>
    <ol class="sidebar-nav">
      {sidebar_html}
    </ol>
  </nav>

  <main class="module-main" id="contenido" tabindex="-1">
    <span id="top" aria-hidden="true"></span>
    {body_html}

    <div class="nav-bottom">
      <button class="nav-btn primary" onclick="finalizarTema()" aria-describedby="completar-help">Completar tema ✓</button>
      <p id="completar-help" class="sr-only">Marca el tema como completado en la plataforma de formación.</p>
    </div>

  </main>

</div>

<footer class="module-footer" role="contentinfo">
  <div class="module-footer-inner">
    <div class="brand">{_h(course.metadata.title)}</div>
    <div>{_h(course.metadata.author or 'Curso e-learning')} · v1.0</div>
  </div>
</footer>

<script>
var MASTERY_SCORE = {mastery};
var WEIGHT_VIEW = {weight_view};
var WEIGHT_QUIZ = {weight_quiz};
var VIEW_MIN_SECONDS = {view_min_seconds};
var VIEW_STRATEGY = "{view_strategy}";
var HAS_QUIZ = {str(has_quiz).lower()};
var SUBSECTION_IDS = {subsection_ids_json};
{js_full}
</script>

</body>
</html>'''


def render_html(
    course: CourseStructure,
    theme: Theme,
    pdf_filenames: Optional[Dict[int, str]] = None,
) -> Dict[int, str]:
    """Renderiza todos los temas del curso. Devuelve {numero_tema: html}.

    Args:
        course: el curso completo
        theme: paleta visual
        pdf_filenames: opcional, {numero_tema: nombre_pdf} para añadir el
            botón "Descargar PDF" en cada tema (v0.5).
    """
    pdfs = pdf_filenames or {}
    return {
        topic.number: render_topic(topic, course, theme, pdf_filename=pdfs.get(topic.number))
        for topic in course.topics
    }
