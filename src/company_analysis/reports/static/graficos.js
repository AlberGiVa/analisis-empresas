/* Charts and live data of the public website (no dependencies).
 *
 * - Colours come from the CSS tokens of the active style, so every chart follows Luceiro, Terminal
 *   or Prensa and light or dark mode.
 * - No visible text lives here: labels are read from hidden elements of the page
 *   (<span data-texto="key">…</span>), which the English site translates like any other text.
 * - Live data come from the ECB data API (open, CORS enabled). If a request fails, the page keeps
 *   the figures computed when the website was built.
 */
(function () {
  "use strict";
  var ECB = "https://data-api.ecb.europa.eu/service/data";
  var LOCALE = document.documentElement.lang === "en" ? "en-GB" : "es-ES";
  var SVG = "http://www.w3.org/2000/svg";

  function texto(key, fallback) {
    var el = document.querySelector('[data-texto="' + key + '"]');
    return el ? el.textContent.trim() : fallback || key;
  }
  function num(value, decimals) {
    return value.toLocaleString(LOCALE, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  }
  function pct(value, decimals) {
    if (Math.abs(value) < 0.00005) value = 0;  /* never "−0,00 %" */
    var text = num(Math.abs(value) * 100, decimals === undefined ? 2 : decimals) + " %";
    return (value > 0 ? "+" : value < 0 ? "−" : "") + text;
  }
  function day(iso) {
    var p = iso.split("-");
    return p.length < 3 ? p[1] + "/" + p[0] : p[2] + "/" + p[1] + "/" + p[0];  /* monthly: MM/YYYY */
  }
  function el(name, attrs, parent) {
    var node = document.createElementNS(SVG, name);
    for (var key in attrs) node.setAttribute(key, attrs[key]);
    if (parent) parent.appendChild(node);
    return node;
  }

  /* --- ECB data API (CSV) ------------------------------------------------------------------- */
  function parseCsv(text) {
    var lines = text.trim().split(/\r?\n/);
    var head = lines.shift().split(",");
    var iKey = head.indexOf("KEY"), iDate = head.indexOf("TIME_PERIOD"), iValue = head.indexOf("OBS_VALUE");
    var rows = [];
    lines.forEach(function (line) {
      var cells = line.split(",");
      var value = parseFloat(cells[iValue]);
      if (!isNaN(value)) rows.push({ key: cells[iKey], date: cells[iDate], value: value });
    });
    return rows;
  }
  function ecb(path) {
    return fetch(ECB + path + (path.indexOf("?") < 0 ? "?" : "&") + "format=csvdata", { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
      .then(parseCsv);
  }
  /* Exchange rates per currency: {USD: [[iso, value], …], …} */
  function fxSeries(currencies, startIso) {
    return ecb("/EXR/D." + currencies.join("+") + ".EUR.SP00.A?startPeriod=" + startIso).then(function (rows) {
      var out = {};
      rows.forEach(function (r) {
        var cur = r.key.split(".")[2];
        (out[cur] = out[cur] || []).push([r.date, r.value]);
      });
      Object.keys(out).forEach(function (c) { out[c].sort(function (a, b) { return a[0] < b[0] ? -1 : 1; }); });
      return out;
    });
  }

  /* --- Line chart with range buttons, crosshair and tooltip ----------------------------------- */
  function lineChart(box, opts) {
    var decimals = opts.decimals === undefined ? 4 : opts.decimals;
    var series = [];  // [{name, points: [[iso, value]], muted}]
    var svg = el("svg", { class: "chart-svg", role: "img" }, box);
    var tip = document.createElement("div");
    tip.className = "chart-tip";
    tip.hidden = true;
    box.appendChild(tip);
    var geometry = null;
    var animated = false;  /* only the first drawing with data is animated */

    function draw() {
      while (svg.firstChild) svg.removeChild(svg.firstChild);
      var width = Math.max(box.clientWidth, 260), height = opts.height || 260;
      var left = 56, right = 14, top = 12, bottom = 26;
      svg.setAttribute("viewBox", "0 0 " + width + " " + height);
      svg.setAttribute("width", width);
      svg.setAttribute("height", height);
      var all = [];
      series.forEach(function (s) { s.points.forEach(function (p) { all.push(p); }); });
      if (all.length < 2) { geometry = null; return; }
      var xs = opts.xNumeric ? all.map(function (p) { return p[0]; }) : all.map(function (p) { return Date.parse(p[0]); });
      var ys = all.map(function (p) { return p[1]; });
      var x0 = Math.min.apply(null, xs), x1 = Math.max.apply(null, xs);
      var y0 = Math.min.apply(null, ys), y1 = Math.max.apply(null, ys);
      var pad = (y1 - y0) * 0.08 || Math.abs(y1) * 0.02 || 1;
      y0 -= pad; y1 += pad;
      function sx(v) { return left + (v - x0) / ((x1 - x0) || 1) * (width - left - right); }
      function sy(v) { return top + (y1 - v) / ((y1 - y0) || 1) * (height - top - bottom); }
      for (var i = 0; i <= 4; i++) {
        var v = y0 + (y1 - y0) * i / 4, y = sy(v);
        el("line", { x1: left, x2: width - right, y1: y, y2: y, class: "chart-grid" }, svg);
        el("text", { x: left - 6, y: y + 4, "text-anchor": "end", class: "chart-tick" }, svg).textContent =
          opts.yFormat ? opts.yFormat(v) : num(v, decimals);
      }
      var ticks = opts.xTicks || 5;
      for (var j = 0; j <= ticks; j++) {
        var xv = x0 + (x1 - x0) * j / ticks;
        var label = opts.xNumeric ? opts.xFormat(xv) : day(new Date(xv).toISOString().slice(0, 10)).slice(3);
        el("text", { x: sx(xv), y: height - 6, "text-anchor": j === 0 ? "start" : j === ticks ? "end" : "middle", class: "chart-tick" }, svg).textContent = label;
      }
      series.forEach(function (s) {
        var d = s.points.map(function (p, k) {
          var xv = opts.xNumeric ? p[0] : Date.parse(p[0]);
          return (k ? "L" : "M") + sx(xv).toFixed(1) + "," + sy(p[1]).toFixed(1);
        }).join("");
        var path = el("path", { d: d, class: "chart-line" + (s.muted ? " chart-line-muted" : "") + (s.dashed ? " chart-line-dashed" : "") + (s.color ? " chart-c" + s.color : "") }, svg);
        if (!animated && !s.dashed && path.getTotalLength) {  /* draw-in once, with the real length */
          var length = path.getTotalLength();
          path.style.strokeDasharray = length;
          path.style.strokeDashoffset = length;
          path.classList.add("chart-anim");
        }
        if (opts.dots) s.points.forEach(function (p) {
          el("circle", { cx: sx(p[0]), cy: sy(p[1]), r: 3.5, class: "chart-dot" + (s.muted ? " chart-dot-muted" : "") }, svg);
        });
      });
      var cross = el("line", { y1: top, y2: height - bottom, class: "chart-cross" }, svg);
      cross.style.display = "none";
      var marks = series.map(function (s) {
        var m = el("circle", { r: 4.5, class: "chart-mark" + (s.muted ? " chart-dot-muted" : "") + (s.color ? " chart-c" + s.color : "") }, svg);
        m.style.display = "none";
        return m;
      });
      geometry = { sx: sx, sy: sy, x0: x0, x1: x1, left: left, right: right, width: width, cross: cross, marks: marks };
      animated = true;
    }

    function nearest(points, x) {
      var best = null, dist = Infinity;
      points.forEach(function (p) {
        var px = opts.xNumeric ? p[0] : Date.parse(p[0]);
        var d = Math.abs(px - x);
        if (d < dist) { dist = d; best = p; }
      });
      return best;
    }
    function move(event) {
      if (!geometry || !series.length) return;
      var rect = svg.getBoundingClientRect();
      var px = (event.clientX - rect.left) * (geometry.width / rect.width);
      var x = geometry.x0 + (px - geometry.left) / (geometry.width - geometry.left - geometry.right) * (geometry.x1 - geometry.x0);
      var lines = [];
      var first = null;
      series.forEach(function (s, i) {
        var p = nearest(s.points, x);
        if (!p) return;
        if (!first) first = p;
        var xv = opts.xNumeric ? p[0] : Date.parse(p[0]);
        geometry.marks[i].setAttribute("cx", geometry.sx(xv));
        geometry.marks[i].setAttribute("cy", geometry.sy(p[1]));
        geometry.marks[i].style.display = "";
        lines.push((s.name ? s.name + ": " : "") + (opts.yFormat ? opts.yFormat(p[1]) : num(p[1], decimals)));
      });
      if (!first) return;
      var fx = opts.xNumeric ? first[0] : Date.parse(first[0]);
      geometry.cross.setAttribute("x1", geometry.sx(fx));
      geometry.cross.setAttribute("x2", geometry.sx(fx));
      geometry.cross.style.display = "";
      tip.textContent = "";
      var head = document.createElement("b");
      head.textContent = opts.xNumeric ? opts.xFormat(first[0]) : day(first[0]);
      tip.appendChild(head);
      lines.forEach(function (t) { var line = document.createElement("div"); line.textContent = t; tip.appendChild(line); });
      tip.hidden = false;
      var tipX = geometry.sx(fx) / geometry.width * rect.width;
      tip.style.left = Math.min(Math.max(tipX + 12, 0), rect.width - tip.offsetWidth - 4) + "px";
      tip.style.top = "8px";
    }
    function leave() {
      tip.hidden = true;
      if (!geometry) return;
      geometry.cross.style.display = "none";
      geometry.marks.forEach(function (m) { m.style.display = "none"; });
    }
    svg.addEventListener("pointermove", move);
    svg.addEventListener("pointerleave", leave);
    if (window.ResizeObserver) new ResizeObserver(function () { draw(); }).observe(box);
    window.addEventListener("luceiro:tema", draw);
    return {
      set: function (list, label) {
        series = list;
        if (label) svg.setAttribute("aria-label", label);
        draw();
      }
    };
  }

  /* --- Horizontal bars (scores) --------------------------------------------------------------- */
  function bars(box) {
    var rows = JSON.parse(box.querySelector("script[type='application/json']").textContent);
    var key = box.getAttribute("data-orden") || "a";
    function render() {
      box.querySelectorAll(".bar-row").forEach(function (r) { r.remove(); });
      rows.slice().sort(function (a, b) { return (b[key] === null ? -1 : b[key]) - (a[key] === null ? -1 : a[key]); })
        .forEach(function (r) {
          var row = document.createElement("a");
          row.className = "bar-row";
          row.href = r.href;
          var name = document.createElement("span");
          name.className = "bar-name";
          name.textContent = r.name;
          row.appendChild(name);
          ["a", "c"].forEach(function (k) {
            var track = document.createElement("span");
            track.className = "bar-track bar-" + k;
            var fill = document.createElement("span");
            fill.className = "bar-fill";
            fill.style.width = (r[k] === null ? 0 : r[k]) + "%";
            var value = document.createElement("span");
            value.className = "bar-value";
            value.textContent = r[k] === null ? "—" : num(r[k], 0);
            track.appendChild(fill);
            track.appendChild(value);
            row.appendChild(track);
          });
          box.appendChild(row);
        });
    }
    box.querySelectorAll("[data-orden-por]").forEach(function (button) {
      button.addEventListener("click", function () {
        key = button.getAttribute("data-orden-por");
        box.querySelectorAll("[data-orden-por]").forEach(function (b) { b.setAttribute("aria-pressed", String(b === button)); });
        render();
      });
    });
    render();
  }

  /* --- Small live touches -------------------------------------------------------------------- */
  function countUp(node) {
    var target = parseFloat(node.getAttribute("data-contar"));
    if (isNaN(target) || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    var start = performance.now();
    function step(now) {
      var t = Math.min((now - start) / 900, 1);
      node.textContent = num(Math.round(target * (1 - Math.pow(1 - t, 3))), 0);
      if (t < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }
  /* Exchanges open or closed now (local hours, Monday to Friday; holidays not considered) */
  function clocks() {
    document.querySelectorAll("[data-mercado]").forEach(function (node) {
      var zone = node.getAttribute("data-zona");
      var hours = node.getAttribute("data-horario").split("-");
      var parts = new Intl.DateTimeFormat("en-GB", { timeZone: zone, hour: "2-digit", minute: "2-digit", weekday: "short", hour12: false })
        .formatToParts(new Date());
      var get = function (t) { return (parts.find(function (p) { return p.type === t; }) || {}).value; };
      var minutes = parseInt(get("hour"), 10) * 60 + parseInt(get("minute"), 10);
      var weekend = get("weekday") === "Sat" || get("weekday") === "Sun";
      var open = !weekend && minutes >= toMinutes(hours[0]) && minutes < toMinutes(hours[1]);
      node.classList.toggle("abierto", open);
      node.querySelector(".hora").textContent = get("hour") + ":" + get("minute");
      node.querySelector(".estado").textContent = texto(open ? "abierto" : "cerrado");
    });
  }
  function toMinutes(hhmm) { var p = hhmm.split(":"); return parseInt(p[0], 10) * 60 + parseInt(p[1], 10); }
  function liveStamp(node, ok) {
    if (!node) return;
    node.classList.toggle("en-directo", ok);
    var now = new Date();
    node.querySelector(".estado").textContent = texto(ok ? "en-directo" : "sin-conexion");
    node.querySelector(".hora").textContent = ok ? now.toLocaleTimeString(LOCALE, { hour: "2-digit", minute: "2-digit" }) : "";
  }

  /* --- Market views (Panel and Mercados) ---------------------------------------------------- */
  var DAY = 864e5;
  var RANGES = { "1M": 31, "3M": 92, "6M": 183, "1A": 366, "2A": 731 };
  var TENOR_YEARS = { "3M": 0.25, "6M": 0.5, "1Y": 1, "2Y": 2, "3Y": 3, "5Y": 5, "7Y": 7, "10Y": 10, "15Y": 15, "20Y": 20, "30Y": 30 };

  function lastDays(points, days) {
    if (!points || !points.length) return [];
    var end = Date.parse(points[points.length - 1][0]) - days * DAY;
    return points.filter(function (p) { return Date.parse(p[0]) >= end; });
  }
  function valueBefore(points, days) {
    var end = Date.parse(points[points.length - 1][0]) - days * DAY;
    for (var i = points.length - 1; i >= 0; i--) if (Date.parse(points[i][0]) <= end) return points[i][1];
    return null;
  }
  function change(points, days) {
    if (!points || points.length < 2) return null;
    var before = days === 1 ? points[points.length - 2][1] : valueBefore(points, days);
    return before ? points[points.length - 1][1] / before - 1 : null;
  }
  function ytd(points) {
    if (!points || !points.length) return null;
    var year = points[points.length - 1][0].slice(0, 4);
    var ref = null;
    points.forEach(function (p) { if (p[0].slice(0, 4) < year) ref = p[1]; });
    return ref ? points[points.length - 1][1] / ref - 1 : null;
  }
  function tone(v) { return v > 0 ? "up" : v < 0 ? "down" : ""; }
  function arrow(v) { return v > 0 ? "▲" : v < 0 ? "▼" : "■"; }
  function sparkSvg(points, width, height) {
    if (!points || points.length < 2) return "";
    var ys = points.map(function (p) { return p[1]; });
    var lo = Math.min.apply(null, ys), hi = Math.max.apply(null, ys), span = hi - lo || 1;
    var d = points.map(function (p, i) {
      return (i ? "L" : "M") + (i * width / (points.length - 1)).toFixed(1) + "," + (height - 2 - (p[1] - lo) / span * (height - 4)).toFixed(1);
    }).join("");
    var last = points[points.length - 1][1], first = points[0][1];
    return '<svg class="spark ' + tone(last - first) + '" viewBox="0 0 ' + width + " " + height + '" aria-hidden="true"><path d="' + d + '"/></svg>';
  }
  function setText(root, selector, text, toneValue) {
    var node = root.querySelector(selector);
    if (!node) return;
    node.textContent = text;
    if (toneValue !== undefined) { node.classList.remove("up", "down"); var t = tone(toneValue); if (t) node.classList.add(t); }
  }
  function curveDates(curve) {
    var days = Object.keys(curve).sort();
    if (!days.length) return [];
    var last = days[days.length - 1], t = Date.parse(last);
    function before(n) { var pick = null; days.forEach(function (d) { if (Date.parse(d) <= t - n * DAY) pick = d; }); return pick; }
    return [last, before(30), before(365)];
  }
  function curvePoints(values, tenors) {
    return tenors.filter(function (k) { return values && values[k] !== undefined; })
      .map(function (k) { return [tenors.indexOf(k), values[k]]; });
  }

  function markets() {
    var source = document.getElementById("mercado");
    if (!source) return;
    var data = JSON.parse(source.textContent);
    var state = { cur: "USD", range: "1A" };
    var tenors = data.tenors;
    var fxBox = document.getElementById("grafico-fx");
    var curveBox = document.getElementById("grafico-curva");
    var estrBox = document.getElementById("grafico-estr");
    var fxChart = fxBox && lineChart(fxBox, { height: fxBox.getAttribute("data-alto") ? +fxBox.getAttribute("data-alto") : 300 });
    var curveChart = curveBox && lineChart(curveBox, {
      height: 260, xNumeric: true, xTicks: tenors.length - 1, dots: true, decimals: 2,
      xFormat: function (v) { return tenors[Math.round(v)] || ""; },
      yFormat: function (v) { return num(v, 2) + " %"; }
    });
    var estrChart = estrBox && lineChart(estrBox, { height: 220, decimals: 3, yFormat: function (v) { return num(v, 3) + " %"; } });
    var bondsBox = document.getElementById("grafico-bonos");
    var spreadBox = document.getElementById("grafico-prima");
    var bondsChart = bondsBox && lineChart(bondsBox, { height: 260, decimals: 2, yFormat: function (v) { return num(v, 2) + " %"; } });
    var spreadChart = spreadBox && lineChart(spreadBox, { height: 260, decimals: 0, yFormat: function (v) { return num(v, 0) + " pb"; } });
    function spread(country) {  /* country minus Germany, in basis points, month by month */
      var de = {}, out = [];
      (data.bonds.DE || []).forEach(function (p) { de[p[0]] = p[1]; });
      (data.bonds[country] || []).forEach(function (p) { if (de[p[0]] !== undefined) out.push([p[0], (p[1] - de[p[0]]) * 100]); });
      return out;
    }

    function curveLatest() {
      var dates = curveDates(data.curve);
      return dates.length ? data.curve[dates[0]] : null;
    }
    function curveYesterday() {
      var days = Object.keys(data.curve).sort();
      return days.length > 1 ? data.curve[days[days.length - 2]] : null;
    }
    function render() {
      var ticker = document.querySelector(".ticker-track");
      if (ticker) {
        var items = [];
        data.currencies.forEach(function (c) {
          var s = data.fx[c]; if (!s || !s.length) return;
          var ch = change(s, 1);
          items.push('<span class="tk"><b>EUR/' + c + "</b> " + num(s[s.length - 1][1], 4) +
            ' <span class="' + tone(ch) + '">' + arrow(ch) + " " + (ch === null ? "" : pct(ch)) + "</span></span>");
        });
        if (data.estr.length) {
          var e = data.estr, de = e.length > 1 ? (e[e.length - 1][1] - e[e.length - 2][1]) * 100 : 0;
          items.push('<span class="tk"><b>€STR</b> ' + num(e[e.length - 1][1], 3) + ' % <span class="' + tone(de) + '">' + arrow(de) + "</span></span>");
        }
        var latest = curveLatest(), prev = curveYesterday();
        if (latest && latest["10Y"] !== undefined) {
          var d10 = prev && prev["10Y"] !== undefined ? latest["10Y"] - prev["10Y"] : 0;
          items.push('<span class="tk"><b>' + texto("curva-10a", "AAA 10Y") + "</b> " + num(latest["10Y"], 2) + ' % <span class="' + tone(d10) + '">' + arrow(d10) + "</span></span>");
        }
        ticker.innerHTML = items.join("") + items.join("");  // twice: the band loops seamlessly
      }
      document.querySelectorAll("[data-kpi]").forEach(function (card) {
        var kind = card.getAttribute("data-kpi"), points = null, value = "", delta = "", deltaValue = 0;
        if (data.fx[kind]) {
          points = data.fx[kind];
          value = num(points[points.length - 1][1], 4);
          deltaValue = change(points, 1);
          delta = deltaValue === null ? "" : pct(deltaValue);
        } else if (kind === "estr" && data.estr.length) {
          points = data.estr;
          value = num(points[points.length - 1][1], 3) + " %";
          deltaValue = points.length > 1 ? (points[points.length - 1][1] - points[points.length - 2][1]) * 100 : 0;
          delta = (deltaValue > 0 ? "+" : deltaValue < 0 ? "−" : "") + num(Math.abs(deltaValue), 1) + " pb";
        } else if (kind === "dfr" && data.dfr.length) {
          points = data.dfr;
          value = num(points[points.length - 1][1], 2) + " %";
          var yearAgo = valueBefore(points, 365);
          deltaValue = yearAgo === null ? 0 : (points[points.length - 1][1] - yearAgo) * 100;
          delta = (deltaValue > 0 ? "+" : deltaValue < 0 ? "−" : "") + num(Math.abs(deltaValue), 0) + " pb · 1A";
        } else if (kind === "prima") {
          points = spread("ES");
          if (points.length) {
            value = num(points[points.length - 1][1], 0) + " pb";
            deltaValue = points.length > 1 ? points[points.length - 1][1] - points[points.length - 2][1] : 0;
            delta = (deltaValue > 0 ? "+" : deltaValue < 0 ? "−" : "") + num(Math.abs(deltaValue), 0) + " pb";
          }
        } else if (kind === "10Y") {
          var days = Object.keys(data.curve).sort();
          points = days.filter(function (d) { return data.curve[d]["10Y"] !== undefined; }).map(function (d) { return [d, data.curve[d]["10Y"]]; });
          if (points.length) {
            value = num(points[points.length - 1][1], 2) + " %";
            deltaValue = points.length > 1 ? (points[points.length - 1][1] - points[points.length - 2][1]) * 100 : 0;
            delta = (deltaValue > 0 ? "+" : deltaValue < 0 ? "−" : "") + num(Math.abs(deltaValue), 1) + " pb";
          }
        }
        if (!points || !points.length) return;
        setText(card, ".k-valor", value);
        setText(card, ".k-cambio", delta, deltaValue);
        setText(card, ".k-fecha", day(points[points.length - 1][0]));
        var sp = card.querySelector(".k-spark");
        if (sp) sp.innerHTML = sparkSvg(lastDays(points, kind === "prima" ? 3 * 366 : 92), 120, 34);  /* monthly series: 3 years */
      });
      var heat = document.getElementById("mapa-fx");
      if (heat) {
        heat.innerHTML = "";
        data.currencies.forEach(function (c) {
          var s = data.fx[c]; if (!s || !s.length) return;
          var ch = change(s, 1) || 0;
          var tile = document.createElement("button");
          tile.type = "button";
          tile.className = "heat-tile " + tone(ch);
          tile.style.setProperty("--fuerza", Math.min(Math.abs(ch) / 0.008, 1).toFixed(2));
          tile.setAttribute("aria-pressed", String(c === state.cur));
          tile.innerHTML = '<span class="heat-code">' + c + '</span><span class="heat-value">' + num(s[s.length - 1][1], 4) +
            '</span><span class="heat-change">' + pct(ch) + "</span>";
          tile.addEventListener("click", function () { state.cur = c; render(); });
          heat.appendChild(tile);
        });
      }
      if (fxChart && data.fx[state.cur]) {
        var points = lastDays(data.fx[state.cur], RANGES[state.range]);
        fxChart.set([{ name: "EUR/" + state.cur, points: points }], "EUR/" + state.cur);
        var vals = points.map(function (p) { return p[1]; });
        var first = points.length ? points[0][1] : null, last = points.length ? points[points.length - 1][1] : null;
        var box = document.getElementById("fx-datos") || document;
        setText(box, "#fx-titulo", "EUR/" + state.cur);
        setText(box, "#fx-ultimo", last === null ? "—" : num(last, 4));
        setText(box, "#fx-cambio", first ? pct(last / first - 1) : "—", first ? last / first - 1 : 0);
        setText(box, "#fx-min", vals.length ? num(Math.min.apply(null, vals), 4) : "—");
        setText(box, "#fx-max", vals.length ? num(Math.max.apply(null, vals), 4) : "—");
        document.querySelectorAll("[data-divisa]").forEach(function (b) { b.setAttribute("aria-pressed", String(b.getAttribute("data-divisa") === state.cur)); });
      }
      if (curveChart) {
        var dates = curveDates(data.curve);
        var names = [texto("hoy", "Hoy"), texto("hace-un-mes", "Hace un mes"), texto("hace-un-ano", "Hace un año")];
        var list = [];
        dates.forEach(function (d, i) {
          if (!d) return;
          list.push({ name: names[i] + " (" + day(d) + ")", points: curvePoints(data.curve[d], tenors), muted: i > 0, dashed: i === 2 });
        });
        curveChart.set(list.reverse(), texto("curva", "Curva"));
      }
      if (estrChart && data.estr.length) estrChart.set([{ name: "€STR", points: lastDays(data.estr, 366) }], "€STR");
      if (bondsChart && data.bonds) {
        bondsChart.set(data.countries.filter(function (c) { return data.bonds[c] && data.bonds[c].length; }).map(function (c, i) {
          return { name: texto("pais-" + c, c), points: lastDays(data.bonds[c], 5 * 366), color: data.countries.indexOf(c) + 1 };
        }), texto("bonos", "Bonos"));
      }
      if (spreadChart && data.bonds) {
        spreadChart.set(["ES", "IT"].map(function (c, i) {
          return { name: texto("prima-" + c, c), points: lastDays(spread(c), 5 * 366), color: data.countries.indexOf(c) + 1 };
        }).filter(function (s) { return s.points.length; }), texto("prima", "Prima"));
      }
      document.querySelectorAll("tr[data-cur]").forEach(function (row) {
        var s = data.fx[row.getAttribute("data-cur")]; if (!s || !s.length) return;
        var v = s[s.length - 1][1];
        setText(row, ".c-valor", num(v, 4));
        setText(row, ".c-inv", num(1 / v, 4));
        [["c-1s", 7], ["c-1m", 30], ["c-1a", 365]].forEach(function (pair) {
          var ch = change(s, pair[1]);
          setText(row, "." + pair[0], ch === null ? "—" : pct(ch), ch || 0);
        });
        var y = ytd(s);
        setText(row, ".c-ytd", y === null ? "—" : pct(y), y || 0);
        var cell = row.querySelector(".c-spark");
        if (cell) cell.innerHTML = sparkSvg(lastDays(s, 366), 140, 36);
      });
      document.querySelectorAll("[data-fecha-mercado]").forEach(function (node) {
        var s = data.fx.USD || data.fx[data.currencies[0]];
        if (s && s.length) node.textContent = day(s[s.length - 1][0]);
      });
    }

    document.querySelectorAll("[data-rango]").forEach(function (b) {
      b.addEventListener("click", function () {
        state.range = b.getAttribute("data-rango");
        document.querySelectorAll("[data-rango]").forEach(function (x) { x.setAttribute("aria-pressed", String(x === b)); });
        render();
      });
    });
    document.querySelectorAll("[data-divisa]").forEach(function (b) {
      b.addEventListener("click", function () { state.cur = b.getAttribute("data-divisa"); render(); });
    });
    render();

    function live() {
      var long = new Date(Date.now() - 735 * DAY).toISOString().slice(0, 10);
      var short = new Date(Date.now() - 400 * DAY).toISOString().slice(0, 10);
      var bondsStart = new Date(Date.now() - 6 * 366 * DAY).toISOString().slice(0, 7);
      Promise.allSettled([
        ecb("/" + data.keys.dfr + "?startPeriod=" + short),
        ecb("/" + data.keys.bonds + "?startPeriod=" + bondsStart),
        fxSeries(data.currencies, long),
        ecb("/EST/B.EU000A2X2A25.WT?startPeriod=" + short),
        ecb("/YC/B.U2.EUR.4F.G_N_A.SV_C_YM." + tenors.map(function (t) { return "SR_" + t; }).join("+") + "?startPeriod=" + short)
      ]).then(function (all) {
        var ok = false;
        if (all[0].status === "fulfilled" && all[0].value.length) { data.dfr = all[0].value.map(function (x) { return [x.date, x.value]; }); ok = true; }
        if (all[1].status === "fulfilled" && all[1].value.length) {
          var b = {};
          all[1].value.forEach(function (x) { var c = x.key.split(".")[2]; (b[c] = b[c] || []).push([x.date, x.value]); });
          Object.keys(b).forEach(function (c) { b[c].sort(function (p, q) { return p[0] < q[0] ? -1 : 1; }); });
          data.bonds = b; ok = true;
        }
        var r = all.slice(2);
        if (r[0].status === "fulfilled" && Object.keys(r[0].value).length) { data.fx = r[0].value; ok = true; }
        if (r[1].status === "fulfilled" && r[1].value.length) { data.estr = r[1].value.map(function (x) { return [x.date, x.value]; }); ok = true; }
        if (r[2].status === "fulfilled" && r[2].value.length) {
          var c = {};
          r[2].value.forEach(function (x) { (c[x.date] = c[x.date] || {})[x.key.split("SR_")[1]] = x.value; });
          data.curve = c; ok = true;
        }
        liveStamp(document.querySelector(".live"), ok);
        if (ok) render();
      });
    }
    live();
    setInterval(live, 15 * 60 * 1000);
  }

  /* --- TradingView widgets (indices, commodities, Spanish stocks) --------------------------------
   * The data are TradingView's, shown inside its own official widget: they are not copied nor
   * republished here. Each container: <div data-tv="widget-file-name"><script type="application/json">
   * {config}</script></div>. Strings starting with "@" are labels of the page (translated). */
  function tradingview() {
    var boxes = document.querySelectorAll("[data-tv]");
    if (!boxes.length) return;
    function build() {
      var dark = (getComputedStyle(document.documentElement).colorScheme || "").indexOf("dark") >= 0;
      boxes.forEach(function (box) {
        var source = box.querySelector("script[type='application/json']");
        if (!box._config) box._config = source ? source.textContent : "{}";
        var config = JSON.parse(box._config, function (key, value) {
          return typeof value === "string" && value.charAt(0) === "@" ? texto(value.slice(1), value.slice(1)) : value;
        });
        config.colorTheme = dark ? "dark" : "light";
        config.isTransparent = true;
        config.locale = document.documentElement.lang === "en" ? "en" : "es";
        box.innerHTML = '<div class="tradingview-widget-container" style="height:100%"><div class="tradingview-widget-container__widget" style="height:100%"></div></div>';
        var script = document.createElement("script");
        script.src = "https://s3.tradingview.com/external-embedding/embed-widget-" + box.getAttribute("data-tv") + ".js";
        script.async = true;
        script.textContent = JSON.stringify(config);
        box.firstChild.appendChild(script);
      });
    }
    build();
    var pending = null;
    window.addEventListener("luceiro:tema", function () {  /* new style or mode: redraw with its theme */
      clearTimeout(pending);
      pending = setTimeout(build, 300);
    });
  }

  /* --- World economy (World Bank, downloaded with the website) ------------------------------ */
  function world() {
    var table = document.getElementById("economia");
    var source = document.getElementById("mercado");
    if (!table || !source) return;
    var data = JSON.parse(source.textContent);
    var w = data.world || {};
    function get(key, country) { return (w[key] || {})[country] || null; }
    var rows = (data.world_countries || []).map(function (c) {
      return { c: c, pib: get("pib", c), ipc: get("inflacion", c), paro: get("paro", c) };
    }).filter(function (r) { return r.pib || r.ipc || r.paro; });
    rows.sort(function (a, b) { return (b.pib ? b.pib[1] : -99) - (a.pib ? a.pib[1] : -99); });
    var max = Math.max.apply(null, rows.map(function (r) { return r.pib ? Math.abs(r.pib[1]) : 0; })) || 1;
    var body = table.querySelector("tbody");
    body.innerHTML = "";
    rows.forEach(function (r) {
      var tr = document.createElement("tr");
      function td(text, cls) { var cell = document.createElement("td"); cell.className = cls || ""; cell.textContent = text; tr.appendChild(cell); return cell; }
      function pctCell(v) { td(v ? num(v[1], 1) + " %" : "—", "num"); }
      td(texto("pais-" + r.c, r.c));
      var bar = td("", "gdp-bar");
      if (r.pib) {
        var fill = document.createElement("span");
        fill.className = "gdp-fill " + (r.pib[1] < 0 ? "down" : "up");
        fill.style.width = (Math.abs(r.pib[1]) / max * 100).toFixed(1) + "%";
        bar.appendChild(fill);
      }
      pctCell(r.pib); pctCell(r.ipc); pctCell(r.paro);
      td(r.pib ? r.pib[0] : r.ipc ? r.ipc[0] : "", "num muted small");
      body.appendChild(tr);
    });
    if (!rows.length) table.closest(".panel-card").hidden = true;
  }

  document.addEventListener("DOMContentLoaded", function () {
    tradingview();
    world();
    document.querySelectorAll("[data-contar]").forEach(countUp);
    document.querySelectorAll(".bars").forEach(bars);
    if (document.querySelector("[data-mercado]")) { clocks(); setInterval(clocks, 30000); }
    markets();
  });
  new MutationObserver(function () { window.dispatchEvent(new Event("luceiro:tema")); })
    .observe(document.documentElement, { attributes: true, attributeFilter: ["data-estilo", "data-theme"] });

  window.Graficos = {
    ecb: ecb, fxSeries: fxSeries, lineChart: lineChart, liveStamp: liveStamp,
    num: num, pct: pct, day: day, texto: texto
  };
})();
