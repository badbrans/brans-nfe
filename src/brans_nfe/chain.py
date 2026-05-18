from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from cryptography import x509


def carregar_bundle_pem(caminho: str | Path | None) -> List[x509.Certificate]:
    if not caminho:
        return []
    p = Path(caminho)
    if not p.exists():
        return []
    data = p.read_bytes()
    try:
        return list(x509.load_pem_x509_certificates(data))
    except Exception:
        return []


def resolver_cadeia(
    leaf: x509.Certificate,
    adicionais: List[x509.Certificate],
    bundle: Optional[List[x509.Certificate]] = None,
) -> List[x509.Certificate]:
    if adicionais:
        return list(adicionais)
    if not bundle:
        return []

    indice: dict[str, x509.Certificate] = {c.subject.rfc4514_string(): c for c in bundle}
    cadeia: List[x509.Certificate] = []
    atual = leaf
    visitados: set[str] = set()

    while True:
        nome_emissor = atual.issuer.rfc4514_string()
        if nome_emissor == atual.subject.rfc4514_string():
            break
        if nome_emissor in visitados:
            break
        visitados.add(nome_emissor)
        pai = indice.get(nome_emissor)
        if pai is None:
            break
        cadeia.append(pai)
        atual = pai

    return cadeia
