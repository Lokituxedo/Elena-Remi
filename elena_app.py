#!/usr/bin/env python3
"""Elena. App propia: chat, voz, correo. Un core local en la 1060.

Modelo: qwen2.5:3b-instruct-q4_K_M vía Ollama.
Memoria: nomic-embed-text, vectores en elena.db, no en D1.
No usa el worker viejo ni Resend. El correo entra por POST /correo y sale texto.
"""

import math
import json
import os
import sqlite3
import subprocess
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

DIR = Path(__file__).resolve().parent
DB = Path(os.environ.get("ELENA_DB", DIR / "elena.db"))
AUDIO = Path(os.environ.get("ELENA_AUDIO", DIR / "audio"))
PERFIL = DIR / "perfil.txt"
VOZ = os.environ.get("ELENA_VOZ", "es-AR-ElenaNeural")
PORT = int(os.environ.get("ELENA_PORT", "8099"))
BIND = os.environ.get("ELENA_BIND", "0.0.0.0")
OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
MODELO = os.environ.get("ELENA_MODELO", "qwen2.5:3b-instruct-q4_K_M")
EMBED = os.environ.get("ELENA_EMBED", "nomic-embed-text")
SILENCIO = int(os.environ.get("ELENA_SILENCIO_SEG", "90"))
TOKEN = os.environ.get("ELENA_TOKEN", "")
CTX = int(os.environ.get("ELENA_CTX", "2048"))

_lock = threading.Lock()

HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Elena</title>
<style>
:root{--bg:#100c0a;--fg:#f6efe8;--mut:#a8988c;--acc:#e8632c;--card:#1c1512}
*{box-sizing:border-box}
html,body{margin:0;height:100%;background:var(--bg);color:var(--fg);font:17px/1.45 "Iowan Old Style",Palatino,serif}
main{max-width:560px;margin:0 auto;height:100%;display:flex;flex-direction:column}
header{display:flex;justify-content:space-between;align-items:baseline;padding:16px 18px 8px}
header b{font-weight:600;letter-spacing:.08em;font-size:13px}
header span{color:var(--mut);font-size:12px}
#hilo{flex:1;overflow:auto;padding:8px 16px 12px;display:flex;flex-direction:column;gap:10px}
.b{max-width:88%;padding:10px 12px;border-radius:14px;white-space:pre-wrap}
.ro{align-self:flex-end;background:var(--acc);color:#fff;border-bottom-right-radius:4px}
.elena{align-self:flex-start;background:var(--card);border-bottom-left-radius:4px}
.sistema{align-self:center;color:var(--mut);font-size:13px;font-family:system-ui,sans-serif}
.meta{display:block;margin-top:6px;font:11px system-ui;color:var(--mut)}
.play{margin-top:8px;background:transparent;color:var(--acc);border:1px solid var(--acc);border-radius:999px;padding:4px 10px;font:12px system-ui}
form{display:flex;gap:8px;padding:12px 12px calc(12px + env(safe-area-inset-bottom))}
input{flex:1;background:#1a1411;color:var(--fg);border:1px solid #3a2c26;border-radius:12px;padding:12px;font:16px system-ui}
button.send{background:var(--acc);color:#fff;border:0;border-radius:12px;padding:0 16px;font:15px system-ui}
</style>
</head>
<body>
<main>
<header><b>ELENA</b><span id="st">en linea</span></header>
<div id="hilo"></div>
<form id="f">
<input id="t" placeholder="Escribile" autocomplete="off" enterkeyhint="send">
<button class="send" type="submit">Enviar</button>
</form>
</main>
<script>
var last = 0;
function pinta(rows){
  var h = document.getElementById("hilo");
  rows.forEach(function(r){
    var d = document.createElement("div");
    d.className = "b " + r.rol;
    d.textContent = r.texto;
    var m = document.createElement("span");
    m.className = "meta";
    m.textContent = r.origen + " · " + r.ts;
    d.appendChild(m);
    if (r.audio_path){
      var b = document.createElement("button");
      b.className = "play"; b.type = "button"; b.textContent = "Oir";
      b.onclick = function(){ new Audio("/audio/" + r.id).play(); };
      d.appendChild(b);
    }
    h.appendChild(d);
    last = r.id;
  });
  h.scrollTop = h.scrollHeight;
}
function poll(){
  fetch("/turnos?desde=" + last).then(function(r){return r.json();}).then(function(j){
    if (j.turnos && j.turnos.length) pinta(j.turnos);
    document.getElementById("st").textContent = j.router ? "router ok" : "router en espera";
  }).catch(function(){ document.getElementById("st").textContent = "sin red"; });
}
document.getElementById("f").onsubmit = function(e){
  e.preventDefault();
  var t = document.getElementById("t");
  var texto = t.value.trim();
  if (!texto) return;
  t.value = "";
  fetch("/turno", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({texto: texto})});
};
poll();
setInterval(poll, 2000);
</script>
</body>
</html>
"""


def connect():
    con = sqlite3.connect(DB, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def init():
    AUDIO.mkdir(parents=True, exist_ok=True)
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = connect()
    con.executescript((DIR / "schema.sql").read_text("utf-8"))
    con.execute(
        "INSERT INTO estado (clave, valor) VALUES ('silencio_seg', ?) "
        "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor",
        (str(SILENCIO),),
    )
    con.commit()
    con.close()


def perfil():
    try:
        return PERFIL.read_text("utf-8")
    except OSError:
        return "Sos Elena. Respondé breve, en rioplatense."


def historial(limite=16):
    con = connect()
    rows = con.execute(
        "SELECT rol, texto FROM turnos WHERE rol IN ('ro','elena') "
        "AND origen != 'import' ORDER BY id DESC LIMIT ?",
        (limite,),
    ).fetchall()
    con.close()
    out = []
    for r in reversed(rows):
        out.append(
            {"role": "user" if r["rol"] == "ro" else "assistant", "content": r["texto"]}
        )
    return out


def guardar(rol, texto, origen="chat"):
    con = connect()
    cur = con.execute(
        "INSERT INTO turnos (rol, texto, origen) VALUES (?,?,?)",
        (rol, texto, origen),
    )
    tid = cur.lastrowid
    con.execute(
        "INSERT INTO estado (clave, valor) VALUES ('ultimo_turno_id', ?) "
        "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor",
        (str(tid),),
    )
    con.execute(
        "INSERT INTO estado (clave, valor) VALUES ('nudge_armado', ?) "
        "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor",
        ("0" if origen == "silencio" else "1",),
    )
    con.commit()
    con.close()
    return tid


def marcar_audio(tid, path):
    con = connect()
    con.execute("UPDATE turnos SET audio_path=? WHERE id=?", (str(path), tid))
    con.commit()
    con.close()


def sintetizar(tid, texto):
    dest = AUDIO / f"{tid}.mp3"
    try:
        subprocess.run(
            ["edge-tts", "--voice", VOZ, "--text", texto[:800], "--write-media", str(dest)],
            check=True,
            capture_output=True,
            timeout=45,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if not dest.exists() or dest.stat().st_size < 200:
        return None
    marcar_audio(tid, dest)
    return dest


def ollama_vivo():
    try:
        with urllib.request.urlopen(OLLAMA + "/api/tags", timeout=2) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _post(url, payload, timeout):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        method="POST",
    )
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def embed(texto):
    data = _post(
        OLLAMA + "/api/embeddings",
        {"model": EMBED, "prompt": texto[:1500]},
        30,
    )
    return data.get("embedding") or []


def cosine(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def recordar(turno_id, texto):
    try:
        vec = embed(texto)
    except Exception:
        return
    if not vec:
        return
    con = connect()
    con.execute(
        "INSERT INTO recuerdos (turno_id, texto, vector) VALUES (?,?,?)",
        (turno_id, texto[:1500], json.dumps(vec)),
    )
    con.commit()
    con.close()


def recuperar(consulta, k=4):
    try:
        q = embed(consulta)
    except Exception:
        return []
    if not q:
        return []
    con = connect()
    rows = con.execute(
        "SELECT texto, vector FROM recuerdos ORDER BY id DESC LIMIT 200"
    ).fetchall()
    con.close()
    scored = []
    for r in rows:
        try:
            vec = json.loads(r["vector"])
        except json.JSONDecodeError:
            continue
        scored.append((cosine(q, vec), r["texto"]))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [t for s, t in scored[:k] if s >= 0.35]


def llamar_modelo(mensajes, extra=""):
    sistema = perfil()
    if extra:
        sistema += "\n\nMemoria relevante, usala solo si encaja:\n" + extra
    data = _post(
        OLLAMA + "/api/chat",
        {
            "model": MODELO,
            "stream": False,
            "keep_alive": "10m",
            "options": {"temperature": 0.6, "num_ctx": CTX},
            "messages": [{"role": "system", "content": sistema}] + mensajes,
        },
        120,
    )
    return (data.get("message") or {}).get("content", "").strip()


def responder(texto_ro, origen="chat", voz=True):
    with _lock:
        tid_in = guardar("ro", texto_ro, origen)
        mem = recuperar(texto_ro)
        try:
            respuesta = llamar_modelo(historial(), "\n".join(mem))
        except Exception as exc:
            guardar("sistema", "Ollama no respondió. Quedó pendiente. " + type(exc).__name__, origen)
            return None
        if not respuesta:
            guardar("sistema", "El modelo devolvió vacío.", origen)
            return None
        tid = guardar("elena", respuesta, origen)
    recordar(tid_in, texto_ro)
    recordar(tid, respuesta)
    if voz:
        sintetizar(tid, respuesta)
    return respuesta


_NO_RESPONDER = ("mailer-daemon", "noreply", "no-reply", "elena@karukren.cl")


def correo(payload):
    frm = (payload.get("from") or "").strip().lower()
    asunto = (payload.get("subject") or "(sin asunto)").strip()
    cuerpo = (payload.get("text") or "").strip()
    if not cuerpo:
        return {"ok": False, "error": "vacio"}
    if any(x in frm for x in _NO_RESPONDER):
        guardar("sistema", "correo ignorado de " + frm, "correo")
        return {"ok": True, "dropped": True}
    texto = f"Correo de {frm}. Asunto: {asunto}.\n{cuerpo[:3000]}"
    respuesta = responder(texto, origen="correo", voz=False)
    if not respuesta:
        return {"ok": False, "error": "modelo"}
    return {"ok": True, "answer": respuesta}


def silencio_loop():
    while True:
        time.sleep(5)
        try:
            con = connect()
            armado = con.execute("SELECT valor FROM estado WHERE clave='nudge_armado'").fetchone()
            ultimo = con.execute(
                "SELECT ts, rol FROM turnos ORDER BY id DESC LIMIT 1"
            ).fetchone()
            con.close()
            if not armado or armado["valor"] != "1" or not ultimo or ultimo["rol"] != "elena":
                continue
            edad = time.time() - time.mktime(time.strptime(ultimo["ts"], "%Y-%m-%d %H:%M:%S"))
            if edad < SILENCIO:
                continue
            with _lock:
                texto = "Sigo acá. Si quedaste a mitad, retomo por donde ibas."
                tid = guardar("elena", texto, "silencio")
            sintetizar(tid, texto)
        except Exception:
            continue


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        return

    def _send(self, code, body, content_type):
        raw = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    def _autorizado(self):
        if not TOKEN:
            return True
        return self.headers.get("X-Elena-Token", "") == TOKEN

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/elena"):
            self._send(200, HTML, "text/html; charset=utf-8")
            return
        if path == "/health":
            self._json(200, {"ok": True, "app": "elena", "ollama": ollama_vivo(), "modelo": MODELO, "embed": EMBED, "db": str(DB)})
            return
        if path == "/turnos":
            qs = parse_qs(urlparse(self.path).query)
            desde = int((qs.get("desde") or ["0"])[0] or 0)
            con = connect()
            rows = con.execute(
                "SELECT id, rol, texto, audio_path, origen, ts FROM turnos WHERE id>? ORDER BY id",
                (desde,),
            ).fetchall()
            con.close()
            self._json(200, {"turnos": [dict(r) for r in rows], "router": ollama_vivo()})
            return
        if path.startswith("/audio/"):
            try:
                tid = int(path.rsplit("/", 1)[-1])
            except ValueError:
                self._json(404, {"error": "audio"})
                return
            f = AUDIO / f"{tid}.mp3"
            if not f.is_file():
                self._json(404, {"error": "sin audio"})
                return
            self._send(200, f.read_bytes(), "audio/mpeg")
            return
        self._json(404, {"error": "no"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in ("/turno", "/correo"):
            self._json(404, {"error": "no"})
            return
        if not self._autorizado():
            self._json(401, {"error": "token"})
            return
        n = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(n).decode() or "{}")
        except json.JSONDecodeError:
            self._json(400, {"error": "json"})
            return
        if path == "/correo":
            self._json(200, correo(payload))
            return
        texto = (payload.get("texto") or "").strip()
        if not texto or len(texto) > 4000:
            self._json(400, {"error": "vacio"})
            return
        threading.Thread(target=responder, args=(texto,), daemon=True).start()
        self._json(202, {"aceptado": True})


def main():
    init()
    threading.Thread(target=silencio_loop, daemon=True).start()
    ThreadingHTTPServer.allow_reuse_address = True
    httpd = ThreadingHTTPServer((BIND, PORT), Handler)
    print(f"Elena lista en http://{BIND}:{PORT}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
