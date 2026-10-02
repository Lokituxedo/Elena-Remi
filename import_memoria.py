#!/usr/bin/env python3
"""Importa una vez el historial de texto a elena.db. No toca otras bases.

Uso:
  python import_memoria.py transcripcion.txt mensaje_ro.txt
Lineas que empiezan con 'Ro:' o 'Elena:' se parten. El resto entra como sistema.
origen=import. No sintetiza audio.
"""

import sqlite3
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent
DB = Path(__import__("os").environ.get("ELENA_DB", DIR / "elena.db"))


def main():
    if len(sys.argv) < 2:
        print("pasame al menos un txt")
        return 1
    con = sqlite3.connect(DB)
    con.executescript((DIR / "schema.sql").read_text("utf-8"))
    n = 0
    for raw in sys.argv[1:]:
        path = Path(raw)
        for line in path.read_text("utf-8", errors="replace").splitlines():
            texto = line.strip()
            if not texto:
                continue
            rol = "sistema"
            low = texto.lower()
            if low.startswith("ro:"):
                rol, texto = "ro", texto.split(":", 1)[1].strip()
            elif low.startswith("elena:"):
                rol, texto = "elena", texto.split(":", 1)[1].strip()
            if not texto:
                continue
            con.execute(
                "INSERT INTO turnos (rol, texto, origen) VALUES (?,?, 'import')",
                (rol, texto),
            )
            n += 1
    con.commit()
    con.close()
    print(f"importadas {n} lineas en {DB}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
