"""Memoria del bot en SQLite: qué anuncios ya se revisaron y qué días ya se procesaron."""
import os
import sqlite3
from datetime import date, datetime


class Store:
    def __init__(self, ruta: str):
        os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
        self.db = sqlite3.connect(ruta)
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS anuncios (
                id TEXT PRIMARY KEY,
                fuente TEXT,
                fecha TEXT,
                titulo TEXT,
                url TEXT,
                enviado INTEGER,
                motivo TEXT,
                revisado_en TEXT
            );
            CREATE TABLE IF NOT EXISTS dias (
                fuente TEXT,
                fecha TEXT,
                PRIMARY KEY (fuente, fecha)
            );
            CREATE TABLE IF NOT EXISTS estado_fuentes (
                id TEXT PRIMARY KEY,
                ultimo_ok TEXT,
                fallos INTEGER DEFAULT 0,
                ultimo_error TEXT,
                avisado INTEGER DEFAULT 0
            );
            """
        )

    def visto(self, ident: str) -> bool:
        return self.db.execute("SELECT 1 FROM anuncios WHERE id = ?", (ident,)).fetchone() is not None

    def guardar(self, c, enviado: bool, motivo: str) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO anuncios VALUES (?,?,?,?,?,?,?,?)",
            (c.id, c.fuente, c.fecha.isoformat(), c.titulo, c.url, int(enviado), motivo,
             datetime.now().isoformat(timespec="seconds")),
        )
        self.db.commit()

    def dia_hecho(self, fuente: str, fecha: date) -> bool:
        return self.db.execute(
            "SELECT 1 FROM dias WHERE fuente = ? AND fecha = ?", (fuente, fecha.isoformat())
        ).fetchone() is not None

    def marcar_dia(self, fuente: str, fecha: date) -> None:
        self.db.execute("INSERT OR IGNORE INTO dias VALUES (?, ?)", (fuente, fecha.isoformat()))
        self.db.commit()

    def ultimo_dia(self, fuente: str) -> date | None:
        fila = self.db.execute("SELECT MAX(fecha) FROM dias WHERE fuente = ?", (fuente,)).fetchone()
        return date.fromisoformat(fila[0]) if fila and fila[0] else None

    # --- Fuentes genéricas -----------------------------------------------------------
    def fuente_nueva(self, fuente_id: str) -> bool:
        """True si nunca se ha revisado (primera pasada: se manda un resumen, no un mensaje por item)."""
        return self.db.execute("SELECT 1 FROM estado_fuentes WHERE id = ? AND ultimo_ok IS NOT NULL",
                               (fuente_id,)).fetchone() is None

    def fuente_ok(self, fuente_id: str) -> None:
        self.db.execute(
            "INSERT INTO estado_fuentes (id, ultimo_ok, fallos, avisado) VALUES (?, ?, 0, 0) "
            "ON CONFLICT(id) DO UPDATE SET ultimo_ok = excluded.ultimo_ok, fallos = 0, avisado = 0",
            (fuente_id, datetime.now().isoformat(timespec="seconds")),
        )
        self.db.commit()

    def fuente_fallo(self, fuente_id: str, error: str) -> int:
        self.db.execute(
            "INSERT INTO estado_fuentes (id, fallos, ultimo_error) VALUES (?, 1, ?) "
            "ON CONFLICT(id) DO UPDATE SET fallos = fallos + 1, ultimo_error = excluded.ultimo_error",
            (fuente_id, error[:300]),
        )
        self.db.commit()
        return self.db.execute("SELECT fallos FROM estado_fuentes WHERE id = ?", (fuente_id,)).fetchone()[0]

    def fuentes_rotas_sin_avisar(self, umbral: int) -> list[tuple[str, int, str]]:
        return self.db.execute(
            "SELECT id, fallos, ultimo_error FROM estado_fuentes WHERE fallos >= ? AND avisado = 0",
            (umbral,),
        ).fetchall()

    def marcar_avisado(self, ids: list[str]) -> None:
        self.db.executemany("UPDATE estado_fuentes SET avisado = 1 WHERE id = ?", [(i,) for i in ids])
        self.db.commit()
