-- Elena. Base propia. No es paralelo, rem, entrenamiento ni D1 de correo.

CREATE TABLE IF NOT EXISTS turnos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  rol TEXT NOT NULL,
  texto TEXT NOT NULL,
  audio_path TEXT,
  origen TEXT NOT NULL DEFAULT 'chat',
  ts TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_turnos_id ON turnos(id);
CREATE INDEX IF NOT EXISTS idx_turnos_origen ON turnos(origen);

CREATE TABLE IF NOT EXISTS estado (
  clave TEXT PRIMARY KEY,
  valor TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recuerdos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  turno_id INTEGER,
  texto TEXT NOT NULL,
  vector TEXT NOT NULL,
  ts TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_recuerdos_turno ON recuerdos(turno_id);

INSERT OR IGNORE INTO estado (clave, valor) VALUES ('ultimo_turno_id', '0');
INSERT OR IGNORE INTO estado (clave, valor) VALUES ('silencio_seg', '90');
INSERT OR IGNORE INTO estado (clave, valor) VALUES ('nudge_armado', '0');
INSERT OR IGNORE INTO estado (clave, valor) VALUES ('modelo', 'qwen2.5:3b-instruct-q4_K_M');
INSERT OR IGNORE INTO estado (clave, valor) VALUES ('embed', 'nomic-embed-text');
