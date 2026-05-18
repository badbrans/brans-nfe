from __future__ import annotations

import base64
import gzip
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from brans_nfe import (
    Ambiente,
    Certificado,
    Endereco,
    NfseClient,
    NotaServico,
    Prestador,
    RegimeTributario,
    Servico,
    Tomador,
    Valores,
)

SENHA_TESTE = "senha-teste-123"
CNPJ_TESTE = "12345678000190"
RAZAO_SOCIAL_TESTE = "EMPRESA TESTE LTDA"


def _gerar_pfx(
    cnpj: str = CNPJ_TESTE,
    razao_social: str = RAZAO_SOCIAL_TESTE,
    senha: str = SENHA_TESTE,
    validade_dias: int = 365,
) -> bytes:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ICP-Brasil Teste"),
            x509.NameAttribute(NameOID.COMMON_NAME, f"{razao_social}:{cnpj}"),
        ]
    )
    now = datetime.now(timezone.utc)
    not_after = now + timedelta(days=validade_dias)
    not_before = min(now - timedelta(days=1), not_after - timedelta(days=1))
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .sign(key, hashes.SHA256())
    )
    return pkcs12.serialize_key_and_certificates(
        name=b"brans-nfe-test",
        key=key,
        cert=cert,
        cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(senha.encode()),
    )


def _gerar_cadeia():
    root_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    root_name = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"),
            x509.NameAttribute(NameOID.COMMON_NAME, "Raiz Teste ICP"),
        ]
    )
    now = datetime.now(timezone.utc)
    root = (
        x509.CertificateBuilder()
        .subject_name(root_name)
        .issuer_name(root_name)
        .public_key(root_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(root_key, hashes.SHA256())
    )

    inter_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    inter_name = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"),
            x509.NameAttribute(NameOID.COMMON_NAME, "Intermediario Teste ICP"),
        ]
    )
    intermediate = (
        x509.CertificateBuilder()
        .subject_name(inter_name)
        .issuer_name(root_name)
        .public_key(inter_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=1825))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(root_key, hashes.SHA256())
    )

    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf_name = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"),
            x509.NameAttribute(NameOID.COMMON_NAME, f"{RAZAO_SOCIAL_TESTE}:{CNPJ_TESTE}"),
        ]
    )
    leaf = (
        x509.CertificateBuilder()
        .subject_name(leaf_name)
        .issuer_name(inter_name)
        .public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=365))
        .sign(inter_key, hashes.SHA256())
    )

    return root, intermediate, leaf


@pytest.fixture(scope="session")
def cadeia_certs():
    return _gerar_cadeia()


@pytest.fixture
def bundle_pem_file(cadeia_certs, tmp_path):
    root, intermediate, _leaf = cadeia_certs
    pem = root.public_bytes(serialization.Encoding.PEM) + intermediate.public_bytes(
        serialization.Encoding.PEM
    )
    arquivo = tmp_path / "cadeia.pem"
    arquivo.write_bytes(pem)
    return arquivo


@pytest.fixture(scope="session")
def pfx_bytes() -> bytes:
    return _gerar_pfx()


@pytest.fixture(scope="session")
def pfx_senha() -> str:
    return SENHA_TESTE


@pytest.fixture(scope="session")
def pfx_expirado() -> bytes:
    return _gerar_pfx(validade_dias=-30)


@pytest.fixture
def certificado(pfx_bytes: bytes, pfx_senha: str) -> Certificado:
    return Certificado.from_pfx_bytes(pfx_bytes, pfx_senha)


@pytest.fixture
def client_homologacao(certificado: Certificado) -> NfseClient:
    return NfseClient(certificado=certificado, ambiente=Ambiente.HOMOLOGACAO)


@pytest.fixture
def nota_minima() -> NotaServico:
    return NotaServico(
        serie_rps="1",
        numero_rps="42",
        data_competencia=date(2026, 5, 18),
        prestador=Prestador(
            cnpj=CNPJ_TESTE,
            razao_social=RAZAO_SOCIAL_TESTE,
            regime_tributario=RegimeTributario.SIMPLES_NACIONAL,
            endereco=Endereco(
                codigo_municipio_ibge="3304557",
                cep="20010000",
                logradouro="Rua do Prestador",
                numero="100",
                bairro="Centro",
            ),
        ),
        tomador=Tomador(
            cpf_cnpj="98765432000110",
            razao_social="CLIENTE TESTE SA",
            endereco=Endereco(
                codigo_municipio_ibge="3304557",
                cep="20010001",
                logradouro="Av. do Tomador",
                numero="200",
                bairro="Centro",
            ),
            email="tomador@teste.com",
        ),
        servico=Servico(
            codigo_tributacao_nacional="010101",
            codigo_municipio_prestacao="3304557",
            discriminacao="Servico de teste automatizado",
        ),
        valores=Valores(valor_bruto=Decimal("1000.00"), valor_liquido=Decimal("950.00")),
    )


def _gzip_b64(xml: str) -> str:
    return base64.b64encode(gzip.compress(xml.encode("utf-8"))).decode("ascii")


@pytest.fixture
def xml_nfse_gzip_b64() -> str:
    return _gzip_b64("<NFSe versao='1.00'><infNFSe>...</infNFSe></NFSe>")


@pytest.fixture
def xml_evento_gzip_b64() -> str:
    return _gzip_b64("<procEventoNFSe><evento>...</evento></procEventoNFSe>")
