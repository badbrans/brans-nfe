from __future__ import annotations

import base64
import gzip
import json

import pytest
import responses

from brans_nfe import (
    CancelamentoError,
    CodigoEventoNfse,
    ConsultaError,
    DanfseIndisponivelError,
    MotivoCancelamento,
    SincronizacaoDfeError,
    StatusProcessamentoDfe,
    TipoDocumentoDfe,
    TransmissaoError,
)

SEFIN_BASE = "https://sefin.producaorestrita.nfse.gov.br/SefinNacional"
ADN_BASE = "https://adn.producaorestrita.nfse.gov.br"
CHAVE = "3" * 50
MOTIVO = "Cancelamento por erro no preenchimento dos dados"


@responses.activate
def test_transmitir_201_extrai_chave_e_id_dps(client_homologacao, nota_minima, xml_nfse_gzip_b64):
    responses.add(
        responses.POST,
        f"{SEFIN_BASE}/nfse",
        json={
            "tipoAmbiente": 2,
            "versaoAplicativo": "1.2.3",
            "dataHoraProcessamento": "2026-05-18T10:00:00-03:00",
            "idDps": "DPS123",
            "chaveAcesso": CHAVE,
            "nfseXmlGZipB64": xml_nfse_gzip_b64,
            "alertas": [{"codigo": "A1", "descricao": "ok"}],
        },
        status=201,
    )

    resp = client_homologacao.transmitir(nota_minima)

    assert resp.chave_acesso == CHAVE
    assert resp.id_dps == "DPS123"
    assert resp.tipo_ambiente == 2
    assert resp.versao_aplicativo == "1.2.3"
    assert resp.xml_nfse_retorno is not None
    assert resp.xml_nfse_retorno.startswith("<NFSe")
    assert len(resp.alertas) == 1
    assert resp.alertas[0].codigo == "A1"
    assert resp.xml_dps_enviado.startswith("<?xml")


@responses.activate
def test_transmitir_400_levanta_erro(client_homologacao, nota_minima):
    responses.add(
        responses.POST,
        f"{SEFIN_BASE}/nfse",
        json={"erros": [{"codigo": "X", "descricao": "Invalido"}]},
        status=400,
    )
    with pytest.raises(TransmissaoError) as exc:
        client_homologacao.transmitir(nota_minima)
    assert exc.value.status_code == 400
    assert "Invalido" in exc.value.corpo


@responses.activate
def test_transmitir_envia_dps_no_campo_correto(client_homologacao, nota_minima, xml_nfse_gzip_b64):
    responses.add(
        responses.POST,
        f"{SEFIN_BASE}/nfse",
        json={
            "tipoAmbiente": 2,
            "versaoAplicativo": "1.0",
            "dataHoraProcessamento": "2026-05-18T10:00:00-03:00",
            "idDps": "X",
            "chaveAcesso": CHAVE,
            "nfseXmlGZipB64": xml_nfse_gzip_b64,
        },
        status=201,
    )
    client_homologacao.transmitir(nota_minima)
    body = json.loads(responses.calls[0].request.body)
    assert set(body.keys()) == {"dpsXmlGZipB64"}
    base64.b64decode(body["dpsXmlGZipB64"], validate=True)


@responses.activate
def test_consultar_devolve_payload(client_homologacao):
    responses.add(
        responses.GET,
        f"{SEFIN_BASE}/nfse/{CHAVE}",
        json={"chaveAcesso": CHAVE, "nfseXmlGZipB64": "abc"},
        status=200,
    )
    body = client_homologacao.consultar(CHAVE)
    assert body["chaveAcesso"] == CHAVE


@responses.activate
def test_consultar_404_levanta_consulta_error(client_homologacao):
    responses.add(
        responses.GET,
        f"{SEFIN_BASE}/nfse/{CHAVE}",
        json={"erro": {"descricao": "Nao encontrada"}},
        status=404,
    )
    with pytest.raises(ConsultaError):
        client_homologacao.consultar(CHAVE)


@responses.activate
def test_consultar_dps_devolve_chave_acesso(client_homologacao):
    responses.add(
        responses.GET,
        f"{SEFIN_BASE}/dps/DPS123",
        json={
            "tipoAmbiente": 2,
            "versaoAplicativo": "1.0",
            "dataHoraProcessamento": "2026-05-18T10:00:00-03:00",
            "idDps": "DPS123",
            "chaveAcesso": CHAVE,
        },
        status=200,
    )
    resp = client_homologacao.consultar_dps("DPS123")
    assert resp.chave_acesso == CHAVE
    assert resp.id_dps == "DPS123"


@responses.activate
def test_existe_dps_true(client_homologacao):
    responses.add(responses.HEAD, f"{SEFIN_BASE}/dps/DPS123", status=200)
    assert client_homologacao.existe_dps("DPS123") is True


@responses.activate
def test_existe_dps_false(client_homologacao):
    responses.add(responses.HEAD, f"{SEFIN_BASE}/dps/DPS999", status=404)
    assert client_homologacao.existe_dps("DPS999") is False


@responses.activate
def test_cancelar_envia_pedido_registro_evento(client_homologacao, xml_evento_gzip_b64):
    responses.add(
        responses.POST,
        f"{SEFIN_BASE}/nfse/{CHAVE}/eventos",
        json={
            "tipoAmbiente": 2,
            "versaoAplicativo": "1.0",
            "dataHoraProcessamento": "2026-05-18T10:00:00-03:00",
            "eventoXmlGZipB64": xml_evento_gzip_b64,
        },
        status=201,
    )
    resp = client_homologacao.cancelar(
        chave_acesso=CHAVE,
        motivo=MOTIVO,
        motivo_codigo=MotivoCancelamento.ERRO_EMISSAO,
    )
    body = json.loads(responses.calls[0].request.body)
    assert set(body.keys()) == {"pedidoRegistroEventoXmlGZipB64"}
    assert resp.evento_xml is not None
    assert resp.evento_xml.startswith("<procEventoNFSe")


@responses.activate
def test_cancelar_422_levanta(client_homologacao):
    responses.add(
        responses.POST,
        f"{SEFIN_BASE}/nfse/{CHAVE}/eventos",
        json={"erro": "regra violada"},
        status=422,
    )
    with pytest.raises(CancelamentoError):
        client_homologacao.cancelar(chave_acesso=CHAVE, motivo=MOTIVO)


@responses.activate
def test_consultar_evento(client_homologacao, xml_evento_gzip_b64):
    responses.add(
        responses.GET,
        f"{SEFIN_BASE}/nfse/{CHAVE}/eventos/101101/1",
        json={
            "tipoAmbiente": 2,
            "versaoAplicativo": "1.0",
            "dataHoraProcessamento": "2026-05-18T10:00:00-03:00",
            "eventoXmlGZipB64": xml_evento_gzip_b64,
        },
        status=200,
    )
    resp = client_homologacao.consultar_evento(CHAVE, CodigoEventoNfse.CANCELAMENTO, 1)
    assert resp.evento_xml is not None


@responses.activate
def test_baixar_danfse_sucesso(client_homologacao):
    pdf_bytes = b"%PDF-1.4 fake danfse"
    responses.add(
        responses.GET,
        f"{ADN_BASE}/danfse/{CHAVE}",
        body=pdf_bytes,
        status=200,
        content_type="application/pdf",
    )
    assert client_homologacao.baixar_danfse(CHAVE) == pdf_bytes


@responses.activate
def test_baixar_danfse_404_levanta(client_homologacao):
    responses.add(
        responses.GET,
        f"{ADN_BASE}/danfse/{CHAVE}",
        body="nao existe",
        status=404,
    )
    with pytest.raises(DanfseIndisponivelError) as exc:
        client_homologacao.baixar_danfse(CHAVE, tentativas=1)
    assert exc.value.status_code == 404


@responses.activate
def test_baixar_danfse_502_retenta_e_consegue(client_homologacao, monkeypatch):
    monkeypatch.setattr("brans_nfe.client.time.sleep", lambda _s: None)
    pdf_bytes = b"%PDF-1.4 ok"
    responses.add(responses.GET, f"{ADN_BASE}/danfse/{CHAVE}", status=502)
    responses.add(
        responses.GET, f"{ADN_BASE}/danfse/{CHAVE}", body=pdf_bytes, status=200
    )
    assert client_homologacao.baixar_danfse(CHAVE, tentativas=3) == pdf_bytes
    assert len(responses.calls) == 2


@responses.activate
def test_baixar_danfse_502_esgota_tentativas(client_homologacao, monkeypatch):
    monkeypatch.setattr("brans_nfe.client.time.sleep", lambda _s: None)
    for _ in range(3):
        responses.add(responses.GET, f"{ADN_BASE}/danfse/{CHAVE}", status=502)
    with pytest.raises(DanfseIndisponivelError):
        client_homologacao.baixar_danfse(CHAVE, tentativas=3)


def _item_dfe(nsu: int, chave: str, xml: str) -> dict:
    return {
        "NSU": nsu,
        "ChaveAcesso": chave,
        "TipoDocumento": "NFSE",
        "TipoEvento": None,
        "ArquivoXml": base64.b64encode(gzip.compress(xml.encode())).decode(),
        "DataHoraGeracao": "2026-05-18T10:00:00-03:00",
    }


@responses.activate
def test_sincronizar_dfe_uma_pagina(client_homologacao):
    chave_a = "1" * 50
    chave_b = "2" * 50
    responses.add(
        responses.GET,
        f"{ADN_BASE}/contribuintes/DFe/0",
        json={
            "StatusProcessamento": "DOCUMENTOS_LOCALIZADOS",
            "LoteDFe": [
                _item_dfe(1, chave_a, "<NFSe>1</NFSe>"),
                _item_dfe(2, chave_b, "<NFSe>2</NFSe>"),
            ],
            "Alertas": [],
            "Erros": [],
            "TipoAmbiente": "HOMOLOGACAO",
            "VersaoAplicativo": "1.0",
            "DataHoraProcessamento": "2026-05-18T10:00:00-03:00",
        },
        status=200,
    )
    responses.add(
        responses.GET,
        f"{ADN_BASE}/contribuintes/DFe/2",
        json={
            "StatusProcessamento": "NENHUM_DOCUMENTO_LOCALIZADO",
            "LoteDFe": [],
            "Alertas": [],
            "Erros": [],
            "TipoAmbiente": "HOMOLOGACAO",
            "VersaoAplicativo": "1.0",
            "DataHoraProcessamento": "2026-05-18T10:00:00-03:00",
        },
        status=200,
    )

    resp = client_homologacao.sincronizar_dfe(ultimo_nsu=0)

    assert len(resp.itens) == 2
    assert resp.ultimo_nsu == 2
    assert resp.itens[0].nsu == 1
    assert resp.itens[0].tipo_documento == TipoDocumentoDfe.NFSE
    assert resp.itens[0].arquivo_xml == "<NFSe>1</NFSe>"
    assert resp.status_processamento == StatusProcessamentoDfe.NENHUM_DOCUMENTO_LOCALIZADO


@responses.activate
def test_sincronizar_dfe_envia_cnpj_como_query(client_homologacao):
    responses.add(
        responses.GET,
        f"{ADN_BASE}/contribuintes/DFe/0",
        json={
            "StatusProcessamento": "NENHUM_DOCUMENTO_LOCALIZADO",
            "LoteDFe": [],
            "TipoAmbiente": "HOMOLOGACAO",
            "VersaoAplicativo": "1.0",
            "DataHoraProcessamento": "2026-05-18T10:00:00-03:00",
        },
        status=200,
    )
    client_homologacao.sincronizar_dfe(ultimo_nsu=0)
    url = responses.calls[0].request.url
    assert "cnpjConsulta=12345678000190" in url
    assert "lote=true" in url


@responses.activate
def test_sincronizar_dfe_500_levanta(client_homologacao):
    responses.add(
        responses.GET,
        f"{ADN_BASE}/contribuintes/DFe/0",
        json={"erro": "server"},
        status=500,
    )
    with pytest.raises(SincronizacaoDfeError):
        client_homologacao.sincronizar_dfe(ultimo_nsu=0)


@responses.activate
def test_listar_eventos_nfse_404_devolve_vazio(client_homologacao):
    responses.add(
        responses.GET,
        f"{ADN_BASE}/contribuintes/NFSe/{CHAVE}/Eventos",
        status=404,
    )
    resp = client_homologacao.listar_eventos_nfse(CHAVE)
    assert resp.itens == []
    assert resp.status_processamento == StatusProcessamentoDfe.NENHUM_DOCUMENTO_LOCALIZADO


@responses.activate
def test_listar_eventos_nfse_500_levanta(client_homologacao):
    responses.add(
        responses.GET,
        f"{ADN_BASE}/contribuintes/NFSe/{CHAVE}/Eventos",
        json={"erro": "x"},
        status=500,
    )
    with pytest.raises(ConsultaError):
        client_homologacao.listar_eventos_nfse(CHAVE)


@responses.activate
def test_existe_dps_500_levanta(client_homologacao):
    responses.add(responses.HEAD, f"{SEFIN_BASE}/dps/DPS999", status=500)
    with pytest.raises(ConsultaError):
        client_homologacao.existe_dps("DPS999")


@responses.activate
def test_consultar_dps_400_levanta(client_homologacao):
    responses.add(
        responses.GET,
        f"{SEFIN_BASE}/dps/INVALIDO",
        json={"erro": "id mal-formado"},
        status=400,
    )
    with pytest.raises(ConsultaError):
        client_homologacao.consultar_dps("INVALIDO")


@responses.activate
def test_consultar_evento_404_levanta(client_homologacao):
    responses.add(
        responses.GET,
        f"{SEFIN_BASE}/nfse/{CHAVE}/eventos/101101/1",
        json={"erro": "nao encontrado"},
        status=404,
    )
    with pytest.raises(ConsultaError):
        client_homologacao.consultar_evento(CHAVE, CodigoEventoNfse.CANCELAMENTO, 1)


@responses.activate
def test_baixar_danfse_retenta_em_excecao_de_rede(client_homologacao, monkeypatch):
    import requests

    monkeypatch.setattr("brans_nfe.client.time.sleep", lambda _s: None)
    pdf_bytes = b"%PDF-1.4 ok"
    responses.add(
        responses.GET, f"{ADN_BASE}/danfse/{CHAVE}", body=requests.ConnectionError("timeout")
    )
    responses.add(
        responses.GET, f"{ADN_BASE}/danfse/{CHAVE}", body=pdf_bytes, status=200
    )
    assert client_homologacao.baixar_danfse(CHAVE, tentativas=3) == pdf_bytes


@responses.activate
def test_baixar_danfse_excecao_rede_esgota_levanta(client_homologacao, monkeypatch):
    import requests

    monkeypatch.setattr("brans_nfe.client.time.sleep", lambda _s: None)
    for _ in range(3):
        responses.add(
            responses.GET,
            f"{ADN_BASE}/danfse/{CHAVE}",
            body=requests.ConnectionError("timeout"),
        )
    with pytest.raises(DanfseIndisponivelError):
        client_homologacao.baixar_danfse(CHAVE, tentativas=3)


def test_cert_path_eh_cacheado(client_homologacao):
    a = client_homologacao._cert_path()
    b = client_homologacao._cert_path()
    assert a == b
    import os

    assert os.path.exists(a[0])
    assert os.path.exists(a[1])


def test_limpa_arquivos_temporarios_apaga_pem(client_homologacao):
    import os

    cert_path, key_path = client_homologacao._cert_path()
    assert os.path.exists(cert_path)
    assert os.path.exists(key_path)
    client_homologacao._limpar_arquivos_temporarios()
    assert not os.path.exists(cert_path)
    assert not os.path.exists(key_path)
    assert client_homologacao._cert_paths is None


def test_limpa_arquivos_temporarios_sem_paths_nao_quebra(client_homologacao):
    client_homologacao._cert_paths = None
    client_homologacao._limpar_arquivos_temporarios()


@responses.activate
def test_transmitir_payload_sem_body(client_homologacao, nota_minima):
    responses.add(responses.POST, f"{SEFIN_BASE}/nfse", body=b"", status=201)
    resp = client_homologacao.transmitir(nota_minima)
    assert resp.chave_acesso is None
    assert resp.payload_bruto == {}


def test_client_usa_ca_bundle_quando_passado(certificado, tmp_path):
    from brans_nfe import Ambiente, NfseClient

    fake_bundle = tmp_path / "fake-ca.pem"
    fake_bundle.write_bytes(b"# placeholder")
    cli = NfseClient(
        certificado=certificado,
        ambiente=Ambiente.HOMOLOGACAO,
        ca_bundle=fake_bundle,
    )
    assert cli._ca_bundle == str(fake_bundle)


def test_client_producao_aponta_para_url_de_producao(certificado):
    from brans_nfe import Ambiente, NfseClient

    cli = NfseClient(certificado=certificado, ambiente=Ambiente.PRODUCAO)
    assert "producaorestrita" not in cli.sefin_url
    assert "producaorestrita" not in cli.adn_url
    assert cli.sefin_url == "https://sefin.nfse.gov.br/SefinNacional"
    assert cli.adn_url == "https://adn.nfse.gov.br"
