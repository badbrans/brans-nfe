from __future__ import annotations

import atexit
import base64
import gzip
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import List, Optional

import requests
from cryptography.hazmat.primitives import serialization

from .certificado import Certificado
from .chain import carregar_bundle_pem, resolver_cadeia
from .dps import construir_dps, serializar_dps
from .enums import (
    Ambiente,
    CodigoEventoNfse,
    MotivoCancelamento,
    StatusProcessamentoDfe,
    TipoDocumentoDfe,
    TipoEventoDfe,
)
from .eventos import construir_cancelamento, serializar_evento
from .exceptions import (
    CancelamentoError,
    ConsultaError,
    DanfseIndisponivelError,
    SincronizacaoDfeError,
    TransmissaoError,
)
from .models import (
    ItemDfe,
    MensagemProcessamento,
    NotaServico,
    RespostaConsultaDps,
    RespostaDfe,
    RespostaEvento,
    RespostaTransmissao,
)
from .signer import assinar_xml, gzip_b64

logger = logging.getLogger(__name__)


SEFIN_URLS = {
    Ambiente.PRODUCAO: "https://sefin.nfse.gov.br/SefinNacional",
    Ambiente.HOMOLOGACAO: "https://sefin.producaorestrita.nfse.gov.br/SefinNacional",
}

ADN_URLS = {
    Ambiente.PRODUCAO: "https://adn.nfse.gov.br",
    Ambiente.HOMOLOGACAO: "https://adn.producaorestrita.nfse.gov.br",
}


class NfseClient:
    def __init__(
        self,
        certificado: Certificado,
        ambiente: Ambiente = Ambiente.HOMOLOGACAO,
        ca_bundle: str | Path | None = None,
        chain_bundle: str | Path | None = None,
        timeout: int = 120,
        versao_aplicativo: str = "brans-nfe-0.1.0",
    ):
        certificado.garantir_valido()
        self.certificado = certificado
        self.ambiente = ambiente
        self.sefin_url = SEFIN_URLS[ambiente]
        self.adn_url = ADN_URLS[ambiente]
        self.timeout = timeout
        self.versao_aplicativo = versao_aplicativo
        self._ca_bundle: str | bool = str(ca_bundle) if ca_bundle else True
        self._chain_bundle_path = chain_bundle
        self._cert_paths: tuple[str, str] | None = None
        atexit.register(self._limpar_arquivos_temporarios)

    def transmitir(self, nota: NotaServico) -> RespostaTransmissao:
        dps = construir_dps(nota, self.ambiente)
        xml_bytes = serializar_dps(dps)
        xml_assinado = assinar_xml(xml_bytes, self.certificado)
        payload = gzip_b64(xml_assinado)

        response = self._post_sefin("/nfse", {"dpsXmlGZipB64": payload})

        if response.status_code >= 400:
            raise TransmissaoError(
                f"Erro na transmissao da DPS: HTTP {response.status_code}",
                status_code=response.status_code,
                corpo=response.text,
            )

        body = response.json() if response.content else {}
        return RespostaTransmissao(
            chave_acesso=body.get("chaveAcesso"),
            id_dps=body.get("idDps") or body.get("idDPS"),
            tipo_ambiente=body.get("tipoAmbiente"),
            versao_aplicativo=body.get("versaoAplicativo"),
            data_hora_processamento=body.get("dataHoraProcessamento"),
            alertas=_parse_mensagens(body.get("alertas")),
            xml_dps_enviado=xml_assinado.decode("utf-8", errors="replace"),
            xml_nfse_retorno=_extrair_xml_nfse(body),
            payload_bruto=body,
        )

    def consultar(self, chave_acesso: str) -> dict:
        response = self._get_sefin(f"/nfse/{chave_acesso}")
        if response.status_code >= 400:
            raise ConsultaError(
                f"Erro ao consultar NFS-e {chave_acesso}: HTTP {response.status_code}",
                status_code=response.status_code,
                corpo=response.text,
            )
        return response.json()

    def consultar_dps(self, id_dps: str) -> RespostaConsultaDps:
        response = self._get_sefin(f"/dps/{id_dps}")
        if response.status_code >= 400:
            raise ConsultaError(
                f"Erro ao consultar DPS {id_dps}: HTTP {response.status_code}",
                status_code=response.status_code,
                corpo=response.text,
            )
        body = response.json()
        return RespostaConsultaDps(
            chave_acesso=body.get("chaveAcesso"),
            id_dps=body.get("idDps"),
            tipo_ambiente=body.get("tipoAmbiente"),
            versao_aplicativo=body.get("versaoAplicativo"),
            data_hora_processamento=body.get("dataHoraProcessamento"),
            payload_bruto=body,
        )

    def existe_dps(self, id_dps: str) -> bool:
        response = requests.head(
            f"{self.sefin_url}/dps/{id_dps}",
            cert=self._cert_path(),
            verify=self._ca_bundle,
            timeout=60,
        )
        if response.status_code == 200:
            return True
        if response.status_code == 404:
            return False
        raise ConsultaError(
            f"Erro ao verificar DPS {id_dps}: HTTP {response.status_code}",
            status_code=response.status_code,
            corpo=response.text,
        )

    def cancelar(
        self,
        chave_acesso: str,
        motivo: str,
        motivo_codigo: MotivoCancelamento = MotivoCancelamento.OUTROS,
        n_seq_evento: int = 1,
    ) -> RespostaEvento:
        evento = construir_cancelamento(
            chave_acesso=chave_acesso,
            motivo=motivo,
            cnpj_autor=self.certificado.cnpj,
            ambiente=self.ambiente,
            motivo_codigo=motivo_codigo,
            n_seq_evento=n_seq_evento,
            versao_aplicativo=self.versao_aplicativo,
        )
        xml_bytes = serializar_evento(evento)
        xml_assinado = assinar_xml(xml_bytes, self.certificado)

        response = self._post_sefin(
            f"/nfse/{chave_acesso}/eventos",
            {"pedidoRegistroEventoXmlGZipB64": gzip_b64(xml_assinado)},
        )
        if response.status_code >= 400:
            raise CancelamentoError(
                f"Erro ao cancelar NFS-e {chave_acesso}: HTTP {response.status_code}",
                status_code=response.status_code,
                corpo=response.text,
            )

        body = response.json()
        return RespostaEvento(
            evento_xml=_extrair_xml_evento(body),
            tipo_ambiente=body.get("tipoAmbiente"),
            versao_aplicativo=body.get("versaoAplicativo"),
            data_hora_processamento=body.get("dataHoraProcessamento"),
            payload_bruto=body,
        )

    def consultar_evento(
        self,
        chave_acesso: str,
        codigo_evento: CodigoEventoNfse,
        n_seq_evento: int = 1,
    ) -> RespostaEvento:
        path = f"/nfse/{chave_acesso}/eventos/{codigo_evento.value}/{n_seq_evento}"
        response = self._get_sefin(path)
        if response.status_code >= 400:
            raise ConsultaError(
                f"Erro ao consultar evento {codigo_evento.value}/{n_seq_evento}: "
                f"HTTP {response.status_code}",
                status_code=response.status_code,
                corpo=response.text,
            )
        body = response.json()
        return RespostaEvento(
            evento_xml=_extrair_xml_evento(body),
            tipo_ambiente=body.get("tipoAmbiente"),
            versao_aplicativo=body.get("versaoAplicativo"),
            data_hora_processamento=body.get("dataHoraProcessamento"),
            payload_bruto=body,
        )

    def listar_eventos_nfse(self, chave_acesso: str) -> RespostaDfe:
        response = requests.get(
            f"{self.adn_url}/contribuintes/NFSe/{chave_acesso}/Eventos",
            cert=self._cert_path(),
            verify=self._ca_bundle,
            headers={"Accept": "application/json"},
            timeout=60,
        )
        if response.status_code == 404:
            return RespostaDfe(
                itens=[],
                ultimo_nsu=0,
                status_processamento=StatusProcessamentoDfe.NENHUM_DOCUMENTO_LOCALIZADO,
            )
        if response.status_code >= 400:
            raise ConsultaError(
                f"Erro ao listar eventos da NFS-e {chave_acesso}: HTTP {response.status_code}",
                status_code=response.status_code,
                corpo=response.text,
            )
        return _parse_lote_dfe(response.json())

    def baixar_danfse(self, chave_acesso: str, tentativas: int = 3) -> bytes:
        url = f"{self.adn_url}/danfse/{chave_acesso}"
        ultimo_status: int | None = None
        ultimo_erro: str | None = None

        for tentativa in range(tentativas):
            try:
                response = requests.get(
                    url,
                    cert=self._cert_path(),
                    verify=self._ca_bundle,
                    headers={"Accept": "application/pdf"},
                    timeout=60,
                )
            except requests.RequestException as exc:
                ultimo_erro = str(exc)
                logger.warning("DANFSe %s tentativa %d: %s", chave_acesso, tentativa + 1, exc)
                time.sleep(1.5 * (tentativa + 1))
                continue

            ultimo_status = response.status_code
            if response.status_code == 200:
                return response.content
            if response.status_code in (502, 503, 504):
                time.sleep(1.5 * (tentativa + 1))
                continue

            raise DanfseIndisponivelError(
                f"Erro ao baixar DANFSe {chave_acesso}: HTTP {response.status_code}",
                status_code=response.status_code,
                corpo=(response.text or "")[:500],
            )

        raise DanfseIndisponivelError(
            f"DANFSe {chave_acesso} indisponivel apos {tentativas} tentativas.",
            status_code=ultimo_status,
            corpo=ultimo_erro,
        )

    def sincronizar_dfe(
        self,
        ultimo_nsu: int = 0,
        max_paginas: int = 20,
        lote: bool = True,
    ) -> RespostaDfe:
        cnpj = self.certificado.cnpj
        itens: List[ItemDfe] = []
        nsu_atual = ultimo_nsu
        ultima_resposta: dict | None = None

        for _ in range(max_paginas):
            response = requests.get(
                f"{self.adn_url}/contribuintes/DFe/{nsu_atual}",
                params={"cnpjConsulta": cnpj, "lote": str(lote).lower()},
                cert=self._cert_path(),
                verify=self._ca_bundle,
                headers={"Accept": "application/json"},
                timeout=60,
            )

            if response.status_code == 404:
                break
            if response.status_code >= 400:
                raise SincronizacaoDfeError(
                    f"Erro ao sincronizar DFe: HTTP {response.status_code}",
                    status_code=response.status_code,
                    corpo=response.text,
                )

            data = response.json()
            ultima_resposta = data
            status = data.get("StatusProcessamento")

            for item in data.get("LoteDFe") or []:
                parsed = _parse_dfe_item(item)
                if parsed:
                    itens.append(parsed)
                    if parsed.nsu > nsu_atual:
                        nsu_atual = parsed.nsu

            if status in (
                StatusProcessamentoDfe.NENHUM_DOCUMENTO_LOCALIZADO.value,
                StatusProcessamentoDfe.REJEICAO.value,
                None,
            ):
                break
            if not data.get("LoteDFe"):
                break

        return _montar_resposta_dfe(itens, nsu_atual, ultima_resposta)

    def _post_sefin(self, path: str, json_body: dict) -> requests.Response:
        return requests.post(
            f"{self.sefin_url}{path}",
            json=json_body,
            cert=self._cert_path(),
            verify=self._ca_bundle,
            headers={"Accept": "application/json"},
            timeout=self.timeout,
        )

    def _get_sefin(self, path: str) -> requests.Response:
        return requests.get(
            f"{self.sefin_url}{path}",
            cert=self._cert_path(),
            verify=self._ca_bundle,
            headers={"Accept": "application/json"},
            timeout=60,
        )

    def _cert_path(self) -> tuple[str, str]:
        if self._cert_paths is not None:
            return self._cert_paths

        bundle = carregar_bundle_pem(self._chain_bundle_path)
        cadeia = resolver_cadeia(
            self.certificado.certificate, self.certificado.additional_certs, bundle
        )

        cert_pem = self.certificado.certificate.public_bytes(serialization.Encoding.PEM)
        for extra in cadeia:
            cert_pem += extra.public_bytes(serialization.Encoding.PEM)

        key_pem = self.certificado.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        cert_file = tempfile.NamedTemporaryFile(delete=False, suffix="_brans_cert.pem")
        cert_file.write(cert_pem)
        cert_file.close()
        key_file = tempfile.NamedTemporaryFile(delete=False, suffix="_brans_key.pem")
        key_file.write(key_pem)
        key_file.close()

        self._cert_paths = (cert_file.name, key_file.name)
        return self._cert_paths

    def _limpar_arquivos_temporarios(self) -> None:
        if not self._cert_paths:
            return
        for caminho in self._cert_paths:
            try:
                os.unlink(caminho)
            except OSError:
                pass
        self._cert_paths = None


def _decode_xml_gzip_b64(value: str | None) -> Optional[str]:
    if not value:
        return None
    try:
        return gzip.decompress(base64.b64decode(value)).decode("utf-8")
    except (OSError, ValueError):
        try:
            return base64.b64decode(value).decode("utf-8")
        except ValueError:
            return None


def _extrair_xml_nfse(payload: dict) -> Optional[str]:
    if not isinstance(payload, dict):
        return None
    xml_str = _decode_xml_gzip_b64(payload.get("nfseXmlGZipB64"))
    if xml_str:
        return xml_str
    xml_inline = payload.get("xmlNFSe") or payload.get("xml")
    if isinstance(xml_inline, str) and xml_inline.lstrip().startswith("<"):
        return xml_inline
    return None


def _extrair_xml_evento(payload: dict) -> Optional[str]:
    if not isinstance(payload, dict):
        return None
    return _decode_xml_gzip_b64(payload.get("eventoXmlGZipB64"))


def _parse_mensagens(raw: object) -> List[MensagemProcessamento]:
    if not isinstance(raw, list):
        return []
    msgs: List[MensagemProcessamento] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        msgs.append(
            MensagemProcessamento(
                codigo=item.get("codigo") or item.get("Codigo"),
                descricao=item.get("descricao") or item.get("Descricao"),
                complemento=item.get("complemento") or item.get("Complemento"),
            )
        )
    return msgs


def _parse_dfe_item(item: dict) -> Optional[ItemDfe]:
    nsu_raw = item.get("NSU") or item.get("nsu")
    if nsu_raw is None:
        return None
    arquivo = _decode_xml_gzip_b64(item.get("ArquivoXml") or item.get("arquivoXml"))
    tipo_doc = item.get("TipoDocumento")
    tipo_evt = item.get("TipoEvento")
    return ItemDfe(
        nsu=int(nsu_raw),
        chave_acesso=item.get("ChaveAcesso") or item.get("chaveAcesso"),
        tipo_documento=TipoDocumentoDfe(tipo_doc) if tipo_doc else None,
        tipo_evento=TipoEventoDfe(tipo_evt) if tipo_evt else None,
        arquivo_xml=arquivo,
        data_hora_geracao=item.get("DataHoraGeracao"),
    )


def _parse_lote_dfe(data: dict) -> RespostaDfe:
    itens: List[ItemDfe] = []
    ultimo_nsu = 0
    for item in data.get("LoteDFe") or []:
        parsed = _parse_dfe_item(item)
        if parsed:
            itens.append(parsed)
            if parsed.nsu > ultimo_nsu:
                ultimo_nsu = parsed.nsu
    return _montar_resposta_dfe(itens, ultimo_nsu, data)


def _montar_resposta_dfe(
    itens: List[ItemDfe], ultimo_nsu: int, data: dict | None
) -> RespostaDfe:
    if data is None:
        return RespostaDfe(itens=itens, ultimo_nsu=ultimo_nsu)
    status = data.get("StatusProcessamento")
    return RespostaDfe(
        itens=itens,
        ultimo_nsu=ultimo_nsu,
        status_processamento=StatusProcessamentoDfe(status) if status else None,
        alertas=_parse_mensagens(data.get("Alertas")),
        erros=_parse_mensagens(data.get("Erros")),
        tipo_ambiente=data.get("TipoAmbiente"),
        versao_aplicativo=data.get("VersaoAplicativo"),
        data_hora_processamento=data.get("DataHoraProcessamento"),
    )
