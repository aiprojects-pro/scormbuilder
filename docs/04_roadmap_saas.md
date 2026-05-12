# Roadmap del SaaS · de motor a producto

> Este documento describe los pasos para convertir el motor (Fase 1, ya construido)
> en un producto SaaS completo (Fases 2-4).

## Estado actual: Fase 1 completada

✅ Motor Python `scorm-builder` con CLI funcional
✅ Convención DOCX → SCORM documentada
✅ Plantilla DOCX rellenable
✅ Generación de SCORM 1.2 + PDFs + bancos Aiken
✅ 6 paletas predefinidas + colores personalizados
✅ Sidebar lateral, scroll-top, quiz integrado

**Lo que ya puedes hacer**: producir cursos a medida para clientes desde la línea de comandos.

---

## Fase 2 · MVP web (estimado: 6-10 semanas)

Objetivo: que un usuario pueda registrarse, subir un Word, configurar marca, descargar SCORM, todo desde un navegador, y pagar por ello.

### Backend (FastAPI)

- [ ] Estructurar proyecto FastAPI con módulos: auth, users, courses, brands, generations
- [ ] Conectar la librería `scorm-builder` como dependencia interna
- [ ] Endpoint `POST /api/courses` para crear curso desde DOCX subido
- [ ] Endpoint `POST /api/courses/{id}/generate` que encola la generación
- [ ] Worker Celery para procesar generaciones en segundo plano
- [ ] Endpoint `GET /api/courses/{id}/download` para descargar el ZIP final
- [ ] Integración con Supabase para auth + base de datos
- [ ] Subida de archivos a Cloudflare R2 con URLs presignadas
- [ ] Webhooks de Stripe para suscripciones

### Frontend (Next.js + TypeScript)

- [ ] Pages: landing, login, register, dashboard, nuevo-curso, mis-cursos, ajustes-marca
- [ ] Login con Supabase Auth (email + Google)
- [ ] Formulario de subida de DOCX con drag & drop
- [ ] Configurador de marca: paleta visual (color picker), upload de logo, selector de tipografía
- [ ] Lista de cursos del usuario con estado (procesando, listo, error)
- [ ] Página de pago con Stripe Checkout
- [ ] Customer Portal de Stripe para gestionar la suscripción

### Base de datos (PostgreSQL via Supabase)

```sql
-- Tablas principales
users (id, email, name, created_at, plan_id)
brands (id, user_id, name, color_deep, color_primary, color_bright, logo_url, font)
courses (id, user_id, brand_id, title, status, source_docx_url, created_at)
generations (id, course_id, scorm_zip_url, pdf_zips, aiken_files, generated_at)
subscriptions (id, user_id, stripe_subscription_id, plan, status, current_period_end)
usage (id, user_id, month, courses_generated)
```

### Despliegue

- [ ] Frontend en Vercel
- [ ] Backend en Railway o Fly.io
- [ ] Redis para Celery (Upstash gratis hasta cierto volumen)
- [ ] Sentry para errores
- [ ] PostHog para analítica

### Coste mensual estimado MVP: 50-150 €

---

## Fase 3 · Editor visual + IA (estimado: 8-12 semanas)

### Editor visual

- [ ] Integrar Tiptap como editor de bloques tras la importación del Word
- [ ] Bloques personalizados: párrafo, h2, h3, callout (4 tipos), tabla, lista, descargable, ejemplo, cita
- [ ] Reordenar bloques con drag & drop
- [ ] Vista previa en iframe del SCORM en tiempo real

### Generación de quiz con IA

- [ ] Integración con API de Anthropic (Claude) o OpenAI
- [ ] Prompt engineering para generar preguntas tipo test a partir del contenido
- [ ] UI de revisión: el usuario edita las preguntas antes de aceptarlas
- [ ] Configuración de IA por plan (cuántas preguntas por mes)

### Otros

- [ ] PDFs descargables editables desde la app
- [ ] Plantillas múltiples por sector (sanitario, deportivo, corporativo)
- [ ] Sistema de carpetas / colecciones de cursos
- [ ] Historial de versiones de un curso

---

## Fase 4 · Profesionalización (estimado: 6-9 meses)

- [ ] Marca blanca completa (consultoras con su logo en el panel)
- [ ] Equipos colaborativos (varios usuarios sobre un curso)
- [ ] Integraciones LMS (Moodle, Canvas, FUNDAE, TalentLMS) — publicar sin descargar
- [ ] Generación de imágenes con IA
- [ ] Soporte xAPI / cmi5 (no solo SCORM 1.2)
- [ ] Multi-idioma con traducción automática
- [ ] App móvil (React Native) para revisar cursos desde el móvil
- [ ] Marketplace de plantillas

---

## Cómo continuar desde aquí

### Si vas a contratar a un desarrollador

1. Empaquétale este proyecto: motor + documentación + visión + roadmap.
2. Contrata por fases. Empieza con Fase 2 a precio cerrado (4.000-12.000 €).
3. Pídele uso de Git, deploy automático, code review básico.

### Si vas a aprender y construir tú

1. Aprende Python básico + FastAPI (libro: "Pyhton Crash Course" + tutoriales FastAPI).
2. Aprende JavaScript/TypeScript + Next.js (curso: nextjs.org/learn, gratuito).
3. Cursos recomendados: "Build SaaS with Next.js" (Lee Robinson, gratis), "FastAPI Full Stack" (oficial).
4. Tiempo estimado: 4-8 meses con dedicación seria.

### Si quieres lanzar antes de construir

1. Usa el motor en línea de comandos para vender 5-10 cursos a medida (1.500-5.000 € cada uno).
2. Eso te paga el desarrollo del SaaS.
3. Mientras facturas, validas mercado y diseñas mejor el producto.
