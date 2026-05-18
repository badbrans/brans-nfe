from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import (
    CstPisCofins,
    RegimeEspecialTributacao,
    RegimeTributario,
    ResponsavelRetencaoIss,
    StatusProcessamentoDfe,
    TipoDocumentoDfe,
    TipoEventoDfe,
    TipoRetencaoPisCofins,
)


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _digits(value: str | None) -> str:
    if not value:
        return ""
    return "".join(ch for ch in value if ch.isdigit())


class Endereco(_Base):
    codigo_municipio_ibge: str = Field(..., min_length=7, max_length=7)
    cep: str = Field(..., min_length=8, max_length=8)
    logradouro: str = Field(..., min_length=1, max_length=200)
    numero: str = Field("S/N", max_length=20)
    complemento: Optional[str] = Field(None, max_length=255)
    bairro: str = Field(..., min_length=1, max_length=100)

    @field_validator("cep", "codigo_municipio_ibge", mode="before")
    @classmethod
    def _so_digitos(cls, v: str) -> str:
        d = _digits(v)
        return d


class Prestador(_Base):
    cnpj: str = Field(..., min_length=14, max_length=14)
    razao_social: str = Field(..., min_length=1, max_length=200)
    inscricao_municipal: Optional[str] = Field(None, max_length=20)
    regime_tributario: RegimeTributario = RegimeTributario.NORMAL
    regime_especial: RegimeEspecialTributacao = RegimeEspecialTributacao.NENHUM
    endereco: Endereco

    @field_validator("cnpj", mode="before")
    @classmethod
    def _normaliza_cnpj(cls, v: str) -> str:
        d = _digits(v)
        if len(d) != 14:
            raise ValueError("CNPJ do prestador deve ter 14 digitos.")
        return d


class Tomador(_Base):
    cpf_cnpj: str = Field(..., description="11 digitos (CPF) ou 14 (CNPJ)")
    razao_social: str = Field(..., min_length=1, max_length=200)
    inscricao_municipal: Optional[str] = Field(None, max_length=20)
    endereco: Optional[Endereco] = None
    telefone: Optional[str] = Field(None, max_length=30)
    email: Optional[str] = Field(None, max_length=200)

    @field_validator("cpf_cnpj", mode="before")
    @classmethod
    def _normaliza_doc(cls, v: str) -> str:
        d = _digits(v)
        if len(d) not in (11, 14):
            raise ValueError("Documento do tomador deve ter 11 (CPF) ou 14 (CNPJ) digitos.")
        return d

    @field_validator("telefone", mode="before")
    @classmethod
    def _normaliza_fone(cls, v: str | None) -> str | None:
        if v is None:
            return None
        d = _digits(v)
        return d or None

    @property
    def tipo_documento(self) -> str:
        return "CNPJ" if len(self.cpf_cnpj) == 14 else "CPF"


class Servico(_Base):
    codigo_tributacao_nacional: str = Field(..., min_length=6, max_length=6)
    codigo_tributacao_municipal: Optional[str] = Field(None, max_length=20)
    codigo_nbs: Optional[str] = Field(None, max_length=20)
    discriminacao: str = Field(..., min_length=1, max_length=1000)
    codigo_municipio_prestacao: str = Field(..., min_length=7, max_length=7)
    observacoes: Optional[str] = Field(None, max_length=2000)

    @field_validator("codigo_tributacao_nacional", "codigo_municipio_prestacao", mode="before")
    @classmethod
    def _so_digitos(cls, v: str) -> str:
        return _digits(v)


class TributacaoIss(_Base):
    retido: bool = False
    responsavel: ResponsavelRetencaoIss = ResponsavelRetencaoIss.PRESTADOR
    aliquota: Decimal = Decimal("0")
    valor: Decimal = Decimal("0")
    base_calculo: Decimal = Decimal("0")
    deducoes: Decimal = Decimal("0")


class TributacaoPisCofins(_Base):
    cst: Optional[CstPisCofins] = None
    aliquota_pis: Decimal = Decimal("0")
    valor_pis: Decimal = Decimal("0")
    aliquota_cofins: Decimal = Decimal("0")
    valor_cofins: Decimal = Decimal("0")
    base_calculo: Decimal = Decimal("0")
    retidos: bool = False


class Retencoes(_Base):
    valor_irrf: Decimal = Decimal("0")
    valor_inss: Decimal = Decimal("0")
    valor_csll: Decimal = Decimal("0")


class Valores(_Base):
    valor_bruto: Decimal
    valor_liquido: Decimal
    desconto_incondicional: Decimal = Decimal("0")
    desconto_condicional: Decimal = Decimal("0")


class NotaServico(_Base):
    serie_rps: str = Field("1", min_length=1, max_length=5)
    numero_rps: str = Field(..., min_length=1, max_length=15)
    data_competencia: date
    prestador: Prestador
    tomador: Tomador
    servico: Servico
    valores: Valores
    iss: TributacaoIss = TributacaoIss()
    pis_cofins: Optional[TributacaoPisCofins] = None
    retencoes: Retencoes = Retencoes()
    versao_aplicacao: str = Field("brans-nfe-0.1.0", max_length=20)


class MensagemProcessamento(_Base):
    codigo: Optional[str] = None
    descricao: Optional[str] = None
    complemento: Optional[str] = None


class RespostaTransmissao(_Base):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    chave_acesso: Optional[str] = None
    id_dps: Optional[str] = None
    tipo_ambiente: Optional[int] = None
    versao_aplicativo: Optional[str] = None
    data_hora_processamento: Optional[str] = None
    alertas: List[MensagemProcessamento] = Field(default_factory=list)
    xml_dps_enviado: str
    xml_nfse_retorno: Optional[str] = None
    payload_bruto: dict


class ItemDfe(_Base):
    nsu: int
    chave_acesso: Optional[str] = None
    tipo_documento: Optional[TipoDocumentoDfe] = None
    tipo_evento: Optional[TipoEventoDfe] = None
    arquivo_xml: Optional[str] = None
    data_hora_geracao: Optional[str] = None


class RespostaDfe(_Base):
    itens: List[ItemDfe]
    ultimo_nsu: int
    status_processamento: Optional[StatusProcessamentoDfe] = None
    alertas: List[MensagemProcessamento] = Field(default_factory=list)
    erros: List[MensagemProcessamento] = Field(default_factory=list)
    tipo_ambiente: Optional[str] = None
    versao_aplicativo: Optional[str] = None
    data_hora_processamento: Optional[str] = None


class RespostaConsultaDps(_Base):
    chave_acesso: Optional[str] = None
    id_dps: Optional[str] = None
    tipo_ambiente: Optional[int] = None
    versao_aplicativo: Optional[str] = None
    data_hora_processamento: Optional[str] = None
    payload_bruto: dict


class RespostaEvento(_Base):
    evento_xml: Optional[str] = None
    tipo_ambiente: Optional[int] = None
    versao_aplicativo: Optional[str] = None
    data_hora_processamento: Optional[str] = None
    payload_bruto: dict
