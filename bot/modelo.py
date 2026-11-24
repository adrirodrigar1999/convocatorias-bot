from dataclasses import dataclass, field
from datetime import date


@dataclass
class Convocatoria:
    """Un anuncio publicado en un boletín. Todas las fuentes devuelven esto."""
    id: str                 # identificador único (p. ej. BOE-A-2026-9919)
    fuente: str             # "BOE", más adelante "BOPA", "BOCYL", "BOC"...
    fecha: date             # fecha de publicación
    departamento: str       # agrupación del sumario (ADMINISTRACIÓN LOCAL, UNIVERSIDADES...)
    titulo: str
    url: str                # enlace para el aviso (versión HTML)
    url_pdf: str = ""
    url_xml: str = ""
    parrafos: list[str] = field(default_factory=list)  # texto completo, por párrafos

    @property
    def texto(self) -> str:
        return "\n".join(self.parrafos)


@dataclass
class Resultado:
    enviar: bool
    motivo: str                       # por qué se descarta o se envía
    ambito: str = ""                  # "informatica" | "region"
    region: str | None = None
    informatica: bool = False
    plazas: list[str] = field(default_factory=list)
    grupos: list[str] = field(default_factory=list)
    titulacion: str = ""              # "ok" | "revisar" | "no"
    nota_titulacion: str = ""
    afin: bool = False                # afín a tu grado en Multimedia
    sistema: str = ""
    turno: str = ""
    organismo: str = ""
    plazo_texto: str = ""
    plazo_fin: date | None = None
    bases: str = ""
