from __future__ import annotations

from pathlib import Path

import pytest

from brans_nfe import (
    Certificado,
    CertificadoExpiradoError,
    CertificadoSenhaInvalidaError,
    validar_pfx,
)
from tests.conftest import CNPJ_TESTE, RAZAO_SOCIAL_TESTE


def test_carrega_certificado_de_bytes(pfx_bytes, pfx_senha):
    cert = Certificado.from_pfx_bytes(pfx_bytes, pfx_senha)
    assert cert.cnpj == CNPJ_TESTE
    assert cert.razao_social == RAZAO_SOCIAL_TESTE
    assert cert.valido is True
    assert cert.senha == pfx_senha
    assert cert.private_key is not None
    assert cert.certificate is not None


def test_carrega_certificado_de_path(pfx_bytes, pfx_senha, tmp_path: Path):
    arquivo = tmp_path / "teste.pfx"
    arquivo.write_bytes(pfx_bytes)
    cert = Certificado.from_pfx_path(arquivo, pfx_senha)
    assert cert.cnpj == CNPJ_TESTE


def test_senha_invalida(pfx_bytes):
    with pytest.raises(CertificadoSenhaInvalidaError):
        Certificado.from_pfx_bytes(pfx_bytes, "senha-errada")


def test_certificado_expirado_falha_garantir(pfx_expirado, pfx_senha):
    cert = Certificado.from_pfx_bytes(pfx_expirado, pfx_senha)
    assert cert.valido is False
    with pytest.raises(CertificadoExpiradoError):
        cert.garantir_valido()


def test_validar_pfx_sucesso(pfx_bytes, pfx_senha):
    ok, erro = validar_pfx(pfx_bytes, pfx_senha)
    assert ok is True
    assert erro is None


def test_validar_pfx_senha_invalida(pfx_bytes):
    ok, erro = validar_pfx(pfx_bytes, "errada")
    assert ok is False
    assert erro is not None


def test_validar_pfx_expirado(pfx_expirado, pfx_senha):
    ok, erro = validar_pfx(pfx_expirado, pfx_senha)
    assert ok is False
    assert "expirado" in erro.lower()
