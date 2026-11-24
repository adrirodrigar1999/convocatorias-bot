from datetime import date
from pathlib import Path

import pytest

from bot import main as M
from bot import telegram
from bot.fuentes import cargar_fuentes, web
from bot.fuentes.web import Fuente
from bot.store import Store

HOY = date(2026, 11, 24)
AQUI = Path(__file__).parent / "web"

PORTADA_BOP = b"""<html><body>
<a href="/contacto">Contacto</a>
<a href="/bop/2026/11/24/sumario">Sumario del bolet\xc3\xadn de hoy</a>
<a href="/hemeroteca">Hemeroteca</a></body></html>"""

SUMARIO_BOCYL = """<html><body><ul>
<li>ORDEN PRE/1/2026 por la que se convoca proceso selectivo para el ingreso, por el sistema de acceso libre,
 en el Cuerpo de Gestión de la Administración de la Comunidad de Castilla y León.
 <a href="/boletines/2026/11/24/pdf/BOCYL-D-1.pdf">PDF</a></li>
<li>RESOLUCIÓN por la que se aprueba la lista provisional de admitidos al Cuerpo Superior.
 <a href="/boletines/2026/11/24/pdf/BOCYL-D-2.pdf">PDF</a></li>
<li>ORDEN por la que se convoca la provisión de plazas de Médico de familia del Sacyl.
 <a href="/boletines/2026/11/24/pdf/BOCYL-D-3.pdf">PDF</a></li>
<li>DECRETO de subvenciones a ganaderos. <a href="/boletines/2026/11/24/pdf/BOCYL-D-4.pdf">PDF</a></li>
</ul></body></html>""".encode()

RSS_BOPA = """<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>BOPA</title>
<item><title>Resolución por la que se convoca procedimiento extraordinario para la formación de una bolsa de
trabajo de personal temporal del Cuerpo de Ingeniería Informática (Grupo A/Subgrupo A1)</title>
<link>https://miprincipado.asturias.es/bopa/2026/11/24/2026-09001.pdf</link><description>Consejería de Presidencia</description></item>
<item><title>Anuncio de licitación de obras de la carretera AS-17</title>
<link>https://miprincipado.asturias.es/bopa/2026/11/24/2026-09002.pdf</link></item>
</channel></rss>""".encode()

INCIBE = """<html><body><div class="convocatorias">
<div class="conv"><h3><a href="/empleo/INC-25001">Convocatoria pública específica de selección de personal para el acceso libre. Perfil Técnico Senior Laboratorio de Tecnologías</a></h3></div>
<div class="conv"><h3><a href="/empleo/cerradas">Convocatorias cerradas</a></h3></div>
</div><a href="/aviso-legal">Aviso legal</a></body></html>""".encode()

CSV = ("FECHA;TITULO;ENLACE\n24/11/2026;ORDEN por la que se convoca bolsa de empleo de Técnico Superior de Sistemas y "
       "Tecnologías de la Información;https://bocyl.jcyl.es/x.pdf\n01/01/2020;Antigua convocatoria de bolsa;https://bocyl.jcyl.es/y.pdf\n").encode()


class R:
    def __init__(self, content, ctype):
        self.content, self.headers, self.status_code = content, {"content-type": ctype}, 200

    def raise_for_status(self):
        pass


PAGINAS = {
    "https://bop.dipgra.es/": (PORTADA_BOP, "text/html"),
    "https://bop.dipgra.es/bop/2026/11/24/sumario": (b'<html><a href="/bop/2026/11/24/bop.pdf">Bolet\xc3\xadn completo 24/11/2026</a></html>', "text/html"),
    "https://bop.dipgra.es/bop/2026/11/24/bop.pdf": ((AQUI / "bop_sumario.pdf").read_bytes(), "application/pdf"),
    "https://bocyl.jcyl.es/": (SUMARIO_BOCYL, "text/html; charset=utf-8"),
    "https://miprincipado.asturias.es/bopa": (b'<html><head><link rel="alternate" type="application/rss+xml" href="/bopa/rss"></head><body><a href="/x">Inicio</a></body></html>', "text/html"),
    "https://miprincipado.asturias.es/bopa/rss": (RSS_BOPA, "application/rss+xml"),
    "https://www.incibe.es/empleo": (INCIBE, "text/html"),
    "https://datos.jcyl.es/bocyl.csv": (CSV, "text/csv"),
}


class Sesion:
    def get(self, url, headers=None, timeout=None, allow_redirects=True, verify=True):
        if url not in PAGINAS:
            raise RuntimeError(f"404 {url}")
        return R(*PAGINAS[url])


F = {
    "granada": Fuente("bop-granada", "BOP Granada", "boletin", "https://bop.dipgra.es/"),
    "bocyl": Fuente("bocyl", "BOCYL", "boletin", "https://bocyl.jcyl.es/", region="Castilla y León"),
    "bopa": Fuente("bopa", "BOPA", "boletin", "https://miprincipado.asturias.es/bopa", region="Asturias"),
    "incibe": Fuente("incibe", "INCIBE", "web", "https://www.incibe.es/empleo", informatica=True),
    "csv": Fuente("bocyl-datos", "BOCYL datos", "boletin", "https://datos.jcyl.es/bocyl.csv", region="Castilla y León"),
}


def _relevantes(f):
    items, diag = web.obtener(f, Sesion(), HOY)
    out = []
    for it in items:
        c = M._a_convocatoria(f, it)
        r = M._clasificar_item(f, c)
        if r.enviar:
            out.append((c, r))
    return items, diag, out


def test_pdf_del_dia_siguiendo_enlaces():
    items, diag, rel = _relevantes(F["granada"])
    assert diag.pdfs == 1 and diag.paginas == 3
    assert len(rel) == 1 and "informático" in rel[0][0].titulo  # policía y presupuesto fuera
    assert rel[0][1].region is None and rel[0][1].informatica


def test_html_con_texto_del_bloque():
    _, _, rel = _relevantes(F["bocyl"])
    titulos = [c.titulo for c, _ in rel]
    assert len(rel) == 1 and "Cuerpo de Gestión" in titulos[0]   # admitidos y médico fuera
    assert rel[0][1].region == "Castilla y León" and rel[0][1].grupos == ["A2"]


def test_rss_autodescubierto():
    items, diag, rel = _relevantes(F["bopa"])
    assert diag.rss.endswith("/bopa/rss")
    assert len(rel) == 1 and rel[0][1].informatica and rel[0][1].region == "Asturias"


def test_web_todo_informatica_y_ruido_fuera():
    items, _, rel = _relevantes(F["incibe"])
    assert len(rel) == 1 and "Laboratorio" in rel[0][0].titulo
    assert not any("Aviso legal" in i.texto for i in items)


def test_csv_solo_de_hoy():
    items, _, rel = _relevantes(F["csv"])
    assert len(items) == 1 and len(rel) == 1


def test_url_con_fecha():
    assert web.expandir_url("https://x.es/{yyyy}/{dd}-{mm}-{yyyy}.html", HOY) == "https://x.es/2026/24-11-2026.html"


def test_fuentes_yaml_valido():
    fuentes = cargar_fuentes()
    assert len(fuentes) > 90
    assert {f.region for f in fuentes} == {None, "Asturias", "Castilla y León", "Cantabria"}


def test_flujo_completo(tmp_path, monkeypatch):
    """Primera pasada: un resumen por fuente. Segunda: nada repetido. Fuente rota: aviso único."""
    enviados = []
    monkeypatch.setattr(M.telegram, "enviar", lambda t, silencioso=False: enviados.append(t) or True)
    monkeypatch.setattr(M.requests, "Session", Sesion)
    rota = Fuente("rota", "Fuente rota", "web", "https://no-existe.es/")
    monkeypatch.setattr(M, "cargar_fuentes", lambda: [F["bopa"], F["incibe"], rota])
    monkeypatch.setattr(M, "hoy", lambda: HOY)
    store = Store(str(tmp_path / "db.sqlite"))

    M.procesar_fuentes(store, dry_run=False)
    assert sum("primera revisión" in t for t in enviados) == 2

    PAGINAS["https://www.incibe.es/empleo"] = (INCIBE.replace(b"</div>\n</div>",
        b'</div><div class="conv"><h3><a href="/empleo/INC-26002">Convocatoria p\xc3\xbablica. Perfil T\xc3\xa9cnico de Ciberseguridad</a></h3></div></div>'), "text/html")
    enviados.clear()
    for _ in range(M.UMBRAL_AVISO_ROTA):
        M.procesar_fuentes(store, dry_run=False)
    nuevos = [t for t in enviados if "Ciberseguridad" in t]
    assert len(nuevos) == 1 and "Ver anuncio" in nuevos[0]
    avisos_rota = [t for t in enviados if "sin responder" in t]
    assert len(avisos_rota) == 1 and "rota" in avisos_rota[0]
