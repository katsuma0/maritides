/* Grand Manan tide viewer.
 *
 * Everything is computed in the browser from harmonic constituents baked into
 * tide-data.js, so the page needs no network once it has been loaded once.
 *
 *   height(t) = datum + sum_i  amp_i(year) * cos( speed_i * (dt + meridian)
 *                                                 + phase_i(year) )
 *
 * where dt is seconds from 00:00 UTC on Jan 1 of `year` to t, and the per-year
 * amp/phase arrays already fold in the node factor and equilibrium argument.
 * This matches XTide and OpenCPN exactly; see tools/build_tide_data.py.
 */
(function () {
  "use strict";

  var DATA = window.TIDE_DATA;
  var TZ = DATA.timezone; // America/Halifax
  var HOUR = 3600, DAY = 86400;
  var FORECAST_DAYS = 14;
  var CHART_BACK = 6 * HOUR, CHART_FWD = 30 * HOUR;

  /* ── Prediction ────────────────────────────────────────────── */

  function yearOf(ts) { return new Date(ts * 1000).getUTCFullYear(); }
  function yearStart(y) { return Date.UTC(y, 0, 1, 0, 0, 0) / 1000; }

  function termsFor(st, ts) {
    var y = yearOf(ts);
    if (y < DATA.firstYear) y = DATA.firstYear;
    if (y > DATA.lastYear) y = DATA.lastYear;
    return { row: st.years[y], dt: ts - yearStart(y) + st.meridian };
  }

  function heightAt(st, ts) {
    var t = termsFor(st, ts), amp = t.row.amp, ph = t.row.phase, sp = st.speeds;
    var h = st.datum;
    for (var i = 0; i < sp.length; i++) h += amp[i] * Math.cos(sp[i] * t.dt + ph[i]);
    return h;
  }

  function slopeAt(st, ts) {
    var t = termsFor(st, ts), amp = t.row.amp, ph = t.row.phase, sp = st.speeds;
    var d = 0;
    for (var i = 0; i < sp.length; i++) d -= amp[i] * sp[i] * Math.sin(sp[i] * t.dt + ph[i]);
    return d;
  }

  /* Turning points, found by bracketing sign changes of the derivative. */
  function extremes(st, t0, t1) {
    var out = [], step = 300, prev = slopeAt(st, t0);
    for (var t = t0; t < t1; t += step) {
      var next = slopeAt(st, t + step);
      if ((prev > 0) !== (next > 0)) {
        var lo = t, hi = t + step;
        for (var k = 0; k < 40; k++) {
          var mid = (lo + hi) / 2;
          if ((slopeAt(st, lo) > 0) !== (slopeAt(st, mid) > 0)) hi = mid; else lo = mid;
        }
        var tm = Math.round((lo + hi) / 2);
        out.push({ t: tm, h: heightAt(st, tm), kind: prev > 0 ? "high" : "low" });
      }
      prev = next;
    }
    return out;
  }

  /* ── Local (Atlantic) time helpers ─────────────────────────── */

  var fmtWeekday = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, weekday: "short" });
  var fmtDayMon = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, month: "short", day: "numeric" });
  var fmtParts = new Intl.DateTimeFormat("en-CA", {
    timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hour12: false
  });

  function localParts(ts) {
    var p = {}, arr = fmtParts.formatToParts(ts * 1000);
    for (var i = 0; i < arr.length; i++) if (arr[i].type !== "literal") p[arr[i].type] = arr[i].value;
    var hour = +p.hour % 24; // en-CA reports midnight as 24
    return { key: p.year + "-" + p.month + "-" + p.day, hour: hour, minute: +p.minute };
  }

  /* "6:04 PM" — built by hand so the whole app agrees on one compact form
     regardless of what the device locale would have produced. */
  function clockTime(ts) {
    var p = localParts(ts);
    var h12 = p.hour % 12 || 12;
    return h12 + ":" + String(p.minute).padStart(2, "0") + (p.hour < 12 ? " AM" : " PM");
  }

  /* "6PM" / "12AM" for axis ticks, "6p" when space is tight. */
  function tickTime(ts, tight) {
    var p = localParts(ts);
    var h12 = p.hour % 12 || 12;
    return tight ? h12 + (p.hour < 12 ? "a" : "p") : h12 + (p.hour < 12 ? "AM" : "PM");
  }

  /* Midnight of the local day containing ts. */
  function startOfLocalDay(ts) {
    var p = localParts(ts);
    var t = Math.floor(ts / 60) * 60 - p.hour * HOUR - p.minute * 60;
    // A DST shift inside the day can leave this an hour off; nudge it back.
    for (var i = 0; i < 3 && localParts(t).key !== p.key; i++) t += HOUR;
    for (var j = 0; j < 3 && localParts(t - 60).key === p.key; j++) t -= HOUR;
    return t;
  }

  /* ── Formatting ────────────────────────────────────────────── */

  /* +0 collapses -0, so a low a few millimetres under datum is not "-0.0 m". */
  function metres(h) { return (h.toFixed(1) === "-0.0" ? 0 : +h.toFixed(1)).toFixed(1) + " m"; }
  function feet(h) { return (Math.round(h * 3.28084) + 0) + " ft"; }
  function bothUnits(h) { return metres(h) + " / " + feet(h); }

  function duration(sec) {
    var m = Math.max(0, Math.round(sec / 60));
    var h = Math.floor(m / 60);
    m -= h * 60;
    if (h === 0) return m + " min";
    return h + "h " + String(m).padStart(2, "0") + "m";
  }

  function durationWords(sec) {
    var m = Math.max(0, Math.round(sec / 60));
    var h = Math.floor(m / 60);
    m -= h * 60;
    if (h === 0) return m + " minute" + (m === 1 ? "" : "s");
    if (m === 0) return h + " hour" + (h === 1 ? "" : "s");
    return h + " hour" + (h === 1 ? "" : "s") + " " + m + " min";
  }

  /* ── State ─────────────────────────────────────────────────── */

  var station = DATA.stations[0];
  var events = [];
  var $ = function (id) { return document.getElementById(id); };

  function recompute() {
    var now = Date.now() / 1000;
    events = extremes(station, now - 2 * DAY, now + (FORECAST_DAYS + 2) * DAY);
  }

  /* True while events[] still covers everything the UI wants to draw. A tab left
     open for days must re-extend before the day list starts losing its tail. */
  function eventsCover(now) {
    return events.length > 0 &&
      events[0].t < now - CHART_BACK &&
      events[events.length - 1].t > now + FORECAST_DAYS * DAY + CHART_FWD;
  }

  /* ── Hero ──────────────────────────────────────────────────── */

  function renderHero(now) {
    var h = heightAt(station, now);
    var rising = slopeAt(station, now) > 0;

    var next = null, prev = null;
    for (var i = 0; i < events.length; i++) {
      if (events[i].t > now) { next = events[i]; prev = events[i - 1] || null; break; }
    }
    if (!next) return;

    var nextHigh = null, nextLow = null;
    for (var j = 0; j < events.length; j++) {
      if (events[j].t <= now) continue;
      if (!nextHigh && events[j].kind === "high") nextHigh = events[j];
      if (!nextLow && events[j].kind === "low") nextLow = events[j];
    }

    $("dir-badge").textContent = rising ? "↑" : "↓";
    $("dir-badge").className = "dir-badge" + (rising ? "" : " is-falling");
    $("dir-word").textContent = rising ? "The tide is coming in" : "The tide is going out";
    $("dir-sub").textContent = rising
      ? "Water is rising toward high tide"
      : "Water is falling toward low tide";

    $("countdown-label").textContent = next.kind === "high" ? "High tide in" : "Low tide in";
    $("countdown").textContent = duration(next.t - now);
    $("countdown-detail").textContent =
      "at " + clockTime(next.t) + " · " + bothUnits(next.h);

    if (prev) {
      var frac = (now - prev.t) / (next.t - prev.t);
      $("meter-fill").style.width = (Math.min(1, Math.max(0, frac)) * 100).toFixed(1) + "%";
      $("meter-from").textContent =
        (prev.kind === "high" ? "High " : "Low ") + clockTime(prev.t);
      $("meter-to").textContent =
        (next.kind === "high" ? "High " : "Low ") + clockTime(next.t);
      $("meter-fig").setAttribute("aria-label",
        durationWords(now - prev.t) + " since " + prev.kind + " tide, " +
        durationWords(next.t - now) + " until " + next.kind + " tide.");
    }

    $("fact-now").innerHTML = metres(h) + "<small>" + feet(h) + "</small>";
    if (nextHigh) {
      $("fact-high").innerHTML = clockTime(nextHigh.t) +
        "<small>" + metres(nextHigh.h) + " · " + duration(nextHigh.t - now) + "</small>";
    }
    if (nextLow) {
      $("fact-low").innerHTML = clockTime(nextLow.t) +
        "<small>" + metres(nextLow.h) + " · " + duration(nextLow.t - now) + "</small>";
    }

    $("clock").textContent =
      fmtWeekday.format(now * 1000) + " " + clockTime(now) + " Atlantic";
  }

  /* ── Chart ─────────────────────────────────────────────────── */

  var SVG_NS = "http://www.w3.org/2000/svg";
  var chartGeom = null;
  var chartCursor = null;   // the hover crosshair; a redraw detaches it

  function el(name, attrs) {
    var n = document.createElementNS(SVG_NS, name);
    for (var k in attrs) if (attrs[k] != null) n.setAttribute(k, attrs[k]);
    return n;
  }

  function renderChart(now) {
    var svg = $("chart");
    var wrap = $("chart-wrap");
    // The viewBox must equal the rendered CSS size. Any mismatch makes the SVG
    // scale-to-fit, which letterboxes the plot and offsets the hover readout.
    var W = Math.round(wrap.clientWidth);
    var H = Math.round(svg.getBoundingClientRect().height) || 260;
    if (W < 1) return;   // container not laid out yet
    var pad = { t: 30, r: 12, b: 40, l: 32 };

    while (svg.firstChild) svg.removeChild(svg.firstChild);
    chartCursor = null;  // the old crosshair node just got detached
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);

    var t0 = now - CHART_BACK, t1 = now + CHART_FWD;
    var iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;

    // Sample the curve.
    var pts = [], N = Math.max(120, Math.round(iw));
    var lo = Infinity, hi = -Infinity;
    for (var i = 0; i <= N; i++) {
      var t = t0 + (t1 - t0) * (i / N), h = heightAt(station, t);
      pts.push([t, h]);
      if (h < lo) lo = h;
      if (h > hi) hi = h;
    }
    // Generous headroom top and bottom: the crest and trough labels live there.
    // yMin is deliberately allowed below zero — clamping it at chart datum eats
    // the bottom headroom on spring tides and drops the trough labels onto the
    // hour axis. Gridlines still start at 0.
    var span = Math.max(0.5, hi - lo);
    var yMin = lo - span * 0.22, yMax = hi + span * 0.22;

    var X = function (t) { return pad.l + iw * (t - t0) / (t1 - t0); };
    var Y = function (h) { return pad.t + ih * (1 - (h - yMin) / (yMax - yMin)); };
    chartGeom = { t0: t0, t1: t1, X: X, Y: Y, pad: pad, W: W, H: H, iw: iw, ih: ih };

    // Horizontal gridlines on clean metre values.
    var stepM = span > 6 ? 2 : 1;
    for (var g = Math.max(0, Math.ceil(yMin / stepM) * stepM); g <= yMax; g += stepM) {
      svg.appendChild(el("line", {
        x1: pad.l, x2: W - pad.r, y1: Y(g), y2: Y(g),
        stroke: "var(--grid)", "stroke-width": 1
      }));
      var lbl = el("text", {
        x: pad.l - 7, y: Y(g) + 4, "text-anchor": "end",
        fill: "var(--ink-muted)", "font-size": 10
      });
      lbl.style.fontVariantNumeric = "tabular-nums";
      lbl.textContent = g + "m";
      svg.appendChild(lbl);
    }

    // Vertical ticks every 6 local hours.
    var tight = iw < 400;
    for (var tt = Math.ceil(t0 / HOUR) * HOUR; tt <= t1; tt += HOUR) {
      var lp = localParts(tt);
      if (lp.minute !== 0 || lp.hour % 6 !== 0) continue;
      var midnight = lp.hour === 0;
      svg.appendChild(el("line", {
        x1: X(tt), x2: X(tt), y1: pad.t, y2: pad.t + ih,
        stroke: "var(--grid)", "stroke-width": 1
      }));
      var xl = el("text", {
        x: X(tt), y: H - 17, "text-anchor": "middle",
        fill: "var(--ink-muted)", "font-size": 10,
        "font-weight": midnight ? 640 : 400
      });
      xl.textContent = tickTime(tt, tight);
      svg.appendChild(xl);
      if (midnight) {
        var dl = el("text", {
          x: X(tt), y: H - 5, "text-anchor": "middle",
          fill: "var(--ink-muted)", "font-size": 9
        });
        dl.textContent = fmtWeekday.format(tt * 1000);
        svg.appendChild(dl);
      }
    }

    // Area wash + 2px line.
    var d = "", area = "";
    for (var p = 0; p < pts.length; p++) {
      d += (p ? "L" : "M") + X(pts[p][0]).toFixed(2) + " " + Y(pts[p][1]).toFixed(2);
    }
    area = d + "L" + X(t1).toFixed(2) + " " + (pad.t + ih) + "L" + X(t0).toFixed(2) + " " + (pad.t + ih) + "Z";
    svg.appendChild(el("path", { d: area, fill: "var(--series)", "fill-opacity": 0.10 }));
    svg.appendChild(el("path", {
      d: d, fill: "none", stroke: "var(--series)", "stroke-width": 2,
      "stroke-linejoin": "round", "stroke-linecap": "round"
    }));

    // Now — drawn before the extreme labels so their text stays on top of the line.
    svg.appendChild(el("line", {
      x1: X(now), x2: X(now), y1: pad.t - 8, y2: pad.t + ih,
      stroke: "var(--ink)", "stroke-width": 1.5, "stroke-opacity": .55
    }));
    var nowLab = el("text", {
      x: Math.min(W - pad.r, Math.max(pad.l + 12, X(now))), y: pad.t - 13,
      "text-anchor": "middle", fill: "var(--ink)", "font-size": 10, "font-weight": 650
    });
    nowLab.textContent = "NOW";
    svg.appendChild(nowLab);

    // Direct labels on the extremes — the points the reader actually wants.
    events.forEach(function (e) {
      if (e.t < t0 || e.t > t1) return;
      var cx = X(e.t), cy = Y(e.h), high = e.kind === "high";
      svg.appendChild(el("circle", {
        cx: cx, cy: cy, r: 4.5, fill: "var(--series)",
        stroke: "var(--surface)", "stroke-width": 2
      }));
      // Time then height, reading downward, on both crests and troughs.
      var timeY = high ? cy - 25 : cy + 16;
      var heightY = timeY + 11;
      var anchor = "middle", tx = cx;
      if (cx < pad.l + 26) { anchor = "start"; tx = pad.l; }
      if (cx > W - pad.r - 26) { anchor = "end"; tx = W - pad.r; }
      var lab = el("text", {
        x: tx, y: timeY, "text-anchor": anchor,
        fill: "var(--ink)", "font-size": 11, "font-weight": 640
      });
      // Keep a compact meridiem: without it a 12:09 crest reads the same at
      // midnight and noon, which is exactly the pair a tide chart must separate.
      lab.textContent = clockTime(e.t).replace(/ ([AP])M$/, function (_, m) {
        return m.toLowerCase();
      });
      svg.appendChild(lab);
      var sub = el("text", {
        x: tx, y: heightY, "text-anchor": anchor,
        fill: "var(--ink-muted)", "font-size": 10
      });
      sub.textContent = e.h.toFixed(1) + "m";
      svg.appendChild(sub);
    });

    var nowH = heightAt(station, now);
    svg.appendChild(el("circle", {
      cx: X(now), cy: Y(nowH), r: 5, fill: "var(--ink)",
      stroke: "var(--surface)", "stroke-width": 2
    }));

    var inWindow = events.filter(function (e) { return e.t >= t0 && e.t <= t1; });
    $("chart-desc").textContent = "Tide curve for " + station.name + ". " +
      inWindow.map(function (e) {
        return e.kind + " tide " + clockTime(e.t) + " at " + metres(e.h);
      }).join("; ") + ".";
  }

  /* ── Hover / touch readout ─────────────────────────────────── */

  function bindTooltip() {
    var wrap = $("chart-wrap"), tip = $("tooltip"), svg = $("chart");

    function move(ev) {
      if (!chartGeom) return;
      var r = svg.getBoundingClientRect();
      var scale = chartGeom.W / r.width;
      var x = (ev.clientX - r.left) * scale;
      if (x < chartGeom.pad.l || x > chartGeom.W - chartGeom.pad.r) return hide();

      var t = chartGeom.t0 + (chartGeom.t1 - chartGeom.t0) *
        (x - chartGeom.pad.l) / chartGeom.iw;
      var h = heightAt(station, t);
      var cy = chartGeom.Y(h) / scale;

      tip.hidden = false;
      tip.innerHTML = "<b>" + clockTime(t) + "</b> · " + bothUnits(h);
      // The bubble is centre-anchored (translateX(-50%)), so clamping its left
      // coordinate alone still lets half of it hang past the edge — which clips
      // it on the left and pushes horizontal page scroll on the right. Clamp
      // against its measured half-width instead.
      var half = tip.offsetWidth / 2 + 4;
      tip.style.left = Math.min(r.width - half, Math.max(half, x / scale)) + "px";
      tip.style.top = cy + "px";

      // A redraw (the 30s tick, a resize, a station change) empties the SVG and
      // nulls this out, so re-create rather than writing into a detached node.
      if (!chartCursor || !chartCursor.parentNode) {
        chartCursor = el("g", {});
        svg.appendChild(chartCursor);
      }
      var cursor = chartCursor;
      while (cursor.firstChild) cursor.removeChild(cursor.firstChild);
      cursor.appendChild(el("line", {
        x1: x, x2: x, y1: chartGeom.pad.t, y2: chartGeom.pad.t + chartGeom.ih,
        stroke: "var(--ink-muted)", "stroke-width": 1
      }));
      cursor.appendChild(el("circle", {
        cx: x, cy: chartGeom.Y(h), r: 4.5, fill: "var(--series)",
        stroke: "var(--surface)", "stroke-width": 2
      }));
    }

    function hide() {
      tip.hidden = true;
      if (chartCursor && chartCursor.parentNode) chartCursor.parentNode.removeChild(chartCursor);
      chartCursor = null;
    }

    wrap.addEventListener("pointermove", move);
    wrap.addEventListener("pointerdown", move);
    wrap.addEventListener("pointerleave", hide);
    wrap.addEventListener("pointercancel", hide);
  }

  /* ── Day list ──────────────────────────────────────────────── */

  function renderDays(now) {
    var host = $("days");
    host.innerHTML = "";
    var todayKey = localParts(now).key;
    var dayStart = startOfLocalDay(now);
    // Cut at the end of the last local day rather than a wall-clock now+14d, so
    // the final row is a whole day instead of one chopped mid-afternoon.
    var dayEnd = startOfLocalDay(dayStart + (FORECAST_DAYS - 1) * DAY + 12 * HOUR) + DAY;
    var byDay = {}, order = [];

    events.forEach(function (e) {
      if (e.t < dayStart || e.t >= dayEnd) return;
      var k = localParts(e.t).key;
      if (!byDay[k]) { byDay[k] = []; order.push(k); }
      byDay[k].push(e);
    });

    order.forEach(function (k) {
      var list = byDay[k], first = list[0].t;
      var row = document.createElement("div");
      row.className = "day" + (k === todayKey ? " is-today" : "");

      var date = document.createElement("div");
      date.className = "day-date";
      date.innerHTML = "<strong>" + (k === todayKey ? "Today" : fmtWeekday.format(first * 1000)) +
        "</strong>" + fmtDayMon.format(first * 1000);
      row.appendChild(date);

      var evs = document.createElement("div");
      evs.className = "events";
      list.forEach(function (e) {
        var chip = document.createElement("span");
        chip.className = "event" + (e.kind === "high" ? " is-high" : "") +
          (e.t < now ? " is-past" : "");
        chip.innerHTML = '<span class="tag">' + (e.kind === "high" ? "High" : "Low") +
          '</span><span class="t">' + clockTime(e.t) +
          '</span><span class="h">' + e.h.toFixed(1) + "m</span>";
        evs.appendChild(chip);
      });
      row.appendChild(evs);
      host.appendChild(row);
    });
  }

  /* ── Wiring ────────────────────────────────────────────────── */

  function renderAll() {
    var now = Date.now() / 1000;
    if (!eventsCover(now)) recompute();
    renderHero(now);
    renderChart(now);
    renderDays(now);
    $("chart-sub").textContent =
      station.name + ", " + station.place + " · metres above chart datum";
    $("foot-station").textContent =
      "Predictions for " + station.source + " (" + station.lat.toFixed(3) + "°N, " +
      Math.abs(station.lon).toFixed(3) + "°W). Heights are metres above chart datum.";
  }

  function init() {
    var sel = $("station");
    DATA.stations.forEach(function (s, i) {
      var o = document.createElement("option");
      o.value = s.id;
      o.textContent = s.name;
      if (i === 0) o.selected = true;
      sel.appendChild(o);
    });

    var saved = null;
    try { saved = localStorage.getItem("gm-tides-station"); } catch (e) { /* private mode */ }
    if (saved) {
      var match = DATA.stations.filter(function (s) { return s.id === saved; })[0];
      if (match) { station = match; sel.value = saved; }
    }

    sel.addEventListener("change", function () {
      station = DATA.stations.filter(function (s) { return s.id === sel.value; })[0] || DATA.stations[0];
      try { localStorage.setItem("gm-tides-station", station.id); } catch (e) { /* ignore */ }
      recompute();
      renderAll();
    });

    // Reveal before the first render: the chart sizes itself from the
    // container, which measures zero while `main` is still hidden.
    $("fallback").hidden = true;
    $("main").hidden = false;

    bindTooltip();
    recompute();
    renderAll();

    setInterval(renderAll, 30000);
    window.addEventListener("resize", function () { renderChart(Date.now() / 1000); });
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) renderAll();
    });
  }

  var y = new Date().getUTCFullYear();
  if (y < DATA.firstYear || y > DATA.lastYear) {
    $("fallback").textContent =
      "This copy holds tide data for " + DATA.firstYear + "–" + DATA.lastYear +
      ". Rebuild it with tools/build_tide_data.py for later years.";
  } else {
    init();
  }

  /* Only claim the page is available offline once a service worker actually
     controls it — an unregistered or failed worker must not be advertised as
     "saved", because the whole point is trusting it with no signal. */
  function setOfflineHint(saved) {
    var node = $("offline-hint");
    if (!node) return;
    node.textContent = saved
      ? "Saved for offline use. On iPhone, tap Share then “Add to Home Screen” " +
        "to keep it one tap away with no signal."
      : "On iPhone, tap Share then “Add to Home Screen” to keep it one tap away.";
  }

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("sw.js").then(function () {
        return navigator.serviceWorker.ready;
      }).then(function () {
        setOfflineHint(true);
      }).catch(function () {
        setOfflineHint(false);   // offline support is best-effort; say so honestly
      });
    });
  }
})();
