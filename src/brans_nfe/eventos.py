from __future__ import annotations

from datetime import datetime, timedelta, timezone

from lxml import etree

from .enums import Ambiente, CodigoEventoNfse, MotivoCancelamento
from .exceptions import ValidacaoDpsError
from .signer import NAMESPACE_DPS

_JUST_MAP = {
    MotivoCancelamento.ERRO_EMISSAO: "1",
    MotivoCancelamento.SERVICO_NAO_PRESTADO: "2",
    MotivoCancelamento.OUTROS: "9",
}


def construir_cancelamento(
    chave_acesso: str,
    motivo: str,
    cnpj_autor: str,
    ambiente: Ambiente,
    motivo_codigo: MotivoCancelamento = MotivoCancelamento.OUTROS,
    versao_aplicativo: str = "brans-nfe-0.1.0",
) -> etree._Element:
    _validar_chave(chave_acesso)
    _validar_motivo(motivo)
    cnpj_digits = _digits(cnpj_autor)
    if len(cnpj_digits) != 14:
        raise ValidacaoDpsError("CNPJ do autor do evento deve ter 14 digitos.")

    tp_amb = "1" if ambiente == Ambiente.PRODUCAO else "2"
    id_pre = gerar_id_pre(chave_acesso, CodigoEventoNfse.CANCELAMENTO)

    nsmap = {None: NAMESPACE_DPS}
    evento = etree.Element(
        f"{{{NAMESPACE_DPS}}}pedRegEvento", nsmap=nsmap, attrib={"versao": "1.01"}
    )
    inf = etree.SubElement(evento, f"{{{NAMESPACE_DPS}}}infPedReg", attrib={"Id": id_pre})
    etree.SubElement(inf, f"{{{NAMESPACE_DPS}}}tpAmb").text = tp_amb
    etree.SubElement(inf, f"{{{NAMESPACE_DPS}}}verAplic").text = versao_aplicativo
    etree.SubElement(inf, f"{{{NAMESPACE_DPS}}}dhEvento").text = _agora_brt_iso()
    etree.SubElement(inf, f"{{{NAMESPACE_DPS}}}CNPJAutor").text = cnpj_digits
    etree.SubElement(inf, f"{{{NAMESPACE_DPS}}}chNFSe").text = chave_acesso
    e101101 = etree.SubElement(inf, f"{{{NAMESPACE_DPS}}}e101101")
    etree.SubElement(e101101, f"{{{NAMESPACE_DPS}}}xDesc").text = "Cancelamento de NFS-e"
    etree.SubElement(e101101, f"{{{NAMESPACE_DPS}}}cMotivo").text = _JUST_MAP[motivo_codigo]
    etree.SubElement(e101101, f"{{{NAMESPACE_DPS}}}xMotivo").text = motivo

    return evento


def serializar_evento(evento: etree._Element) -> bytes:
    return etree.tostring(evento, xml_declaration=True, encoding="UTF-8", standalone=True)


def gerar_id_pre(chave_acesso: str, codigo_evento: CodigoEventoNfse) -> str:
    if len(chave_acesso) != 50:
        raise ValidacaoDpsError("Chave de acesso da NFS-e deve ter 50 caracteres.")
    return f"PRE{chave_acesso}{codigo_evento.value}"


def _agora_brt_iso() -> str:
    agora = datetime.now(timezone(timedelta(hours=-3))) - timedelta(minutes=1)
    return agora.strftime("%Y-%m-%dT%H:%M:%S-03:00")


def _validar_chave(chave: str) -> None:
    if not chave or len(chave) != 50 or not chave.isdigit():
        raise ValidacaoDpsError("Chave de acesso da NFS-e deve ter 50 digitos numericos.")


def _validar_motivo(motivo: str) -> None:
    texto = (motivo or "").strip()
    if len(texto) < 15:
        raise ValidacaoDpsError("Motivo do cancelamento deve ter no minimo 15 caracteres.")
    if len(texto) > 255:
        raise ValidacaoDpsError("Motivo do cancelamento deve ter no maximo 255 caracteres.")


def _digits(value: str | None) -> str:
    if not value:
        return ""
    return "".join(ch for ch in value if ch.isdigit())
