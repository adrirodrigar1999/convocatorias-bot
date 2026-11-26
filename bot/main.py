"""Punto de entrada.

  python -m bot.main                       procesa los días pendientes hasta hoy y termina
  python -m bot.main --programado          revisa solo si toca (DIAS_EJECUCION); lo lanza launchd cada hora en el Mac
  python -m bot.main --daemon              se queda corriendo y revisa cada día a HORA_EJECUCION
  python -m bot.main --fecha 2026-11-24 --dry-run    muestra qué avisaría, sin enviar ni guardar
  python -m bot.main --desde 2026-11-01 --hasta 2026-11-24
  python -m bot.main --prueba-telegram     manda un mensaje de prueba
  python -m bot.main --reset               borra los mensajes enviados y reinicia el estado
  python -m bot.main --probar-fuentes [id ...]   diagnóstico de boletines y webs
  python -m bot.main --solo-fuentes --dry-run    qué avisaría hoy de boletines y webs
  python -m bot.main --seguimiento [--dry-run]   revisa ya los procesos de seguimiento.yaml
"""
import argparse
import logging
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from . import clasificador, config, llm, seguimiento, telegram
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


def _repetida(store: Store | None, texto: str) -> bool:
    if store is None:
        return False
    h = clasificador.huella(texto)
    return any(clasificador.parecidas(h, otra) for otra in store.huellas_recientes(config.DIAS_ANTIDUPLICADOS))


def _enviar_aviso(store: Store, c, r, texto_huella: str) -> bool:
    """Envía si no es repetida. Devuelve False solo si Telegram falla (para reintentar)."""
    if _repetida(store, texto_huella):
        store.guardar(c, False, "repetida (ya enviada desde otra fuente)")
        return True
    if not telegram.enviar(telegram.formatear(c, r)):
        return False
    store.guardar(c, True, r.motivo)
    store.registrar_envio(c.id, clasificador.huella(texto_huella))
    return True


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
        elif r.enviar and not r.plazo_fin and clasificador.plazo_seguro_cerrado(c.fecha, r.plazo_texto, hoy()):
            r.enviar, r.motivo = False, "plazo cerrado (contado desde otro boletín)"
        if r.enviar:
            r = llm.afinar(c, r)
        if dry_run:
            if r.enviar:
                print("\n" + "=" * 70 + "\n" + telegram.formatear(c, r))
            else:
                print(f"  descartado {c.id}: {r.motivo} | {c.titulo[:110]}")
        elif r.enviar:
            if not _enviar_aviso(store, c, r, r.organismo + " " + " ".join(r.plazas or [c.titulo])):
                fallos += 1
        else:
            store.guardar(c, False, r.motivo)
        avisos += int(r.enviar)

    if fallos:
        # No se marca el día: los avisos que fallaron se reintentan en la próxima pasada
        raise RuntimeError(f"{fallos} avisos no se pudieron enviar por Telegram")
    if store and not dry_run:
        store.marcar_dia(nombre, fecha)
    log.info("%s %s: %d anuncios nuevos, %d avisos", nombre, fecha, nuevos, avisos)
    return nuevos, avisos


# --- Boletines autonómicos/provinciales y webs (lector genérico) ----------------------------
UMBRAL_AVISO_ROTA = 2   # revisiones seguidas fallando antes de avisar


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
            fin = clasificador.fin_de_plazo_en_texto(c.titulo, hoy())
            if fin:
                r.plazo_fin, r.plazo_texto = fin, "según el anuncio"
                if r.enviar and fin < hoy():
                    r.enviar, r.motivo = False, "plazo cerrado"
            # Primera vez que se mira esta fuente: lo que ya estaba publicado solo se avisa
            # si el propio anuncio dice que el plazo sigue abierto (el resto se guarda en silencio).
            if r.enviar and primera and not fin:
                r.enviar, r.motivo = False, "ya publicado antes de empezar a vigilar la fuente"
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

        fallo = False
        for c, r in pares:
            if r.enviar:
                if not _enviar_aviso(store, c, r, c.titulo):
                    fallo = True
            else:
                store.guardar(c, False, r.motivo)
        if not fallo:
            store.fuente_ok(f.id)

    if store and not dry_run:
        rotas = store.fuentes_rotas_sin_avisar(UMBRAL_AVISO_ROTA)
        if rotas:
            lineas = ["🛠 Estas fuentes llevan varias pasadas sin responder (puede que hayan cambiado de web):"]
            lineas += [f"• {i} ({n} fallos): {telegram._e(err or '')[:120]}" for i, n, err in rotas]
            lineas.append("El BOE y el resto de fuentes siguen revisándose con normalidad. No te volveré a avisar de estas mismas.")
            if telegram.enviar("\n".join(lineas), silencioso=True):
                store.marcar_avisado([i for i, *_ in rotas])
    log.info("Fuentes: %d anuncios nuevos, %d avisos", nuevos_total, avisos_total)
    return nuevos_total, avisos_total


def probar_fuentes(solo: list[str] | None = None) -> None:
    """Diagnóstico: qué devuelve cada fuente, sin enviar ni guardar nada."""
    import os

    def expandir(u):
        return web.expandir_url(u, hoy())
    fuentes = [f for f in cargar_fuentes() if not solo or f.id in solo]
    filas = []
    for f, items, diag, error in descargar_todas(fuentes):
        relevantes = []
        for it in items:
            c = _a_convocatoria(f, it)
            r = _clasificar_item(f, c)
            if r.enviar:
                relevantes.append(f"[{r.titulacion}{' 💻' if r.informatica else ''}] {it.texto[:140]}")
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
    print("\n\n########## DETALLE POR FUENTE ##########")
    for f, estado, diag, error, items, rel in filas:
        print(f"\n=== {f.id} [{estado}] {expandir(f.url)}")
        if error:
            print("  error:", error)
            continue
        for t in rel[:8]:
            print("  ✓", t)
        if not rel:
            for it in items[:5]:
                print("  · empleo (no encaja):", it.texto[:110])
        if not items:
            for t in diag.muestra:
                print("  ~", t)
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


DIAS_SEMANA = {"lun": 0, "mar": 1, "mie": 2, "mié": 2, "jue": 3, "vie": 4, "sab": 5, "sáb": 5, "dom": 6}


def toca_ejecutar(ahora: datetime, ultima: datetime | None, dias: list[int], hora: int, minuto: int) -> bool:
    """¿Ha pasado alguna cita (p. ej. lunes o jueves a las 9:00) desde la última ejecución?"""
    if ultima is None:
        return True
    for atras in range(8):
        d = (ahora - timedelta(days=atras)).date()
        cita = datetime(d.year, d.month, d.day, hora, minuto, tzinfo=ahora.tzinfo)
        if d.weekday() in dias and cita <= ahora:
            return ultima < cita
    return False


def seguimiento_diario(ahora: datetime) -> None:
    """Los procesos a los que te has presentado se miran cada día (desde HORA_EJECUCION), no solo lunes y jueves."""
    import os
    h, m = map(int, config.HORA_EJECUCION.split(":"))
    if (ahora.hour, ahora.minute) < (h, m):
        return
    ruta = config.ULTIMO_SEGUIMIENTO_PATH
    if os.path.exists(ruta):
        with open(ruta) as fh:
            if fh.read().strip() == ahora.date().isoformat():
                return
    try:
        seguimiento.revisar(Store(config.DB_PATH), ahora.date())
    except Exception as e:
        log.exception("Error en el seguimiento de procesos")
        telegram.enviar(f"⚠️ Error revisando tus procesos: {e}", silencioso=True)
        return
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w") as fh:
        fh.write(ahora.date().isoformat())


def programado() -> None:
    """Pensado para lanzarse cada hora (launchd): solo trabaja si toca."""
    import os
    seguimiento_diario(datetime.now(TZ))
    dias = [DIAS_SEMANA[x.strip().lower()] for x in config.DIAS_EJECUCION.split(",") if x.strip()]
    h, m = map(int, config.HORA_EJECUCION.split(":"))
    ruta = config.ULTIMA_EJECUCION_PATH
    ultima = None
    if os.path.exists(ruta):
        with open(ruta) as fh:
            ultima = datetime.fromisoformat(fh.read().strip())
    ahora = datetime.now(TZ)
    if not toca_ejecutar(ahora, ultima, dias, h, m):
        log.info("No toca todavía (última ejecución: %s)", ultima)
        return
    log.info("Toca revisar (última ejecución: %s)", ultima)
    ejecutar(None, dry_run=False)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w") as fh:
        fh.write(ahora.isoformat(timespec="seconds"))


def resetear(confirmado: bool = False) -> None:
    """Borra los mensajes del chat (Telegram permite hasta 48 h atrás) y el estado del bot."""
    import os
    if not confirmado:
        resp = input("Se borrarán los mensajes del chat del bot y todo lo que ha visto. Escribe SI para seguir: ")
        if resp.strip().upper() != "SI":
            print("Cancelado.")
            return
    borrados = telegram.borrar_mensajes()
    for ruta in (config.DB_PATH, config.ULTIMA_EJECUCION_PATH, config.ULTIMO_SEGUIMIENTO_PATH):
        if os.path.exists(ruta):
            os.remove(ruta)
    print(f"Hecho: chat limpiado (últimos {borrados} mensajes) y estado del bot reiniciado.")
    print("La próxima revisión volverá a mirar 45 días atrás y solo avisará de lo que siga abierto.")


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
    ap.add_argument("--programado", action="store_true",
                    help="revisa solo si ha pasado un día de DIAS_EJECUCION desde la última vez (Mac)")
    ap.add_argument("--fecha", type=date.fromisoformat)
    ap.add_argument("--desde", type=date.fromisoformat)
    ap.add_argument("--hasta", type=date.fromisoformat)
    ap.add_argument("--dry-run", action="store_true", help="no envía ni guarda; imprime los avisos")
    ap.add_argument("--prueba-telegram", action="store_true")
    ap.add_argument("--reset", action="store_true", help="borra los mensajes enviados y el estado del bot")
    ap.add_argument("--si", action="store_true", help="no pedir confirmación (con --reset)")
    ap.add_argument("--probar-fuentes", nargs="*", metavar="ID",
                    help="diagnóstico de boletines/webs (todas o las indicadas)")
    ap.add_argument("--solo-fuentes", action="store_true", help="revisa boletines/webs sin el BOE")
    ap.add_argument("--seguimiento", action="store_true", help="revisa ya los procesos de seguimiento.yaml")
    a = ap.parse_args()

    if a.reset:
        resetear(a.si)
        return
    if a.probar_fuentes is not None:
        probar_fuentes(a.probar_fuentes or None)
        return
    if a.seguimiento:
        seguimiento.revisar(None if a.dry_run else Store(config.DB_PATH), hoy(), a.dry_run)
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
    if a.programado:
        programado()
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
