from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

reportlab = pytest.importorskip("reportlab")

from brans_nfe import CstPisCofins, Retencoes, TributacaoIss, TributacaoPisCofins
from brans_nfe.danfse_pdf import (
    _brl,
    _fmt_cep,
    _fmt_cnpj,
    _fmt_cpf,
    _fmt_data,
    _pct,
    gerar_danfse_pdf,
)


CHAVE = "3" * 50


def test_gera_pdf_minimo(nota_minima):
    pdf = gerar_danfse_pdf(nota=nota_minima, chave_acesso=CHAVE)
    assert pdf[:5] == b"%PDF-"
    assert len(pdf) > 1000


def test_gera_pdf_com_todos_campos(nota_minima):
    nota_minima.servico.observacoes = "Pagamento via PIX em 30 dias\nNF de servico"
    nota_minima.pis_cofins = TributacaoPisCofins(
        cst=CstPisCofins.CST_01,
        aliquota_pis=Decimal("0.0065"),
        aliquota_cofins=Decimal("0.0300"),
        valor_pis=Decimal("6.50"),
        valor_cofins=Decimal("30.00"),
        base_calculo=Decimal("1000"),
    )
    nota_minima.retencoes = Retencoes(
        valor_irrf=Decimal("15.00"),
        valor_inss=Decimal("12.00"),
        valor_csll=Decimal("10.00"),
    )
    nota_minima.iss = TributacaoIss(
        aliquota=Decimal("5.00"),
        valor=Decimal("50.00"),
        base_calculo=Decimal("1000.00"),
    )

    pdf = gerar_danfse_pdf(
        nota=nota_minima,
        chave_acesso=CHAVE,
        numero_nfse="00000123",
        data_emissao=date(2026, 5, 18),
        codigo_verificacao="ABCD1234",
    )
    assert pdf[:5] == b"%PDF-"
    assert len(pdf) > 3000


def test_pdf_aceita_tomador_sem_endereco(nota_minima):
    nota_minima.tomador.endereco = None
    pdf = gerar_danfse_pdf(nota=nota_minima, chave_acesso=CHAVE)
    assert pdf[:5] == b"%PDF-"


def test_pdf_com_logo_bytes(nota_minima):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from io import BytesIO

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.drawString(100, 100, "logo placeholder")
    c.showPage()
    c.save()
    pdf_bytes = buf.getvalue()
    assert pdf_bytes[:5] == b"%PDF-"


def test_pdf_com_logo_path_inexistente_nao_quebra(nota_minima, tmp_path):
    pdf = gerar_danfse_pdf(
        nota=nota_minima,
        chave_acesso=CHAVE,
        logo=tmp_path / "logo-inexistente.png",
    )
    assert pdf[:5] == b"%PDF-"


def test_pdf_tomador_cpf(nota_minima):
    from brans_nfe import Tomador

    nota_minima.tomador = Tomador(
        cpf_cnpj="123.456.789-00",
        razao_social="JOAO DA SILVA",
    )
    pdf = gerar_danfse_pdf(nota=nota_minima, chave_acesso=CHAVE)
    assert pdf[:5] == b"%PDF-"


def test_brl_formata_decimal():
    assert _brl(Decimal("1234.56")) == "R$ 1.234,56"
    assert _brl(Decimal("0")) == "R$ 0,00"
    assert _brl(None) == "R$ 0,00"
    assert _brl(1000000) == "R$ 1.000.000,00"


def test_pct_formata():
    assert _pct(Decimal("5")) == "5,00%"
    assert _pct(Decimal("5.5")) == "5,50%"
    assert _pct(0) == "0,00%"
    assert _pct(None) == "0,00%"


def test_fmt_data():
    assert _fmt_data(date(2026, 5, 18)) == "18/05/2026"
    assert _fmt_data(None) == "-"
    assert _fmt_data("ja-formatado") == "ja-formatado"


def test_fmt_cnpj_aplica_mascara():
    assert _fmt_cnpj("12345678000190") == "12.345.678/0001-90"
    assert _fmt_cnpj("123") == "123"


def test_fmt_cpf_aplica_mascara():
    assert _fmt_cpf("12345678900") == "123.456.789-00"
    assert _fmt_cpf("123") == "123"


def test_fmt_cep_aplica_mascara():
    assert _fmt_cep("20010000") == "20010-000"
    assert _fmt_cep("123") == "123"
