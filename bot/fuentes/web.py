"""Lector genérico de boletines y webs de empleo.

Cada fuente se define en fuentes.yaml. El lector descarga la URL y, según lo que encuentre:
  * RSS/Atom         -> un item por entrada
  * XML / CSV        -> un item por registro con texto y enlace
  * PDF              -> un item por línea del sumario que hable de empleo
  * HTML             -> un item por enlace (con el texto de su bloque); si la página anuncia un
                        RSS lo usa, y sigue hasta 4 enlaces tipo "sumario", "último boletín",
                        "empleo", "procesos selectivos"... para llegar al listado real.
Los items se filtran luego con el clasificador; aquí solo se extrae.
"""
import csv
import hashlib
import io
import json
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import urljoin, urlparse

import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/131.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
}
TIMEOUT = 40
MAX_PDF_BYTES = 25 * 1024 * 1024
MAX_PDF_PAGINAS = 12
MAX_SALTOS = 12

SEGUIR_BOLETIN = (
    r"sumario|[uú]ltimo (bolet[ií]n|n[uú]mero|bop)|bolet[ií]n (de hoy|del d[ií]a|actual)"
    r"|edici[oó]n (de hoy|del d[ií]a|actual)|bop de hoy|consultar? (el )?bolet[ií]n|ver bolet[ií]n"
    r"|autoridades y personal|oposiciones y concursos|empleo p[uú]blico"
    r"|butllet[ií] del dia|[uú]ltim n[uú]mero|^avui\b|sumari del dia"
)
SEGUIR_WEB = (
    r"empleo|trabaja con nosotros|trabajar en|procesos? (de )?selecci|procesos selectivos|oposiciones"
    r"|ofertas? de (empleo|trabajo)|convocatorias|recursos humanos|bolsas? de (empleo|trabajo)"
    r"|\bptgas\b|\bpas\b|selecci[oó]n de personal|carreras|careers"
)
# Texto mínimo para considerar que un item habla de empleo
EMPLEO = re.compile(
    r"convoca|bolsa|plaza|proceso selectivo|procesos selectivos|pruebas selectivas|oposici"
    r"|selecci[oó]n de personal|personal (funcionario|laboral|interino|temporal|estatutario)"
    r"|interin|cobertura|provisi[oó]n|contrataci[oó]n (temporal|laboral)|lista de (empleo|espera)"
    r"|puesto|vacante|empleo",
    re.I,
)
EMPLEO_WEB_EXTRA = re.compile(r"t[eé]cnic|perfil|analista|programador|ingenier|responsable|gestor|auxiliar", re.I)
# Señal fuerte de que el anuncio es un proceso de selección (no un menú ni una noticia)
CONVOCATORIA = re.compile(
    r"convoca|bolsa|proceso selectivo|procesos selectivos|pruebas selectivas|oposici|\bplazas?\b"
    r"|selecci[oó]n de personal|procesos? de selecci|provisi[oó]n (de|definitiva|temporal|interina)"
    r"|lista de empleo|vacantes?\b|puestos? de trabajo|interin|perfil (t[eé]cnico|profesional)"
    r"|contrataci[oó]n (temporal|laboral|de personal)|personal (laboral|funcionario|estatutario|temporal)",
    re.I,
)
# Cosas que parecen empleo pero no lo son
NO_EMPLEO = re.compile(
    r"perfil (del|de) contratante|licitaci|contrato (de|menor)|subvenci|\bayudas?\b|\bbecas?\b|\bpremios?\b"
    r"|pr[aá]cticas|presupuest|subasta|enajenaci|expropiaci|actas previas|ordenanza|padr[oó]n|\btasas?\b"
    r"|impuesto|cursos? de formaci|planes? de formaci|formaci[oó]n (transversal|continua|abierta)|juez de paz"
    r"|convenio colectivo|urbanis|licencia|cobranza|recaudaci|tribut|noticia|agenda|eventos?\b"
    r"|^(en )?este apartado|enlace de acceso|calendario|predoctoral|postdoctoral|envejecimiento|programa de"
    r"|^(el|la|los|las) (ayuntamiento|diputaci|junta|universidad|consejer|gobierno|alcald)",
    re.I,
)
# Documentos de un proceso ya en marcha (no son convocatorias nuevas)
TRAMITE = re.compile(
    r"calificaci|resultados?\b|nota (rectificativa|aclaratoria|informativa)|situaci[oó]n de la bolsa|^normas\b"
    r"|criterios de|llamamiento|propuesta de (contrataci|nombramiento)|omitid|plantilla (de respuestas|correctora)"
    r"|cuestionario|\bex[aá]menes?\b|ejercicio|temario|baremaci|valoraci[oó]n|subsanaci|alegaci|acuerdo adoptado"
    r"|mesa (de|general)|modificaci|instrucciones|\banexos?\b|modelo de|formulario|movilidad|carrera (y|profesional)"
    r"|jefaturas?|supervisi|coordinaci|desarrollo profesional|bases generales|toma de posesi|adjudica|admitid|excluid"
    r"|aprobad|nombramient|tribunal|correcci[oó]n|rectificaci|desiert|renuncia|lista (provisional|definitiva)|listado"
    r"|acumulaci[oó]n|ampliaci[oó]n|pruebas f[ií]sicas|fecha (de|del) (examen|ejercicio)",
    re.I,
)
# Para webs: si el texto es corto, debe nombrar un puesto o cuerpo
PUESTO = re.compile(
    r"t[eé]cnic|analista|programador|ingenier|auxiliar|administrativ|gestor|gesti[oó]n|celador|enfermer|m[eé]dic"
    r"|operari|oficial|polic|bomber|conductor|escala|cuerpo|categor[ií]a|subgrupo|grupo [a-e]|plazas? de|puesto de"
    r"|informátic|informatic|sistemas|ciberseguridad|desarroll|datos|titulad|ordenanza|subalterno|limpiad|pe[oó]n",
    re.I,
)
INICIO_PDF = re.compile(
    r"^[\d\.\-\s/]*(resoluci|anuncio|edicto|bases|convocatoria|decreto|orden\b|acuerdo|extracto|ayuntamiento"
    r"|diputaci|aprobaci|oferta|proceso|procedimiento|lista|bolsa)",
    re.I,
)
TAMANO = re.compile(r"\(\s*(pdf|docx?|odt)\s*,?\s*[\d.,]+\s*[kKmM][bB]\s*\)|\b\d+[.,]?\d*\s*[kKmM][bB]\b")
NAV_CLASES = ("menu", "nav", "footer", "header", "breadcrumb", "cookie", "migas", "dropdown", "sidebar-menu")
RUIDO = re.compile(
    r"^(inicio|contacto|aviso legal|cookies|accesibilidad|mapa web|pol[ií]tica de privacidad|buscar|"
    r"men[uú]|volver|siguiente|anterior|ver m[aá]s|leer m[aá]s|m[aá]s informaci[oó]n|descargar|pdf|"
    r"compartir|imprimir|facebook|twitter|x|instagram|linkedin|youtube)$",
    re.I,
)
# Etiquetas de menú: llevan al listado, pero no son anuncios
MENU = re.compile(
    r"^(convocatorias?|ofertas? de empleo|empleo|empleo p[uú]blico|trabaja con nosotros|procesos selectivos"
    r"|procesos de selecci[oó]n|bolsas?|bolsas? de (empleo|trabajo)|oposiciones|recursos humanos|sumario)"
    r"( (abiertas?|cerradas?|en curso|vigentes|activas?|anteriores|finalizad[ao]s|del d[ií]a|de hoy))?$",
    re.I,
)
BLOQUES = ("li", "tr", "article", "dd", "dt", "p", "h2", "h3", "h4", "h5")


@dataclass
class Fuente:
    id: str
    nombre: str
    tipo: str                      # "boletin" | "web"
    url: str
    region: str | None = None      # Asturias / Castilla y León / Cantabria, o None (solo informática)
    seguir: str | None = None      # regex de enlaces a seguir; por defecto según tipo
    pdf: bool = True               # leer PDFs del día enlazados (boletines)
    verificar_ssl: bool = True     # false solo para webs públicas con el certificado mal instalado
    tls_antiguo: bool = False      # true solo para webs públicas con TLS antiguo que OpenSSL 3 rechaza
    informatica: bool = False      # todo lo que publica es de informática (p. ej. INCIBE)
    verificada: bool = False
    extra: dict = field(default_factory=dict)


@dataclass
class Item:
    texto: str
    url: str
    nav: bool = False   # enlace de menú/cabecera/pie: sirve para navegar, no es un anuncio
    desde_pdf: bool = False

    @property
    def clave(self) -> str:
        base = (self.url + "|" + " ".join(self.texto.lower().split())[:200]).encode()
        return hashlib.sha1(base).hexdigest()[:16]


@dataclass
class Diagnostico:
    estado: str = "ok"
    paginas: int = 0
    enlaces: int = 0
    items: int = 0
    rss: str = ""
    pdfs: int = 0
    error: str = ""
    muestra: list = field(default_factory=list)   # textos de enlaces (no menú) para depurar


def expandir_url(url: str, hoy: date) -> str:
    return (url.replace("{yyyy}", f"{hoy:%Y}").replace("{mm}", f"{hoy:%m}")
               .replace("{dd}", f"{hoy:%d}").replace("{yyyymmdd}", f"{hoy:%Y%m%d}"))


DIAS_ATRAS = 4   # el bot revisa lunes y jueves: hay que mirar también los boletines de los días anteriores


def _fechas_hoy(hoy: date) -> list[str]:
    from datetime import timedelta
    fechas = []
    for i in range(DIAS_ATRAS + 1):
        d = hoy - timedelta(days=i)
        fechas += [f"{d:%Y%m%d}", f"{d:%Y/%m/%d}", f"{d:%d-%m-%Y}", f"{d:%d/%m/%Y}", f"{d:%Y-%m-%d}",
                   f"{d:%d%m%Y}", f"{d:%d-%m-%y}"]
    return fechas


def _limpio(s: str) -> str:
    return " ".join(s.split())


def _dominio(url: str) -> str:
    partes = urlparse(url).netloc.lower().split(".")
    return ".".join(partes[-2:])


# --- Formatos estructurados ---------------------------------------------------------------
def _parsear_feed(contenido: bytes) -> list[Item] | None:
    try:
        root = ET.fromstring(contenido)
    except ET.ParseError:
        return None
    tag = root.tag.split("}")[-1].lower()
    items: list[Item] = []
    if tag in ("rss", "rdf"):
        for it in root.iter():
            if it.tag.split("}")[-1] != "item":
                continue
            campos = {c.tag.split("}")[-1]: (c.text or "") for c in it}
            texto = _limpio(campos.get("title", "") + ". " + BeautifulSoup(campos.get("description", ""), "html.parser").get_text(" ")[:300])
            if campos.get("link"):
                items.append(Item(texto, campos["link"].strip()))
        return items
    if tag == "feed":
        for en in root:
            if en.tag.split("}")[-1] != "entry":
                continue
            titulo = resumen = link = ""
            for c in en:
                n = c.tag.split("}")[-1]
                if n == "title":
                    titulo = c.text or ""
                elif n in ("summary", "content"):
                    resumen = BeautifulSoup(c.text or "", "html.parser").get_text(" ")[:300]
                elif n == "link" and (c.get("rel") in (None, "alternate")):
                    link = c.get("href", "")
            if link:
                items.append(Item(_limpio(titulo + ". " + resumen), link))
        return items
    return None


def _parsear_xml_generico(contenido: bytes, base: str) -> list[Item]:
    """Registros con un campo de título y otro de enlace (p. ej. sumarios en datos abiertos)."""
    root = ET.fromstring(contenido)
    items = []
    for nodo in root.iter():
        hijos = list(nodo)
        if not hijos:
            continue
        texto = url = ""
        for h in hijos:
            n = h.tag.split("}")[-1].lower()
            v = _limpio("".join(h.itertext()))
            if not texto and re.search(r"titul|title|sumario|texto|descripcion|extracto", n) and len(v) > 15:
                texto = v
            if not url:
                cand = v if v.startswith("http") else (h.get("href") or "")
                if cand.startswith("http") or (re.search(r"url|enlace|link|pdf|html", n) and cand):
                    url = urljoin(base, cand)
        if texto and url:
            items.append(Item(texto, url))
    return items


CATEGORIAS_EMPLEO = re.compile(r"empleo|oposici|convocatoria|proceso", re.I)


def _parsear_jsonapi(contenido: bytes, base: str) -> list[Item] | None:
    """Drupal JSON:API (p. ej. drupal.gijon.es, que alimenta la web de Gijón hecha con JavaScript)."""
    try:
        doc = json.loads(contenido)
    except ValueError:
        return None
    datos = doc.get("data") if isinstance(doc, dict) else None
    if not isinstance(datos, list) or not all(isinstance(d, dict) and "attributes" in d for d in datos[:3]):
        return _parsear_json_generico(doc, base)
    items = []
    for d in datos:
        a = (d or {}).get("attributes") or {}
        titulo = (a.get("title") or "").strip()
        if not titulo:
            continue
        cat = a.get("field_categoria_convocatorias")
        if isinstance(cat, str) and cat and not CATEGORIAS_EMPLEO.search(cat):
            continue
        partes = [titulo]
        for k in ("field_convoca", "field_resumen_tablon"):
            v = a.get(k)
            if isinstance(v, str) and v.strip():
                partes.append(BeautifulSoup(v, "lxml").get_text(" ", strip=True)[:400])
        cuerpo = a.get("body")
        if isinstance(cuerpo, dict) and (cuerpo.get("summary") or cuerpo.get("value")):
            txt = BeautifulSoup(cuerpo.get("summary") or cuerpo.get("value"), "lxml").get_text(" ", strip=True)
            partes.append(txt[:400])
        plazo = a.get("field_plazo2")
        if isinstance(plazo, str) and plazo.strip():
            partes.append(f"Plazo de solicitudes hasta el {plazo.strip()}")
        url = ""
        for k in ("field_enlace", "field_url"):
            v = a.get(k)
            v = v.get("uri") if isinstance(v, dict) else (v[0].get("uri") if isinstance(v, list) and v and isinstance(v[0], dict) else v)
            if isinstance(v, str) and v.startswith("http"):
                url = v
                break
        if not url:
            alias = (a.get("path") or {}).get("alias") if isinstance(a.get("path"), dict) else None
            host = urlparse(base)
            url = f"{host.scheme}://{host.netloc.replace('drupal.', 'www.')}/es{alias}" if alias else base
        items.append(Item(". ".join(partes), url))
    return items


CLAVES_TEXTO = ("sumarioCas", "titulo", "title", "asunto", "sumarioEdicto", "sumario", "descripcion", "nombre")
CLAVES_URL = ("url", "enlace", "link", "href", "urlPdf", "pdf")


def _parsear_json_generico(doc, base: str) -> list[Item]:
    """APIs JSON de boletines (p. ej. BOP Ourense): recoge los textos largos de cada objeto."""
    items, vistos = [], set()

    def recorrer(x, profundidad=0):
        if profundidad > 8:
            return
        if isinstance(x, dict):
            texto = next((x[k] for k in CLAVES_TEXTO if isinstance(x.get(k), str) and len(x[k].strip()) >= 25), None)
            if texto:
                url = next((x[k] for k in CLAVES_URL if isinstance(x.get(k), str) and x[k].startswith("http")), base)
                t = _limpio(BeautifulSoup(texto, "lxml").get_text(" ")) if "<" in texto else _limpio(texto)
                if t not in vistos:
                    vistos.add(t)
                    items.append(Item(t[:400], url))
            for v in x.values():
                recorrer(v, profundidad + 1)
        elif isinstance(x, list):
            for v in x:
                recorrer(v, profundidad + 1)

    recorrer(doc)
    return items


def _parsear_csv(contenido: bytes, base: str, hoy: date) -> list[Item]:
    texto = contenido.decode("utf-8-sig", errors="replace")
    muestra = texto[:5000]
    try:
        dialecto = csv.Sniffer().sniff(muestra, delimiters=";,\t|")
    except csv.Error:
        dialecto = csv.excel
    filas = list(csv.DictReader(io.StringIO(texto), dialect=dialecto))
    if not filas:
        return []
    cols = list(filas[0].keys())
    col_txt = next((c for c in cols if c and re.search(r"titul|sumario|texto|descrip|extracto", c, re.I)), None)
    col_url = next((c for c in cols if c and re.search(r"url|enlace|link|pdf|html", c, re.I)), None)
    if not col_txt:
        return []
    fechas = _fechas_hoy(hoy)
    recientes = [f for f in filas if any(x in " ".join(map(str, f.values())) for x in fechas)]
    filas = recientes or filas[-300:]
    items = []
    for f in filas:
        url = (f.get(col_url) or "").strip() if col_url else ""
        items.append(Item(_limpio(f.get(col_txt) or ""), urljoin(base, url) if url else base))
    return [i for i in items if i.texto]


def _parsear_pdf(contenido: bytes, url: str) -> list[Item]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(contenido))
    lineas: list[str] = []
    for pagina in reader.pages[:MAX_PDF_PAGINAS]:
        try:
            lineas += (pagina.extract_text() or "").splitlines()
        except Exception:
            continue
    # Une líneas partidas: si la siguiente empieza en minúscula, es continuación
    unidas: list[str] = []
    for l in (x.strip() for x in lineas):
        if not l:
            continue
        if unidas and (l[0].islower() or unidas[-1].endswith(("-", ",", " de", " la", " del"))):
            unidas[-1] = unidas[-1].rstrip("-") + " " + l
        else:
            unidas.append(l)
    items = []
    for l in unidas:
        l = re.sub(r"\.{3,}\s*\d+\s*$", "", l).strip()  # "Título ........ 23" del sumario
        if 25 <= len(l) <= 400:
            items.append(Item(l, url, desde_pdf=True))
    return items


# --- HTML ---------------------------------------------------------------------------
GENERICO = re.compile(
    r"\.pdf|\.html?\b|\bkb\b|\bmb\b|^pdf$|^html|otros formatos|^descargar|^ver (documento|anuncio|disposici|pdf|m[aá]s)"
    r"|^ir al detalle$|^\d+$|^(aqu[ií]|enlace|documento|anuncio|texto completo|leer m[aá]s)$",
    re.I,
)


def _texto_previo(a, maximo: int = 300) -> str:
    """Texto que precede al enlace (títulos de sumario cuyo enlace es solo «PDF»)."""
    trozos, total = [], 0
    for nodo in a.find_all_previous(string=True):
        padre = nodo.parent
        if padre is not None and padre.name in ("a", "script", "style"):
            if trozos:
                break  # el anterior enlace marca el fin del título
            continue
        t = _limpio(str(nodo))
        if not t:
            continue
        trozos.append(t)
        total += len(t)
        if total >= maximo or (padre is not None and padre.name in ("h1", "h2", "h3", "h4", "li", "p", "td")):
            break
    return _limpio(" ".join(reversed(trozos)))[:400]


def _texto_enlace(a) -> str:
    propio = _limpio(a.get_text(" "))
    if GENERICO.search(propio) or len(propio) < 25:
        previo = _texto_previo(a)
        if len(previo) >= 25 and not GENERICO.search(previo[:40]):
            return previo
    if len(propio) >= 25 and not RUIDO.match(propio):
        return propio[:400]
    padre = a
    for _ in range(4):
        padre = padre.parent
        if padre is None or padre.name in ("body", "html"):
            break
        if len(padre.find_all("a")) > 2:
            break  # el bloque es un menú o un listado: el texto del padre no describe este enlace
        if padre.name in BLOQUES or padre.name == "div":
            t = _limpio(padre.get_text(" "))
            if len(t) > 500:
                break
            if len(t) >= len(propio):
                return t[:400]
    return propio[:400]


def _es_nav(a) -> bool:
    for p in a.parents:
        if p.name in ("nav", "header", "footer", "aside"):
            return True
        marca = (" ".join(p.get("class") or []) + " " + (p.get("id") or "") + " " + (p.get("role") or "")).lower()
        if any(k in marca for k in NAV_CLASES) or "navigation" in marca:
            return True
    return False


def _enlaces_html(html: bytes, base: str) -> tuple[list[Item], str]:
    sopa = BeautifulSoup(html, "lxml")
    rss = ""
    for l in sopa.find_all("link", attrs={"rel": "alternate"}):
        if "rss" in (l.get("type") or "") or "atom" in (l.get("type") or ""):
            rss = urljoin(base, l.get("href", ""))
            break
    items, vistos = [], set()
    for a in sopa.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("mailto:", "tel:")):
            continue
        texto = _texto_enlace(a)
        if href.startswith("javascript:") or href.startswith("#"):
            # anuncios que se abren con JavaScript (p. ej. BOP Zaragoza): el título vale, el enlace es la página
            if not texto or len(texto) < 40:
                continue
            url = base
        else:
            url = urljoin(base, href)
        if not texto or (url, texto) in vistos:
            continue
        vistos.add((url, texto))
        items.append(Item(texto, url, nav=_es_nav(a)))
    return items, rss


class _AdaptadorTLSAntiguo(requests.adapters.HTTPAdapter):
    """Para las pocas webs públicas marcadas con `tls_antiguo: true` en fuentes.yaml: aceptan solo
    renegociación heredada o claves cortas y OpenSSL 3 las rechaza. Se usa únicamente para leerlas."""

    def init_poolmanager(self, *args, **kwargs):
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
        try:
            ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
        except ssl.SSLError:
            pass
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)


_sesion_tls_antiguo: requests.Session | None = None


def _sesion_antigua() -> requests.Session:
    global _sesion_tls_antiguo
    if _sesion_tls_antiguo is None:
        _sesion_tls_antiguo = requests.Session()
        _sesion_tls_antiguo.mount("https://", _AdaptadorTLSAntiguo())
    return _sesion_tls_antiguo


def _get(session: requests.Session, url: str, verificar: bool = True,
         tls_antiguo: bool = False) -> requests.Response:
    if tls_antiguo:
        session, verificar = _sesion_antigua(), False
    for _ in range(3):
        r = session.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True, verify=verificar)
        r.raise_for_status()
        sig = _redireccion_html(r)
        if not sig or sig == r.url:
            return r
        url = sig
    return r


RX_REFRESH = re.compile(rb"""<meta[^>]+http-equiv=["']?refresh["']?[^>]*content=["']?\s*\d+\s*;\s*url=([^"'>\s]+)""", re.I)
RX_FRAME = re.compile(rb"""<frame\b[^>]*\bsrc=["']?([^"'>\s]+)""", re.I)


def _redireccion_html(r: requests.Response) -> str | None:
    """Páginas que solo redirigen con <meta refresh> o son un <frameset>: devuelve la página real."""
    if _es_pdf(r) or len(r.content) > 20000:
        return None
    cabeza = r.content[:20000]
    m = RX_REFRESH.search(cabeza)
    if not m and b"<frameset" in cabeza.lower():
        frames = RX_FRAME.findall(cabeza)
        # se descartan cabecera, pie y menú; queda el marco del contenido
        utiles = [f for f in frames if not re.search(rb"cab|pie|head|foot|top|menu|nav|banner", f, re.I)]
        m_url = (utiles or frames or [None])[0]
    else:
        m_url = m.group(1) if m else None
    if not m_url:
        return None
    return urljoin(r.url, m_url.decode("latin-1").strip())


def _es_pdf(r: requests.Response) -> bool:
    return "pdf" in r.headers.get("content-type", "").lower() or r.content[:5] == b"%PDF-"


def _procesar(session, url: str, r: requests.Response, hoy: date, diag: Diagnostico) -> tuple[list[Item], str]:
    ctype = r.headers.get("content-type", "").lower()
    if _es_pdf(r):
        diag.pdfs += 1
        return _parsear_pdf(r.content, url), ""
    if "json" in ctype or r.content[:1] == b"{":
        api = _parsear_jsonapi(r.content, url)
        if api is not None:
            return api, ""
    if "csv" in ctype or url.lower().endswith(".csv"):
        return _parsear_csv(r.content, url, hoy), ""
    cabeza = r.content[:3000].lstrip().lower()
    es_html = b"<html" in cabeza or "html" in ctype
    if not es_html and (cabeza.startswith(b"<?xml") or "xml" in ctype or cabeza.startswith((b"<rss", b"<feed"))):
        feed = _parsear_feed(r.content)
        if feed is not None:
            return feed, url
        return _parsear_xml_generico(r.content, url), ""
    return _enlaces_html(r.content, url)


def obtener_crudo(f: Fuente, session: requests.Session, hoy: date) -> tuple[list[Item], Diagnostico]:
    """Todo lo que publica la fuente (siguiendo sumarios), sin el filtro de empleo.

    Lo usa también el seguimiento de procesos, que necesita ver listas de admitidos, tribunales...
    """
    diag = Diagnostico()
    from datetime import timedelta
    dias = range(DIAS_ATRAS + 1) if "{" in f.url else range(1)
    urls = list(dict.fromkeys(expandir_url(f.url, hoy - timedelta(days=i)) for i in dias))
    url = urls[0]
    items, rss, error, alguna = [], "", None, False
    for u in urls:   # con plantilla de fecha: hoy y los días anteriores (días sin boletín no cuentan como fallo)
        try:
            r = _get(session, u, f.verificar_ssl, f.tls_antiguo)
            nuevos, rs = _procesar(session, u, r, hoy, diag)
            items += nuevos
            rss = rss or rs
            alguna = True
            diag.paginas += 1
        except Exception as e:
            error = error or e
    if not alguna:
        raise error

    # Si la página anuncia un RSS, se usa además del HTML
    if rss and rss != url:
        try:
            feed = _parsear_feed(_get(session, rss, f.verificar_ssl, f.tls_antiguo).content) or []
            items += feed
            diag.rss = rss
        except Exception as e:
            log.info("%s: RSS %s no disponible (%s)", f.id, rss, e)
            rss = ""

    # Saltos (hasta 2 niveles) a páginas tipo "sumario", "empleo", o que llevan la fecha de hoy
    if not rss:
        patron = re.compile(f.seguir or (SEGUIR_BOLETIN if f.tipo == "boletin" else SEGUIR_WEB), re.I)
        fechas = _fechas_hoy(hoy)
        dom = _dominio(url)
        vistos = {url}
        frontera = list(items)
        saltos = 0
        for _nivel in range(2):
            candidatos = []
            for it in frontera:
                if it.url in vistos or _dominio(it.url) != dom:
                    continue
                es_pdf = it.url.lower().split("?")[0].endswith(".pdf")
                if es_pdf and not (f.tipo == "boletin" and f.pdf):
                    continue
                con_fecha = any(x in it.url or x in it.texto for x in fechas)
                # los PDF solo si son del día (si no, serían anuncios sueltos o históricos)
                if con_fecha or (not es_pdf and patron.search(it.texto) and len(it.texto) < 120):
                    candidatos.append((0 if con_fecha else 1, it.url))
                    vistos.add(it.url)
            frontera = []
            for _, sig in sorted(candidatos):
                if saltos >= MAX_SALTOS:
                    break
                saltos += 1
                try:
                    r2 = _get(session, sig, f.verificar_ssl, f.tls_antiguo)
                    if _es_pdf(r2) and len(r2.content) > MAX_PDF_BYTES:
                        continue
                    nuevos, _ = _procesar(session, sig, r2, hoy, diag)
                    items += nuevos
                    frontera += nuevos
                    diag.paginas += 1
                except Exception as e:
                    log.info("%s: no se pudo seguir %s (%s)", f.id, sig, e)
            if not frontera:
                break

    diag.enlaces = len(items)
    diag.muestra = [f"{i.texto[:110]} -> {i.url[:90]}" for i in items if not i.nav and len(i.texto) > 30][:12]
    return items, diag


def obtener(f: Fuente, session: requests.Session, hoy: date) -> tuple[list[Item], Diagnostico]:
    items, diag = obtener_crudo(f, session, hoy)
    # Filtro de empleo (los boletines publican de todo)
    filtrados, claves = [], set()
    anio = hoy.year
    excluir = re.compile(f.extra["excluir"], re.I) if f.extra.get("excluir") else None
    for it in items:
        it.texto = _limpio(TAMANO.sub("", it.texto)).strip(" -–·")
        t = it.texto
        if it.clave in claves or t.lower() in claves:
            continue  # mismo anuncio en otro formato (PDF / HTML)
        if it.nav or RUIDO.match(t) or MENU.match(t.strip(" .:")) or NO_EMPLEO.search(t) or TRAMITE.search(t):
            continue
        if excluir and excluir.search(t):
            continue
        if it.url.lower().split("?")[0].endswith(".pdf") and it.desde_pdf and not INICIO_PDF.match(t):
            continue  # frase suelta del interior de un PDF, no una entrada de sumario
        if len(t.split()) <= 8 and not PUESTO.search(t):
            continue  # etiquetas tipo «Convocatoria ordinaria», «Contratación temporal»
        anios = [int(x) for x in re.findall(r"\b(20\d\d)\b", t)]
        if anios and max(anios) <= anio - 2:
            continue  # histórico
        if f.informatica:
            ok = CONVOCATORIA.search(it.texto) or EMPLEO_WEB_EXTRA.search(it.texto)
        else:
            ok = CONVOCATORIA.search(it.texto)
        if ok and len(it.texto) >= 20:
            claves.add(it.clave)
            claves.add(t.lower())
            filtrados.append(it)
    diag.items = len(filtrados)
    if diag.enlaces == 0:
        diag.estado = "vacía"
    return filtrados, diag
