from __future__ import annotations

import base64
import gzip

import pytest
from lxml import etree

from brans_nfe import (
    Ambiente,
    AssinaturaXmlError,
    assinar_xml,
    construir_dps,
    gzip_b64,
    serializar_dps,
)

NS = {
    "n": "http://www.sped.fazenda.gov.br/nfse",
    "ds": "http://www.w3.org/2000/09/xmldsig#",
}


def test_assinatura_inclui_signature_value_e_x509(nota_minima, certificado):
    xml = serializar_dps(construir_dps(nota_minima, Ambiente.HOMOLOGACAO))
    assinado = assinar_xml(xml, certificado)
    root = etree.fromstring(assinado)
    assert root.find("ds:Signature", NS) is not None
    assert root.find("ds:Signature/ds:SignatureValue", NS).text
    cert_el = root.find("ds:Signature/ds:KeyInfo/ds:X509Data/ds:X509Certificate", NS)
    assert cert_el is not None and cert_el.text


def test_referencia_aponta_para_id_do_inf_dps(nota_minima, certificado):
    dps = construir_dps(nota_minima, Ambiente.HOMOLOGACAO)
    xml = serializar_dps(dps)
    assinado = assinar_xml(xml, certificado)
    root = etree.fromstring(assinado)
    ref = root.find("ds:Signature/ds:SignedInfo/ds:Reference", NS)
    assert ref.get("URI") == f"#{dps.infDPS.Id}"


def test_assinatura_de_xml_invalido_levanta(certificado):
    with pytest.raises(AssinaturaXmlError):
        assinar_xml(b"<<<nao-eh-xml", certificado)


def test_assinatura_sem_elemento_assinavel_levanta(certificado):
    xml = b"<?xml version='1.0'?><raiz xmlns='http://www.sped.fazenda.gov.br/nfse'><outro/></raiz>"
    with pytest.raises(AssinaturaXmlError, match="assinavel"):
        assinar_xml(xml, certificado)


def test_gzip_b64_roundtrip():
    original = b"<xml/>"
    encoded = gzip_b64(original)
    decoded = gzip.decompress(base64.b64decode(encoded))
    assert decoded == original


def test_gzip_b64_eh_base64_valido(nota_minima, certificado):
    xml = serializar_dps(construir_dps(nota_minima, Ambiente.HOMOLOGACAO))
    assinado = assinar_xml(xml, certificado)
    encoded = gzip_b64(assinado)
    base64.b64decode(encoded, validate=True)
