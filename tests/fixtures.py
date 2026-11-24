"""Datos de prueba con la misma forma que la API del BOE (sumario y documentos XML)."""
from xml.sax.saxutils import escape

FECHA = "20261124"

BOE_FIN = ("El plazo de presentación de solicitudes será de veinte días hábiles a contar desde el "
           "siguiente al de la publicación de esta resolución en el «Boletín Oficial del Estado».")

# id -> (departamento, epigrafe|None, titulo, [parrafos])
ITEMS = {
    "BOE-A-2026-9919": ("ADMINISTRACIÓN LOCAL", None,
        "Resolución de 18 de noviembre de 2026, del Ayuntamiento de Segovia, referente a la convocatoria para proveer una plaza.",
        ["En el «Boletín Oficial de Castilla y León» número 75, de 21 de abril de 2026, se han publicado las bases que han de regir la convocatoria para proveer:",
         "Una plaza de Técnico/a Medio de Informática, perteneciente a la escala de Administración Especial, subescala Técnica, clase Media, mediante el sistema de concurso-oposición, en turno libre.",
         BOE_FIN]),
    "BOE-A-2026-0002": ("ADMINISTRACIÓN LOCAL", None,
        "Resolución de 10 de noviembre de 2026, del Ayuntamiento de Elche (Alicante), referente a la convocatoria para proveer una plaza.",
        ["En el «Boletín Oficial de la Provincia de Alicante» número 35, de 20 de octubre de 2026, se han publicado las bases que han de regir la convocatoria para proveer:",
         "Una plaza de Técnico/a Auxiliar de Informática, perteneciente a la escala de Administración Especial, subescala Técnica, clase Auxiliar, por el sistema de oposición, en turno libre.",
         BOE_FIN]),
    "BOE-A-2026-0003": ("ADMINISTRACIÓN LOCAL", None,
        "Resolución de 2 de noviembre de 2026, del Ayuntamiento de Ontinyent (Valencia), referente a la convocatoria para proveer una plaza.",
        ["En el «Boletín Oficial de la Provincia de Valencia» número 88, de 12 de octubre de 2026, se han publicado las bases que han de regir la convocatoria para proveer:",
         "Una plaza de Técnico/a Superior de Informática, perteneciente a la escala de Administración Especial, subescala Técnica y clase Superior, por el sistema de concurso-oposición, en turno de promoción interna.",
         BOE_FIN]),
    "BOE-A-2026-0004": ("ADMINISTRACIÓN LOCAL", None,
        "Resolución de 12 de noviembre de 2026, del Ayuntamiento de Gijón/Xixón (Asturias), referente a la convocatoria para proveer varias plazas.",
        ["En el «Boletín Oficial del Principado de Asturias» número 210, de 30 de octubre de 2026, se han publicado las bases que han de regir la convocatoria para proveer:",
         "Una plaza de Técnico/a de Administración General, perteneciente a la escala de Administración General, subescala Técnica, por el sistema de oposición, en turno libre.",
         "Una plaza de Arquitecto/a, perteneciente a la escala de Administración Especial, subescala Técnica, clase Superior, por el sistema de concurso-oposición, en turno libre.",
         "Dos plazas de Auxiliar Administrativo, pertenecientes a la escala de Administración General, subescala Auxiliar, por el sistema de oposición, en turno libre.",
         BOE_FIN]),
    "BOE-A-2026-0005": ("ADMINISTRACIÓN LOCAL", None,
        "Resolución de 5 de noviembre de 2026, del Ayuntamiento de Torrelavega (Cantabria), referente a la convocatoria para proveer cuatro plazas.",
        ["En el «Boletín Oficial de Cantabria» número 200, de 15 de octubre de 2026, se han publicado las bases que han de regir la convocatoria para proveer:",
         "Cuatro plazas de Agente de Policía Local, pertenecientes a la escala de Administración Especial, subescala de Servicios Especiales, por el sistema de oposición, en turno libre.",
         BOE_FIN]),
    "BOE-A-2026-0006": ("UNIVERSIDADES", None,
        "Resolución de 9 de noviembre de 2026, de la Universidad de Oviedo, por la que se convoca concurso de acceso a plazas de cuerpos docentes universitarios.",
        ["De conformidad con lo dispuesto..."]),
    "BOE-A-2026-0007": ("MINISTERIO PARA LA TRANSFORMACIÓN DIGITAL Y DE LA FUNCIÓN PÚBLICA", "Cuerpo de Gestión de Sistemas e Informática",
        "Resolución de 17 de noviembre de 2026, de la Subsecretaría, por la que se convocan procesos selectivos para ingreso, por el sistema general de acceso libre, en el Cuerpo de Gestión de Sistemas e Informática de la Administración del Estado.",
        ["En cumplimiento de lo dispuesto en el Real Decreto de oferta de empleo público...",
         "Las solicitudes se presentarán en el plazo de veinte días hábiles contados a partir del día siguiente al de la fecha de publicación de esta convocatoria en el «Boletín Oficial del Estado»."]),
    "BOE-A-2026-0008": ("COMUNIDAD DE CASTILLA Y LEÓN", None,
        "Orden de 3 de noviembre de 2026, de la Consejería de la Presidencia, por la que se convoca proceso selectivo para el ingreso, por el sistema de acceso libre, en el Cuerpo Administrativo de la Administración de la Comunidad de Castilla y León.",
        ["De acuerdo con el Decreto de oferta de empleo público..."]),
    "BOE-A-2026-0009": ("ADMINISTRACIÓN LOCAL", None,
        "Resolución de 4 de noviembre de 2026, del Ayuntamiento de Santander, por la que se aprueba la lista provisional de admitidos y excluidos.",
        ["..."]),
    "BOE-A-2026-0010": ("COMUNIDAD AUTÓNOMA DEL PRINCIPADO DE ASTURIAS", None,
        "Resolución de 1 de noviembre de 2026, de la Consejería de Hacienda, por la que se convoca la provisión, por el sistema de libre designación, del puesto de Jefe de Servicio de Informática.",
        ["..."]),
    "BOE-A-2026-0011": ("ADMINISTRACIÓN LOCAL", None,
        "Resolución de 6 de noviembre de 2026, del Ayuntamiento de Getafe (Madrid), referente a la convocatoria para proveer una plaza.",
        ["En el «Boletín Oficial de la Comunidad de Madrid» número 250, de 20 de octubre de 2026, se han publicado las bases que han de regir la convocatoria para proveer:",
         "Una plaza de Técnico/a de Administración General, perteneciente a la escala de Administración General, subescala Técnica, por el sistema de oposición, en turno libre.",
         BOE_FIN]),
    "BOE-A-2026-0012": ("ADMINISTRACIÓN LOCAL", None,
        "Resolución de 7 de noviembre de 2026, del Ayuntamiento de León, referente a la convocatoria para proveer dos plazas.",
        ["En el «Boletín Oficial de la Provincia de León» número 190, de 2 de octubre de 2026, se han publicado las bases que han de regir la convocatoria para proveer:",
         "Dos plazas de Agente de Movilidad, pertenecientes a la escala de Administración Especial, por el sistema de oposición, en turno libre.",
         BOE_FIN]),
}


def _item(ident, titulo):
    return (f"<item><identificador>{ident}</identificador><titulo>{escape(titulo)}</titulo>"
            f'<url_pdf szBytes="1" szKBytes="1">https://www.boe.es/boe/dias/2026/11/24/pdfs/{ident}.pdf</url_pdf>'
            f"<url_html>https://www.boe.es/diario_boe/txt.php?id={ident}</url_html>"
            f"<url_xml>https://www.boe.es/diario_boe/xml.php?id={ident}</url_xml></item>")


def sumario_xml() -> bytes:
    deps: dict[str, list[str]] = {}
    for ident, (dep, epi, titulo, _) in ITEMS.items():
        xml = _item(ident, titulo)
        if epi:
            xml = f'<epigrafe nombre="{escape(epi)}">{xml}</epigrafe>'
        deps.setdefault(dep, []).append(xml)
    cuerpo = "".join(
        f'<departamento codigo="{i}" nombre="{escape(d)}">{"".join(x)}</departamento>'
        for i, (d, x) in enumerate(deps.items())
    )
    otra = ('<seccion codigo="2A" nombre="II. Autoridades y personal. - A. Nombramientos">'
            '<departamento codigo="1" nombre="UNIVERSIDADES">'
            + _item("BOE-A-2026-9999", "Resolución por la que se nombra Profesor Titular de Universidad")
            + "</departamento></seccion>")
    return (f'<?xml version="1.0" encoding="utf-8"?><response><status><code>200</code><text>Ok</text></status>'
            f'<data><sumario><metadatos><publicacion>BOE</publicacion><fecha_publicacion>{FECHA}</fecha_publicacion></metadatos>'
            f'<diario numero="284">{otra}<seccion codigo="2B" nombre="II. Autoridades y personal. - B. Oposiciones y concursos">'
            f"{cuerpo}</seccion></diario></sumario></data></response>").encode()


def documento_xml(ident: str) -> bytes:
    dep, _, titulo, parrafos = ITEMS[ident]
    ps = "".join(f'<p class="parrafo">{escape(p)}</p>' for p in parrafos)
    return (f'<?xml version="1.0" encoding="utf-8"?><documento><metadatos><identificador>{ident}</identificador>'
            f"<departamento>{escape(dep)}</departamento><titulo>{escape(titulo)}</titulo></metadatos>"
            f"<analisis/><texto>{ps}</texto></documento>").encode()


class FakeResp:
    def __init__(self, content: bytes, status: int = 200):
        self.content, self.status_code = content, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeSession:
    def get(self, url, headers=None, timeout=None):
        if "/sumario/" in url:
            return FakeResp(sumario_xml()) if url.endswith(FECHA) else FakeResp(b"", 404)
        ident = url.split("id=")[-1]
        return FakeResp(documento_xml(ident))
