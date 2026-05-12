# SCORM Builder · Documento de visión

> **Versión:** 0.1 · borrador inicial
> **Fecha:** abril 2026
> **Estado:** documento de trabajo

---

## 1. El problema

Crear un curso e-learning compatible con SCORM 1.2 (formato exigido por la mayoría de plataformas LMS y por **FUNDAE** en España) es una tarea compleja, técnica y cara:

- Las herramientas profesionales del mercado (Articulate Storyline, Adobe Captivate, iSpring Suite, Lectora) tienen curvas de aprendizaje de semanas y precios de **300-1.500 €/año**.
- Las opciones más sencillas (Articulate Rise, EvolveAuthoring) producen cursos visualmente genéricos, difíciles de personalizar con marca propia.
- Los formadores autónomos y las consultoras pequeñas terminan **subcontratando** la producción del SCORM a precios de **1.500-5.000 € por curso**, con plazos de varias semanas.
- La parte más penosa del proceso es **convertir el contenido didáctico que ya existe** (un Word, un PDF, una presentación) en un paquete SCORM bien empaquetado, con quiz, descargables, navegación, manifest válido y todo lo que exige FUNDAE.

El usuario típico afectado:

- **Formador/a autónomo/a** que prepara cursos para empresas o para FUNDAE y necesita varios al año.
- **Consultora de formación** que produce decenas de cursos para sus clientes.
- **Departamento de formación interno** de empresa mediana/grande que digitaliza formación interna.
- **Asociaciones, federaciones y entidades** que necesitan cumplir requisitos formativos legales (LOPIVI, prevención de riesgos, igualdad, etc.).

## 2. La solución

Una plataforma SaaS web que convierte un documento Word —o el contenido escrito en su editor— en un paquete SCORM 1.2 listo para subir al LMS, con el diseño y la marca del cliente, en minutos.

**Promesa de producto en una frase:**

> Sube tu Word y descárgate un curso SCORM con tu marca, listo para FUNDAE, en menos de 5 minutos.

## 3. Características diferenciales

1. **Entrada flexible**: el cliente sube un Word con su contenido y la app lo importa, o escribe directamente en un editor visual web.
2. **Edición posterior**: tras la importación, puede editar bloques (texto, callouts, tablas, ejemplos, listas) en una interfaz tipo Notion.
3. **Marca personalizada**: paleta de colores propia, logo, tipografía. El SCORM resultante es indistinguible de una producción a medida.
4. **Quiz inteligente**: las preguntas las escribe el cliente, o las genera la app con IA a partir del contenido y el cliente las revisa.
5. **PDFs descargables**: incluidos automáticamente en el SCORM, con el contenido del curso o subidos por el cliente.
6. **Banco Aiken**: además del quiz embebido, exporta un .txt en formato Aiken para importar al LMS.
7. **Validación FUNDAE**: el SCORM cumple las restricciones específicas que FUNDAE exige (peso, duración, masteryscore, formato del manifest).
8. **Vista previa en navegador**: el cliente ve el resultado antes de descargar.

## 4. Mercado objetivo (España)

### Tamaño aproximado

- **Formación bonificada FUNDAE en España**: aproximadamente 700.000-900.000 acciones formativas al año.
- **Empresas que tramitan FUNDAE**: aproximadamente 450.000-500.000.
- **Consultoras de formación registradas en SEPE**: varios miles.
- **Formadores autónomos**: decenas de miles.

### Nicho inicial recomendado

Para evitar dispersión, arrancar con uno o dos de estos perfiles:

- **Consultoras pequeñas (1-10 empleados) que tramitan FUNDAE**: producen muchos cursos, presupuesto razonable, conocimiento del dolor.
- **Asociaciones y federaciones** que deben cumplir formación obligatoria por ley (LOPIVI deportiva, riesgos laborales, igualdad, protección de datos).

## 5. Modelo de negocio

### Estructura de planes

| Plan | Precio | Cursos/mes | Características clave |
|------|--------|------------|----------------------|
| Free | 0 € | 1 | Marca de agua, plantillas estándar |
| Starter | 29 € / mes | 5 | Sin marca de agua, paleta personalizada, IA básica |
| Pro | 79 € / mes | 20 | IA avanzada, marca blanca, plantillas premium |
| Business | 199 € / mes | Ilimitado | Hasta 5 usuarios, integraciones LMS, soporte prioritario |
| Enterprise | A medida | Ilimitado | Marca blanca total, SLA, asesoramiento, on-premise |

Descuentos del 17 % por pago anual.

### Estimación de costes operativos por curso generado

- Almacenamiento (R2/S3): 0,001 €
- Cómputo de generación: 0,01-0,05 €
- IA para preguntas (si se usa): 0,05-0,30 € (Claude/OpenAI)
- Total marginal por curso: **≈ 0,06-0,35 €**

Margen bruto sobre suscripción: **80-95 %** según uso.

### Proyecciones razonables (no agresivas)

| Mes | Usuarios pagos | Ingreso mensual estimado |
|-----|----------------|---------------------------|
| 3 | 5 | ≈ 200 € |
| 6 | 25 | ≈ 1.200 € |
| 12 | 100 | ≈ 5.500 € |
| 24 | 400 | ≈ 22.000 € |

## 6. Competencia y diferenciación

| Competidor | Punto fuerte | Punto débil aprovechable |
|-----------|--------------|--------------------------|
| Articulate Rise | Editor potente, plantillas | Caro (1.500 €/año), complejo, marca genérica |
| iSpring Suite | Integración con PowerPoint | Solo Windows, pesado, requiere Office |
| Adobe Captivate | Muy completo | Muy caro, curva pronunciada |
| Easygenerator | Web, sencillo | Limitado, no FUNDAE-friendly, marca genérica |
| EvolveAuthoring | Bonito | Caro, sin nicho hispanohablante |

**Nuestra diferenciación principal**:

1. **Flujo único Word → SCORM en 5 minutos**: ninguno de los grandes hace esto bien.
2. **Foco hispanohablante y FUNDAE**: ninguno está pensado específicamente para el mercado español/latinoamericano.
3. **Precio**: mucho menor que las opciones profesionales.
4. **Calidad visual**: no parece "auto-generado", sale como una producción a medida.

## 7. Roadmap de producto

### Fase 0 · Validación de mercado (semanas 1-3)

- [ ] Landing con lista de espera
- [ ] 200 € en publicidad LinkedIn / Google
- [ ] 10 entrevistas con apuntados
- [ ] Decisión: seguir / pivotar / aparcar

### Fase 1 · Motor + uso personal (semanas 1-4, en paralelo)

- [ ] Librería Python con CLI funcional
- [ ] Plantilla DOCX documentada
- [ ] Conversión DOCX → SCORM 1.2 válido
- [ ] Conversión DOCX → PDF descargable
- [ ] Conversión DOCX → banco Aiken
- [ ] Personalización por archivo de configuración
- [ ] Vendo cursos a medida con la herramienta (1.500-5.000 €/curso)

### Fase 2 · MVP web (mes 2-4)

- [ ] Frontend Next.js con login (Supabase Auth)
- [ ] Subida de Word + parseo
- [ ] Configuración de marca (paleta, logo, tipografía)
- [ ] Vista previa SCORM en iframe
- [ ] Generación + descarga del ZIP
- [ ] Pasarela de pago (Stripe Checkout)
- [ ] Plan Free + Starter activos
- [ ] 3 beta testers de pago

### Fase 3 · Producto completo (mes 4-9)

- [ ] Editor visual de bloques (Tiptap)
- [ ] Generación de quiz con IA
- [ ] PDFs descargables generados desde la app
- [ ] Plantillas múltiples por sector
- [ ] Sistema de marca blanca
- [ ] Lanzamiento público

### Fase 4 · Escalado (mes 9-18)

- [ ] Marca blanca total para consultoras
- [ ] Integración directa con LMS (Moodle, Canvas, FUNDAE)
- [ ] Generación de imágenes con IA
- [ ] Soporte xAPI / cmi5
- [ ] Multi-idioma
- [ ] Equipos colaborativos

## 8. Stack técnico

### Backend

- **Lenguaje**: Python 3.11
- **Framework API**: FastAPI
- **Cola asíncrona**: Celery + Redis
- **Base de datos**: PostgreSQL (vía Supabase)
- **Almacenamiento de archivos**: Cloudflare R2 (compatible S3)
- **Validación**: Pydantic
- **Generación de PDF**: reportlab
- **Parseo Word**: python-docx + mammoth
- **IA**: API de Anthropic (Claude) / OpenAI (alternativa)

### Frontend

- **Framework**: Next.js 14 (App Router) + TypeScript
- **Estilos**: TailwindCSS + shadcn/ui
- **Editor de bloques**: Tiptap
- **Auth**: Supabase Auth
- **Pagos**: Stripe Checkout + Customer Portal

### Infraestructura

- **Frontend hosting**: Vercel
- **Backend hosting**: Railway o Fly.io
- **Base de datos**: Supabase
- **Storage**: Cloudflare R2
- **Email**: Resend
- **Errores**: Sentry
- **Analítica**: PostHog
- **Soporte**: Crisp

### Coste mensual operativo estimado

- **Mes 1-3 (validación)**: 0-50 €/mes
- **Mes 4-6 (MVP)**: 50-150 €/mes
- **Mes 7-12 (producto)**: 150-400 €/mes
- **Mes 12+ (escalado)**: 400-1.500 €/mes según volumen

## 9. Métricas clave a seguir

- **MRR** (Monthly Recurring Revenue): ingresos suscripción por mes.
- **Churn**: porcentaje de bajas mensual. Objetivo < 5 %.
- **CAC** (Customer Acquisition Cost): cuánto cuesta captar un cliente de pago.
- **LTV** (Lifetime Value): cuánto deja de media un cliente a lo largo de su vida útil.
- **Activation rate**: porcentaje de registros que generan al menos un SCORM en su primera semana.
- **Conversion rate** Free → pago: porcentaje de usuarios gratuitos que pasan a plan de pago.
- **NPS** (Net Promoter Score): satisfacción del cliente.

## 10. Riesgos identificados

### Técnicos

- **Variabilidad del DOCX**: documentos mal formateados pueden romper el parser. Mitigación: plantilla obligatoria + validador previo + conversión tolerante a fallos.
- **Compatibilidad LMS**: cada LMS interpreta SCORM 1.2 ligeramente distinto. Mitigación: testing en SCORM Cloud, Moodle, Canvas, TalentLMS.
- **Coste de IA fuera de control**: si los usuarios abusan de generación con IA. Mitigación: límites por plan + caching + tarifas escalonadas.

### De mercado

- **El mercado FUNDAE puede cambiar de criterios**: posible riesgo regulatorio. Mitigación: no depender solo de FUNDAE, expandir a LATAM y mercado privado.
- **Competidor grande copia la propuesta**: posible pero el foco hispanohablante y el precio nos protegen al inicio.

### Operativos

- **Soporte saturado**: cada cliente con dudas técnicas consume tiempo. Mitigación: documentación rica, plantilla DOCX clara, comunidad de usuarios.

## 11. Equipo y necesidades

### Mínimo para arrancar (fase 1)

- 1 persona técnica (full-stack o equivalente con IA como copiloto): podrías ser tú o un freelance.

### Para llegar a producto (fase 3)

- 1 desarrollador/a full-stack a tiempo completo.
- 1 diseñador/a UX/UI a tiempo parcial.
- Apoyo puntual de un experto en SCORM/FUNDAE para validar.

### Para escalar (fase 4)

- 2 desarrolladores.
- 1 atención al cliente / customer success.
- 1 marketing.

---

## Próxima acción inmediata

1. Lanzar landing de validación con formulario de lista de espera.
2. 100-200 € en LinkedIn Ads dirigidos a "responsable de formación", "consultor FUNDAE", "técnico e-learning".
3. Empezar a producir cursos con el motor existente para clientes reales mientras se construye el SaaS.
