from datetime import date

import pytest

from bot import clasificador, telegram
from bot.fuentes import boe

from .fixtures import FakeSession

FECHA = date(2026, 11, 24)


@pytest.fixture(scope="module")
def resultados(monkeypatch_module):
    monkeypatch_module.setattr(boe, "PAUSA_ENTRE_PETICIONES", 0)
    convocatorias = boe.obtener(FECHA, FakeSession())
    return {c.id: (c, clasificador.clasificar(c)) for c in convocatorias}


@pytest.fixture(scope="module")
def monkeypatch_module():
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()


def test_solo_seccion_2B(resultados):
    assert "BOE-A-2026-9999" not in resultados
    assert len(resultados) == 12


def test_items_bajo_epigrafe(resultados):
    assert "BOE-A-2026-0007" in resultados


ESPERADO = {
    "BOE-A-2026-9919": True,   # Segovia, informática, CyL
    "BOE-A-2026-0002": True,   # Elche, informática, resto de España
    "BOE-A-2026-0003": False,  # promoción interna
    "BOE-A-2026-0004": True,   # Gijón, TAG + auxiliar (arquitecto fuera)
    "BOE-A-2026-0005": True,   # Torrelavega, policía local (revisar)
    "BOE-A-2026-0006": False,  # docentes universitarios
    "BOE-A-2026-0007": True,   # Estado, Cuerpo de Gestión de Sistemas e Informática
    "BOE-A-2026-0008": True,   # Junta CyL, Cuerpo Administrativo
    "BOE-A-2026-0009": False,  # lista de admitidos
    "BOE-A-2026-0010": False,  # libre designación
    "BOE-A-2026-0011": False,  # Getafe TAG: ni informática ni región
    "BOE-A-2026-0012": True,   # León, agente de movilidad
}


@pytest.mark.parametrize("ident,enviar", ESPERADO.items())
def test_decision(resultados, ident, enviar):
    c, r = resultados[ident]
    assert r.enviar is enviar, f"{ident}: {r.motivo}"


def test_detalle_segovia(resultados):
    _, r = resultados["BOE-A-2026-9919"]
    assert r.region == "Castilla y León" and r.informatica
    assert r.grupos == ["A2"]
    assert r.titulacion == "revisar"
    assert r.sistema == "Concurso-oposición"
    assert r.plazo_fin == date(2026, 12, 23)  # 20 hábiles (8/12 es festivo)
    assert r.bases.startswith("Boletín Oficial de Castilla y León nº 75")


def test_gijon_quita_arquitecto(resultados):
    _, r = resultados["BOE-A-2026-0004"]
    assert r.region == "Asturias"
    assert len(r.plazas) == 2
    assert not any("Arquitect" in p for p in r.plazas)
    assert r.titulacion == "ok"
    assert set(r.grupos) == {"A1", "C2"}


def test_elche_espana(resultados):
    _, r = resultados["BOE-A-2026-0002"]
    assert r.region is None and r.ambito == "informatica"
    assert r.grupos == ["C1"] and r.titulacion == "ok"


def test_estado_titulo(resultados):
    _, r = resultados["BOE-A-2026-0007"]
    assert r.informatica and r.grupos == ["A2"]
    assert r.plazo_fin is not None
    assert r.organismo.startswith("Ministerio para la Transformación Digital")


def test_mensaje(resultados):
    c, r = resultados["BOE-A-2026-0004"]
    texto = telegram.formatear(c, r)
    assert "📍 Asturias" in texto and "txt.php?id=BOE-A-2026-0004" in texto


def test_sin_boletin():
    with pytest.raises(boe.SinBoletin):
        boe.obtener(date(2026, 11, 22), FakeSession())


def test_plazo_naturales_acaba_en_habil():
    # 30 naturales desde viernes 30/10/2026 -> domingo 29/11 -> lunes 30/11
    assert clasificador.sumar_dias(date(2026, 10, 30), 30, habiles=False) == date(2026, 11, 30)


def test_sistema_solo_de_plazas_elegidas(resultados):
    _, r = resultados["BOE-A-2026-0004"]
    assert r.sistema == "Oposición"


def test_motivo_promocion(resultados):
    _, r = resultados["BOE-A-2026-0003"]
    assert r.motivo == "promoción interna"


BOE_FIN = ("El plazo de presentación de solicitudes será de veinte días hábiles a contar desde el "
           "siguiente al de la publicación de esta resolución en el «Boletín Oficial del Estado».")


def _local(nombre, fecha=FECHA):
    from bot.modelo import Convocatoria
    return Convocatoria(
        "X", "BOE", fecha, "ADMINISTRACIÓN LOCAL",
        "Resolución de 10 de noviembre de 2026, del Ayuntamiento de Elche (Alicante), referente a la convocatoria para proveer una plaza.",
        "u", parrafos=[
            "En el «Boletín Oficial de la Provincia de Alicante» número 35, de 20 de octubre de 2026, se han publicado las bases que han de regir la convocatoria para proveer:",
            f"Una plaza de {nombre}, por el sistema de oposición, en turno libre.", BOE_FIN])


def _estado(nombre):
    from bot.modelo import Convocatoria
    return Convocatoria(
        "Y", "BOE", FECHA, "MINISTERIO X",
        f"Resolución de 17 de noviembre de 2026, de la Subsecretaría, por la que se convoca proceso selectivo para ingreso, por el sistema general de acceso libre, en {nombre}.",
        "u", parrafos=["..."])


NOMBRES = [l for l in (__import__("pathlib").Path(__file__).parent / "nombres_informatica.txt").read_text().splitlines() if l]


@pytest.mark.parametrize("nombre", NOMBRES)
def test_puestos_informatica_reales(nombre):
    for c in (_local(nombre), _estado(nombre)):
        r = clasificador.clasificar(c)
        assert r.enviar and r.informatica, f"{nombre}: {r.motivo}"


def test_docentes_fuera_aunque_sean_de_informatica():
    from bot.modelo import Convocatoria
    c = Convocatoria("Z", "BOE", FECHA, "COMUNIDAD DE MADRID",
                     "Orden por la que se convoca procedimiento selectivo de ingreso en el Cuerpo de Profesores de Enseñanza Secundaria, especialidad Informática.",
                     "u", parrafos=["Especialidad: Sistemas y Aplicaciones Informáticas. 12 plazas."])
    r = clasificador.clasificar(c)
    assert not r.enviar and "docente" in r.motivo
    assert not clasificador.clasificar(_local("Profesorado de FP: Sistemas y Aplicaciones Informáticas")).enviar


def test_docentes_sin_informatica_fuera():
    from bot.modelo import Convocatoria
    c = Convocatoria("Z", "BOE", FECHA, "COMUNIDAD DE MADRID",
                     "Orden por la que se convoca procedimiento selectivo de ingreso en el Cuerpo de Maestros.",
                     "u", parrafos=["Especialidad: Educación Física."])
    assert not clasificador.clasificar(c).enviar


def test_grupos_nuevos():
    assert clasificador.detectar_grupos("tecnico/a titulado/a medio en informatica") == ["A2"]
    assert clasificador.detectar_grupos("gestion universitaria, especialidad informatica") == ["A2"]


def test_titulacion_especifica_con_barra():
    from bot.modelo import Convocatoria
    c = Convocatoria("T", "BOE", FECHA, "ADMINISTRACIÓN LOCAL",
                     "Resolución del Ayuntamiento de Las Regueras (Asturias), referente a la convocatoria para proveer una plaza.",
                     "u", parrafos=["Una plaza de Trabajador/a Social de la plantilla de personal laboral fijo, por el sistema de oposición, en turno libre."])
    assert not clasificador.clasificar(c).enviar
