from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Optional, Union

from .models import NotaServico

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Image,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )
except ImportError as exc:
    raise ImportError(
        "reportlab nao instalado. Instale o extra DANFSe: " 'pip install "brans-nfe[danfse]"'
    ) from exc


GREY_BG = colors.HexColor("#E5E7EB")
LINE_COLOR = colors.black

LogoFonte = Union[bytes, str, Path, None]


def gerar_danfse_pdf(
    nota: NotaServico,
    chave_acesso: str,
    numero_nfse: Optional[str] = None,
    data_emissao: Optional[date] = None,
    codigo_verificacao: Optional[str] = None,
    logo: LogoFonte = None,
    versao_aplicativo: str = "brans-nfe-0.1.0",
) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        title=f"DANFSe {numero_nfse or chave_acesso}",
        author=nota.prestador.razao_social,
    )

    estilos = _estilos()
    flowables = []
    flowables.append(_cabecalho(nota, chave_acesso, numero_nfse, data_emissao, logo, estilos))
    flowables.append(Spacer(1, 3 * mm))
    flowables.append(_bloco_chave(chave_acesso, codigo_verificacao, estilos))
    flowables.append(Spacer(1, 3 * mm))
    flowables.append(_bloco_prestador(nota, estilos))
    flowables.append(Spacer(1, 3 * mm))
    flowables.append(_bloco_tomador(nota, estilos))
    flowables.append(Spacer(1, 3 * mm))
    flowables.append(_bloco_servico(nota, estilos))
    flowables.append(Spacer(1, 3 * mm))
    flowables.append(_bloco_valores(nota, estilos))
    flowables.append(Spacer(1, 3 * mm))
    flowables.append(_bloco_tributacao(nota, estilos))
    if nota.servico.observacoes:
        flowables.append(Spacer(1, 3 * mm))
        flowables.append(_bloco_observacoes(nota.servico.observacoes, estilos))
    flowables.append(Spacer(1, 3 * mm))
    flowables.append(_rodape(versao_aplicativo, estilos))

    doc.build(flowables)
    return buffer.getvalue()


def _estilos() -> dict:
    base = getSampleStyleSheet()
    return {
        "titulo": ParagraphStyle(
            "Titulo",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=14,
            alignment=1,
            spaceAfter=2,
        ),
        "subtitulo": ParagraphStyle(
            "Subtitulo",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            alignment=1,
            textColor=colors.grey,
        ),
        "rotulo": ParagraphStyle(
            "Rotulo",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7,
        ),
        "valor": ParagraphStyle(
            "Valor",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
        ),
        "valor_pequeno": ParagraphStyle(
            "ValorPequeno",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7,
        ),
        "secao": ParagraphStyle(
            "Secao",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            backColor=GREY_BG,
            spaceBefore=0,
            spaceAfter=0,
            leftIndent=2,
        ),
        "rodape": ParagraphStyle(
            "Rodape",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=7,
            alignment=1,
            textColor=colors.grey,
        ),
        "chave": ParagraphStyle(
            "Chave",
            parent=base["Normal"],
            fontName="Courier-Bold",
            fontSize=9,
            alignment=1,
            leading=11,
        ),
    }


def _cabecalho(
    nota: NotaServico,
    chave_acesso: str,
    numero_nfse: Optional[str],
    data_emissao: Optional[date],
    logo: LogoFonte,
    estilos: dict,
) -> Table:
    logo_cell = _logo_flowable(logo) if logo else Paragraph("", estilos["valor"])
    identificacao = [
        Paragraph("DANFSe", estilos["titulo"]),
        Paragraph("Documento Auxiliar da Nota Fiscal de Servicos Eletronica", estilos["subtitulo"]),
        Spacer(1, 2 * mm),
        Paragraph(f"<b>N&deg; NFS-e:</b> {numero_nfse or '-'}", estilos["valor"]),
        Paragraph(
            f"<b>Emissao:</b> {_fmt_data(data_emissao or nota.data_competencia)}",
            estilos["valor"],
        ),
    ]
    tabela = Table(
        [[logo_cell, identificacao]],
        colWidths=[45 * mm, None],
    )
    tabela.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (0, 0), "CENTER"),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE_COLOR),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return tabela


def _logo_flowable(logo: LogoFonte):
    fonte: Union[str, BytesIO]
    if isinstance(logo, (bytes, bytearray)):
        fonte = BytesIO(bytes(logo))
    else:
        caminho = Path(str(logo))
        if not caminho.exists():
            return Paragraph("", ParagraphStyle("placeholder"))
        fonte = str(caminho)
    try:
        return Image(fonte, width=35 * mm, height=20 * mm, kind="proportional")
    except Exception:
        return Paragraph("", ParagraphStyle("placeholder"))


def _bloco_chave(chave: str, codigo_verificacao: Optional[str], estilos: dict) -> Table:
    chave_fmt = " ".join(chave[i : i + 4] for i in range(0, len(chave), 4))
    linhas = [
        [Paragraph("CHAVE DE ACESSO", estilos["secao"])],
        [Paragraph(chave_fmt, estilos["chave"])],
    ]
    if codigo_verificacao:
        linhas.append(
            [
                Paragraph(
                    f"<b>Codigo de verificacao:</b> {codigo_verificacao}",
                    estilos["valor_pequeno"],
                )
            ]
        )
    tabela = Table(linhas, colWidths=[None])
    tabela.setStyle(_estilo_box())
    return tabela


def _bloco_prestador(nota: NotaServico, estilos: dict) -> Table:
    p = nota.prestador
    end = p.endereco
    dados = [
        [Paragraph("PRESTADOR DE SERVICOS", estilos["secao"])],
        [
            Paragraph(
                f"<b>Razao Social:</b> {p.razao_social}<br/>"
                f"<b>CNPJ:</b> {_fmt_cnpj(p.cnpj)}"
                + (f" &nbsp; <b>IM:</b> {p.inscricao_municipal}" if p.inscricao_municipal else "")
                + f"<br/>"
                f"<b>Endereco:</b> {end.logradouro}, {end.numero}"
                + (f", {end.complemento}" if end.complemento else "")
                + f" - {end.bairro} - CEP {_fmt_cep(end.cep)} - "
                f"Municipio IBGE: {end.codigo_municipio_ibge}",
                estilos["valor"],
            )
        ],
    ]
    tabela = Table(dados, colWidths=[None])
    tabela.setStyle(_estilo_box())
    return tabela


def _bloco_tomador(nota: NotaServico, estilos: dict) -> Table:
    t = nota.tomador
    doc_label = "CNPJ" if len(t.cpf_cnpj) == 14 else "CPF"
    doc_fmt = _fmt_cnpj(t.cpf_cnpj) if len(t.cpf_cnpj) == 14 else _fmt_cpf(t.cpf_cnpj)
    end_str = "-"
    if t.endereco:
        end = t.endereco
        end_str = (
            f"{end.logradouro}, {end.numero}"
            + (f", {end.complemento}" if end.complemento else "")
            + f" - {end.bairro} - CEP {_fmt_cep(end.cep)} - "
            f"Municipio IBGE: {end.codigo_municipio_ibge}"
        )
    contato_partes = []
    if t.telefone:
        contato_partes.append(f"Tel: {t.telefone}")
    if t.email:
        contato_partes.append(f"Email: {t.email}")
    contato = " &nbsp;|&nbsp; ".join(contato_partes) or "-"

    dados = [
        [Paragraph("TOMADOR DE SERVICOS", estilos["secao"])],
        [
            Paragraph(
                f"<b>Nome/Razao Social:</b> {t.razao_social}<br/>"
                f"<b>{doc_label}:</b> {doc_fmt}"
                + (f" &nbsp; <b>IM:</b> {t.inscricao_municipal}" if t.inscricao_municipal else "")
                + f"<br/>"
                f"<b>Endereco:</b> {end_str}<br/>"
                f"<b>Contato:</b> {contato}",
                estilos["valor"],
            )
        ],
    ]
    tabela = Table(dados, colWidths=[None])
    tabela.setStyle(_estilo_box())
    return tabela


def _bloco_servico(nota: NotaServico, estilos: dict) -> Table:
    s = nota.servico
    info_codigos = (
        f"<b>Codigo LC 116 (cTribNac):</b> {s.codigo_tributacao_nacional}"
        + (
            f" &nbsp; <b>Cod. Municipal:</b> {s.codigo_tributacao_municipal}"
            if s.codigo_tributacao_municipal
            else ""
        )
        + (f" &nbsp; <b>NBS:</b> {s.codigo_nbs}" if s.codigo_nbs else "")
        + f" &nbsp; <b>Municipio prestacao IBGE:</b> {s.codigo_municipio_prestacao}"
        + f" &nbsp; <b>Competencia:</b> {_fmt_data(nota.data_competencia)}"
    )
    dados = [
        [Paragraph("DISCRIMINACAO DOS SERVICOS", estilos["secao"])],
        [Paragraph(info_codigos, estilos["valor_pequeno"])],
        [Paragraph(s.discriminacao.replace("\n", "<br/>"), estilos["valor"])],
    ]
    tabela = Table(dados, colWidths=[None])
    tabela.setStyle(_estilo_box())
    return tabela


def _bloco_valores(nota: NotaServico, estilos: dict) -> Table:
    v = nota.valores
    linhas = [
        [
            Paragraph("Valor dos Servicos", estilos["rotulo"]),
            Paragraph("Desconto Incond.", estilos["rotulo"]),
            Paragraph("Desconto Cond.", estilos["rotulo"]),
            Paragraph("Deducoes ISS", estilos["rotulo"]),
            Paragraph("Base de Calculo", estilos["rotulo"]),
            Paragraph("Valor Liquido", estilos["rotulo"]),
        ],
        [
            Paragraph(_brl(v.valor_bruto), estilos["valor"]),
            Paragraph(_brl(v.desconto_incondicional), estilos["valor"]),
            Paragraph(_brl(v.desconto_condicional), estilos["valor"]),
            Paragraph(_brl(nota.iss.deducoes), estilos["valor"]),
            Paragraph(_brl(nota.iss.base_calculo or v.valor_bruto), estilos["valor"]),
            Paragraph(_brl(v.valor_liquido), estilos["valor"]),
        ],
    ]
    cabecalho = [[Paragraph("VALORES", estilos["secao"])]]
    cab_tabela = Table(cabecalho, colWidths=[None])
    cab_tabela.setStyle(_estilo_box_topo())

    tabela = Table(linhas, colWidths=[None] * 6)
    tabela.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, LINE_COLOR),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, LINE_COLOR),
                ("BACKGROUND", (0, 0), (-1, 0), GREY_BG),
                ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )

    return Table([[cab_tabela], [tabela]], colWidths=[None])


def _bloco_tributacao(nota: NotaServico, estilos: dict) -> Table:
    iss = nota.iss
    retencoes = nota.retencoes
    pis_cofins = nota.pis_cofins

    valor_pis = pis_cofins.valor_pis if pis_cofins else Decimal("0")
    aliq_pis = pis_cofins.aliquota_pis if pis_cofins else Decimal("0")
    valor_cofins = pis_cofins.valor_cofins if pis_cofins else Decimal("0")
    aliq_cofins = pis_cofins.aliquota_cofins if pis_cofins else Decimal("0")

    linhas = [
        [
            Paragraph("Tributo", estilos["rotulo"]),
            Paragraph("Aliquota (%)", estilos["rotulo"]),
            Paragraph("Base de Calculo", estilos["rotulo"]),
            Paragraph("Valor", estilos["rotulo"]),
            Paragraph("Retido", estilos["rotulo"]),
        ],
        [
            Paragraph("ISS", estilos["valor"]),
            Paragraph(_pct(iss.aliquota), estilos["valor"]),
            Paragraph(_brl(iss.base_calculo), estilos["valor"]),
            Paragraph(_brl(iss.valor), estilos["valor"]),
            Paragraph(
                "Sim" if iss.retido else "Nao",
                estilos["valor"],
            ),
        ],
        [
            Paragraph("PIS", estilos["valor"]),
            Paragraph(_pct(aliq_pis * 100 if aliq_pis else 0), estilos["valor"]),
            Paragraph(_brl(pis_cofins.base_calculo if pis_cofins else 0), estilos["valor"]),
            Paragraph(_brl(valor_pis), estilos["valor"]),
            Paragraph("Sim" if pis_cofins and pis_cofins.retidos else "Nao", estilos["valor"]),
        ],
        [
            Paragraph("COFINS", estilos["valor"]),
            Paragraph(_pct(aliq_cofins * 100 if aliq_cofins else 0), estilos["valor"]),
            Paragraph(_brl(pis_cofins.base_calculo if pis_cofins else 0), estilos["valor"]),
            Paragraph(_brl(valor_cofins), estilos["valor"]),
            Paragraph("Sim" if pis_cofins and pis_cofins.retidos else "Nao", estilos["valor"]),
        ],
        [
            Paragraph("CSLL", estilos["valor"]),
            Paragraph("-", estilos["valor"]),
            Paragraph("-", estilos["valor"]),
            Paragraph(_brl(retencoes.valor_csll), estilos["valor"]),
            Paragraph("Sim" if retencoes.valor_csll else "Nao", estilos["valor"]),
        ],
        [
            Paragraph("IRRF", estilos["valor"]),
            Paragraph("-", estilos["valor"]),
            Paragraph("-", estilos["valor"]),
            Paragraph(_brl(retencoes.valor_irrf), estilos["valor"]),
            Paragraph("Sim" if retencoes.valor_irrf else "Nao", estilos["valor"]),
        ],
        [
            Paragraph("INSS", estilos["valor"]),
            Paragraph("-", estilos["valor"]),
            Paragraph("-", estilos["valor"]),
            Paragraph(_brl(retencoes.valor_inss), estilos["valor"]),
            Paragraph("Sim" if retencoes.valor_inss else "Nao", estilos["valor"]),
        ],
    ]

    cabecalho = [[Paragraph("TRIBUTOS E RETENCOES", estilos["secao"])]]
    cab_tabela = Table(cabecalho, colWidths=[None])
    cab_tabela.setStyle(_estilo_box_topo())

    tabela = Table(linhas, colWidths=[30 * mm, 25 * mm, None, None, 18 * mm])
    tabela.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, LINE_COLOR),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, LINE_COLOR),
                ("BACKGROUND", (0, 0), (-1, 0), GREY_BG),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("ALIGN", (0, 0), (0, -1), "LEFT"),
                ("ALIGN", (-1, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )

    return Table([[cab_tabela], [tabela]], colWidths=[None])


def _bloco_observacoes(observacoes: str, estilos: dict) -> Table:
    dados = [
        [Paragraph("OBSERVACOES / INFORMACOES COMPLEMENTARES", estilos["secao"])],
        [Paragraph(observacoes.replace("\n", "<br/>"), estilos["valor_pequeno"])],
    ]
    tabela = Table(dados, colWidths=[None])
    tabela.setStyle(_estilo_box())
    return tabela


def _rodape(versao_aplicativo: str, estilos: dict) -> Paragraph:
    return Paragraph(
        "Documento auxiliar nao oficial. Nao substitui a NFS-e emitida pelo SEFIN.<br/>"
        f"Gerado por {versao_aplicativo} em {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        estilos["rodape"],
    )


def _estilo_box() -> TableStyle:
    return TableStyle(
        [
            ("BOX", (0, 0), (-1, -1), 0.5, LINE_COLOR),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, LINE_COLOR),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]
    )


def _estilo_box_topo() -> TableStyle:
    return TableStyle(
        [
            ("BOX", (0, 0), (-1, -1), 0.5, LINE_COLOR),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]
    )


def _brl(valor) -> str:
    if valor is None:
        return "R$ 0,00"
    n = Decimal(str(valor))
    s = f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def _pct(valor) -> str:
    if not valor:
        return "0,00%"
    n = Decimal(str(valor))
    return f"{n:.2f}".replace(".", ",") + "%"


def _fmt_data(d) -> str:
    if not d:
        return "-"
    if isinstance(d, str):
        return d
    return d.strftime("%d/%m/%Y")


def _fmt_cnpj(cnpj: str) -> str:
    s = "".join(ch for ch in cnpj if ch.isdigit())
    if len(s) != 14:
        return cnpj
    return f"{s[:2]}.{s[2:5]}.{s[5:8]}/{s[8:12]}-{s[12:]}"


def _fmt_cpf(cpf: str) -> str:
    s = "".join(ch for ch in cpf if ch.isdigit())
    if len(s) != 11:
        return cpf
    return f"{s[:3]}.{s[3:6]}.{s[6:9]}-{s[9:]}"


def _fmt_cep(cep: str) -> str:
    s = "".join(ch for ch in cep if ch.isdigit())
    if len(s) != 8:
        return cep
    return f"{s[:5]}-{s[5:]}"
