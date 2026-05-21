
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
