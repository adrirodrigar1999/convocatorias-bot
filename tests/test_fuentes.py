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
    assert rel == []   # CyL ya no es región y nada es de informática


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
    """1ª pasada: silencio salvo plazo abierto explícito. Después: solo lo nuevo, sin repetir entre fuentes."""
    enviados = []
    monkeypatch.setattr(M.telegram, "enviar", lambda t, silencioso=False: enviados.append(t) or True)
    monkeypatch.setattr(M.requests, "Session", Sesion)
    rota = Fuente("rota", "Fuente rota", "web", "https://no-existe.es/")
    otra = Fuente("otra", "Otra web", "web", "https://otra.es/", informatica=True)
    monkeypatch.setattr(M, "cargar_fuentes", lambda: [F["bopa"], F["incibe"], otra, rota])
    monkeypatch.setattr(M, "hoy", lambda: HOY)
    monkeypatch.setattr(M.config, "DB_PATH", str(tmp_path / "db.sqlite"))
    PAGINAS["https://otra.es/"] = (b"<html><ul><li><a href='/x'>Convocatoria de bolsa de T\xc3\xa9cnico de Ciberseguridad "
                                   b"(plazo hasta el 2 de diciembre de 2026)</a></li>"
                                   b"<li><a href='/y'>Convocatoria de bolsa de Programador (fecha fin: 01/11/2026)</a></li></ul></html>",
                                   "text/html")
    store = Store(str(tmp_path / "db.sqlite"))

    M.procesar_fuentes(store, dry_run=False)
    # solo el de plazo abierto explícito; el cerrado y lo ya publicado en BOPA/INCIBE, en silencio
    assert len(enviados) == 1 and "Ciberseguridad" in enviados[0] and "02/12/2026" in enviados[0]

    enviados.clear()
    PAGINAS["https://www.incibe.es/empleo"] = (INCIBE.replace(b"</div>\n</div>",
        b'</div><div class="conv"><h3><a href="/empleo/INC-26002">Convocatoria p\xc3\xbablica. Perfil T\xc3\xa9cnico de Ciberseguridad de Sistemas</a></h3></div>'
        b'<div class="conv"><h3><a href="/empleo/INC-26003">Convocatoria de bolsa de T\xc3\xa9cnico de Ciberseguridad (plazo hasta el 2 de diciembre de 2026)</a></h3></div></div>'), "text/html")
    # las webs se comprueban abriendo el anuncio: solo se avisa si el plazo está abierto
    PAGINAS["https://www.incibe.es/empleo/INC-26002"] = (
        b"<html><p>Plazo de presentaci\xc3\xb3n de solicitudes hasta el 15/12/2026</p></html>", "text/html")
    for _ in range(M.UMBRAL_AVISO_ROTA):
        M.procesar_fuentes(store, dry_run=False)
    avisos = [t for t in enviados if "Ver anuncio" in t]
    assert len(avisos) == 1 and "Sistemas" in avisos[0]      # el INC-26003 es el mismo que ya llegó de "otra"
    assert sum("sin responder" in t for t in enviados) == 1


def test_ruido_de_webs_fuera():
    html = """<html><body><nav><a href="/empleo">Empleo público</a></nav><ul>
    <li><a href="/a.pdf">BASES DE LA CONVOCATORIA ( pdf , 316,6 kB )</a></li>
    <li><a href="/b.pdf">Calificación final de la convocatoria y propuesta de contratación Perfil Técnico de Desarrollo</a></li>
    <li><a href="/c.pdf">Situación de la Bolsa el 05-02-2025 (128 KB)</a></li>
    <li><a href="/d">Contratación Temporal</a></li>
    <li><a href="/e">Normas de Constitución, funcionamiento y gestión de las Bolsas de Empleo (Resolución de 1 de agosto de 2017)</a></li>
    <li><a href="/f">Convocatoria de bolsa de empleo de Técnico/a de Sistemas Informáticos</a></li>
    </ul>
    <p>ORDEN PRE/2/2026 por la que se convoca proceso selectivo para el Cuerpo de Gestión de Sistemas e Informática.</p>
    <a href="/g.pdf">BOCYL-D-24112026-227-5.pdf - 829 KB</a> <a href="/g.html">html y otros formatos</a>
    </body></html>""".encode()
    PAGINAS["https://ruido.es/"] = (html, "text/html")
    f = Fuente("ruido", "Ruido", "web", "https://ruido.es/", region="Asturias")
    items, _ = web.obtener(f, Sesion(), HOY)
    textos = [i.texto for i in items]
    assert any("Sistemas Informáticos" in t for t in textos)
    assert any(t.startswith("ORDEN PRE/2/2026") for t in textos)   # título tomado del texto anterior al enlace PDF
    assert len(items) == 2, textos


def test_reset_borra_chat_y_estado(tmp_path, monkeypatch):
    llamadas = []

    def api(metodo, datos):
        llamadas.append((metodo, datos.get("message_ids", [])))
        return {"ok": True, "result": {"message_id": 250}} if metodo == "sendMessage" else {"ok": True}

    monkeypatch.setattr(M.telegram, "_api", api)
    monkeypatch.setattr(M.telegram.time, "sleep", lambda s: None)
    monkeypatch.setattr(M.config, "TELEGRAM_TOKEN", "x")
    monkeypatch.setattr(M.config, "TELEGRAM_CHAT_ID", "1")
    db = tmp_path / "db.sqlite"
    Store(str(db))
    monkeypatch.setattr(M.config, "DB_PATH", str(db))
    monkeypatch.setattr(M.config, "ULTIMA_EJECUCION_PATH", str(tmp_path / "ultima.txt"))
    M.resetear(confirmado=True)
    borradas = sorted(i for m, ids in llamadas if m == "deleteMessages" for i in ids)
    assert borradas == list(range(1, 251)) and not db.exists()


def test_boe_y_boletin_no_repiten(tmp_path, monkeypatch):
    from bot.modelo import Convocatoria, Resultado
    enviados = []
    monkeypatch.setattr(M.telegram, "enviar", lambda t, silencioso=False: enviados.append(t) or True)
    store = Store(str(tmp_path / "db.sqlite"))
    c1 = Convocatoria("BOE-A-1", "BOE", HOY, "ADMINISTRACIÓN LOCAL", "t", "u")
    r1 = Resultado(True, "region", organismo="Ayuntamiento de Siero (Asturias)",
                   plazas=["Una plaza de Técnico/a de Administración General"])
    assert M._enviar_aviso(store, c1, r1, r1.organismo + " " + r1.plazas[0])
    c2 = Convocatoria("bopa:1", "BOPA", HOY, "BOPA",
                      "Anuncio. Ayuntamiento de Siero. Bases para la provisión de una plaza de Técnico/a de Administración General", "u")
    assert M._enviar_aviso(store, c2, Resultado(True, "region"), c2.titulo)
    assert len(enviados) == 1 and store.visto("bopa:1")


def test_jsonapi_drupal_gijon():
    import json
    from bot.fuentes import web
    doc = {"data": [
        {"attributes": {"title": "Bolsa de empleo Técnico/a de Gestión. Ayuntamiento de Castrillón",
                        "field_categoria_convocatorias": "Empleo", "field_plazo2": "11/12/2026",
                        "path": {"alias": "/bolsa-tecnico-gestion"}}},
        {"attributes": {"title": "Programa Juventud Asturiana Cooperante 2027",
                        "field_categoria_convocatorias": "Ayudas y Subvenciones"}},
    ]}
    items = web._parsear_jsonapi(json.dumps(doc).encode(), "https://drupal.gijon.es/es/jsonapi/node/convocatorias")
    assert len(items) == 1
    assert "11/12/2026" in items[0].texto
    assert items[0].url == "https://www.gijon.es/es/bolsa-tecnico-gestion"
    assert web._parsear_jsonapi(b"<html></html>", "x") is None


def test_meta_refresh_y_frameset():
    from bot.fuentes import web

    class R:
        def __init__(self, url, contenido):
            self.url, self.content, self.headers = url, contenido, {"content-type": "text/html"}
    r = R("https://boletin.dguadalajara.es/",
          b"<html><head><META HTTP-EQUIV='Refresh' CONTENT='0; URL=https://boletin.dguadalajara.es/boletin/'></head><body></body></html>")
    assert web._redireccion_html(r) == "https://boletin.dguadalajara.es/boletin/"
    r = R("https://www.boplaspalmas.net/nbop2/index.php", b"<html><frameset rows='80,*,40'><frame src='cab.php'>"
          b"<frame src='main1.php'><frame src='pie.php'></frameset></html>")
    assert web._redireccion_html(r) == "https://www.boplaspalmas.net/nbop2/main1.php"
    assert web._redireccion_html(R("https://x.es/", b"<html><body><a href='a'>a</a></body></html>")) is None


def test_json_generico_bop_ourense():
    import json
    from bot.fuentes import web
    doc = [{"boletin": {"numeroBop": 227, "edictos": [
        {"id": 1, "sumarioCas": "Convocatoria de una plaza de Técnico/a de Informática, Concello de Verín",
         "sumario": "CONVOCATORIA"},
        {"id": 2, "sumarioCas": "Convenio Colectivo de la empresa Comar Orense, S.L."}]}}]
    items = web._parsear_jsonapi(json.dumps(doc).encode(), "https://bop.depourense.es/portalapi/x")
    assert [i.texto[:20] for i in items] == ["Convocatoria de una ", "Convenio Colectivo d"]
    assert items[0].url == "https://bop.depourense.es/portalapi/x"


def test_json_boa_latin1_y_claves_mayusculas():
    from bot.fuentes import web
    raw = ('[{"Titulo": "RESOLUCIÓN por la que se convoca proceso selectivo de Técnico de Sistemas", '
           '"UriEli": "https://www.boa.aragon.es/eli/x"}]').encode("latin-1")
    items = web._parsear_jsonapi(raw, "https://www.boa.aragon.es/cgi-bin/x")
    assert items and items[0].url == "https://www.boa.aragon.es/eli/x" and "Sistemas" in items[0].texto


def test_texto_con_slug_de_la_url():
    from bot.fuentes import web
    html = b'<html><body><a href="/bopt/web/anunci/366759/bases-convocatoria-tecnic-informatica-ajuntament">DIPUTACIO TARRAGONA - PERSONES I TALENT</a></body></html>'
    items, _ = web._enlaces_html(html, "https://www.dipta.cat/bopt/web/")
    assert any("tecnic informatica" in i.texto for i in items)


def _sesion_falsa(html):
    class R:
        def __init__(self):
            self.content, self.url, self.headers = html.encode(), "https://x.es/a", {"content-type": "text/html"}
        def raise_for_status(self):
            pass
    class S:
        def get(self, *a, **k):
            return R()
    return S()


def test_estado_plazo_pagina():
    from datetime import date
    from bot.fuentes import web
    f = web.Fuente(id="ayto-oviedo", nombre="Oviedo", tipo="web", url="https://www.oviedo.es/")
    hoy = date(2026, 11, 26)
    # proceso de 2024 sin plazo: cerrado por antigüedad
    e, _, _ = web.estado_plazo(f, "https://x.es/a", _sesion_falsa(
        "<p>1 plaza de Técnico de Gestión. Bases publicadas el 12/03/2024. OEP 2024</p>"), hoy)
    assert e == "cerrada"
    # con lista de admitidos: cerrado
    e, _, _ = web.estado_plazo(f, "https://x.es/a", _sesion_falsa(
        "<p>Analista TIC. 20/11/2026: Lista provisional de personas admitidas y excluidas</p>"), hoy)
    assert e == "cerrada"
    # plazo explícito futuro: abierto
    e, fin, _ = web.estado_plazo(f, "https://x.es/a", _sesion_falsa(
        "<p>Plazo de presentación de solicitudes: del 20/11/2026 al 10/12/2026</p>"), hoy)
    assert e == "abierta" and fin == date(2026, 12, 10)
    # plazo explícito pasado: cerrado
    e, _, _ = web.estado_plazo(f, "https://x.es/a", _sesion_falsa(
        "<p>Plazo de solicitudes hasta el 05/11/2026</p>"), hoy)
    assert e == "cerrada"
    # sin ninguna fecha: no se puede confirmar
    e, _, _ = web.estado_plazo(f, "https://x.es/a", _sesion_falsa("<p>Bolsa de Analista TIC</p>"), hoy)
    assert e == "desconocido"


def test_slug_no_se_repite_si_ya_esta_en_el_texto():
    from bot.fuentes import web
    html = b'<a href="/empleo/1-plaza-de-tecnico-a-de-gestion">1 plaza de t\xc3\xa9cnico/a de Gesti\xc3\xb3n</a>'
    items, _ = web._enlaces_html(html, "https://www.oviedo.es/")
    assert items[0].texto == "1 plaza de técnico/a de Gestión"
