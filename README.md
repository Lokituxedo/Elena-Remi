Elena
=====

App propia de chat y voz. No es el mesh, no abre LiteLLM, no lee paralelo.db, rem.db ni D1.

Qué hace
--------
Modelo en la 1060 del i5: qwen2.5:3b-instruct-q4_K_M por Ollama. Memoria: nomic-embed-text, vectores en elena.db. Contexto 2048 para no llenar los 6 GB (la placa también maneja el escritorio).

Correo: POST /correo {"from","subject","text"} devuelve {"answer"}. No llama a Resend ni escribe en la D1 vieja. Ignora mailer-daemon, noreply y elena@karukren.cl.
- Si Elena habló y Ro no contesta en 90 segundos, manda un solo aviso y no insiste.
- Base elena.db, tabla turnos. El audio vive en archivos, no en el sqlite.

Deploy
------
En el host, al lado de este directorio:

    cp .env.example .env
    # si el 9router corre en el host y no en el compose:
    # NINEROUTER_URL=http://host.docker.internal:20128
    docker compose up -d --build

Sin Docker:

    pip install -r requirements.txt
    python3 elena_app.py

Abrir http://<ip-tailscale>:8099 desde el móvil. Health: GET /health.

Importar memoria, una vez, con el proceso ya creado la base
------------------------------------------------------------
    python3 import_memoria.py /ruta/transcripcion.txt /ruta/mensaje_ro.txt

Esas líneas entran con origen=import y no se reenvían al modelo como turno vivo.
El modelo solo ve los turnos nuevos de chat.

Variables
---------
ELENA_PORT, ELENA_VOZ, ELENA_MODELO, ELENA_SILENCIO_SEG, NINEROUTER_URL, NINEROUTER_KEY, ELENA_TOKEN.
Si ELENA_TOKEN está seteado, POST /turno exige la cabecera X-Elena-Token. El navegador de esta versión no la manda: dejalo vacío en la red Tailscale, o ponelo solo si el cliente lo agrega.
