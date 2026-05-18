from __future__ import annotations

import pytest
from lxml import etree

from brans_nfe import (
    Ambiente,
    CodigoEventoNfse,
    MotivoCancelamento,
    ValidacaoDpsError,
    construir_cancelamento,
    gerar_id_pre,
    serializar_evento,
)

NS = {"n": "http://www.sped.fazenda.gov.br/nfse"}
CHAVE_OK = "3" * 50
MOTIVO_OK = "Erro no preenchimento dos dados do servico"


def test_id_pre_formato():
    id_pre = gerar_id_pre(CHAVE_OK, CodigoEventoNfse.CANCELAMENTO)
    assert id_pre.startswith("PRE")
    assert len(id_pre) == 3 + 50 + 6
    assert id_pre.endswith("101101")


def test_id_pre_chave_invalida_levanta():
    with pytest.raises(ValidacaoDpsError):
        gerar_id_pre("123", CodigoEventoNfse.CANCELAMENTO)


def test_id_pre_diferentes_codigos():
    base = "PRE" + CHAVE_OK
    assert gerar_id_pre(CHAVE_OK, CodigoEventoNfse.CANCELAMENTO_POR_OFICIO) == base + "305101"
    assert gerar_id_pre(CHAVE_OK, CodigoEventoNfse.BLOQUEIO_POR_OFICIO) == base + "305102"


def test_cancelamento_gera_xml_com_e101101():
    evento = construir_cancelamento(
        chave_acesso=CHAVE_OK,
        motivo=MOTIVO_OK,
        cnpj_autor="12345678000190",
        ambiente=Ambiente.HOMOLOGACAO,
        motivo_codigo=MotivoCancelamento.ERRO_EMISSAO,
    )
    xml = serializar_evento(evento)
    root = etree.fromstring(xml)
    assert root.find(".//n:e101101/n:cMotivo", NS).text == "1"
    assert root.find(".//n:e101101/n:xMotivo", NS).text == MOTIVO_OK
    assert root.find(".//n:e101101/n:xDesc", NS).text == "Cancelamento de NFS-e"
    assert root.find(".//n:tpAmb", NS).text == "2"
    assert root.find(".//n:CNPJAutor", NS).text == "12345678000190"
    assert root.find(".//n:chNFSe", NS).text == CHAVE_OK


def test_cancelamento_xml_versao_e_estrutura_v1_01():
    evento = construir_cancelamento(
        chave_acesso=CHAVE_OK,
        motivo=MOTIVO_OK,
        cnpj_autor="12345678000190",
        ambiente=Ambiente.HOMOLOGACAO,
    )
    xml = serializar_evento(evento)
    root = etree.fromstring(xml)
    assert root.tag == f"{{{NS['n']}}}pedRegEvento"
    assert root.get("versao") == "1.01"
    inf = root.find("n:infPedReg", NS)
    assert inf is not None
    id_pre = inf.get("Id", "")
    assert len(id_pre) == 59
    assert id_pre == f"PRE{CHAVE_OK}101101"
    assert inf.find("n:nPedRegEvento", NS) is None


@pytest.mark.parametrize(
    "motivo_enum, esperado",
    [
        (MotivoCancelamento.ERRO_EMISSAO, "1"),
        (MotivoCancelamento.SERVICO_NAO_PRESTADO, "2"),
        (MotivoCancelamento.OUTROS, "9"),
    ],
)
def test_codigo_motivo_mapeado(motivo_enum, esperado):
    evento = construir_cancelamento(
        chave_acesso=CHAVE_OK,
        motivo=MOTIVO_OK,
        cnpj_autor="12345678000190",
        ambiente=Ambiente.HOMOLOGACAO,
        motivo_codigo=motivo_enum,
    )
    xml = serializar_evento(evento)
    root = etree.fromstring(xml)
    assert root.find(".//n:cMotivo", NS).text == esperado


def test_motivo_muito_curto_rejeitado():
    with pytest.raises(ValidacaoDpsError, match="minimo 15"):
        construir_cancelamento(
            chave_acesso=CHAVE_OK,
            motivo="curto",
            cnpj_autor="12345678000190",
            ambiente=Ambiente.HOMOLOGACAO,
        )


def test_motivo_muito_longo_rejeitado():
    with pytest.raises(ValidacaoDpsError, match="maximo 255"):
        construir_cancelamento(
            chave_acesso=CHAVE_OK,
            motivo="x" * 256,
            cnpj_autor="12345678000190",
            ambiente=Ambiente.HOMOLOGACAO,
        )


def test_chave_invalida_rejeitada():
    with pytest.raises(ValidacaoDpsError, match="50 digitos"):
        construir_cancelamento(
            chave_acesso="3" * 49,
            motivo=MOTIVO_OK,
            cnpj_autor="12345678000190",
            ambiente=Ambiente.HOMOLOGACAO,
        )


def test_cnpj_autor_invalido_rejeitado():
    with pytest.raises(ValidacaoDpsError, match="14 digitos"):
        construir_cancelamento(
            chave_acesso=CHAVE_OK,
            motivo=MOTIVO_OK,
            cnpj_autor="123",
            ambiente=Ambiente.HOMOLOGACAO,
        )
