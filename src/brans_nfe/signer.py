from __future__ import annotations

import base64
import gzip
import hashlib

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from lxml import etree

from .certificado import Certificado
from .exceptions import AssinaturaXmlError

NAMESPACE_DPS = "http://www.sped.fazenda.gov.br/nfse"
DS_NS = "http://www.w3.org/2000/09/xmldsig#"
ALG_C14N = "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"
ALG_RSA_SHA1 = "http://www.w3.org/2000/09/xmldsig#rsa-sha1"
ALG_SHA1 = "http://www.w3.org/2000/09/xmldsig#sha1"
ALG_ENVELOPED = "http://www.w3.org/2000/09/xmldsig#enveloped-signature"

REFERENCIAS_ASSINAVEIS = ("infDPS", "infPedReg", "infEvento")


def assinar_xml(xml_bytes: bytes, certificado: Certificado) -> bytes:
    try:
        root = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError as exc:
        raise AssinaturaXmlError(f"XML invalido para assinatura: {exc}") from exc

    referencia = _localizar_referencia(root)
    if referencia is None:
        raise AssinaturaXmlError(
            "Nao foi possivel localizar elemento assinavel (infDPS/infEvento)."
        )

    ref_uri = referencia.get("Id")
    if not ref_uri:
        raise AssinaturaXmlError("Elemento assinavel sem atributo Id.")

    inf_canonical = etree.canonicalize(etree.tostring(referencia).decode())
    digest_value = base64.b64encode(hashlib.sha1(inf_canonical.encode()).digest()).decode()

    signed_info = _montar_signed_info(ref_uri, digest_value)
    signature_value = _assinar_signed_info(signed_info, certificado)

    root.append(_montar_signature_element(signed_info, signature_value, certificado))

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def gzip_b64(xml_bytes: bytes) -> str:
    return base64.b64encode(gzip.compress(xml_bytes)).decode("ascii")


def _localizar_referencia(root: etree._Element) -> etree._Element | None:
    for tag in REFERENCIAS_ASSINAVEIS:
        encontrado = root.find(f"{{{NAMESPACE_DPS}}}{tag}")
        if encontrado is not None:
            return encontrado
        encontrado = root.find(tag)
        if encontrado is not None:
            return encontrado
    return None


def _montar_signed_info(ref_uri: str, digest_value: str) -> etree._Element:
    signed_info = etree.Element(f"{{{DS_NS}}}SignedInfo", nsmap={None: DS_NS})
    etree.SubElement(signed_info, f"{{{DS_NS}}}CanonicalizationMethod", Algorithm=ALG_C14N)
    etree.SubElement(signed_info, f"{{{DS_NS}}}SignatureMethod", Algorithm=ALG_RSA_SHA1)
    ref = etree.SubElement(signed_info, f"{{{DS_NS}}}Reference", URI=f"#{ref_uri}")
    transforms = etree.SubElement(ref, f"{{{DS_NS}}}Transforms")
    etree.SubElement(transforms, f"{{{DS_NS}}}Transform", Algorithm=ALG_ENVELOPED)
    etree.SubElement(transforms, f"{{{DS_NS}}}Transform", Algorithm=ALG_C14N)
    etree.SubElement(ref, f"{{{DS_NS}}}DigestMethod", Algorithm=ALG_SHA1)
    digest = etree.SubElement(ref, f"{{{DS_NS}}}DigestValue")
    digest.text = digest_value
    return signed_info


def _assinar_signed_info(signed_info: etree._Element, certificado: Certificado) -> str:
    canonical = etree.canonicalize(etree.tostring(signed_info).decode()).encode()
    signature_bytes = certificado.private_key.sign(canonical, padding.PKCS1v15(), hashes.SHA1())
    return base64.b64encode(signature_bytes).decode()


def _montar_signature_element(
    signed_info: etree._Element, signature_value: str, certificado: Certificado
) -> etree._Element:
    sig = etree.Element(f"{{{DS_NS}}}Signature", nsmap={None: DS_NS})
    sig.append(signed_info)
    sv = etree.SubElement(sig, f"{{{DS_NS}}}SignatureValue")
    sv.text = signature_value
    key_info = etree.SubElement(sig, f"{{{DS_NS}}}KeyInfo")
    x509_data = etree.SubElement(key_info, f"{{{DS_NS}}}X509Data")
    cert_el = etree.SubElement(x509_data, f"{{{DS_NS}}}X509Certificate")
    cert_el.text = base64.b64encode(
        certificado.certificate.public_bytes(serialization.Encoding.DER)
    ).decode()
    return sig
