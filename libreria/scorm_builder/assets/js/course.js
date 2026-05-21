
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
    alert('Tema completado.\n\nNota final ponderada: ' + f + '%\nEstado: ' + (passed ? 'APROBADO' : 'NO SUPERADO') + '\n\nTu progreso ha sido guardado. Puedes cerrar esta ventana cuando quieras.');
  } else {
    alert('Tema completado. Tu progreso ha sido guardado.\n\nPuedes cerrar esta ventana cuando quieras.');
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
