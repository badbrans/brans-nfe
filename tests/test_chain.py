from __future__ import annotations

from cryptography.hazmat.primitives import serialization

from brans_nfe.chain import carregar_bundle_pem, resolver_cadeia


def test_carregar_bundle_pem_caminho_none():
    assert carregar_bundle_pem(None) == []


def test_carregar_bundle_pem_arquivo_inexistente(tmp_path):
    assert carregar_bundle_pem(tmp_path / "nao-existe.pem") == []


def test_carregar_bundle_pem_arquivo_invalido(tmp_path):
    arquivo = tmp_path / "lixo.pem"
    arquivo.write_bytes(b"isso aqui nao eh um PEM valido")
    assert carregar_bundle_pem(arquivo) == []


def test_carregar_bundle_pem_arquivo_valido(bundle_pem_file):
    bundle = carregar_bundle_pem(bundle_pem_file)
    assert len(bundle) == 2


def test_carregar_bundle_pem_aceita_string(bundle_pem_file):
    bundle = carregar_bundle_pem(str(bundle_pem_file))
    assert len(bundle) == 2


def test_resolver_cadeia_usa_adicionais_quando_presentes(cadeia_certs):
    root, intermediate, leaf = cadeia_certs
    cadeia = resolver_cadeia(leaf, [intermediate, root], bundle=None)
    assert cadeia == [intermediate, root]


def test_resolver_cadeia_sem_bundle_sem_adicionais(cadeia_certs):
    _root, _intermediate, leaf = cadeia_certs
    assert resolver_cadeia(leaf, [], bundle=None) == []
    assert resolver_cadeia(leaf, [], bundle=[]) == []


def test_resolver_cadeia_self_signed_para_imediatamente(certificado):
    cadeia = resolver_cadeia(certificado.certificate, [], bundle=[certificado.certificate])
    assert cadeia == []


def test_resolver_cadeia_multi_nivel_a_partir_de_bundle(cadeia_certs):
    root, intermediate, leaf = cadeia_certs
    cadeia = resolver_cadeia(leaf, [], bundle=[root, intermediate])
    assert len(cadeia) == 2
    assert cadeia[0] == intermediate
    assert cadeia[1] == root


def test_resolver_cadeia_bundle_sem_emissor_para(cadeia_certs):
    _root, intermediate, leaf = cadeia_certs
    cadeia = resolver_cadeia(leaf, [], bundle=[intermediate])
    assert cadeia == [intermediate]
