"""Decide qué convocatorias te interesan.

Reglas:
  * En Asturias, Castilla y León y Cantabria: cualquier plaza de acceso libre a la que
    puedas presentarte con tu titulación (grado + máster), de cualquier organismo.
  * En el resto de España: solo plazas de informática.
  * Se descartan anuncios que no abren plazo (listas, tribunales, nombramientos...),
    promoción interna, provisión de puestos entre funcionarios y plazas docentes
    universitarias (exigen doctorado).
"""
import re
import unicodedata
from datetime import date, timedelta

from . import config
from .modelo import Convocatoria, Resultado


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.replace("«", '"').replace("»", '"')


def _rx(patron: str) -> re.Pattern:
    return re.compile(patron)


# --- ¿Es una convocatoria nueva? ------------------------------------------------
NO_NUEVA = _rx(
    r"libre designacion|concurso de traslados|provision de puestos|concurso especifico"
    r"|concurso general de meritos|concurso de meritos|turno de movilidad|concurso de movilidad"
    r"|movilidad interadministrativa|admitid|excluid"
    r"|relacion de aprobados|lista de aprobados|aspirantes aprobados|se nombra|nombramiento"
    r"|tribunal|calificador|correccion de errores|se corrigen|se modifica|desiert"
    r"|lista (provisional|definitiva)|lista de (admitidos|excluidos|aspirantes|aprobados|seleccionados)"
    r"|relacion definitiva|relacion provisional|fecha de celebracion|lugar de celebracion"
    r"|cuerpos docentes universitarios|profesor[a]? (titular|contratad|ayudante|asociad|visitante)"
    r"|catedratic|personal docente e investigador|ayudante doctor|personal investigador"
    r"|se adjudica|adjudicacion|cese|jubilacion|convocatorias? cerrad|proceso finalizado|finalizad[oa]s?$"
)
ES_CONVOCATORIA = _rx(r"convoca|convocatoria|proceso selectivo|pruebas selectivas|bolsa|proveer|seleccion")
SOLO_PROMOCION = _rx(r"promocion interna")
DOCENTE = _rx(r"profesor|profesorado|cuerpo de maestros|ensenanza secundaria")
PLAZA_EXCLUIR = _rx(r"turno de movilidad|por movilidad|movilidad interadministrativa")
LIBRE = _rx(r"turno libre|acceso libre|turno de acceso libre|sistema general de acceso libre|libre concurrencia")

# --- Regiones ------------------------------------------------------------------------
PROV_CYL = "avila|burgos|leon|palencia|salamanca|segovia|soria|valladolid|zamora"
REGION_PATRONES = {
    "Asturias": _rx(
        r"asturias|ayuntamiento de (oviedo|gijon|aviles)\b|universidad de oviedo"
    ),
    "Castilla y León": _rx(
        rf"castilla y leon|\(({PROV_CYL})\)|ayuntamiento de ({PROV_CYL})\b"
        rf"|diputacion provincial de ({PROV_CYL})\b|universidad (pontificia )?de ({PROV_CYL})\b"
        rf"|provincia de ({PROV_CYL})\b"
    ),
    "Cantabria": _rx(r"cantabria|ayuntamiento de santander\b|universidad de cantabria"),
}

# --- Informática --------------------------------------------------------------------
INFORMATICA = _rx(
    r"informatic|tecnologias? de la informacion|\btic\b|sistemas de informacion|sistemas informaticos"
    r"|sistemas y tecnologias|telecomunicaci|programador|analista|ciberseguridad"
    r"|seguridad de la informacion|seguridad informatica|transformacion digital"
    r"|desarrollo de aplicaciones|administrador de (sistemas|redes|bases de datos)|bases de datos"
    r"|redes informaticas|ciencia de datos|cientific[oa] de datos|inteligencia artificial"
    r"|tecnic[oa] de sistemas|microinformatica|digitalizacion|administracion electronica"
    r"|\bsti\b|\bstic\b|\btgm\b.{0,20}sistemas|sistemas y aplicaciones"
)

# --- Titulación -----------------------------------------------------------------------
# Plazas que exigen una titulación concreta que no tienes.
TITULACION_ESPECIFICA = _rx(
    r"arquitect|aparejador|ingenier[oa]s? (de caminos|industrial|agronom|de montes|de minas|quimic)"
    r"|ingenier[oa]s? tecnic[oa]s? (industrial|agricola|de obras|forestal|de minas)|obras publicas"
    r"|medic[oa]|enfermer|fisioterapeut|psicolog|trabajador[a]? social|trabajo social"
    r"|educador[a]? social|educador[a]? infantil|educacion infantil|escuela infantil|maestr[oa]"
    r"|veterinari|farmaceutic|biolog|quimic[oa]|geolog|logoped|terapeuta ocupacional|odontolog"
    r"|matron|auxiliar de enfermeria|\btcae\b|cuidados auxiliares|letrad[oa]|asesor[a]? juridic"
    r"|licenciad[oa] en derecho|grado en derecho|delineante|topograf|tecnic[oa] de laboratorio"
    r"|guarda forestal|agente medioambiental|agente forestal|celador forestal|socorrista"
    r"|tecnic[oa] en emergencias sanitarias|facultativ[oa]|radiodiagnostico|anestesi"
)
# Requisitos extra (carnés, pruebas físicas) o titulación que conviene mirar.
REVISAR_EXTRA = _rx(r"policia|bombero|agente de movilidad|conductor|periodist|economista|ingenier")
# Plazas genéricas: valen con cualquier grado o con titulación inferior.
GENERICAS = _rx(
    r"administracion general|tecnic[oa] de gestion|gestion administrativa|gestion economica"
    r"|administrativ|subalterno|ordenanza|conserje|archiv|bibliotec|agente de desarrollo local"
    r"|tecnic[oa] de (empleo|desarrollo local|juventud|turismo|cultura|deportes|igualdad|participacion)"
    r"|cuerpo (superior|de gestion|administrativo|auxiliar) de (la )?administracion"
    r"|escala (de gestion|administrativa|auxiliar)|gestion universitaria|tecnic[oa] de administracion"
)
AFIN = _rx(
    r"audiovisual|multimedia|diseno grafico|\bcomunicacion\b|fotograf|\bvideo|\bweb\b"
    r"|contenidos digitales|redes sociales|community|prensa"
)

# --- Grupo ------------------------------------------------------------------------------
T = r"tecnic[oa](?:s|/a|/o|\([oa]\)|/tecnica)?"  # Técnico, Técnico/a, Técnico/Técnica...
GRUPO_PATRONES = [
    (r"subgrupo\s+(a1|a2|c1|c2)\b", None),
    (r"grupo\s+(a1|a2|c1|c2)\b", None),
    (r"grupo\s+([abe])\b", None),
    (r"agrupaciones? profesionales?|subescala subalterna|\bsubalterno|ordenanza|conserje|\bpeon", "AP"),
    (rf"administracion general,? subescala tecnica|clase superior|{T}\s+superior|cuerpo superior"
     r"|titulad[oa](?:/a)? superior"
     r"|escala superior|cuerpo de tecnicos superiores", "A1"),
    (rf"subescala de gestion|subescala gestion|clase media|{T}\s+medi[oa]|{T}\s+de gestion"
     r"|cuerpo de gestion|escala de gestion|ingenier[oa] tecnic|titulad[oa](?:/a)? medi[oa]|\btgm\b"
     r"|gestion universitaria|tecnicos medios", "A2"),
    (rf"subescala administrativa|clase auxiliar|{T}\s+auxiliar|{T}\s+especialista|cuerpo administrativo"
     r"|escala administrativa|policia local|agente de policia", "C1"),
    (r"subescala auxiliar|auxiliar administrativ|cuerpo auxiliar|escala auxiliar", "C2"),
]
GRUPO_PATRONES = [(re.compile(p), g) for p, g in GRUPO_PATRONES]

NUMEROS = {
    "uno": 1, "un": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
    "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14,
    "quince": 15, "dieciseis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19,
    "veinte": 20, "veintiun": 21, "veintiuno": 21, "veinticinco": 25, "treinta": 30,
    "cuarenta": 40, "cuarenta y cinco": 45, "sesenta": 60,
}
PLAZA_INICIO = re.compile(
    r"^(una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|\d+)\s+plazas?\s+de\b"
)


def detectar_region(c: Convocatoria) -> str | None:
    """Por departamento (comunidad autónoma), título o boletín donde se publicaron las bases."""
    candidatos = [norm(c.departamento), norm(c.titulo)] + [norm(p) for p in c.parrafos[:3]]
    for texto in candidatos:
        for region, rx in REGION_PATRONES.items():
            if region in config.REGIONES and rx.search(texto):
                return region
    return None


def detectar_grupos(texto_norm: str) -> list[str]:
    encontrados: list[str] = []
    for rx, grupo in GRUPO_PATRONES:
        for m in rx.finditer(texto_norm):
            g = (grupo or m.group(1)).upper()
            if g not in encontrados:
                encontrados.append(g)
        if encontrados and grupo is None:
            break  # un grupo explícito manda sobre las deducciones
    return encontrados


def evaluar_titulacion(texto_norm: str, grupos: list[str], informatica: bool) -> tuple[str, str]:
    if DOCENTE.search(texto_norm):
        return "no", "Plaza docente (exige Máster de Profesorado)"
    if TITULACION_ESPECIFICA.search(texto_norm) and not informatica:
        return "no", "Exige una titulación específica"
    if REVISAR_EXTRA.search(texto_norm) and not informatica:
        return "revisar", "Puede tener requisitos extra (carnés, pruebas físicas o titulación concreta)"
    superiores = {"A1", "A2"} & set(grupos)
    if informatica:
        if superiores:
            return "revisar", "Comprueba en las bases si aceptan tu máster/grado o piden Ingeniería Informática"
        if grupos:
            return "ok", "Tu titulación supera la exigida"
        return "revisar", "No se indica el grupo: revisa la titulación en las bases"
    if grupos and not superiores:
        return "ok", "Tu titulación supera la exigida"
    if superiores and GENERICAS.search(texto_norm):
        return "ok", "Plaza genérica: suele valer cualquier grado"
    if superiores:
        return "revisar", "Puede exigir un grado concreto: revisa las bases"
    if GENERICAS.search(texto_norm):
        return "ok", "Plaza genérica"
    return "revisar", "No se indica el grupo: revisa la titulación en las bases"


def _a_numero(palabra: str) -> int | None:
    palabra = palabra.strip()
    if palabra.isdigit():
        return int(palabra)
    return NUMEROS.get(palabra)


def _pascua(anio: int) -> date:
    a, b, c = anio % 19, anio // 100, anio % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return date(anio, mes, dia)


def _festivo_nacional(d: date) -> bool:
    fijos = {(1, 1), (1, 6), (5, 1), (8, 15), (10, 12), (11, 1), (12, 6), (12, 8), (12, 25)}
    return (d.month, d.day) in fijos or d == _pascua(d.year) - timedelta(days=2)


def sumar_dias(inicio: date, n: int, habiles: bool) -> date:
    """Cuenta desde el día siguiente a la publicación. Hábiles: sin sábados, domingos ni festivos nacionales."""
    d = inicio
    contados = 0
    while contados < n:
        d += timedelta(days=1)
        if habiles and (d.weekday() >= 5 or _festivo_nacional(d)):
            continue
        contados += 1
    # Si un plazo en días naturales acaba en inhábil, pasa al siguiente hábil
    while not habiles and (d.weekday() >= 5 or _festivo_nacional(d)):
        d += timedelta(days=1)
    return d


PLAZO_PATRONES = [
    re.compile(
        r"plazo de presentacion de (?:las )?(?:solicitudes|instancias)[^.]{0,40}?(?:sera de|de)\s+"
        r"([a-z0-9]+(?: y [a-z]+)?)\s+dias (habiles|naturales)(.{0,220})"
    ),
    re.compile(r"en el plazo de\s+([a-z0-9]+(?: y [a-z]+)?)\s+dias (habiles|naturales)(.{0,220})"),
]


def detectar_plazo(texto_norm: str, publicacion: date) -> tuple[str, date | None]:
    for rx in PLAZO_PATRONES:
        m = rx.search(texto_norm)
        if not m:
            continue
        n = _a_numero(m.group(1))
        if not n:
            continue
        tipo = m.group(2)
        texto = f"{n} días {'hábiles' if tipo == 'habiles' else 'naturales'}"
        if "boletin oficial del estado" in m.group(3):
            return texto, sumar_dias(publicacion, n, tipo == "habiles")
        return texto + " desde la publicación en otro boletín (mira las bases)", None
    return "", None


def detectar_bases(texto: str) -> str:
    m = re.search(r"En el «([^»]+)»(?:,)?(?: núm(?:ero|\.)\s*(\d+))?,? de (\d{1,2} de \w+ de \d{4})", texto)
    if not m:
        return ""
    nombre, num, fecha = m.groups()
    return f"{nombre}{f' nº {num}' if num else ''} ({fecha})"


MINUSCULAS = {"de", "del", "la", "las", "el", "los", "y", "e", "para", "en", "a"}


def bonito(s: str) -> str:
    """MINISTERIO PARA LA TRANSFORMACIÓN DIGITAL -> Ministerio para la Transformación Digital"""
    palabras = s.lower().split()
    return " ".join(p if (i and p in MINUSCULAS) else p.capitalize() for i, p in enumerate(palabras))


def detectar_organismo(c: Convocatoria) -> str:
    m = re.search(
        r"\b(?:del|de la|de los|de las)\s+((?:Ayuntamiento|Diputación|Universidad|Consell|Cabildo|Mancomunidad"
        r"|Consorcio|Comarca|Entidad|Instituto|Agencia|Servicio|Consejería|Fundación|Patronato"
        r"|Organismo|Junta|Gerencia|Dirección General|Subsecretaría|Secretaría)[^,]*)",
        c.titulo,
    )
    dep = bonito(c.departamento)
    if not m:
        return dep
    org = m.group(1).strip().rstrip(".")
    if c.departamento.upper().startswith(("MINISTERIO", "COMUNIDAD")) and dep.lower() not in org.lower():
        return f"{dep} · {org}"
    return org


def detectar_sistema(texto_norm: str) -> str:
    if "concurso-oposicion" in texto_norm or "concurso oposicion" in texto_norm:
        return "Concurso-oposición"
    if "oposicion" in texto_norm:
        return "Oposición"
    if "bolsa" in texto_norm:
        return "Bolsa de empleo"
    if "concurso" in texto_norm:
        return "Concurso"
    return ""


def _limpiar_plaza(p: str) -> str:
    corte = re.split(r",\s*(?:perteneciente|de la plantilla|encuadrada|incluida|por el sistema)", p, maxsplit=1)[0]
    return corte.rstrip(".:;")


AUTO = object()


def clasificar(c: Convocatoria, region=AUTO, exigir_convocatoria: bool = True,
               todo_informatica: bool = False) -> Resultado:
    """region: AUTO = deducirla del texto; un nombre = la fuente es de esa región;
    None = fuente de fuera de tus regiones (solo informática)."""
    titulo_n = norm(c.titulo)

    if NO_NUEVA.search(titulo_n):
        return Resultado(False, "no abre plazo o no es acceso libre")
    if exigir_convocatoria and not ES_CONVOCATORIA.search(titulo_n):
        return Resultado(False, "no es una convocatoria")
    if SOLO_PROMOCION.search(titulo_n) and not LIBRE.search(titulo_n):
        return Resultado(False, "promoción interna")

    if region is AUTO:
        region = detectar_region(c)
    elif region is None:
        region = detectar_region(c)  # un boletín de fuera puede publicar algo de tus regiones
    elif region not in config.REGIONES:
        region = None

    # Modo extracto (típico de Administración Local): un párrafo por plaza
    plazas_parr = [p for p in c.parrafos if PLAZA_INICIO.match(norm(p))]
    if plazas_parr:
        bloques = [(p, norm(p)) for p in plazas_parr]
    else:
        # Convocatorias completas (Estado, CCAA, universidades): título + inicio del texto
        cabeza = " ".join([c.titulo] + c.parrafos[:4])
        bloques = [(c.titulo, norm(cabeza))]

    elegidas: list[tuple[str, list[str], str, str, bool]] = []
    descartes: list[str] = []
    for original, n in bloques:
        if SOLO_PROMOCION.search(n) and not LIBRE.search(n):
            descartes.append("promoción interna")
            continue
        if PLAZA_EXCLUIR.search(n):
            descartes.append("movilidad")
            continue
        es_info = bool(todo_informatica or INFORMATICA.search(n) or (not plazas_parr and INFORMATICA.search(titulo_n)))
        grupos = detectar_grupos(n)
        tit, nota = evaluar_titulacion(n, grupos, es_info)
        if tit == "no":
            descartes.append(nota.lower())
            continue
        if region:
            if config.GRUPOS_REGION is not None and not es_info:
                if grupos and not set(grupos) & set(config.GRUPOS_REGION):
                    descartes.append("grupo fuera de tu filtro")
                    continue
                if not grupos and not config.INCLUIR_GRUPO_DESCONOCIDO:
                    descartes.append("grupo desconocido")
                    continue
        elif not es_info:
            descartes.append("no es de informática")
            continue
        elegidas.append((original, grupos, tit, nota, es_info))

    if not elegidas:
        motivo = ", ".join(dict.fromkeys(descartes)) or "sin plazas que encajen"
        return Resultado(False, motivo, region=region)

    texto_n = norm(c.texto) or titulo_n
    grupos_tot: list[str] = []
    for _, gs, *_ in elegidas:
        grupos_tot += [g for g in gs if g not in grupos_tot]
    # La etiqueta global es la mejor de las plazas elegidas
    orden = {"ok": 0, "revisar": 1}
    mejor = min(elegidas, key=lambda e: orden[e[2]])
    plazo_txt, plazo_fin = detectar_plazo(texto_n, c.fecha)
    elegidas_n = " ".join(norm(e[0]) for e in elegidas)
    informatica = any(e[4] for e in elegidas)

    return Resultado(
        enviar=True,
        motivo="region" if region else "informatica",
        ambito="region" if region else "informatica",
        region=region,
        informatica=informatica,
        plazas=[_limpiar_plaza(e[0]) for e in elegidas] if plazas_parr else [],
        grupos=grupos_tot,
        titulacion=mejor[2],
        nota_titulacion=mejor[3],
        afin=bool(AFIN.search(" ".join(norm(e[0]) for e in elegidas))),
        sistema=detectar_sistema(elegidas_n if plazas_parr else texto_n),
        turno="Libre" if LIBRE.search(elegidas_n if plazas_parr else texto_n) else "",
        organismo=detectar_organismo(c),
        plazo_texto=plazo_txt,
        plazo_fin=plazo_fin,
        bases=detectar_bases(c.texto),
    )
