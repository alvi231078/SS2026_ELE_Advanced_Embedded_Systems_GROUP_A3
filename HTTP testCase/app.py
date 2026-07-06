"""
Raspberry Pi central server for the Smart Parking System.
Run this on the Pi with:  python3 app.py
Then visit http://<pi-ip-address>:5000 from any device on the same
Wi-Fi network to see the live dashboard.

Endpoints:
  POST /spot-update   <- ESP32 #1 calls this whenever a spot's status changes
  POST /gate-update   <- ESP32 #2 calls this whenever a gate opens/closes
  GET  /can-enter     <- ESP32 #2 calls this BEFORE opening the entry gate
  GET  /status        <- one-off status fetch (kept for debugging)
  GET  /stream        <- push-based live updates (dashboard uses this)
  GET  /              <- the dashboard page itself

CHANGES vs the original version (see comments marked "REALTIME FIX"):
  - server timestamps + client-side latency measurement, so you can SEE
    the delay in milliseconds instead of guessing
  - anti-buffering SSE headers
  - fast reconnect (1s instead of the browser default ~3s)
  - debug/reloader turned off (was silently killing SSE connections)
  - full redesign of the dashboard UI
"""
from flask import Flask, request, jsonify, render_template_string, Response
import json
import queue
import threading
import time

app = Flask(__name__)

# In-memory state. Resets to these defaults if the Pi restarts.
spot_status = {1: "unknown", 2: "unknown", 3: "unknown"}
gate_status = {"entry": "closed", "exit": "closed"}

# REALTIME FIX: per-item "last changed" timestamps, so the dashboard can
# show "updated 3s ago" and you can visually confirm nothing is stale.
last_update = {"spots": {}, "gates": {}}

# Every connected browser gets its own queue. Whenever state changes,
# we push the new state into every queue so each browser's /stream
# connection wakes up immediately - no polling delay.
subscribers = []
subscribers_lock = threading.Lock()


def current_state_json():
    return json.dumps({
        "spots": spot_status,
        "gates": gate_status,
        "last_update": last_update,
        # REALTIME FIX: lets the browser compute real end-to-end latency
        # (Date.now() on the browser minus this timestamp), instead of
        # you having to guess whether the delay is server-side or not.
        "server_time": time.time(),
    })


def broadcast_state():
    state = current_state_json()
    with subscribers_lock:
        for q in list(subscribers):
            q.put(state)


@app.route("/spot-update", methods=["POST"])
def spot_update():
    data = request.get_json(force=True)
    spot_id = int(data["spot"])
    status = data["status"]  # expects "free" or "occupied"
    spot_status[spot_id] = status
    last_update["spots"][str(spot_id)] = time.time()
    print(f"[spot-update] spot {spot_id} -> {status}")
    broadcast_state()
    return jsonify({"ok": True})


@app.route("/gate-update", methods=["POST"])
def gate_update():
    data = request.get_json(force=True)
    gate = data["gate"]      # "entry" or "exit"
    status = data["status"]  # "open" or "closed"
    gate_status[gate] = status
    last_update["gates"][gate] = time.time()
    print(f"[gate-update] {gate} -> {status}")
    broadcast_state()
    return jsonify({"ok": True})


@app.route("/can-enter", methods=["GET"])
def can_enter():
    any_free = any(status == "free" for status in spot_status.values())
    return jsonify({"allow": any_free})


@app.route("/status", methods=["GET"])
def status():
    return jsonify({"spots": spot_status, "gates": gate_status})


@app.route("/stream")
def stream():
    def event_stream():
        q = queue.Queue()
        with subscribers_lock:
            subscribers.append(q)
        try:
            # REALTIME FIX: tells the browser to retry after 1s if the
            # connection drops, instead of the ~3s browser default.
            yield "retry: 1000\n\n"
            # send current state immediately on connect
            yield f"data: {current_state_json()}\n\n"
            while True:
                try:
                    state = q.get(timeout=10)
                    yield f"data: {state}\n\n"
                except queue.Empty:
                    yield ": keep-alive\n\n"  # keeps the connection from timing out
        finally:
            with subscribers_lock:
                if q in subscribers:
                    subscribers.remove(q)

    resp = Response(event_stream(), mimetype="text/event-stream")
    # REALTIME FIX: without these headers, some browsers/proxies buffer
    # the stream and you get delayed, "batched" updates instead of
    # instant ones.
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"
    resp.headers["Connection"] = "keep-alive"
    return resp


@app.route("/")
def dashboard():
    return render_template_string(DASHBOARD_HTML)


DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Smart-Park // System View</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{--bg:#0a0e17;--pan:#10192c;--p2:#0d1424;--gl:rgba(97,219,251,.04);--ln:#1e3050;--ink:#e2e8f4;--mt:#5c6d8e;--fr:#33d17a;--oc:#ff5a5f;--uk:#3a4660;--sg:#f5a623;--tr:#1e3050}
*{box-sizing:border-box;margin:0;padding:0}
body{min-height:100vh;background:var(--bg);background-image:linear-gradient(var(--gl) 1px,transparent 1px),linear-gradient(90deg,var(--gl) 1px,transparent 1px);background-size:24px 24px;color:var(--ink);font-family:'JetBrains Mono',monospace;padding:16px}
.w{max-width:1000px;margin:0 auto}

/* ─── TOP BAR ─── */
.top{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;background:var(--pan);border:1px solid var(--ln);border-radius:10px;padding:12px 16px;margin-bottom:14px}
.br{display:flex;align-items:center;gap:12px}
.bm{font-weight:600;font-size:.8rem;color:var(--sg);border:1.5px solid var(--sg);border-radius:5px;padding:2px 8px;letter-spacing:.05em}
.bt{font-family:'Space Grotesk',sans-serif;font-weight:700;font-size:1rem;letter-spacing:.04em;text-transform:uppercase}
.bs{font-size:.65rem;color:var(--mt);margin-top:2px}
.te{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.ts{font-size:.72rem;color:var(--mt)}
.ts b{color:var(--ink);font-weight:500}
.pill{font-size:.68rem;padding:3px 10px;border-radius:20px;display:inline-flex;align-items:center;gap:6px;background:rgba(51,209,122,.12);color:var(--fr)}
.pill::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--fr);animation:pulse 1.5s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.2}}

/* ─── KPI STRIP ─── */
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px}
.kpi{background:var(--pan);border:1px solid var(--ln);border-radius:8px;padding:12px 14px;position:relative;overflow:hidden}
.kpi::before{content:"";position:absolute;top:0;left:0;width:100%;height:3px}
.kpi.kg::before{background:var(--fr)}
.kpi.kr::before{background:var(--oc)}
.kpi.ka::before{background:var(--sg)}
.kpi-label{font-size:.62rem;color:var(--mt);text-transform:uppercase;letter-spacing:.1em}
.kpi-val{font-family:'Space Grotesk',sans-serif;font-weight:700;font-size:1.5rem;margin-top:3px}
.kpi-val.g{color:var(--fr)}.kpi-val.r{color:var(--oc)}.kpi-val.a{color:var(--sg)}
.kpi-sub{font-size:.6rem;color:var(--mt);margin-top:2px}

/* ─── FLOOR PLAN ─── */
.hero{background:var(--pan);border:1px solid var(--ln);border-radius:12px;padding:14px 16px;margin-bottom:14px}
.hl{font-size:.68rem;color:var(--mt);text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px}
svg.fp{width:100%;height:auto;display:block}

/* ─── CONTROLS ─── */
.ctrl{background:var(--pan);border:1px solid var(--ln);border-radius:10px;padding:14px 16px;margin-bottom:14px}
.cr{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}
.b{font-family:'JetBrains Mono',monospace;font-size:.72rem;letter-spacing:.04em;padding:8px 16px;border-radius:6px;border:1px solid var(--ln);background:var(--p2);color:var(--ink);cursor:pointer;transition:all .15s;user-select:none}
.b:hover{background:#182340;border-color:var(--sg)}
.b:active{transform:scale(.97)}
.bf{border-color:var(--fr)!important;color:var(--fr);background:rgba(51,209,122,.08)!important}
.bo{border-color:var(--oc)!important;color:var(--oc);background:rgba(255,90,95,.08)!important}

/* ─── LOG ─── */
.log{background:var(--pan);border:1px solid var(--ln);border-radius:10px;padding:14px 16px}
.log-items{display:flex;flex-direction:column;gap:4px;max-height:120px;overflow-y:auto;margin-top:8px;font-size:.7rem}
.log-items::-webkit-scrollbar{width:4px}
.log-items::-webkit-scrollbar-thumb{background:var(--ln);border-radius:2px}
.log-entry{display:flex;gap:10px;padding:4px 0;border-bottom:1px solid rgba(30,48,80,.4)}
.log-time{color:var(--mt);min-width:70px}
.log-msg span.free{color:var(--fr)}.log-msg span.occupied{color:var(--oc)}
.log-msg span.open{color:var(--fr)}.log-msg span.closed{color:var(--oc)}

.ft{text-align:center;margin-top:14px;font-size:.62rem;color:var(--mt)}
@media(max-width:640px){.kpis{grid-template-columns:1fr 1fr}.top{flex-direction:column;align-items:flex-start}}
@media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
</style>
</head>
<body>
<div class="w">

<!-- TOP BAR -->
<div class="top">
  <div class="br">
    <span class="bm">[P]</span>
    <div>
      <div class="bt">Smart-Park // System View</div>
      <div class="bs">HSHL Advanced Embedded Systems · Team A3 · Summer 2026</div>
    </div>
  </div>
  <div class="te">
    <span class="pill" id="conn">LIVE</span>
    <span class="ts">LAT <b id="lat">–</b></span>
    <span class="ts" id="ck"></span>
  </div>
</div>

<!-- KPI STRIP -->
<div class="kpis">
  <div class="kpi kg"><div class="kpi-label">Available</div><div class="kpi-val g" id="kf">0</div><div class="kpi-sub" id="kfs">of 3 bays</div></div>
  <div class="kpi kr"><div class="kpi-label">Occupied</div><div class="kpi-val r" id="ko">0</div><div class="kpi-sub" id="kos">of 3 bays</div></div>
  <div class="kpi ka"><div class="kpi-label">Entry Gate</div><div class="kpi-val a" id="ke">CLOSED</div><div class="kpi-sub" id="ket">—</div></div>
  <div class="kpi ka"><div class="kpi-label">Exit Gate</div><div class="kpi-val a" id="kx">CLOSED</div><div class="kpi-sub" id="kxt">—</div></div>
</div>

<!-- FLOOR PLAN -->
<div class="hero">
  <div class="hl">Live floor plan · entry → bays → exit</div>
  <svg class="fp" viewBox="0 0 940 300" xmlns="http://www.w3.org/2000/svg">

    <!-- driving lane -->
    <rect x="80" y="198" width="780" height="34" rx="4" fill="#1e3050" fill-opacity=".12"/>
    <line x1="80" y1="215" x2="860" y2="215" stroke="#e2e8f4" stroke-opacity=".1" stroke-width="1.5" stroke-dasharray="10 10"/>
    <text x="440" y="211" font-family="JetBrains Mono" font-size="8" fill="#5c6d8e" text-anchor="middle" letter-spacing=".12em">MQTT · SENSOR BUS</text>

    <!-- bay connectors -->
    <line x1="255" y1="198" x2="255" y2="162" stroke="#1e3050" stroke-dasharray="3 5"/>
    <line x1="470" y1="198" x2="470" y2="162" stroke="#1e3050" stroke-dasharray="3 5"/>
    <line x1="685" y1="198" x2="685" y2="162" stroke="#1e3050" stroke-dasharray="3 5"/>

    <!-- BAY 01 -->
    <rect x="185" y="32" width="140" height="130" rx="6" fill="#0d1424" stroke="#1e3050" stroke-width="1.5"/>
    <line x1="185" y1="32" x2="185" y2="162" stroke="#e2e8f4" stroke-opacity=".08" stroke-dasharray="5 5"/>
    <line x1="325" y1="32" x2="325" y2="162" stroke="#e2e8f4" stroke-opacity=".08" stroke-dasharray="5 5"/>
    <text x="196" y="50" font-family="JetBrains Mono" font-size="10" fill="#5c6d8e" letter-spacing=".06em">BAY·01</text>
    <circle id="l1" cx="255" cy="65" r="7" fill="#3a4660"/>
    <g id="c1" opacity="0" style="transition:opacity .5s">
      <rect x="231" y="76" width="48" height="60" rx="13" fill="none" stroke="#e2e8f4" stroke-width="1.8"/>
      <rect x="238" y="85" width="34" height="12" rx="3" fill="#0d1424" stroke="#e2e8f4" stroke-width="1.2"/>
      <rect x="238" y="107" width="34" height="10" rx="3" fill="#0d1424" stroke="#e2e8f4" stroke-width="1.2"/>
    </g>
    <text id="s1" x="196" y="148" font-family="JetBrains Mono" font-size="11" fill="#e2e8f4" font-weight="600">UNKNOWN</text>
    <text id="t1" x="196" y="159" font-family="JetBrains Mono" font-size="8.5" fill="#5c6d8e">—</text>

    <!-- BAY 02 -->
    <rect x="400" y="32" width="140" height="130" rx="6" fill="#0d1424" stroke="#1e3050" stroke-width="1.5"/>
    <line x1="400" y1="32" x2="400" y2="162" stroke="#e2e8f4" stroke-opacity=".08" stroke-dasharray="5 5"/>
    <line x1="540" y1="32" x2="540" y2="162" stroke="#e2e8f4" stroke-opacity=".08" stroke-dasharray="5 5"/>
    <text x="411" y="50" font-family="JetBrains Mono" font-size="10" fill="#5c6d8e" letter-spacing=".06em">BAY·02</text>
    <circle id="l2" cx="470" cy="65" r="7" fill="#3a4660"/>
    <g id="c2" opacity="0" style="transition:opacity .5s">
      <rect x="446" y="76" width="48" height="60" rx="13" fill="none" stroke="#e2e8f4" stroke-width="1.8"/>
      <rect x="453" y="85" width="34" height="12" rx="3" fill="#0d1424" stroke="#e2e8f4" stroke-width="1.2"/>
      <rect x="453" y="107" width="34" height="10" rx="3" fill="#0d1424" stroke="#e2e8f4" stroke-width="1.2"/>
    </g>
    <text id="s2" x="411" y="148" font-family="JetBrains Mono" font-size="11" fill="#e2e8f4" font-weight="600">UNKNOWN</text>
    <text id="t2" x="411" y="159" font-family="JetBrains Mono" font-size="8.5" fill="#5c6d8e">—</text>

    <!-- BAY 03 -->
    <rect x="615" y="32" width="140" height="130" rx="6" fill="#0d1424" stroke="#1e3050" stroke-width="1.5"/>
    <line x1="615" y1="32" x2="615" y2="162" stroke="#e2e8f4" stroke-opacity=".08" stroke-dasharray="5 5"/>
    <line x1="755" y1="32" x2="755" y2="162" stroke="#e2e8f4" stroke-opacity=".08" stroke-dasharray="5 5"/>
    <text x="626" y="50" font-family="JetBrains Mono" font-size="10" fill="#5c6d8e" letter-spacing=".06em">BAY·03</text>
    <circle id="l3" cx="685" cy="65" r="7" fill="#3a4660"/>
    <g id="c3" opacity="0" style="transition:opacity .5s">
      <rect x="661" y="76" width="48" height="60" rx="13" fill="none" stroke="#e2e8f4" stroke-width="1.8"/>
      <rect x="668" y="85" width="34" height="12" rx="3" fill="#0d1424" stroke="#e2e8f4" stroke-width="1.2"/>
      <rect x="668" y="107" width="34" height="10" rx="3" fill="#0d1424" stroke="#e2e8f4" stroke-width="1.2"/>
    </g>
    <text id="s3" x="626" y="148" font-family="JetBrains Mono" font-size="11" fill="#e2e8f4" font-weight="600">UNKNOWN</text>
    <text id="t3" x="626" y="159" font-family="JetBrains Mono" font-size="8.5" fill="#5c6d8e">—</text>

    <!-- ENTRY GATE -->
    <circle cx="48" cy="215" r="7" fill="#0d1424" stroke="#e2e8f4" stroke-width="1.5"/>
    <line id="ae" x1="48" y1="215" x2="112" y2="215" stroke="#f5a623" stroke-width="5" stroke-linecap="round" style="transform-origin:48px 215px;transition:transform .5s cubic-bezier(.4,0,.2,1)"/>
    <text x="18" y="200" font-family="JetBrains Mono" font-size="10" fill="#5c6d8e" letter-spacing=".06em">ENTRY</text>
    <text id="ge" x="18" y="252" font-family="JetBrains Mono" font-size="10" fill="#e2e8f4">CLOSED</text>

    <!-- EXIT GATE -->
    <circle cx="892" cy="215" r="7" fill="#0d1424" stroke="#e2e8f4" stroke-width="1.5"/>
    <line id="ax" x1="892" y1="215" x2="828" y2="215" stroke="#f5a623" stroke-width="5" stroke-linecap="round" style="transform-origin:892px 215px;transition:transform .5s cubic-bezier(.4,0,.2,1)"/>
    <text x="862" y="200" font-family="JetBrains Mono" font-size="10" fill="#5c6d8e" letter-spacing=".06em">EXIT</text>
    <text id="gx" x="862" y="252" font-family="JetBrains Mono" font-size="10" fill="#e2e8f4">CLOSED</text>

    <!-- Pi hub -->
    <line x1="470" y1="232" x2="470" y2="262" stroke="#1e3050" stroke-dasharray="3 5"/>
    <rect x="450" y="262" width="40" height="24" rx="5" fill="#0d1424" stroke="#f5a623" stroke-width="1.5"/>
    <text x="470" y="278" font-family="JetBrains Mono" font-size="8" fill="#f5a623" text-anchor="middle">RPI</text>
  </svg>
</div>

<!-- CONTROLS -->
<div class="ctrl">
  <div class="hl">Simulate sensor readings · click to toggle</div>
  <div class="cr">
    <button class="b" onclick="tS(1)" id="x1">Bay 01</button>
    <button class="b" onclick="tS(2)" id="x2">Bay 02</button>
    <button class="b" onclick="tS(3)" id="x3">Bay 03</button>
    <button class="b" onclick="tG('entry')" id="xe">Entry Gate</button>
    <button class="b" onclick="tG('exit')" id="xx">Exit Gate</button>
    <button class="b" onclick="rnd()">⚡ Randomize</button>
  </div>
</div>

<!-- EVENT LOG -->
<div class="log">
  <div class="hl">Event log</div>
  <div class="log-items" id="logbox"></div>
</div>

<div class="ft">SMART-PARK · ESP32 × 2 + Raspberry Pi · SSE real-time push · HSHL 2026</div>
</div>

<script>
var S = {
  s: {1:"unknown", 2:"unknown", 3:"unknown"},
  g: {entry:"closed", exit:"closed"},
  t: {1:0, 2:0, 3:0, entry:0, exit:0}
};
var logEntries = [];

function ta(t) {
  if (!t) return "\u2014";
  var d = (Date.now() - t) / 1e3;
  return d < 1 ? "now" : d < 60 ? Math.floor(d) + "s ago" : Math.floor(d/60) + "m ago";
}

function addLog(msg) {
  var now = new Date().toLocaleTimeString();
  logEntries.unshift({time: now, msg: msg});
  if (logEntries.length > 20) logEntries.pop();
  var box = document.getElementById("logbox");
  box.innerHTML = "";
  for (var i = 0; i < logEntries.length; i++) {
    box.innerHTML += '<div class="log-entry"><span class="log-time">' + logEntries[i].time + '</span><span class="log-msg">' + logEntries[i].msg + '</span></div>';
  }
}

function render() {
  var f = 0, o = 0;
  for (var i = 1; i <= 3; i++) {
    var s = S.s[i];
    var led = document.getElementById("l" + i);
    led.setAttribute("fill", s === "free" ? "#33d17a" : s === "occupied" ? "#ff5a5f" : "#3a4660");
    led.setAttribute("filter", s === "free" ? "drop-shadow(0 0 8px rgba(51,209,122,.7))" : s === "occupied" ? "drop-shadow(0 0 8px rgba(255,90,95,.7))" : "none");
    document.getElementById("c" + i).setAttribute("opacity", s === "occupied" ? "0.85" : "0");
    document.getElementById("s" + i).textContent = s.toUpperCase();
    document.getElementById("t" + i).textContent = ta(S.t[i]);
    var btn = document.getElementById("x" + i);
    btn.className = "b" + (s === "free" ? " bf" : s === "occupied" ? " bo" : "");
    if (s === "free") f++;
    if (s === "occupied") o++;
  }
  document.getElementById("kf").textContent = f;
  document.getElementById("ko").textContent = o;
  document.getElementById("kfs").textContent = f + " of 3 bays";
  document.getElementById("kos").textContent = o + " of 3 bays";

  var gs = ["entry", "exit"];
  for (var j = 0; j < 2; j++) {
    var g = gs[j], st = S.g[g], k = g === "entry" ? "e" : "x";
    document.getElementById("a" + k).style.transform = st === "open"
      ? (g === "entry" ? "rotate(-75deg)" : "rotate(75deg)")
      : "rotate(0)";
    document.getElementById("g" + k).textContent = st.toUpperCase();
    document.getElementById("k" + k).textContent = st.toUpperCase();
    document.getElementById("k" + k + "t").textContent = ta(S.t[g]);
    document.getElementById("x" + k).className = "b" + (st === "open" ? " bf" : " bo");
  }
}

function tS(i) {
  S.s[i] = S.s[i] === "occupied" ? "free" : "occupied";
  S.t[i] = Date.now();
  addLog('Bay ' + i + ' \u2192 <span class="' + S.s[i] + '">' + S.s[i].toUpperCase() + '</span>');
  render();
}

function tG(g) {
  S.g[g] = S.g[g] === "open" ? "closed" : "open";
  S.t[g] = Date.now();
  addLog(g.charAt(0).toUpperCase() + g.slice(1) + ' gate \u2192 <span class="' + S.g[g] + '">' + S.g[g].toUpperCase() + '</span>');
  render();
}

function rnd() {
  for (var i = 1; i <= 3; i++) {
    S.s[i] = Math.random() > .5 ? "occupied" : "free";
    S.t[i] = Date.now();
  }
  S.g.entry = Math.random() > .5 ? "open" : "closed";
  S.g.exit = Math.random() > .5 ? "open" : "closed";
  S.t.entry = S.t.exit = Date.now();
  addLog('\u26a1 Randomized all sensors');
  render();
}

setInterval(function() {
  document.getElementById("ck").textContent = new Date().toLocaleTimeString();
  for (var i = 1; i <= 3; i++) document.getElementById("t" + i).textContent = ta(S.t[i]);
  document.getElementById("ket").textContent = ta(S.t.entry);
  document.getElementById("kxt").textContent = ta(S.t.exit);
}, 1000);

document.getElementById("ck").textContent = new Date().toLocaleTimeString();
render();

// ─── SSE: when running on the Pi, this overrides the simulation ───
if (location.port === "5000" || location.pathname !== "/") {
  // do nothing, file opened locally
} 
try {
  var evtSource = new EventSource("/stream");
  evtSource.onopen = function() {
    document.getElementById("conn").textContent = "LIVE";
    document.getElementById("conn").style.background = "rgba(51,209,122,.12)";
    document.getElementById("conn").style.color = "#33d17a";
  };
  evtSource.onerror = function() {
    document.getElementById("conn").textContent = "RECONNECTING";
    document.getElementById("conn").style.background = "rgba(255,90,95,.12)";
    document.getElementById("conn").style.color = "#ff5a5f";
  };
  evtSource.onmessage = function(event) {
    var data = JSON.parse(event.data);
    document.getElementById("conn").textContent = "LIVE";
    document.getElementById("conn").style.background = "rgba(51,209,122,.12)";
    document.getElementById("conn").style.color = "#33d17a";
    var latMs = Math.max(0, Math.round((Date.now()/1000 - data.server_time) * 1000));
    document.getElementById("lat").textContent = latMs + "ms";
    for (var id in data.spots) {
      S.s[id] = data.spots[id];
      if (data.last_update && data.last_update.spots && data.last_update.spots[id])
        S.t[id] = data.last_update.spots[id] * 1000;
    }
    for (var g in data.gates) {
      S.g[g] = data.gates[g];
      if (data.last_update && data.last_update.gates && data.last_update.gates[g])
        S.t[g] = data.last_update.gates[g] * 1000;
    }
    render();
  };
} catch(e) {}

</script>
</body>
</html>
"""

if __name__ == "__main__":
    # REALTIME FIX: debug=True was running the Werkzeug auto-reloader,
    # which restarts the whole process (and kills every open SSE
    # connection) whenever it detects a file change. threaded=True is
    # kept so multiple browsers can hold open /stream connections at
    # the same time without blocking each other.
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False, threaded=True)
