/* Lado cliente del lector.
 *
 * Responsabilidades:
 *   - inicializar KaTeX y Mermaid sobre lo que dejo render.py
 *   - avisarle a Qt en que seccion esta el scroll (para resaltar el indice)
 *   - restaurar y reportar la posicion de lectura
 *   - marcar los links que navegan adentro del lector
 *   - reemplazar las imagenes remotas bloqueadas por un cartel
 *
 * El canal con Qt es QWebChannel. Si no esta disponible, todo lo visual sigue
 * funcionando: solo se pierde la sincronizacion con el indice.
 */

(function () {
  "use strict";

  var bridge = null;
  var headings = [];
  var activeAnchor = null;
  var restoring = false;

  /* ===== Utilidades ====================================================== */

  function throttle(fn, ms) {
    var last = 0;
    var timer = null;
    return function () {
      var now = Date.now();
      var wait = ms - (now - last);
      if (wait <= 0) {
        last = now;
        fn();
      } else if (timer === null) {
        timer = setTimeout(function () {
          timer = null;
          last = Date.now();
          fn();
        }, wait);
      }
    };
  }

  function scrollFraction() {
    var max = document.documentElement.scrollHeight - window.innerHeight;
    if (max <= 0) return 0;
    return Math.min(1, Math.max(0, window.scrollY / max));
  }

  /* ===== Tablas ========================================================== */

  /* Una tabla ancha tiene que scrollear en su propia caja. Envolverla en JS
   * evita tener que ensuciar el HTML que genera el renderer. */
  function wrapTables() {
    var tables = document.querySelectorAll(".paper > table, .paper table");
    tables.forEach(function (table) {
      if (table.parentElement && table.parentElement.classList.contains("table-scroll")) return;
      var wrap = document.createElement("div");
      wrap.className = "table-scroll";
      table.parentNode.insertBefore(wrap, table);
      wrap.appendChild(table);
    });
  }

  /* ===== KaTeX =========================================================== */

  function renderMath() {
    if (typeof window.katex === "undefined") return;
    var nodes = document.querySelectorAll(".math");
    nodes.forEach(function (node) {
      if (node.dataset.rendered === "1") return;
      var tex = node.textContent;
      var display = node.classList.contains("block");
      try {
        window.katex.render(tex, node, {
          displayMode: display,
          throwOnError: false,
          output: "html",
        });
        node.dataset.rendered = "1";
      } catch (err) {
        /* Una formula rota no debe romper el resto del documento: se muestra
         * el TeX original marcado en rojo. */
        node.classList.add("math-error");
        node.textContent = tex;
        node.dataset.rendered = "1";
      }
    });
  }

  /* ===== Mermaid ========================================================= */

  function mermaidTheme() {
    return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "default";
  }

  function renderMermaid() {
    if (typeof window.mermaid === "undefined") return;
    var blocks = document.querySelectorAll("pre.mermaid:not([data-processed])");
    if (!blocks.length) return;

    try {
      window.mermaid.initialize({
        startOnLoad: false,
        theme: mermaidTheme(),
        securityLevel: "strict",
        /* Una familia concreta, no "inherit": Mermaid mide el texto para
         * calcular el tamaño de cada nodo, y con un valor que no resuelve a
         * una fuente real le salen cajas del tamaño equivocado. */
        fontFamily: 'system-ui, "Cantarell", "Segoe UI", Roboto, sans-serif',
      });
    } catch (err) {
      /* sin configuracion valida no tiene sentido seguir */
    }

    blocks.forEach(function (block, index) {
      var source = block.textContent;
      var id = "mermaid-" + index + "-" + Math.random().toString(36).slice(2, 8);
      try {
        var result = window.mermaid.render(id, source);
        /* mermaid v10+ devuelve una promesa; v9 devuelve el svg directo. */
        if (result && typeof result.then === "function") {
          result
            .then(function (out) {
              block.innerHTML = out.svg;
              block.setAttribute("data-processed", "1");
              notifyGeometryChanged();
            })
            .catch(function () {
              failMermaid(block, source);
            });
        } else if (typeof result === "string") {
          block.innerHTML = result;
          block.setAttribute("data-processed", "1");
        } else {
          failMermaid(block, source);
        }
      } catch (err) {
        failMermaid(block, source);
      }
    });
  }

  function failMermaid(block, source) {
    /* Un diagrama con error de sintaxis se muestra como el codigo que es,
     * que es mas util que un hueco en blanco. */
    block.textContent = source;
    block.classList.add("mermaid-error");
    block.setAttribute("data-processed", "1");
  }

  /* ===== Imagenes remotas bloqueadas ===================================== */

  function markBlockedImages() {
    var imgs = document.querySelectorAll("img");
    imgs.forEach(function (img) {
      if (img.dataset.blockChecked === "1") return;
      img.dataset.blockChecked = "1";
      img.addEventListener("error", function () {
        if (img.dataset.replaced === "1") return;
        var src = img.getAttribute("src") || "";
        if (!/^https?:|^\/\//i.test(src)) return;
        img.dataset.replaced = "1";
        var note = document.createElement("span");
        note.className = "remote-blocked";
        note.textContent = "imagen remota bloqueada — " + (img.getAttribute("alt") || src);
        img.replaceWith(note);
      });
    });
  }

  /* ===== Links =========================================================== */

  /* Marca visualmente los links que el lector va a abrir adentro. La decision
   * real de navegar la toma Qt en acceptNavigationRequest; esto es solo
   * la pista visual para el usuario. */
  function markInternalLinks() {
    var links = document.querySelectorAll("a[href]");
    links.forEach(function (link) {
      var href = link.getAttribute("href") || "";
      if (/^(https?:|mailto:|tel:)/i.test(href)) return;
      if (href.charAt(0) === "#") return;
      if (/\.(md|markdown|mdown|mkd|txt)(\?|#|$)/i.test(href)) {
        link.setAttribute("data-internal", "1");
      }
    });
  }

  /* ===== Indice: que seccion se esta leyendo ============================= */

  function collectHeadings() {
    headings = [];
    var nodes = document.querySelectorAll(".paper h1[id], .paper h2[id], .paper h3[id], .paper h4[id], .paper h5[id], .paper h6[id]");
    nodes.forEach(function (node) {
      headings.push(node);
    });
  }

  function currentAnchor() {
    if (!headings.length) return null;

    /* Al final del documento gana el ultimo heading aunque no haya cruzado la
     * linea: si no, la ultima seccion nunca se resalta en documentos donde el
     * cierre es mas corto que la ventana. */
    if (scrollFraction() > 0.995) {
      return headings[headings.length - 1].id;
    }

    var line = window.innerHeight * 0.28;
    var found = null;
    for (var i = 0; i < headings.length; i++) {
      if (headings[i].getBoundingClientRect().top <= line) {
        found = headings[i].id;
      } else {
        break;
      }
    }
    return found || headings[0].id;
  }

  function notifyScroll() {
    var anchor = currentAnchor();
    if (anchor !== activeAnchor) {
      activeAnchor = anchor;
      if (bridge && anchor) bridge.setActiveHeading(anchor);
    }
    if (bridge && !restoring) bridge.setScroll(scrollFraction());
  }

  function notifyGeometryChanged() {
    /* Mermaid cambia el alto de la pagina despues del primer layout: hay que
     * recalcular, si no la posicion restaurada queda corrida. */
    window.setTimeout(notifyScroll, 50);
  }

  /* ===== API que llama Qt ================================================ */

  window.mdreader = {
    scrollToAnchor: function (anchor) {
      var target = document.getElementById(anchor);
      if (!target) return false;
      target.scrollIntoView({ behavior: "smooth", block: "start" });
      return true;
    },

    restoreScroll: function (fraction) {
      restoring = true;
      var apply = function () {
        var max = document.documentElement.scrollHeight - window.innerHeight;
        window.scrollTo({ top: max * fraction, behavior: "auto" });
        restoring = false;
        notifyScroll();
      };
      /* Dos frames: el primero deja que el layout se asiente tras las fuentes
       * y las imagenes locales, el segundo aplica sobre el alto ya definitivo. */
      requestAnimationFrame(function () {
        requestAnimationFrame(apply);
      });
    },

    setTheme: function (theme) {
      document.documentElement.setAttribute("data-theme", theme);
      /* Mermaid embebe los colores en el SVG: hay que redibujar. */
      document.querySelectorAll("pre.mermaid[data-processed]").forEach(function (block) {
        if (block.classList.contains("mermaid-error")) return;
        if (block.dataset.source) {
          block.textContent = block.dataset.source;
          block.removeAttribute("data-processed");
        }
      });
      renderMermaid();
    },

    setFullWidth: function (on) {
      document.body.classList.toggle("full-width", !!on);
      notifyScroll();
    },

    getScroll: scrollFraction,
  };

  /* ===== Arranque ======================================================== */

  function stashMermaidSources() {
    document.querySelectorAll("pre.mermaid").forEach(function (block) {
      block.dataset.source = block.textContent;
    });
  }

  function boot() {
    stashMermaidSources();
    wrapTables();
    markInternalLinks();
    markBlockedImages();
    renderMath();
    renderMermaid();
    collectHeadings();

    window.addEventListener("scroll", throttle(notifyScroll, 100), { passive: true });
    window.addEventListener("resize", throttle(notifyScroll, 200));

    if (typeof QWebChannel !== "undefined" && typeof qt !== "undefined") {
      new QWebChannel(qt.webChannelTransport, function (channel) {
        bridge = channel.objects.bridge;
        if (bridge && bridge.ready) bridge.ready();
        notifyScroll();
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
