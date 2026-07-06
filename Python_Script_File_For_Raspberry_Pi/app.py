"""
Raspberry Pi central server for the Smart Parking System (MQTT version).

This server exposes the same web dashboard as the HTTP-based version and
keeps the user interface exactly the same.  However, instead of relying on
HTTP POST/GET requests from the ESP32 devices, it uses the MQTT publish/
subscribe protocol to receive sensor updates and gate state changes and to
answer entry‑gate access requests.  The MQTT broker is expected to run on
the same Pi (localhost) by default.  If you change the broker address,
update the MQTT_BROKER constant below.

When an ESP32 parking node publishes a topic like ``parking/spot/1/status``
with payload ``"free"`` or ``"occupied"``, this server updates its in‑memory
state and broadcasts the new state to all connected web clients via Server
Sent Events (SSE).  Similarly, when a gate controller publishes
``parking/gate/entry/status`` or ``parking/gate/exit/status`` with payload
``"open"`` or ``"closed"``, the dashboard updates accordingly.

For the entry gate, the ESP32 publishes a ``parking/gate/entry/request``
message whenever it detects a vehicle waiting to enter.  Upon receiving
that request, this server checks whether any parking bays are free and
publishes a corresponding ``parking/gate/entry/allow`` message with
payload ``"true"`` or ``"false"``.  The gate controller uses this
information to decide whether to open the gate.

The dashboard continues to be served over HTTP and uses SSE to receive
realtime updates.  The existing HTTP endpoints for `/spot-update`,
`/gate-update` and `/can-enter` are retained for compatibility and
debugging but are no longer used by the ESP32 devices when using MQTT.

MQTT details
------------
Broker:  `MQTT_BROKER` (default ``"localhost"``)
Port:    1883
Topics:
    parking/spot/<id>/status       (payload "free" or "occupied")
    parking/gate/<entry|exit>/status (payload "open" or "closed")
    parking/gate/entry/request     (payload ignored)
    parking/gate/entry/allow       (payload "true" or "false")

"""

import json
import queue
import threading
import time
import typing

from flask import Flask, Response, jsonify, render_template_string, request

# Import the Paho MQTT client. This library lets the Flask server subscribe
# to MQTT topics from the ESP32 nodes and publish entry-gate allow/deny replies.
import paho.mqtt.client as mqtt  # type: ignore

app = Flask(__name__)

###############################################################################
# Application state
###############################################################################

# In-memory state.  Resets to these defaults if the Pi restarts.
spot_status = {1: "unknown", 2: "unknown", 3: "unknown"}
gate_status = {"entry": "closed", "exit": "closed"}

# per-item "last changed" timestamps, so the dashboard can
# show "updated 3s ago" and you can visually confirm nothing is stale.
last_update = {"spots": {}, "gates": {}}

# Every connected browser gets its own queue.  Whenever state changes,
# we push the new state into every queue so each browser's /stream
# connection wakes up immediately - no polling delay.
subscribers: list[queue.Queue[str]] = []
subscribers_lock = threading.Lock()

# Event history shown in the dashboard log.
event_log: list[dict[str, object]] = []
EVENT_LOG_LIMIT = 40


def add_event(message: str) -> None:
    """Add one entry to the dashboard event log."""
    event_log.insert(0, {"time": time.time(), "msg": message})
    del event_log[EVENT_LOG_LIMIT:]


# MQTT broker configuration
#
# By default the MQTT broker is assumed to run on the same host as this
# Flask server ("localhost").  However, if you are running the web
# server on a different machine than the broker (e.g. the broker is
# running on a Raspberry Pi at 192.168.178.35), you must update
# MQTT_BROKER accordingly.  The ESP32 devices in this project are
# configured to publish to the broker at 192.168.178.35 by default,
# so using that address here will allow the web server to receive
# sensor updates and gate commands via MQTT from the broker.
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_KEEPALIVE = 60

# Topics used by this application.  Wildcards (+) are handled in the
# on_message callback.
TOPIC_SPOT_STATUS = "parking/spot/+/status"
TOPIC_GATE_STATUS = "parking/gate/+/status"
TOPIC_ENTRY_REQUEST = "parking/gate/entry/request"
TOPIC_ENTRY_ALLOW = "parking/gate/entry/allow"


def current_state_json() -> str:
    """Return the current in-memory state as a JSON string."""
    return json.dumps(
        {
            "spots": spot_status,
            "gates": gate_status,
            "last_update": last_update,
            "events": event_log,
            # The server timestamp lets the browser compute real end-to-end latency.
            "server_time": time.time(),
        }
    )


def broadcast_state() -> None:
    """Send the current state to all connected SSE clients."""
    state = current_state_json()
    with subscribers_lock:
        for q in list(subscribers):
            q.put(state)


###############################################################################
# Flask HTTP endpoints (unchanged)
###############################################################################

@app.route("/spot-update", methods=["POST"])
def spot_update():
    """Legacy HTTP endpoint for updating a parking spot status.

    This endpoint is kept for compatibility and debugging; the ESP32 devices
    should use MQTT in the new architecture.  It updates the in-memory state
    and broadcasts the change via SSE.
    """
    data = request.get_json(force=True)
    spot_id = int(data["spot"])
    status = data["status"]  # expects "free" or "occupied"
    spot_status[spot_id] = status
    last_update["spots"][str(spot_id)] = time.time()
    print(f"[spot-update] spot {spot_id} -> {status}")
    add_event(f"Bay {spot_id} -> <span class='{status}'>{status.upper()}</span>")
    broadcast_state()
    return jsonify({"ok": True})


@app.route("/gate-update", methods=["POST"])
def gate_update():
    """Legacy HTTP endpoint for reporting gate state (open/closed)."""
    data = request.get_json(force=True)
    gate = data["gate"]  # "entry" or "exit"
    status = data["status"]  # "open" or "closed"
    gate_status[gate] = status
    last_update["gates"][gate] = time.time()
    print(f"[gate-update] {gate} -> {status}")
    add_event(f"{gate.capitalize()} gate -> <span class='{status}'>{status.upper()}</span>")
    broadcast_state()
    return jsonify({"ok": True})


@app.route("/can-enter", methods=["GET"])
def can_enter():
    """Legacy HTTP endpoint to check if a car may enter.

    Returns {"allow": true} if any parking bay is free, otherwise {"allow": false}.
    """
    any_free = any(status == "free" for status in spot_status.values())
    return jsonify({"allow": any_free})


@app.route("/status", methods=["GET"])
def status():
    """Return current spot and gate state."""
    return jsonify({"spots": spot_status, "gates": gate_status})


@app.route("/stream")
def stream():
    """SSE endpoint used by the dashboard to receive realtime updates."""

    def event_stream() -> typing.Iterator[str]:
        q: queue.Queue[str] = queue.Queue()
        with subscribers_lock:
            subscribers.append(q)
        try:
            # Send retry directive on initial connection so the browser retries
            # quickly if disconnected (1s instead of ~3s default).
            yield "retry: 1000\n\n"
            # send current state immediately on connect
            yield f"data: {current_state_json()}\n\n"
            while True:
                try:
                    state = q.get(timeout=10)
                    yield f"data: {state}\n\n"
                except queue.Empty:
                    # Send a comment as a keep‑alive so proxies don't time out.
                    yield ": keep-alive\n\n"
        finally:
            with subscribers_lock:
                if q in subscribers:
                    subscribers.remove(q)


    resp = Response(event_stream(), mimetype="text/event-stream")
    # Without these headers, some browsers/proxies buffer the stream and you get
    # delayed, "batched" updates instead of instant ones.
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"
    resp.headers["Connection"] = "keep-alive"
    return resp


@app.route("/")
def dashboard():
    """Render the dashboard HTML."""
    return render_template_string(DASHBOARD_HTML)


###############################################################################
# MQTT setup and callbacks
###############################################################################

def on_connect(client: mqtt.Client, userdata: object, flags: dict, rc: int) -> None:
    """Callback when the MQTT client connects to the broker.

    Subscribes to the relevant topics so incoming messages are delivered to
    on_message().
    """
    if rc == 0:
        print("[mqtt] Connected to broker")
        # Subscribe to spot status updates, gate status updates and entry requests.
        client.subscribe(TOPIC_SPOT_STATUS)
        client.subscribe(TOPIC_GATE_STATUS)
        client.subscribe(TOPIC_ENTRY_REQUEST)
    else:
        print(f"[mqtt] Connection failed with code {rc}")


def on_message(client: mqtt.Client, userdata: object, msg: mqtt.MQTTMessage) -> None:
    """Callback when an MQTT message is received."""
    topic = msg.topic
    payload = msg.payload.decode("utf-8") if isinstance(msg.payload, (bytes, bytearray)) else str(msg.payload)
    # Split the topic into parts for parsing.  Example topics:
    #   parking/spot/1/status
    #   parking/gate/entry/status
    #   parking/gate/entry/request
    parts = topic.split("/")
    # Handle spot status updates
    if len(parts) == 4 and parts[0] == "parking" and parts[1] == "spot" and parts[3] == "status":
        try:
            spot_id = int(parts[2])
        except ValueError:
            print(f"[mqtt] Ignoring invalid spot id in topic '{topic}'")
            return
        status_value = payload.strip().lower()
        if status_value not in ("free", "occupied"):
            print(f"[mqtt] Ignoring invalid spot status '{payload}' for spot {spot_id}")
            return
        spot_status[spot_id] = status_value
        last_update["spots"][str(spot_id)] = time.time()
        print(f"[mqtt] spot {spot_id} -> {status_value}")
        add_event(f"Bay {spot_id} -> <span class='{status_value}'>{status_value.upper()}</span>")
        broadcast_state()
        return
    # Handle gate status updates
    if len(parts) == 4 and parts[0] == "parking" and parts[1] == "gate" and parts[3] == "status":
        gate_name = parts[2]
        status_value = payload.strip().lower()
        if gate_name not in gate_status or status_value not in ("open", "closed"):
            print(f"[mqtt] Ignoring invalid gate status '{payload}' for gate {gate_name}")
            return
        gate_status[gate_name] = status_value
        last_update["gates"][gate_name] = time.time()
        print(f"[mqtt] gate {gate_name} -> {status_value}")
        add_event(f"{gate_name.capitalize()} gate -> <span class='{status_value}'>{status_value.upper()}</span>")
        broadcast_state()
        return
    # Handle entry gate permission requests
    if topic == TOPIC_ENTRY_REQUEST:
        # Whenever the entry gate requests permission to open, check if there is
        # any free bay.  Publish "true" if there is at least one free spot,
        # otherwise publish "false".  This follows the same logic as the
        # previous /can-enter HTTP endpoint.
        allow = any(status == "free" for status in spot_status.values())
        result = "true" if allow else "false"
        print(f"[mqtt] entry request -> allow={result}")
        add_event(f"Entry request -> <span class='{('free' if allow else 'occupied')}'>{'ALLOWED' if allow else 'DENIED'}</span>")
        client.publish(TOPIC_ENTRY_ALLOW, result, qos=0, retain=False)
        broadcast_state()
        return
    # Ignore any other topics.
    print(f"[mqtt] Unhandled topic '{topic}'")


def start_mqtt_client() -> None:
    """Start the MQTT client in a dedicated thread."""
    
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)  # paho-mqtt 2.x
    except AttributeError:
        client = mqtt.Client()  # paho-mqtt 1.x

    client.on_connect = on_connect
    client.on_message = on_message
    # Connect to broker
    client.connect(MQTT_BROKER, MQTT_PORT, MQTT_KEEPALIVE)
    # Loop forever.  This call blocks, so run it in a daemon thread.
    client.loop_forever()


###############################################################################
# HTML for the dashboard
###############################################################################
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
body.light{--bg:#f6f8fb;--pan:#ffffff;--p2:#f1f5f9;--gl:rgba(15,23,42,.05);--ln:#d6deeb;--ink:#0f172a;--mt:#64748b;--fr:#15803d;--oc:#dc2626;--uk:#94a3b8;--sg:#b45309;--tr:#d6deeb}
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
.theme-btn{border-color:var(--sg);color:var(--sg)}
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
    <button class="b theme-btn" onclick="toggleTheme()" id="themeBtn">LIGHT</button>
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

<div class="ft">SMART-PARK · MQTT + ESP32 × 2 + Raspberry Pi · SSE real-time push · HSHL 2026</div>
</div>

<script>
var S = {
  s: {1:"unknown", 2:"unknown", 3:"unknown"},
  g: {entry:"closed", exit:"closed"},
  t: {1:0, 2:0, 3:0, entry:0, exit:0}
};
var logEntries = [];

function applyTheme(mode) {
  if (mode === "light") {
    document.body.classList.add("light");
    document.getElementById("themeBtn").textContent = "DARK";
  } else {
    document.body.classList.remove("light");
    document.getElementById("themeBtn").textContent = "LIGHT";
  }
}

function toggleTheme() {
  var next = document.body.classList.contains("light") ? "dark" : "light";
  localStorage.setItem("smartpark-theme", next);
  applyTheme(next);
}

applyTheme(localStorage.getItem("smartpark-theme") || "dark");

function renderServerEvents(events) {
  if (!events || !events.length) return;
  logEntries = [];
  for (var i = 0; i < events.length; i++) {
    var ev = events[i];
    var tt = ev.time ? new Date(ev.time * 1000).toLocaleTimeString() : new Date().toLocaleTimeString();
    logEntries.push({time: tt, msg: ev.msg});
  }
  var box = document.getElementById("logbox");
  box.innerHTML = "";
  for (var j = 0; j < logEntries.length; j++) {
    box.innerHTML += '<div class="log-entry"><span class="log-time">' + logEntries[j].time + '</span><span class="log-msg">' + logEntries[j].msg + '</span></div>';
  }
}

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
    renderServerEvents(data.events);
    render();
  };
} catch(e) {}

</script>
</body>
</html>
"""


###############################################################################
# Entry point
###############################################################################

if __name__ == "__main__":
    # Start MQTT client in a background thread
    mqtt_thread = threading.Thread(target=start_mqtt_client, daemon=True)
    mqtt_thread.start()
    # Start Flask web server.  We turn off the debug reloader and use threaded=True
    # so multiple browsers can hold open /stream connections simultaneously.
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False, threaded=True)