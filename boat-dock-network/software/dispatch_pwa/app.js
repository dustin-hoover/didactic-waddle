/* DockOS Crew — field PWA for boat/truck crews (doc 23).
 * Offline-first: the run sheet is cached; every field action is queued with a client id
 * and replayed to POST /field/actions (idempotent server-side) whenever there's signal.
 * window.BDN_DEMO switches to an embedded snapshot with no network (artifact preview). */
(function () {
  "use strict";
  var DEMO = window.BDN_DEMO || null;

  // ---------- storage (per-device; never the source of truth) ----------
  var store = {
    get: function (k, d) { try { var v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
    set: function (k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }
  };
  function todayLocal() { var d = new Date(); return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0"); }
  var qs = new URLSearchParams(location.search);
  var CREW = DEMO ? DEMO.crew : (qs.get("crew") || store.get("bdn.crew", "CREW-1"));
  var DAY = DEMO ? DEMO.day : (qs.get("day") || todayLocal());
  if (!DEMO) store.set("bdn.crew", CREW);
  var K = { plan: "bdn.plan." + CREW + "." + DAY, outbox: "bdn.outbox", local: "bdn.local." + DAY, load: "bdn.loaded." + CREW + "." + DAY };

  var LABEL = {
    "cpe-wireless-nlos": "Wireless install", "cpe-wireless-ptmp": "Wireless install (line of sight)",
    "drop-aerial-fiber": "Fiber drop (aerial)", "drop-ug-fiber": "Fiber drop (buried)", "repair": "Repair",
    "survey": "Site survey", "t2-docknode": "Dock node build", "t3-relay": "Relay build", "t1-core": "Core node build",
    "t0-headend": "Head-end build", "lake-crossing-mw": "Lake crossing (microwave)", "subaqueous-fiber": "Cove cable lay",
    "fiber-aerial-mile": "Aerial fiber", "fiber-ug-mile": "Buried fiber"
  };
  var CAPTURE = {
    device_mac: { label: "CPE MAC address", mono: true, scan: true, ph: "AA:BB:CC:DD:EE:FF", mode: "text" },
    ont_serial: { label: "ONT serial", mono: true, scan: true, ph: "e.g. ABCD12345678", mode: "text" },
    speed_down_mbps: { label: "Speed test down (Mbps)", mode: "decimal", ph: "940" },
    speed_up_mbps: { label: "Speed test up (Mbps)", mode: "decimal", ph: "930" },
    rssi_dbm: { label: "Signal RSSI (dBm)", mode: "decimal", ph: "-58" },
    rx_power_dbm: { label: "Light level at ONT (dBm)", mode: "decimal", ph: "-18.5" },
    resolution: { label: "What fixed it", area: true, ph: "Swapped backhaul radio from spare kit; NOC confirmed links up" },
    dock_access: { label: "Dock access", options: ["yes", "limited", "no"] },
    gps: { label: "GPS point", mode: "text", ph: "36.35481, -94.05786" },
    asbuilt_ref: { label: "As-built reference", mode: "text", ph: "Photo set / drawing id" }
  };
  var REASONS = ["No dock access", "Member not home", "Weather", "Parts missing", "Unsafe site", "Other"];

  var S = { plan: null, lake: null, outbox: store.get(K.outbox, []), local: store.get(K.local, {}),
            view: "list", tab: "run", current: null, pos: null, syncing: false, online: true, why: null };

  var $ = function (id) { return document.getElementById(id); };
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  var LAKE_TZ = "America/Chicago";          // the lake runs on Central time, whatever the device says
  function hhmm(iso) { var d = new Date(iso); return isNaN(d) ? "—" : d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", timeZone: LAKE_TZ }); }
  function uuid() { return (crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2)); }
  function toast(msg) { var t = $("toast"); t.textContent = msg; t.hidden = false; clearTimeout(toast._t); toast._t = setTimeout(function () { t.hidden = true; }, 4200); }
  function loc(wo) { return S.local[wo] || (S.local[wo] = { checks: {} }); }
  function saveLocal() { store.set(K.local, S.local); }

  // ---------- data adapter ----------
  var API = {
    runsheet: function () {
      if (DEMO) return Promise.resolve(JSON.parse(JSON.stringify(DEMO.runsheet)));
      return fetch("/dispatch/runsheet/" + encodeURIComponent(CREW) + "?day=" + DAY).then(function (r) {
        if (!r.ok) throw new Error(r.status === 404 ? "No run planned for " + CREW + " on " + DAY + "." : "Server error " + r.status);
        return r.json();
      });
    },
    lake: function () {
      if (DEMO) return Promise.resolve(DEMO.lake);
      return fetch("/lake.geojson").then(function (r) { return r.json(); });
    },
    sync: function (actions) {
      if (DEMO) return Promise.resolve({ results: actions.map(demoApply) });
      return fetch("/field/actions", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ actions: actions }) }).then(function (r) { if (!r.ok) throw new Error("sync " + r.status); return r.json(); });
    }
  };
  function demoApply(a) {
    var s = stopById(a.wo_id);
    if (a.kind === "completed") {
      var miss = (s.required_captures || []).filter(function (k) { return !String((s.captures || {})[k] || "").trim(); });
      if (miss.length) return { client_action_id: a.client_action_id, ok: false, error: "missing captures", missing: miss };
      return { client_action_id: a.client_action_id, ok: true, status: "closed",
               activation: s.wo_type === "repair" ? undefined : { first_invoice: { invoice_id: "demo", total: "83.91" } } };
    }
    return { client_action_id: a.client_action_id, ok: true };
  }

  // ---------- load ----------
  function stopById(id) { return (S.plan && S.plan.stops || []).filter(function (s) { return s.wo_id === id; })[0]; }
  function boot() {
    if (DEMO) { $("demo").hidden = false; $("demo").textContent = DEMO.note; }
    API.lake().then(function (g) { S.lake = g; drawMap(); }).catch(function () {});
    API.runsheet().then(function (p) { S.plan = p; store.set(K.plan, p); reapplyOutbox(); render(); })
      .catch(function (e) {
        var cached = store.get(K.plan, null);
        if (cached) { S.plan = cached; reapplyOutbox(); render(); toast("Offline — showing the run sheet saved on this device."); }
        else { $("crew").textContent = e.message || "Couldn't load today's run."; }
      });
    if (!DEMO && "geolocation" in navigator) {
      try { navigator.geolocation.watchPosition(function (p) { S.pos = [p.coords.longitude, p.coords.latitude]; drawMap(); },
        function () {}, { enableHighAccuracy: true, maximumAge: 15000 }); } catch (e) {}
    }
    addEventListener("online", function () { S.online = true; sync(); renderChips(); });
    addEventListener("offline", function () { S.online = false; renderChips(); });
    setInterval(sync, 15000);
    addEventListener("resize", drawMap);
    try { matchMedia("(prefers-color-scheme: dark)").addEventListener("change", drawMap); } catch (e) {}
    $("tabRun").onclick = function () { setTab("run"); };
    $("tabLoad").onclick = function () { setTab("load"); };
  }

  // ---------- actions / outbox ----------
  function optimistic(a) {
    var s = stopById(a.wo_id); if (!s) return;
    var l = loc(a.wo_id);
    if (a.kind === "arrived") l.arrived = a.at;
    if (a.kind === "departed") l.departed = a.at;
    if (a.kind === "started") s.status = "in_progress";
    if (a.kind === "capture") { s.captures = Object.assign({}, s.captures || {}, a.data); }
    if (a.kind === "completed") { s.status = "closed"; l.pendingComplete = true; }
    if (a.kind === "cant_complete") { s.status = "released"; s.blocked_reason = a.data.reason; }
  }
  function reapplyOutbox() { S.outbox.forEach(optimistic); }
  function enqueue(kind, wo, data) {
    var a = { client_action_id: uuid(), wo_id: wo, kind: kind, at: new Date().toISOString(), data: data || {}, crew_id: CREW };
    if (S.pos) { a.lon = S.pos[0]; a.lat = S.pos[1]; }
    S.outbox.push(a); store.set(K.outbox, S.outbox);
    optimistic(a); saveLocal(); render(); sync();
  }
  function sync() {
    if (S.syncing || !S.outbox.length) return;
    if (!DEMO && navigator.onLine === false) { S.online = false; renderChips(); return; }
    S.syncing = true; renderChips();
    var batch = S.outbox.slice(0, 50);
    API.sync(batch).then(function (res) {
      S.online = true;
      (res.results || []).forEach(function (r) {
        S.outbox = S.outbox.filter(function (a) { return a.client_action_id !== r.client_action_id; });
        var a = batch.filter(function (x) { return x.client_action_id === r.client_action_id; })[0];
        if (!a) return;
        if (a.kind === "completed") {
          var s = stopById(a.wo_id), l = loc(a.wo_id); l.pendingComplete = false;
          if (!r.ok) {
            if (s) s.status = "in_progress";
            toast(r.missing ? "Can't close yet — still need: " + r.missing.map(function (k) { return (CAPTURE[k] || {}).label || k; }).join(", ") : (r.error || "Couldn't close the job."));
          } else {
            if (s) s.status = r.status || "closed";
            if (r.activation && r.activation.first_invoice) toast("Job closed. Service is live — first bill issued ($" + r.activation.first_invoice.total + ").");
            else toast("Job closed.");
          }
        }
      });
      store.set(K.outbox, S.outbox); saveLocal();
    }).catch(function () { S.online = false; }).then(function () { S.syncing = false; render(); if (S.outbox.length && S.online) setTimeout(sync, 800); });
  }

  // ---------- rendering ----------
  function render() { renderChips(); if (S.view === "list") renderList(); else renderDetail(); drawMap(); }
  function renderChips() {
    if (!S.plan) return;
    var p = S.plan, v = p.vehicle || {};
    $("crew").textContent = p.crew + " · " + (v.kind === "boat" ? (v.name || "Boat") : (v.name || "Truck"));
    $("day").textContent = new Date(DAY + "T12:00:00").toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });
    var w = p.weather || {}, chips = [];
    if (v.kind === "boat") {
      var go = (w.classes || {})[v.boat_class] !== false;
      chips.push('<span class="chip ' + (go ? "go" : "nogo") + '"><i></i><span>' + (go ? "Boats go" : "No-go for " + esc(v.boat_class)) +
        (w.max_wind_mph != null ? " · wind " + w.max_wind_mph + " mph" : "") + "</span></span>");
      chips.push('<span class="chip"><span>Dock turnaround ' + Math.round(p.boat_tieup_min) + " min</span></span>");
    } else {
      chips.push('<span class="chip"><span>' + esc((v.name || "Truck")) + "</span></span>");
    }
    if (w.source === "unavailable") chips.push('<span class="chip warn"><i></i><span>Check marine forecast</span></span>');
    var q = S.outbox.length;
    chips.push('<span class="chip ' + (q ? "warn" : "go") + '"><i></i><span>' + (S.syncing ? "Syncing…" : q ? q + " queued" + (S.online ? "" : " · offline") : "All synced") + "</span></span>");
    $("chips").innerHTML = chips.join("");
  }
  function statusPill(s) {
    if (s.status === "closed" || s.status === "asbuilt") return '<span class="pill done">Done</span>';
    if (s.status === "in_progress") return '<span class="pill live">On site</span>';
    if (s.status === "released") return '<span class="pill">Sent back</span>';
    return "";
  }
  function legText(t) {
    if (!t) return "";
    var truck = t.mode === "truck";
    return '<div class="leg ' + (truck ? "truck" : "") + '"><span class="m">' + Math.round(t.minutes) + " min</span>" + (truck ? "by road" : "by water") + "</div>";
  }
  function renderList() {
    $("listView").hidden = false; $("detailView").hidden = true; $("actions").hidden = true;
    var p = S.plan; if (!p) return;
    if (!p.stops.length) { $("run").innerHTML = '<li class="home">No stops planned for this crew today.</li>'; }
    else {
      $("run").innerHTML = p.stops.map(function (s) {
        return '<li><button class="stop" data-wo="' + s.wo_id + '" data-status="' + esc(s.status) + '" data-p="' + esc(s.priority) + '">' +
          '<span class="buoy">' + s.seq + "</span>" +
          '<span><span class="eta">' + hhmm(s.eta) + '</span><span class="pill ' + esc(s.priority) + '">' + esc(s.priority) + "</span>" + statusPill(s) +
          '<div class="what">' + esc(LABEL[s.wo_type] || s.wo_type) + (s.member ? " — " + esc(s.member) : "") + "</div>" +
          '<div class="where">' + esc(s.address || s.note || "Node site") + "</div></span>" + legText(s.travel) + "</button></li>";
      }).join("");
      Array.prototype.forEach.call(document.querySelectorAll(".stop"), function (b) { b.onclick = function () { open(+b.dataset.wo); }; });
    }
    var r = p.return;
    $("home").innerHTML = r ? "<span>Back to " + esc(p.vehicle.kind === "boat" ? "the yard dock" : "the yard") + "</span><span>" + Math.round(r.minutes) + " min</span>" : "";
    renderLoad();
  }
  function setTab(t) {
    S.tab = t; $("tabRun").setAttribute("aria-selected", t === "run"); $("tabLoad").setAttribute("aria-selected", t === "load");
    $("runPane").hidden = t !== "run"; $("loadPane").hidden = t !== "load";
  }
  function renderLoad() {
    var p = S.plan; if (!p) return;
    var loaded = store.get(K.load, {});
    function group(title, rows) {
      if (!rows.length) return "";
      return "<h3>" + title + '</h3><div class="load">' + rows.map(function (r) {
        var id = "ld-" + r.for.replace(/\W/g, "") + "-" + r.sku;
        return '<label for="' + esc(id) + '"><input type="checkbox" id="' + esc(id) + '" data-k="' + esc(id) + '"' + (loaded[id] ? " checked" : "") +
          "><span>" + esc(r.item) + '</span><span class="qty">' + (+r.qty) + " " + esc(r.unit) + "</span></label>";
      }).join("") + "</div>";
    }
    var ll = p.load_list || [];
    $("loadPane").innerHTML = group("For today's jobs", ll.filter(function (r) { return r.for === "jobs"; })) +
      group("Spare kit (every run)", ll.filter(function (r) { return r.for !== "jobs"; }));
    Array.prototype.forEach.call($("loadPane").querySelectorAll("input"), function (i) {
      i.onchange = function () { var l = store.get(K.load, {}); l[i.dataset.k] = i.checked; store.set(K.load, l); };
    });
  }
  function open(wo) { S.view = "detail"; S.current = wo; S.why = null; render(); scrollTo(0, 0);
    try { if (navigator.wakeLock) navigator.wakeLock.request("screen").catch(function () {}); } catch (e) {} }
  function back() { S.view = "list"; S.current = null; render(); }

  function renderDetail() {
    var s = stopById(S.current); if (!s) return back();
    var l = loc(s.wo_id), t = s.travel || {}, boat = t.mode === "boat";
    $("listView").hidden = true; $("detailView").hidden = false; $("actions").hidden = false;
    var caps = s.captures || {};
    var fields = (s.required_captures || []).map(function (k) {
      var c = CAPTURE[k] || { label: k }, v = caps[k] == null ? "" : caps[k], id = "cap-" + k;
      var input = c.options ? '<select id="' + id + '" data-k="' + k + '"><option value="">Choose…</option>' +
        c.options.map(function (o) { return "<option" + (o === v ? " selected" : "") + ">" + o + "</option>"; }).join("") + "</select>"
        : c.area ? '<textarea id="' + id + '" data-k="' + k + '" rows="3" placeholder="' + esc(c.ph) + '">' + esc(v) + "</textarea>"
        : '<input id="' + id + '" data-k="' + k + '" inputmode="' + (c.mode || "text") + '"' + (c.mono ? ' class="mono" autocapitalize="characters" spellcheck="false"' : "") +
          ' placeholder="' + esc(c.ph || "") + '" value="' + esc(v) + '">';
      var scan = c.scan && !DEMO && "BarcodeDetector" in window && navigator.mediaDevices ? '<button type="button" class="scan" data-scan="' + k + '">Scan label</button>' : "";
      return '<div class="field"><label for="' + id + '">' + esc(c.label) + ' <span class="req">*</span></label>' + input + scan + "</div>";
    }).join("");
    var checks = (s.checklist || []).map(function (c, i) {
      var id = "ck-" + s.wo_id + "-" + i;
      return '<li><label for="' + id + '"><input type="checkbox" id="' + id + '" data-i="' + i + '"' + (l.checks[i] ? " checked" : "") + "><span>" + esc(c) + "</span></label></li>";
    }).join("");
    $("detailView").innerHTML =
      '<button class="back" id="back">← Today\'s run</button>' +
      '<div class="d-head"><span class="pill ' + esc(s.priority) + '">' + esc(s.priority) + "</span>" + statusPill(s) +
      "<h2>" + s.seq + " · " + esc(LABEL[s.wo_type] || s.wo_type) + "</h2></div>" +
      '<dl class="facts">' +
      (s.member ? "<dt>Member</dt><dd>" + esc(s.member) + (s.plan_name ? " · " + esc(s.plan_name) : "") + "</dd>" : "") +
      (s.phone ? '<dt>Phone</dt><dd><span class="sel">' + esc(s.phone) + "</span></dd>" : "") +
      "<dt>Where</dt><dd>" + esc(s.address || "Node site") + "</dd>" +
      "<dt>ETA</dt><dd>" + hhmm(s.eta) + " · " + (boat ? Math.round(t.water_min) + " min on the water" : Math.round(t.minutes) + " min by road") + "</dd>" +
      (boat && t.dock_to_site_m != null ? "<dt>Dock → site</dt><dd>" + t.dock_to_site_m + " m on foot</dd>" : "") +
      (s.radius_username ? '<dt>Registered</dt><dd class="mono sel">' + esc(s.radius_username) + "</dd>" : "") +
      (s.note ? "<dt>Note</dt><dd>" + esc(s.note) + "</dd>" : "") + "</dl>" +
      (checks ? "<h3>Checklist</h3><ul class=\"check\">" + checks + "</ul>" : "") +
      (fields ? '<h3>Readings to close the job</h3><div class="fields" id="fields">' + fields + "</div>" : "") +
      '<div id="whyBox"></div>';
    $("back").onclick = back;
    Array.prototype.forEach.call($("detailView").querySelectorAll(".check input"), function (i) {
      i.onchange = function () { l.checks[i.dataset.i] = i.checked; saveLocal(); };
    });
    Array.prototype.forEach.call($("detailView").querySelectorAll("[data-k]"), function (i) { i.oninput = renderActions; i.onchange = renderActions; });
    Array.prototype.forEach.call($("detailView").querySelectorAll("[data-scan]"), function (b) { b.onclick = function () { scanInto(b.dataset.scan); }; });
    renderWhy(); renderActions();
  }
  function formValues() {
    var out = {};
    Array.prototype.forEach.call($("detailView").querySelectorAll("[data-k]"), function (i) { if (String(i.value).trim() !== "") out[i.dataset.k] = i.value.trim(); });
    return out;
  }
  function renderActions() {
    var s = stopById(S.current); if (!s) return;
    var l = loc(s.wo_id), boat = (s.travel || {}).mode === "boat", html = "";
    var done = s.status === "closed" || s.status === "asbuilt";
    if (s.status === "released") html = '<button class="btn primary" id="act">Back to the run</button>';
    else if (done) html = l.departed ? '<button class="btn primary" id="act">Next stop</button>'
      : '<button class="btn primary" id="act">' + (boat ? "Leaving the dock" : "Leaving the site") + "</button>";
    else if (s.status === "in_progress") {
      var have = Object.assign({}, s.captures || {}, formValues());
      var ready = (s.required_captures || []).every(function (k) { return String(have[k] || "").trim(); });
      html = '<button class="btn primary complete" id="act"' + (ready ? "" : " disabled") + ">" + (ready ? "Complete job" : "Fill readings to complete") + "</button>";
    }
    else html = '<button class="btn primary" id="act">' + (l.arrived ? "Start work" : boat ? "Tied up at the dock" : "Arrived on site") + "</button>";
    if (!done && s.status !== "released") html += '<button class="btn ghost" id="cant">Can\'t complete</button>';
    // Don't rebuild an unchanged bar: blurring a reading fires `change` as the tech taps
    // Complete, and replacing the button mid-tap would swallow that tap.
    if ($("actionsIn").dataset.sig === html) return;
    $("actionsIn").dataset.sig = html;
    $("actionsIn").innerHTML = html;
    $("act").onclick = primary;
    if ($("cant")) $("cant").onclick = function () { S.why = S.why ? null : ""; renderWhy(); };
  }
  function primary() {
    var s = stopById(S.current), l = loc(s.wo_id);
    if (s.status === "released") return back();
    if (s.status === "closed" || s.status === "asbuilt") {
      if (!l.departed) { enqueue("departed", s.wo_id); }
      return back();
    }
    if (s.status === "in_progress") {
      var v = formValues(), prev = s.captures || {}, changed = {};
      Object.keys(v).forEach(function (k) { if (String(prev[k] || "") !== v[k]) changed[k] = v[k]; });
      if (Object.keys(changed).length) enqueue("capture", s.wo_id, changed);
      return enqueue("completed", s.wo_id);
    }
    if (!l.arrived) return enqueue("arrived", s.wo_id);
    enqueue("started", s.wo_id);
  }
  function renderWhy() {
    var box = $("whyBox"); if (!box) return;
    if (S.why === null) { box.innerHTML = ""; return; }
    box.innerHTML = "<h3>Why can't it be completed?</h3><div class=\"why\">" + REASONS.map(function (r) {
      return '<button type="button" aria-pressed="' + (S.why === r) + '" data-r="' + esc(r) + '">' + esc(r) + "</button>";
    }).join("") + '</div><p class="note">The job goes back to dispatch for re-planning.</p>' +
      (S.why ? '<button class="btn ghost" id="sendBack" style="margin-top:8px">Send back to dispatch</button>' : "");
    Array.prototype.forEach.call(box.querySelectorAll("[data-r]"), function (b) { b.onclick = function () { S.why = b.dataset.r; renderWhy(); }; });
    if ($("sendBack")) $("sendBack").onclick = function () { var s = stopById(S.current); enqueue("cant_complete", s.wo_id, { reason: S.why }); S.why = null; toast("Sent back to dispatch."); back(); };
  }
  function scanInto(k) {           // camera + BarcodeDetector where the device offers it
    var input = $("cap-" + k);
    navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } }).then(function (stream) {
      var v = document.createElement("video"); v.srcObject = stream; v.setAttribute("playsinline", ""); v.play();
      var det = new BarcodeDetector({ formats: ["code_128", "qr_code", "data_matrix", "code_39"] }), tries = 0;
      (function tick() {
        det.detect(v).then(function (codes) {
          if (codes.length) { input.value = codes[0].rawValue; renderActions(); stream.getTracks().forEach(function (t) { t.stop(); }); toast("Scanned " + codes[0].rawValue); }
          else if (++tries < 60) setTimeout(tick, 300); else { stream.getTracks().forEach(function (t) { t.stop(); }); toast("Couldn't read the label — type it in."); }
        }).catch(function () { stream.getTracks().forEach(function (t) { t.stop(); }); });
      })();
    }).catch(function () { toast("Camera unavailable — type the value in."); });
  }

  // ---------- chart ----------
  function css(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
  function drawMap() {
    var cv = $("map"); if (!cv || !S.plan) return;
    var W = cv.clientWidth, H = cv.clientHeight, dpr = Math.max(1, window.devicePixelRatio || 1);
    cv.width = W * dpr; cv.height = H * dpr;
    var g = cv.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0);
    var p = S.plan, pts = [[p.yard.lon, p.yard.lat]];
    p.stops.forEach(function (s) { pts.push([s.lon, s.lat]); (s.travel && s.travel.path || []).forEach(function (q) { pts.push(q); }); });
    if (p.return && p.return.path) p.return.path.forEach(function (q) { pts.push(q); });
    var x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    pts.forEach(function (q) { x0 = Math.min(x0, q[0]); x1 = Math.max(x1, q[0]); y0 = Math.min(y0, q[1]); y1 = Math.max(y1, q[1]); });
    var kx = Math.cos((y0 + y1) / 2 * Math.PI / 180), minSpan = 0.03;
    var cx = (x0 + x1) / 2, cy = (y0 + y1) / 2, sx = Math.max((x1 - x0) * kx, minSpan) * 1.3, sy = Math.max(y1 - y0, minSpan) * 1.3;
    var sc = Math.min(W / sx, H / sy);
    function X(lon) { return W / 2 + (lon - cx) * kx * sc; } function Y(lat) { return H / 2 - (lat - cy) * sc; }
    g.fillStyle = css("--ground"); g.fillRect(0, 0, W, H);
    if (S.lake) {
      var geom = S.lake.features ? S.lake.features[0].geometry : (S.lake.geometry || S.lake);
      var polys = geom.type === "MultiPolygon" ? geom.coordinates : [geom.coordinates];
      g.beginPath();
      polys.forEach(function (poly) { poly.forEach(function (ring) { ring.forEach(function (q, i) { i ? g.lineTo(X(q[0]), Y(q[1])) : g.moveTo(X(q[0]), Y(q[1])); }); g.closePath(); }); });
      g.fillStyle = css("--water"); g.fill("evenodd"); g.strokeStyle = css("--shore"); g.lineWidth = 1; g.stroke();
    }
    var prev = [p.yard.lon, p.yard.lat];
    function legLine(t, from, to) {
      g.lineWidth = 3.5; g.lineCap = "round"; g.lineJoin = "round";
      if (t && t.mode === "boat" && t.path && t.path.length) {
        g.setLineDash([]); g.strokeStyle = css("--boat"); g.beginPath();
        t.path.forEach(function (q, i) { i ? g.lineTo(X(q[0]), Y(q[1])) : g.moveTo(X(q[0]), Y(q[1])); }); g.stroke();
        g.setLineDash([2, 4]); g.lineWidth = 2; g.beginPath(); g.moveTo(X(t.path[t.path.length - 1][0]), Y(t.path[t.path.length - 1][1])); g.lineTo(X(to[0]), Y(to[1])); g.stroke();
      } else {
        g.setLineDash([8, 6]); g.strokeStyle = css("--truck"); g.beginPath(); g.moveTo(X(from[0]), Y(from[1])); g.lineTo(X(to[0]), Y(to[1])); g.stroke();
      }
      g.setLineDash([]);
    }
    p.stops.forEach(function (s) { legLine(s.travel, prev, [s.lon, s.lat]); prev = [s.lon, s.lat]; });
    if (p.return) legLine(p.return.path ? { mode: "boat", path: p.return.path } : { mode: "truck" }, prev, [p.yard.lon, p.yard.lat]);
    var ys = 12; g.fillStyle = css("--ink"); g.fillRect(X(p.yard.lon) - ys / 2, Y(p.yard.lat) - ys / 2, ys, ys);
    g.font = "700 12px " + css("--f-display"); g.textBaseline = "middle";
    g.fillText("YARD", X(p.yard.lon) + 10, Y(p.yard.lat));
    p.stops.forEach(function (s) {
      var x = X(s.lon), y = Y(s.lat), done = s.status === "closed" || s.status === "asbuilt", live = s.status === "in_progress";
      g.beginPath(); g.arc(x, y, 12, 0, Math.PI * 2);
      g.fillStyle = done ? css("--go") : live ? css("--warn") : css("--surface"); g.fill();
      g.lineWidth = 3; g.strokeStyle = s.priority === "P1" ? css("--stop") : done ? css("--go") : css("--boat"); g.stroke();
      g.fillStyle = done || live ? css("--onaccent") : css("--ink"); g.textAlign = "center";
      g.font = "700 14px " + css("--f-display"); g.fillText(String(s.seq), x, y + 1); g.textAlign = "start";
    });
    if (S.pos) { g.beginPath(); g.arc(X(S.pos[0]), Y(S.pos[1]), 6, 0, Math.PI * 2); g.fillStyle = css("--boat"); g.fill(); g.lineWidth = 3; g.strokeStyle = css("--surface"); g.stroke(); }
  }

  boot();
})();
