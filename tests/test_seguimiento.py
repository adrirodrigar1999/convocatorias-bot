from datetime import date, datetime
from zoneinfo import ZoneInfo

from bot import main as M
from bot import seguimiento as S
from bot.fuentes import web
from bot.store import Store

HOY = date(2027, 1, 15)

SUMARIO = """<html><body><ul>
<li>LISTA PROVISIONAL DE PERSONAS ADMITIDAS Y EXCLUIDAS A LA CONVOCATORIA PARA LA PROVISIÓN EN PROPIEDAD,
 MEDIANTE CONCURSO-OPOSICIÓN LIBRE, DE UNA PLAZA DE TÉCNICO/A AUXILIAR INFORMÁTICA
 <a href="https://boletin.dguadalajara.es/boletin/pdf/pdf2027_100.pdf">PDF</a></li>
<li>BASES PARA UNA PLAZA DE TÉCNICO/A AUXILIAR DE INFORMÁTICA DEL AYUNTAMIENTO DE AZUQUECA
 <a href="https://boletin.dguadalajara.es/boletin/pdf/pdf2027_101.pdf">PDF</a></li>
<li>SUBVENCIONES PARA FIESTAS DE INTERÉS TURÍSTICO <a href="https://boletin.dguadalajara.es/boletin/pdf/pdf2027_102.pdf">PDF</a></li>
</ul></body></html>""".encode()

TABLON = """<html><body><table>
<tr><td>13-01-2027</td><td>Recursos Humanos</td><td>Tribunal y fecha primer ejercicio TAI</td>
<td><a href="https://www.dguadalajara.es/documents/tribunal-tai.pdf">Documento</a></td></tr>
<tr><td>12-01-2027</td><td>Recursos Humanos</td><td>Bolsa de Oficial Cerrajero</td>
<td><a href="https://www.dguadalajara.es/documents/cerrajero.pdf">Documento</a></td></tr>
</table></body></html>""".encode()


class R:
    def __init__(self, content):
        self.content, self.headers, self.status_code = content, {"content-type": "text/html"}, 200

    def raise_for_status(self):
        pass


PAGINAS = {"https://boletin.dguadalajara.es/": SUMARIO,
           "https://www.dguadalajara.es/web/guest/tablon-informativo": TABLON}


class Sesion:
    def get(self, url, headers=None, timeout=None, allow_redirects=True, verify=True):
        if url not in PAGINAS:
            raise RuntimeError(f"404 {url}")
        return R(PAGINAS[url])


def _proceso(**kw):
    datos = dict(id="tai", nombre="TAI Diputación", buscar=__import__("re").compile(r"auxiliar\W+(de\W+)?informatica|\btai\b"),
                 excluir=__import__("re").compile("ayuntamiento"), fuentes=["bop-guadalajara"],
                 urls=["https://www.dguadalajara.es/web/guest/tablon-informativo"])
    datos.update(kw)
    return S.Proceso(**datos)


def _preparar(monkeypatch, tmp_path):
    enviados = []
    monkeypatch.setattr(S.telegram, "enviar", lambda t, silencioso=False: enviados.append(t) or True)
    monkeypatch.setattr(S.requests, "Session", Sesion)
    monkeypatch.setattr(S, "cargar_fuentes", lambda: [
        web.Fuente("bop-guadalajara", "BOP Guadalajara", "boletin", "https://boletin.dguadalajara.es/")])
    return enviados, Store(str(tmp_path / "db.sqlite"))


def test_yaml_valido():
    procesos = S.cargar()
    assert procesos and all(p.fuentes or p.urls for p in procesos)
    assert S.coincide(procesos[0], "Lista provisional de admitidos, una plaza de TÉCNICO/A AUXILIAR INFORMÁTICA")


def test_avisa_admitidos_y_tablon_una_sola_vez(monkeypatch, tmp_path):
    enviados, store = _preparar(monkeypatch, tmp_path)
    assert S.revisar(store, HOY, procesos=[_proceso()]) == 2
    assert any("ADMITIDAS" in t for t in enviados)
    assert any("Tribunal y fecha primer ejercicio TAI" in t for t in enviados)
    assert not any("AZUQUECA" in t or "Cerrajero" in t or "SUBVENCIONES" in t for t in enviados)
    # la segunda pasada no repite
    assert S.revisar(store, HOY, procesos=[_proceso()]) == 0
    assert len(enviados) == 2


def test_proceso_caducado_no_se_mira(monkeypatch, tmp_path):
    enviados, store = _preparar(monkeypatch, tmp_path)
    assert S.revisar(store, HOY, procesos=[_proceso(hasta=date(2026, 12, 31))]) == 0
    assert enviados == []


def test_seguimiento_una_vez_al_dia(monkeypatch, tmp_path):
    llamadas = []
    monkeypatch.setattr(M.seguimiento, "revisar", lambda store, hoy, dry_run=False: llamadas.append(hoy) or 0)
    monkeypatch.setattr(M.config, "DB_PATH", str(tmp_path / "db.sqlite"))
    monkeypatch.setattr(M.config, "ULTIMO_SEGUIMIENTO_PATH", str(tmp_path / "seg.txt"))
    tz = ZoneInfo("Europe/Madrid")
    M.seguimiento_diario(datetime(2027, 1, 15, 7, 0, tzinfo=tz))    # antes de la hora: nada
    M.seguimiento_diario(datetime(2027, 1, 15, 10, 0, tzinfo=tz))
    M.seguimiento_diario(datetime(2027, 1, 15, 11, 0, tzinfo=tz))   # ya hecho hoy
    M.seguimiento_diario(datetime(2027, 1, 16, 10, 0, tzinfo=tz))
    assert llamadas == [date(2027, 1, 15), date(2027, 1, 16)]
