from __future__ import annotations

from datetime import datetime, timedelta, timezone

from nfelib.nfse.bindings.v1_0 import ped_reg_evento_v1_00 as ped
from nfelib.nfse.bindings.v1_0 import tipos_eventos_v1_00 as te
from xsdata.formats.dataclass.serializers import XmlSerializer
from xsdata.formats.dataclass.serializers.config import SerializerConfig

from .enums import Ambiente, CodigoEventoNfse, MotivoCancelamento
from .exceptions import ValidacaoDpsError
from .signer import NAMESPACE_DPS


def construir_cancelamento(
    chave_acesso: str,
    motivo: str,
    cnpj_autor: str,
    ambiente: Ambiente,
    motivo_codigo: MotivoCancelamento = MotivoCancelamento.OUTROS,
    n_seq_evento: int = 1,
    versao_aplicativo: str = "brans-nfe-0.1.0",
) -> ped.PedRegEvento:
    _validar_chave(chave_acesso)
    _validar_motivo(motivo)
    cnpj_digits = _digits(cnpj_autor)
    if len(cnpj_digits) != 14:
        raise ValidacaoDpsError("CNPJ do autor do evento deve ter 14 digitos.")

    tp_amb = (
        te.TstipoAmbiente.VALUE_1
        if ambiente == Ambiente.PRODUCAO
        else te.TstipoAmbiente.VALUE_2
    )

    just_map = {
        MotivoCancelamento.ERRO_EMISSAO: te.TscodJustCanc.VALUE_1,
        MotivoCancelamento.SERVICO_NAO_PRESTADO: te.TscodJustCanc.VALUE_2,
        MotivoCancelamento.OUTROS: te.TscodJustCanc.VALUE_9,
    }

    e101101 = te.Te101101(
        xDesc=te.Te101101XDesc.CANCELAMENTO_DE_NFS_E,
        cMotivo=just_map[motivo_codigo],
        xMotivo=motivo,
    )

    inf = te.TcinfPedReg(
        tpAmb=tp_amb,
        verAplic=versao_aplicativo,
        dhEvento=_agora_brt_iso(),
        CNPJAutor=cnpj_digits,
        chNFSe=chave_acesso,
        nPedRegEvento=str(n_seq_evento),
        e101101=e101101,
        Id=gerar_id_pre(chave_acesso, CodigoEventoNfse.CANCELAMENTO, n_seq_evento),
    )

    return ped.PedRegEvento(infPedReg=inf, versao="1.00")


def serializar_evento(evento: ped.PedRegEvento) -> bytes:
    config = SerializerConfig(pretty_print=False, xml_declaration=True, encoding="UTF-8")
    serializer = XmlSerializer(config=config)
    xml_str = serializer.render(evento, ns_map={None: NAMESPACE_DPS})
    return xml_str.encode("utf-8")


def gerar_id_pre(
    chave_acesso: str,
    codigo_evento: CodigoEventoNfse,
    n_seq_evento: int = 1,
) -> str:
    if len(chave_acesso) != 50:
        raise ValidacaoDpsError("Chave de acesso da NFS-e deve ter 50 caracteres.")
    return f"PRE{chave_acesso}{codigo_evento.value}{str(n_seq_evento).zfill(3)}"


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
