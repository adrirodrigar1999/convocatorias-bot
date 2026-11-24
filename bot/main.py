"""Punto de entrada.

  python -m bot.main                       procesa los días pendientes hasta hoy y termina
  python -m bot.main --daemon              se queda corriendo y revisa cada día a HORA_EJECUCION
  python -m bot.main --fecha 2026-11-24 --dry-run    muestra qué avisaría, sin enviar ni guardar
  python -m bot.main --desde 2026-11-01 --hasta 2026-11-24
  python -m bot.main --prueba-telegram     manda un mensaje de prueba
  python -m bot.main --probar-fuentes [id ...]   diagnóstico de boletines y webs
  python -m bot.main --solo-fuentes --dry-run    qué avisaría hoy de boletines y webs
"""
import argparse
import logging
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from . import clasificador, config, llm, telegram
from concurrent.futures import ThreadPoolExecutor

from .fuentes import FUENTES, cargar_fuentes
from .fuentes import web
from .fuentes.boe import SinBoletin
from .modelo import Convocatoria
from .store import Store

log = logging.getLogger("bot")
TZ = ZoneInfo(config.ZONA_HORARIA)


def hoy() -> date:
    return datetime.now(TZ).date()


def procesar_dia(nombre: str, fecha: date, store: Store | None, dry_run: bool,
                 session: requests.Session) -> tuple[int, int] | None:
    """Devuelve (anuncios nuevos revisados, avisos) o None si el boletín de ese día aún no está disponible."""
    modulo = FUENTES[nombre]
    try:
        convocatorias = modulo.obtener(fecha, session)
    except SinBoletin:
        if fecha == hoy() and fecha.weekday() != 6:
            log.info("%s de %s aún no publicado", nombre, fecha)
            return None
        log.info("No hay %s el %s", nombre, fecha)
        if store and not dry_run:
            store.marcar_dia(nombre, fecha)
        return 0, 0

    avisos = fallos = nuevos = 0
    for c in convocatorias:
        if store and not dry_run and store.visto(c.id):
            continue
        nuevos += 1
        r = clasificador.clasificar(c)
        if r.enviar and r.plazo_fin and r.plazo_fin < hoy():
            r.enviar, r.motivo = False, "plazo cerrado"
        if r.enviar:
            r = llm.afinar(c, r)
        if dry_run:
            if r.enviar:
                print("\n" + "=" * 70 + "\n" + telegram.formatear(c, r))
            else:
                print(f"  descartado {c.id}: {r.motivo} | {c.titulo[:110]}")
        else:
            ok = telegram.enviar(telegram.formatear(c, r)) if r.enviar else True
            if ok:
                store.guardar(c, r.enviar, r.motivo)
            else:
                fallos += 1
        avisos += int(r.enviar)

    if fallos:
        # No se marca el día: los avisos que fallaron se reintentan en la próxima pasada
        raise RuntimeError(f"{fallos} avisos no se pudieron enviar por Telegram")
    if store and not dry_run:
        store.marcar_dia(nombre, fecha)
    log.info("%s %s: %d anuncios nuevos, %d avisos", nombre, fecha, nuevos, avisos)
    return nuevos, avisos


# --- Boletines autonómicos/provinciales y webs (lector genérico) ----------------------------
UMBRAL_AVISO_ROTA = 6   # pasadas seguidas fallando (~2 días) antes de avisar


def _descargar(f: web.Fuente):
    session = requests.Session()
    try:
        items, diag = web.obtener(f, session, hoy())
        return f, items, diag, None
    except Exception as e:
        return f, [], None, f"{type(e).__name__}: {e}"[:300]


def _a_convocatoria(f: web.Fuente, it: web.Item) -> Convocatoria:
    return Convocatoria(id=f"{f.id}:{it.clave}", fuente=f.nombre, fecha=hoy(),
                        departamento=f.nombre, titulo=it.texto, url=it.url)


def _clasificar_item(f: web.Fuente, c: Convocatoria):
    return clasificador.clasificar(c, region=f.region, exigir_convocatoria=(f.tipo == "boletin"),
                                   todo_informatica=f.informatica)


def descargar_todas(fuentes: list[web.Fuente]):
    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(_descargar, fuentes))


def procesar_fuentes(store: Store | None, dry_run: bool, solo: list[str] | None = None) -> tuple[int, int]:
    fuentes = [f for f in cargar_fuentes() if not solo or f.id in solo]
    nuevos_total = avisos_total = 0
    for f, items, diag, error in descargar_todas(fuentes):
        if error or (diag and diag.enlaces == 0):
            motivo = error or "la página no devolvió enlaces"
            log.warning("Fuente %s falla: %s", f.id, motivo)
            if store and not dry_run:
                store.fuente_fallo(f.id, motivo)
            continue
        primera = store.fuente_nueva(f.id) if (store and not dry_run) else False
        pares = []
        for it in items:
            c = _a_convocatoria(f, it)
            if store and not dry_run and store.visto(c.id):
                continue
            nuevos_total += 1
            r = _clasificar_item(f, c)
            if r.enviar:
                r = llm.afinar(c, r)
            pares.append((c, r))
        enviables = [(c, r) for c, r in pares if r.enviar]
        avisos_total += len(enviables)

        if dry_run:
            print(f"\n##### {f.nombre} ({f.id}): {len(items)} anuncios de empleo, {len(enviables)} encajan")
            for c, r in enviables[:10]:
                print(telegram.formatear(c, r) + "\n")
            continue

        if primera and enviables:
            ok = telegram.enviar(telegram.formatear_resumen(f.nombre, enviables))
            if not ok:
                continue  # se reintentará entera en la próxima pasada
            for c, r in pares:
                store.guardar(c, r.enviar, r.motivo)
        else:
            for c, r in pares:
                if r.enviar and not telegram.enviar(telegram.formatear(c, r)):
                    continue
                store.guardar(c, r.enviar, r.motivo)
        store.fuente_ok(f.id)

    if store and not dry_run:
        rotas = store.fuentes_rotas_sin_avisar(UMBRAL_AVISO_ROTA)
        if rotas:
            lineas = ["🛠 Estas fuentes llevan varias pasadas sin responder (puede que hayan cambiado de web):"]
            lineas += [f"• {i} ({n} fallos): {telegram._e(err or '')[:120]}" for i, n, err in rotas]
            lineas.append("Revísalas en fuentes.yaml o lanza el workflow con «probar_fuentes».")
            if telegram.enviar("\n".join(lineas), silencioso=True):
                store.marcar_avisado([i for i, *_ in rotas])
    log.info("Fuentes: %d anuncios nuevos, %d avisos", nuevos_total, avisos_total)
    return nuevos_total, avisos_total


def probar_fuentes(solo: list[str] | None = None) -> None:
    """Diagnóstico: qué devuelve cada fuente, sin enviar ni guardar nada."""
    import os
    fuentes = [f for f in cargar_fuentes() if not solo or f.id in solo]
    filas = []
    for f, items, diag, error in descargar_todas(fuentes):
        relevantes = []
        for it in items:
            c = _a_convocatoria(f, it)
            if _clasificar_item(f, c).enviar:
                relevantes.append(it.texto[:90])
        if error:
            estado = "❌ error"
        elif diag.enlaces == 0:
            estado = "⚠️ vacía"
        elif diag.items == 0:
            estado = "⚠️ sin empleo"
        else:
            estado = "✅ ok"
        filas.append((f, estado, diag, error, items, relevantes))

    cab = "| Fuente | Estado | Páginas | Enlaces | Empleo | Encajan | Detalle |\n|---|---|---|---|---|---|---|"
    lineas = [cab]
    for f, estado, diag, error, items, rel in filas:
        if error:
            det = error[:100]
        else:
            partes = []
            if diag.rss:
                partes.append("RSS")
            if diag.pdfs:
                partes.append(f"{diag.pdfs} PDF")
            if rel:
                partes.append("ej.: " + rel[0])
            elif items:
                partes.append("ej. empleo: " + items[0].texto[:80])
            det = "; ".join(partes)
        det = det.replace("|", "/")
        lineas.append(f"| {f.id}{'' if f.verificada else ' *'} | {estado} | {diag.paginas if diag else 0} | "
                      f"{diag.enlaces if diag else 0} | {len(items)} | {len(rel)} | {det} |")
    ok = sum(1 for x in filas if x[1].startswith("✅"))
    resumen = f"\n{ok}/{len(filas)} fuentes responden con anuncios de empleo. (* = URL sin verificar a mano)\n"
    texto = "\n".join(lineas) + resumen
    print(texto)
    destino = os.getenv("GITHUB_STEP_SUMMARY")
    if destino:
        with open(destino, "a", encoding="utf-8") as fh:
            fh.write("## Diagnóstico de fuentes\n\n" + texto)


def dias_pendientes(store: Store, nombre: str) -> list[date]:
    ultimo = store.ultimo_dia(nombre)
    inicio = (ultimo + timedelta(days=1)) if ultimo else hoy() - timedelta(days=config.DIAS_PRIMERA_EJECUCION)
    dias = []
    d = inicio
    while d <= hoy():
        if not store.dia_hecho(nombre, d):
            dias.append(d)
        d += timedelta(days=1)
    return dias


def ejecutar(fechas: list[date] | None, dry_run: bool) -> bool:
    """Procesa las fechas indicadas (o las pendientes). Devuelve True si el BOE de hoy ya está hecho."""
    store = None if dry_run else Store(config.DB_PATH)
    session = requests.Session()
    hoy_hecho = True
    for nombre in FUENTES:
        dias = fechas if fechas is not None else dias_pendientes(store, nombre)
        total_rev = total_av = 0
        for d in dias:
            try:
                res = procesar_dia(nombre, d, store, dry_run, session)
            except Exception as e:
                log.exception("Error en %s %s", nombre, d)
                if not dry_run:
                    telegram.enviar(f"⚠️ Error revisando {nombre} del {d:%d/%m/%Y}: {e}", silencioso=True)
                if d == hoy():
                    hoy_hecho = False
                continue
            if res is None:
                hoy_hecho = False
                continue
            total_rev += res[0]
            total_av += res[1]
        if not dry_run and config.RESUMEN_DIARIO and dias and total_rev:
            rango = f"{dias[0]:%d/%m}" + (f"–{dias[-1]:%d/%m}" if len(dias) > 1 else "")
            if total_av == 0:
                telegram.enviar(f"😴 {nombre} {rango}: sin novedades ({total_rev} anuncios revisados)",
                                silencioso=True)
            else:
                telegram.enviar(f"📊 {nombre} {rango}: {total_av} avisos de {total_rev} anuncios revisados",
                                silencioso=True)
    if fechas is None:
        try:
            nuevos, avisos = procesar_fuentes(store, dry_run)
            if not dry_run and config.RESUMEN_DIARIO and avisos:
                telegram.enviar(f"📊 Boletines y webs: {avisos} avisos de {nuevos} anuncios nuevos",
                                silencioso=True)
        except Exception as e:
            log.exception("Error en las fuentes genéricas")
            if not dry_run:
                telegram.enviar(f"⚠️ Error revisando boletines y webs: {e}", silencioso=True)
    return hoy_hecho


def bucle() -> None:
    h, m = map(int, config.HORA_EJECUCION.split(":"))
    log.info("Modo daemon: revisión diaria a las %s (%s)", config.HORA_EJECUCION, config.ZONA_HORARIA)
    while True:
        ahora = datetime.now(TZ)
        objetivo = ahora.replace(hour=h, minute=m, second=0, microsecond=0)
        hoy_hecho = True
        if ahora >= objetivo:
            hoy_hecho = ejecutar(None, dry_run=False)
        if hoy_hecho or ahora < objetivo:
            siguiente = objetivo if ahora < objetivo else objetivo + timedelta(days=1)
        else:
            siguiente = ahora + timedelta(hours=1)  # el BOE de hoy aún no estaba: reintenta
        espera = max(60, (siguiente - datetime.now(TZ)).total_seconds())
        log.info("Próxima revisión: %s", siguiente.strftime("%d/%m %H:%M"))
        time.sleep(espera)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Avisos de convocatorias de empleo público por Telegram")
    ap.add_argument("--daemon", action="store_true")
    ap.add_argument("--fecha", type=date.fromisoformat)
    ap.add_argument("--desde", type=date.fromisoformat)
    ap.add_argument("--hasta", type=date.fromisoformat)
    ap.add_argument("--dry-run", action="store_true", help="no envía ni guarda; imprime los avisos")
    ap.add_argument("--prueba-telegram", action="store_true")
    ap.add_argument("--probar-fuentes", nargs="*", metavar="ID",
                    help="diagnóstico de boletines/webs (todas o las indicadas)")
    ap.add_argument("--solo-fuentes", action="store_true", help="revisa boletines/webs sin el BOE")
    a = ap.parse_args()

    if a.probar_fuentes is not None:
        probar_fuentes(a.probar_fuentes or None)
        return
    if a.solo_fuentes:
        store = None if a.dry_run else Store(config.DB_PATH)
        procesar_fuentes(store, a.dry_run)
        return

    if a.prueba_telegram:
        ok = telegram.enviar("👋 Bot de convocatorias conectado correctamente.")
        print("Enviado" if ok else "No se pudo enviar (revisa TELEGRAM_TOKEN y TELEGRAM_CHAT_ID)")
        return
    if a.daemon:
        bucle()
        return

    fechas = None
    if a.fecha:
        fechas = [a.fecha]
    elif a.desde:
        fin = a.hasta or hoy()
        fechas = [a.desde + timedelta(days=i) for i in range((fin - a.desde).days + 1)]
    ejecutar(fechas, a.dry_run)


if __name__ == "__main__":
    main()
