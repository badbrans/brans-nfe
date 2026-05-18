# brans-nfe

[![PyPI version](https://img.shields.io/pypi/v/brans-nfe?style=flat-square&color=blue)](https://pypi.org/project/brans-nfe/)
[![Python versions](https://img.shields.io/pypi/pyversions/brans-nfe?style=flat-square)](https://pypi.org/project/brans-nfe/)
[![Downloads](https://static.pepy.tech/badge/brans-nfe)](https://pepy.tech/project/brans-nfe)
[![Downloads/month](https://static.pepy.tech/badge/brans-nfe/month)](https://pepy.tech/project/brans-nfe)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](https://opensource.org/licenses/MIT)
[![Tests](https://github.com/badbrans/brans-nfe/actions/workflows/tests.yml/badge.svg)](https://github.com/badbrans/brans-nfe/actions/workflows/tests.yml)

Cliente Python para a **NFS-e Nacional do Brasil** (SEFIN/Receita Federal) — emissão, consulta, cancelamento, distribuição de DFe e DANFSe, com assinatura XMLDSIG, mTLS com certificado A1 ICP-Brasil e payloads compactados em gzip+base64.

A `nfelib` fornece os bindings do XSD oficial. A `brans-nfe` foca na conversa com o SEFIN: PKCS#12, cadeia ICP-Brasil, assinatura XMLDSIG, transporte mTLS, paginação de DFe, mapeamentos de enums e modelagem de input.

## Recursos

- ✅ Emissão de NFS-e a partir de DPS (`POST /nfse`)
- ✅ Consulta de NFS-e por chave de acesso (`GET /nfse/{chave}`)
- ✅ Consulta/verificação de DPS por Id (`GET /dps/{id}`, `HEAD /dps/{id}`)
- ✅ Cancelamento com evento e101101 assinado (`POST /nfse/{chave}/eventos`)
- ✅ Consulta de evento específico (`GET /nfse/{chave}/eventos/{tipo}/{seq}`)
- ✅ Download do DANFSe oficial (`GET /danfse/{chave}` no ADN)
- ✅ Sincronização DFe (`GET /contribuintes/DFe/{NSU}?cnpjConsulta=...`)
- ✅ Listagem de eventos de uma NFS-e (`GET /contribuintes/NFSe/{chave}/Eventos`)
- ✅ Carregamento de certificado A1 (.pfx/.p12) com extração de CNPJ do subject **ou** SAN ICP-Brasil
- ✅ Resolução automática da cadeia ICP-Brasil a partir de bundle PEM
- ✅ Modelos Pydantic v2 com validação (CEP, CNPJ, codigos IBGE, codigos LC 116)
- ✅ Sanitização Latin-1 do `xInfComp` (en-dash, aspas curvas, emojis)
- ✅ Patch automático do enum `TstipoRetPiscofins` da nfelib 2.5.2
- ✅ Tipagem estrita (mypy-friendly), erros tipados

## Instalação

```bash
pip install brans-nfe
```

Para gerar DANFSe não-oficial em PDF (auxiliar, quando o portal SEFIN está fora):

```bash
pip install "brans-nfe[danfse]"
```

## Quick start

### Emitir NFS-e

```python
from datetime import date
from decimal import Decimal
from brans_nfe import (
    Ambiente, Certificado, NfseClient, NotaServico,
    Prestador, Tomador, Servico, Valores, Endereco,
    RegimeTributario, TributacaoIss,
)

certificado = Certificado.from_pfx_path("certificado.pfx", "senha-do-pfx")

client = NfseClient(
    certificado=certificado,
    ambiente=Ambiente.HOMOLOGACAO,
)

nota = NotaServico(
    serie_rps="1",
    numero_rps="42",
    data_competencia=date(2026, 5, 18),
    prestador=Prestador(
        cnpj=certificado.cnpj,
        razao_social=certificado.razao_social,
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
        cpf_cnpj="98.765.432/0001-10",
        razao_social="CLIENTE TESTE SA",
        endereco=Endereco(
            codigo_municipio_ibge="3304557",
            cep="20010001",
            logradouro="Av. do Tomador",
            numero="200",
            bairro="Centro",
        ),
        email="financeiro@cliente.com",
    ),
    servico=Servico(
        codigo_tributacao_nacional="010101",
        codigo_municipio_prestacao="3304557",
        discriminacao="Servico de consultoria em TI",
    ),
    valores=Valores(
        valor_bruto=Decimal("1000.00"),
        valor_liquido=Decimal("950.00"),
    ),
    iss=TributacaoIss(
        aliquota=Decimal("5.00"),
        valor=Decimal("50.00"),
        base_calculo=Decimal("1000.00"),
    ),
)

resp = client.transmitir(nota)
print(resp.chave_acesso)
print(resp.id_dps)
print(resp.xml_nfse_retorno)
```

### Cancelar NFS-e

```python
from brans_nfe import MotivoCancelamento

resp = client.cancelar(
    chave_acesso=resp.chave_acesso,
    motivo="Erro no preenchimento dos valores tributados",
    motivo_codigo=MotivoCancelamento.ERRO_EMISSAO,
)
```

### Consultar e baixar DANFSe oficial

```python
nfse = client.consultar(chave_acesso="33...50_digitos")
pdf_bytes = client.baixar_danfse(chave_acesso="33...50_digitos")

with open("danfse.pdf", "wb") as f:
    f.write(pdf_bytes)
```

### Sincronizar DFe (notas recebidas)

```python
resp = client.sincronizar_dfe(ultimo_nsu=0)
for item in resp.itens:
    print(item.nsu, item.chave_acesso, item.tipo_documento)
print("Proximo NSU:", resp.ultimo_nsu)
```

### Recuperar de timeout: consultar DPS por Id

Se a transmissão deu timeout mas você quer descobrir se a NFS-e foi gerada:

```python
if client.existe_dps(id_dps="DPS3304557..."):
    resp = client.consultar_dps(id_dps="DPS3304557...")
    print("Foi emitida:", resp.chave_acesso)
```

### Construir DPS sem transmitir

Útil para preview, auditoria ou armazenamento prévio:

```python
from brans_nfe import construir_dps, serializar_dps, assinar_xml

dps = construir_dps(nota, Ambiente.HOMOLOGACAO)
xml = serializar_dps(dps)
xml_assinado = assinar_xml(xml, certificado)
```

## API

### Modelos (Pydantic v2)

| Modelo | Descrição |
|---|---|
| `NotaServico` | DPS completa: prestador, tomador, serviço, valores, ISS, PIS/COFINS, retenções |
| `Prestador` | CNPJ + razão social + regime tributário + endereço |
| `Tomador` | CPF ou CNPJ + razão social + endereço (opcional) + contato |
| `Servico` | Código LC 116 (6 dígitos) + município prestação + discriminação |
| `Endereco` | IBGE 7 dígitos + CEP 8 dígitos + logradouro + bairro |
| `Valores` | Valor bruto, líquido, descontos condicional/incondicional |
| `TributacaoIss` | Alíquota, valor, base, retenção (prestador/tomador/intermediário) |
| `TributacaoPisCofins` | CST, alíquotas, valores, retidos |
| `Retencoes` | IRRF, INSS, CSLL |

### Cliente

```python
NfseClient(
    certificado: Certificado,
    ambiente: Ambiente = Ambiente.HOMOLOGACAO,
    ca_bundle: str | Path | None = None,
    chain_bundle: str | Path | None = None,
    timeout: int = 120,
    versao_aplicativo: str = "brans-nfe-0.1.0",
)
```

| Método | Endpoint | Retorno |
|---|---|---|
| `transmitir(nota)` | `POST /nfse` | `RespostaTransmissao` |
| `consultar(chave)` | `GET /nfse/{chave}` | `dict` |
| `consultar_dps(id)` | `GET /dps/{id}` | `RespostaConsultaDps` |
| `existe_dps(id)` | `HEAD /dps/{id}` | `bool` |
| `cancelar(chave, motivo)` | `POST /nfse/{chave}/eventos` | `RespostaEvento` |
| `consultar_evento(chave, codigo, seq)` | `GET /nfse/{chave}/eventos/{tipo}/{seq}` | `RespostaEvento` |
| `baixar_danfse(chave)` | `GET /danfse/{chave}` | `bytes` |
| `sincronizar_dfe(ultimo_nsu)` | `GET /contribuintes/DFe/{NSU}` | `RespostaDfe` |
| `listar_eventos_nfse(chave)` | `GET /contribuintes/NFSe/{chave}/Eventos` | `RespostaDfe` |

### Erros

Todos derivam de `BransNfeError`:

- `CertificadoError`, `CertificadoExpiradoError`, `CertificadoSenhaInvalidaError`
- `ValidacaoDpsError`
- `AssinaturaXmlError`
- `TransmissaoError`, `ConsultaError`, `CancelamentoError`, `DanfseIndisponivelError`, `SincronizacaoDfeError` (todos com `status_code` e `corpo`)

## Ambientes oficiais

| Serviço | Homologação | Produção |
|---|---|---|
| SEFIN | `https://sefin.producaorestrita.nfse.gov.br/SefinNacional` | `https://sefin.nfse.gov.br/SefinNacional` |
| ADN | `https://adn.producaorestrita.nfse.gov.br` | `https://adn.nfse.gov.br` |

O `NfseClient` resolve automaticamente com base no `Ambiente`.

## Por que outra lib?

A `nfelib` é excelente — fornece os bindings gerados a partir do XSD oficial — mas é apenas o **modelo de dados**. Pra emitir realmente uma NFS-e Nacional você precisa de:

| Etapa | nfelib | brans-nfe |
|---|---|---|
| Dataclasses do XSD (`Dps`, `Tcserv`, enums) | ✅ | reutiliza |
| Serializar dataclass → XML | ✅ (via xsdata) | reutiliza |
| Carregar PKCS#12 + extrair CNPJ ICP-Brasil | ❌ | ✅ |
| Resolver cadeia ICP-Brasil | ❌ | ✅ |
| Assinar XML-DSig (C14N + SHA1 + KeyInfo) | ❌ | ✅ |
| Gzip + base64 do payload | ❌ | ✅ |
| POST mTLS ao SEFIN | ❌ | ✅ |
| Consultar / Cancelar / Sincronizar DFe | ❌ | ✅ |
| Baixar DANFSe oficial | ❌ | ✅ |
| Patch de enum bugado da nfelib 2.5.2 | ❌ | ✅ |
| Sanitização Latin-1 do `xInfComp` | ❌ | ✅ |
| Modelagem Pydantic pronta pra usar | ❌ | ✅ |

## Desenvolvimento

```bash
git clone https://github.com/badbrans/brans-nfe.git
cd brans-nfe

python -m venv venv
.\venv\Scripts\Activate.ps1     # Windows
source venv/bin/activate         # Linux/Mac

pip install -e ".[dev]"

pytest                           # 89 testes
pytest --cov=brans_nfe            # com coverage
black src tests
isort src tests
mypy src
```

## Licença

[MIT](LICENSE) — Copyright (c) 2026 Raphael Brans

## Disclaimer

Esta biblioteca é um projeto independente e **não tem vínculo com a Receita Federal, SEFIN, ICP-Brasil ou Comitê Gestor da NFS-e Nacional**. Use em produção por sua conta e risco, em conformidade com a legislação vigente.
