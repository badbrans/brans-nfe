from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import List

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.hazmat.primitives.serialization import pkcs12

from .exceptions import CertificadoError, CertificadoExpiradoError, CertificadoSenhaInvalidaError

OID_COMMON_NAME = "2.5.4.3"
OID_SERIAL_NUMBER = "2.5.4.5"
OID_SUBJECT_ALT_NAME = "2.5.29.17"
OID_ICPBRASIL_CNPJ_PJ = "2.16.76.1.3.3"


class Certificado:
    def __init__(
        self,
        cnpj: str,
        razao_social: str,
        validade: date,
        private_key: RSAPrivateKey,
        certificate: x509.Certificate,
        additional_certs: List[x509.Certificate],
        pfx_bytes: bytes,
        senha: str,
    ):
        self.cnpj = cnpj
        self.razao_social = razao_social
        self.validade = validade
        self.private_key = private_key
        self.certificate = certificate
        self.additional_certs = additional_certs
        self.pfx_bytes = pfx_bytes
        self.senha = senha

    @property
    def valido(self) -> bool:
        return self.validade >= datetime.now(timezone.utc).date()

    @classmethod
    def from_pfx_bytes(cls, pfx_bytes: bytes, senha: str) -> "Certificado":
        try:
            private_key, certificate, additional_certs = pkcs12.load_key_and_certificates(
                pfx_bytes, senha.encode(), default_backend()
            )
        except ValueError as exc:
            raise CertificadoSenhaInvalidaError(
                "Senha do certificado invalida ou arquivo corrompido."
            ) from exc
        except Exception as exc:
            raise CertificadoError(f"Erro ao carregar certificado: {exc}") from exc

        if certificate is None:
            raise CertificadoError("Certificado nao encontrado no arquivo PFX.")
        if private_key is None:
            raise CertificadoError("Chave privada nao encontrada no arquivo PFX.")
        if not isinstance(private_key, RSAPrivateKey):
            raise CertificadoError("Apenas chaves RSA sao suportadas (ICP-Brasil exige RSA).")

        cnpj, razao_social = _extrair_identidade(certificate)
        validade = certificate.not_valid_after_utc.date()

        return cls(
            cnpj=cnpj,
            razao_social=razao_social,
            validade=validade,
            private_key=private_key,
            certificate=certificate,
            additional_certs=list(additional_certs or []),
            pfx_bytes=pfx_bytes,
            senha=senha,
        )

    @classmethod
    def from_pfx_path(cls, caminho: str | Path, senha: str) -> "Certificado":
        with open(caminho, "rb") as f:
            return cls.from_pfx_bytes(f.read(), senha)

    def garantir_valido(self) -> None:
        if not self.valido:
            raise CertificadoExpiradoError(f"Certificado expirado em {self.validade.isoformat()}.")


def _extrair_identidade(certificate: x509.Certificate) -> tuple[str, str]:
    cnpj_subject = ""
    razao_social = ""

    for attribute in certificate.subject:
        oid = attribute.oid.dotted_string
        if oid == OID_COMMON_NAME:
            razao_social = str(attribute.value)
            if ":" in razao_social:
                cnpj_candidate = razao_social.split(":")[-1]
                razao_social = razao_social.split(":")[0]
                if not cnpj_subject:
                    cnpj_subject = cnpj_candidate
        elif oid == OID_SERIAL_NUMBER:
            serial = str(attribute.value)
            cnpj_subject = serial.split(":")[-1] if ":" in serial else serial

    cnpj_digits = "".join(filter(str.isdigit, cnpj_subject))
    if len(cnpj_digits) != 14:
        cnpj_digits = _extrair_cnpj_san(certificate) or cnpj_digits

    return cnpj_digits, razao_social


def _extrair_cnpj_san(certificate: x509.Certificate) -> str:
    for extension in certificate.extensions:
        if extension.oid.dotted_string != OID_SUBJECT_ALT_NAME:
            continue
        for name in extension.value:
            type_id = getattr(name, "type_id", None)
            if type_id is None or type_id.dotted_string != OID_ICPBRASIL_CNPJ_PJ:
                continue
            raw = name.value
            if isinstance(raw, bytes):
                texto = raw.decode("latin-1", "ignore")
            else:
                texto = str(raw)
            digits = "".join(filter(str.isdigit, texto))
            if len(digits) >= 14:
                return digits[-14:]
    return ""


def validar_pfx(pfx_bytes: bytes, senha: str) -> tuple[bool, str | None]:
    try:
        cert = Certificado.from_pfx_bytes(pfx_bytes, senha)
    except CertificadoSenhaInvalidaError as exc:
        return False, str(exc)
    except CertificadoError as exc:
        return False, str(exc)
    if not cert.valido:
        return False, f"Certificado expirado em {cert.validade.isoformat()}"
    return True, None
