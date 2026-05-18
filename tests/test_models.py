from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from brans_nfe import Endereco, Prestador, RegimeTributario, Servico, Tomador


def _endereco_valido():
    return Endereco(
        codigo_municipio_ibge="3304557",
        cep="20010000",
        logradouro="Rua",
        numero="1",
        bairro="Centro",
    )


def test_endereco_normaliza_mascara_no_cep():
    end = Endereco(
        codigo_municipio_ibge="3304557",
        cep="20.010-000",
        logradouro="Rua",
        numero="1",
        bairro="Centro",
    )
    assert end.cep == "20010000"


def test_endereco_cep_curto_rejeitado():
    with pytest.raises(ValidationError):
        Endereco(
            codigo_municipio_ibge="3304557",
            cep="123",
            logradouro="Rua",
            bairro="Centro",
        )


def test_prestador_cnpj_aceita_mascara():
    p = Prestador(
        cnpj="12.345.678/0001-90",
        razao_social="X",
        endereco=_endereco_valido(),
    )
    assert p.cnpj == "12345678000190"


def test_prestador_cnpj_com_menos_digitos_rejeitado():
    with pytest.raises(ValidationError):
        Prestador(cnpj="123", razao_social="X", endereco=_endereco_valido())


def test_tomador_cnpj_ok():
    t = Tomador(cpf_cnpj="98.765.432/0001-10", razao_social="X")
    assert t.cpf_cnpj == "98765432000110"
    assert t.tipo_documento == "CNPJ"


def test_tomador_cpf_ok():
    t = Tomador(cpf_cnpj="123.456.789-00", razao_social="X")
    assert t.cpf_cnpj == "12345678900"
    assert t.tipo_documento == "CPF"


def test_tomador_documento_invalido_rejeitado():
    with pytest.raises(ValidationError, match="11.*14"):
        Tomador(cpf_cnpj="12345", razao_social="X")


def test_tomador_telefone_so_digitos():
    t = Tomador(
        cpf_cnpj="98765432000110",
        razao_social="X",
        telefone="(21) 99999-8888",
    )
    assert t.telefone == "21999998888"


def test_servico_codigo_trib_nacional_curto_rejeitado():
    with pytest.raises(ValidationError):
        Servico(
            codigo_tributacao_nacional="123",
            codigo_municipio_prestacao="3304557",
            discriminacao="x",
        )


def test_servico_extra_field_rejeitado():
    with pytest.raises(ValidationError):
        Servico(
            codigo_tributacao_nacional="010101",
            codigo_municipio_prestacao="3304557",
            discriminacao="x",
            campo_inventado="X",
        )
