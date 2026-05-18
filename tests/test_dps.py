from __future__ import annotations

from decimal import Decimal

import pytest
from lxml import etree

from brans_nfe import (
    Ambiente,
    CstPisCofins,
    ResponsavelRetencaoIss,
    TributacaoIss,
    TributacaoPisCofins,
    ValidacaoDpsError,
    construir_dps,
    serializar_dps,
)

NS = {"n": "http://www.sped.fazenda.gov.br/nfse"}


def _serializa(nota, ambiente=Ambiente.HOMOLOGACAO):
    return serializar_dps(construir_dps(nota, ambiente))


def test_id_dps_formato(nota_minima):
    dps = construir_dps(nota_minima, Ambiente.HOMOLOGACAO)
    id_dps = dps.infDPS.Id
    assert id_dps.startswith("DPS")
    assert len(id_dps) == 3 + 7 + 1 + 14 + 5 + 15
    assert id_dps[3:10] == "3304557"
    assert id_dps[10] == "2"
    assert id_dps[11:25] == "12345678000190"
    assert id_dps[25:30] == "00001"
    assert id_dps[30:45] == "000000000000042"


def test_dps_ambiente_homologacao(nota_minima):
    xml = _serializa(nota_minima, Ambiente.HOMOLOGACAO)
    root = etree.fromstring(xml)
    tp_amb = root.find(".//n:tpAmb", NS)
    assert tp_amb.text == "2"


def test_dps_ambiente_producao(nota_minima):
    xml = _serializa(nota_minima, Ambiente.PRODUCAO)
    root = etree.fromstring(xml)
    tp_amb = root.find(".//n:tpAmb", NS)
    assert tp_amb.text == "1"


def test_dps_contem_cnpj_prestador_e_tomador(nota_minima):
    xml = _serializa(nota_minima)
    text = xml.decode()
    assert "<CNPJ>12345678000190</CNPJ>" in text
    assert "<CNPJ>98765432000110</CNPJ>" in text


def test_cep_invalido_levanta(nota_minima):
    nota_minima.prestador.endereco.cep = "12345"
    with pytest.raises(ValidacaoDpsError, match="CEP"):
        construir_dps(nota_minima, Ambiente.HOMOLOGACAO)


def test_codigo_tributacao_nacional_invalido_levanta(nota_minima):
    nota_minima.servico.codigo_tributacao_nacional = "12345"
    with pytest.raises(ValidacaoDpsError, match="cTribNac"):
        construir_dps(nota_minima, Ambiente.HOMOLOGACAO)


def test_observacoes_latin1_substitui_aspas_curvas(nota_minima):
    nota_minima.servico.observacoes = "texto com aspas “curvas” e travessao — fim"
    xml = _serializa(nota_minima).decode()
    assert "“" not in xml
    assert "”" not in xml
    assert "—" not in xml
    assert '"curvas"' in xml or "&quot;curvas&quot;" in xml


def test_observacoes_remove_caracteres_nao_latin1(nota_minima):
    nota_minima.servico.observacoes = "ascii \U0001f600 emoji"
    xml = _serializa(nota_minima).decode()
    assert "\U0001f600" not in xml


def test_iss_retido_tomador_gera_tpRetIss_2(nota_minima):
    nota_minima.iss = TributacaoIss(
        retido=True,
        responsavel=ResponsavelRetencaoIss.TOMADOR,
        aliquota=Decimal("5"),
        valor=Decimal("50"),
        base_calculo=Decimal("1000"),
    )
    xml = _serializa(nota_minima)
    root = etree.fromstring(xml)
    tp_ret = root.find(".//n:tpRetISSQN", NS)
    assert tp_ret.text == "2"


def test_iss_retido_intermediario_gera_tpRetIss_3(nota_minima):
    nota_minima.iss = TributacaoIss(
        retido=True,
        responsavel=ResponsavelRetencaoIss.INTERMEDIARIO,
        valor=Decimal("50"),
    )
    xml = _serializa(nota_minima)
    root = etree.fromstring(xml)
    tp_ret = root.find(".//n:tpRetISSQN", NS)
    assert tp_ret.text == "3"


def test_pis_cofins_retidos_codigo_3(nota_minima):
    nota_minima.pis_cofins = TributacaoPisCofins(
        cst=CstPisCofins.CST_01,
        aliquota_pis=Decimal("0.0065"),
        aliquota_cofins=Decimal("0.0300"),
        valor_pis=Decimal("6.50"),
        valor_cofins=Decimal("30.00"),
        base_calculo=Decimal("1000"),
        retidos=True,
    )
    xml = _serializa(nota_minima)
    root = etree.fromstring(xml)
    tp_ret = root.find(".//n:tpRetPisCofins", NS)
    assert tp_ret.text == "3"


def test_simples_nacional_sem_tributos_usa_indTotTrib_0(nota_minima):
    nota_minima.iss = TributacaoIss()
    xml = _serializa(nota_minima)
    root = etree.fromstring(xml)
    ind = root.find(".//n:indTotTrib", NS)
    assert ind is not None
    assert ind.text == "0"


def test_dhEmi_tem_offset_brt(nota_minima):
    xml = _serializa(nota_minima)
    root = etree.fromstring(xml)
    dh = root.find(".//n:dhEmi", NS).text
    assert dh.endswith("-03:00")
