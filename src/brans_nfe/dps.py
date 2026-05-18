from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from nfelib.nfse.bindings.v1_0 import dps_v1_00
from nfelib.nfse.bindings.v1_0 import tipos_complexos_v1_00 as tc
from nfelib.nfse.bindings.v1_0 import tipos_simples_v1_00 as ts
from xsdata.formats.dataclass.serializers import XmlSerializer
from xsdata.formats.dataclass.serializers.config import SerializerConfig

from .enums import Ambiente, RegimeEspecialTributacao, RegimeTributario, ResponsavelRetencaoIss
from .exceptions import ValidacaoDpsError
from .models import NotaServico
from .signer import NAMESPACE_DPS


SUBSTITUICOES_LATIN1 = {
    "–": "-",
    "—": "-",
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
    "…": "...",
    " ": " ",
}


def construir_dps(nota: NotaServico, ambiente: Ambiente) -> dps_v1_00.Dps:
    _validar(nota)

    cod_mun_emi = nota.prestador.endereco.codigo_municipio_ibge
    cod_mun_prest = nota.servico.codigo_municipio_prestacao or cod_mun_emi

    tp_amb = (
        ts.TstipoAmbiente.VALUE_1
        if ambiente == Ambiente.PRODUCAO
        else ts.TstipoAmbiente.VALUE_2
    )

    prest = _montar_prestador(nota)
    toma = _montar_tomador(nota, cod_mun_prest)
    serv = _montar_servico(nota, cod_mun_prest)
    valores = _montar_valores(nota)

    serie = nota.serie_rps or "1"
    n_dps = nota.numero_rps
    id_dps = _gerar_id_dps(cod_mun_emi, nota.prestador.cnpj, serie, n_dps)

    inf_dps = tc.TcinfDps(
        tpAmb=tp_amb,
        dhEmi=_agora_brt_iso(),
        verAplic=nota.versao_aplicacao,
        serie=serie,
        nDPS=n_dps,
        dCompet=nota.data_competencia.isoformat(),
        tpEmit=ts.TsemitenteDps.VALUE_1,
        cLocEmi=cod_mun_emi,
        prest=prest,
        toma=toma,
        serv=serv,
        valores=valores,
        Id=id_dps,
    )

    return dps_v1_00.Dps(infDPS=inf_dps, versao="1.00")


def serializar_dps(dps: dps_v1_00.Dps) -> bytes:
    config = SerializerConfig(pretty_print=False, xml_declaration=True, encoding="UTF-8")
    serializer = XmlSerializer(config=config)
    xml_str = serializer.render(dps, ns_map={None: NAMESPACE_DPS})
    return xml_str.encode("utf-8")


def _validar(nota: NotaServico) -> None:
    cep = nota.prestador.endereco.cep
    if len(cep) != 8:
        raise ValidacaoDpsError(
            "CEP da empresa prestadora invalido. Deve ter 8 digitos."
        )
    if nota.tomador.endereco and len(nota.tomador.endereco.cep) != 8:
        raise ValidacaoDpsError(
            f"CEP do tomador '{nota.tomador.razao_social}' invalido."
        )
    c_trib_nac = nota.servico.codigo_tributacao_nacional
    if len(c_trib_nac) != 6:
        raise ValidacaoDpsError(
            "Codigo de Tributacao Nacional (cTribNac) invalido. "
            "Use 6 digitos (Item LC 116 + Subitem + Desdobro)."
        )


def _montar_prestador(nota: NotaServico) -> tc.TcinfoPrestador:
    simp_map = {
        RegimeTributario.MEI: ts.TsopSimpNac.VALUE_2,
        RegimeTributario.SIMPLES_NACIONAL: ts.TsopSimpNac.VALUE_3,
    }
    esp_map = {
        RegimeEspecialTributacao.NENHUM: ts.TsregEspTrib.VALUE_0,
        RegimeEspecialTributacao.ATO_COOPERADO: ts.TsregEspTrib.VALUE_1,
        RegimeEspecialTributacao.ESTIMATIVA: ts.TsregEspTrib.VALUE_2,
        RegimeEspecialTributacao.MICROEMPRESA_MUNICIPAL: ts.TsregEspTrib.VALUE_3,
        RegimeEspecialTributacao.NOTARIO_REGISTRADOR: ts.TsregEspTrib.VALUE_4,
        RegimeEspecialTributacao.PROFISSIONAL_AUTONOMO: ts.TsregEspTrib.VALUE_5,
        RegimeEspecialTributacao.SOCIEDADE_PROFISSIONAIS: ts.TsregEspTrib.VALUE_6,
    }
    reg_trib = tc.TcregTrib(
        opSimpNac=simp_map.get(nota.prestador.regime_tributario, ts.TsopSimpNac.VALUE_1),
        regEspTrib=esp_map.get(nota.prestador.regime_especial, ts.TsregEspTrib.VALUE_0),
    )
    return tc.TcinfoPrestador(CNPJ=nota.prestador.cnpj, regTrib=reg_trib)


def _montar_tomador(nota: NotaServico, cod_mun_fallback: str) -> tc.TcinfoPessoa:
    tom = nota.tomador
    end = None
    if tom.endereco:
        end = tc.Tcendereco(
            endNac=tc.TcenderNac(
                cMun=tom.endereco.codigo_municipio_ibge or cod_mun_fallback,
                CEP=tom.endereco.cep,
            ),
            xLgr=tom.endereco.logradouro,
            nro=tom.endereco.numero or "S/N",
            xCpl=tom.endereco.complemento,
            xBairro=tom.endereco.bairro,
        )
    return tc.TcinfoPessoa(
        CNPJ=tom.cpf_cnpj if len(tom.cpf_cnpj) == 14 else None,
        CPF=tom.cpf_cnpj if len(tom.cpf_cnpj) == 11 else None,
        IM=tom.inscricao_municipal,
        xNome=tom.razao_social,
        end=end,
        fone=tom.telefone,
        email=tom.email,
    )


def _montar_servico(nota: NotaServico, cod_mun_prest: str) -> tc.Tcserv:
    loc_prest = tc.TclocPrest(cLocPrestacao=cod_mun_prest)
    cserv = tc.Tccserv(
        cTribNac=nota.servico.codigo_tributacao_nacional,
        cTribMun=nota.servico.codigo_tributacao_municipal,
        xDescServ=nota.servico.discriminacao,
        cNBS=nota.servico.codigo_nbs,
    )
    info_compl = _montar_info_complementar(nota.servico.observacoes)
    return tc.Tcserv(locPrest=loc_prest, cServ=cserv, infoCompl=info_compl)


def _montar_info_complementar(observacoes: str | None) -> tc.TcinfoCompl | None:
    if not observacoes:
        return None
    texto = observacoes
    for orig, sub in SUBSTITUICOES_LATIN1.items():
        texto = texto.replace(orig, sub)
    texto = re.sub(r"[\r\n\t]+", " | ", texto)
    texto = re.sub(r"[\x00-\x1f\x7f]", "", texto)
    texto = "".join(c for c in texto if ord(c) <= 0xFF)
    texto = texto.strip()[:2000].strip()
    if not texto:
        return None
    return tc.TcinfoCompl(xInfComp=texto)


def _montar_valores(nota: NotaServico) -> tc.TcinfoValores:
    iss = nota.iss
    pis_cofins = nota.pis_cofins
    retencoes = nota.retencoes

    tp_ret_iss = ts.TstipoRetIssqn.VALUE_1
    if iss.retido:
        if iss.responsavel == ResponsavelRetencaoIss.TOMADOR:
            tp_ret_iss = ts.TstipoRetIssqn.VALUE_2
        elif iss.responsavel == ResponsavelRetencaoIss.INTERMEDIARIO:
            tp_ret_iss = ts.TstipoRetIssqn.VALUE_3

    trib_mun = tc.TctribMunicipal(
        tribISSQN=ts.TstribIssqn.VALUE_1,
        tpRetISSQN=tp_ret_iss,
    )

    if pis_cofins and pis_cofins.retidos:
        tp_ret_code = "3"
        v_ret_csll_total = (pis_cofins.valor_pis + pis_cofins.valor_cofins + retencoes.valor_csll)
    elif retencoes.valor_csll:
        tp_ret_code = "8"
        v_ret_csll_total = retencoes.valor_csll
    else:
        tp_ret_code = "0"
        v_ret_csll_total = Decimal("0")

    piscofins_node = None
    if pis_cofins and (pis_cofins.cst or pis_cofins.aliquota_pis or pis_cofins.aliquota_cofins):
        cst_value = pis_cofins.cst.value if pis_cofins.cst else "01"
        cst_enum = getattr(ts.TstipoCst, f"VALUE_{cst_value}", ts.TstipoCst.VALUE_01)
        piscofins_node = tc.TctribOutrosPisCofins(
            CST=cst_enum,
            vBCPisCofins=_fmt(pis_cofins.base_calculo or nota.valores.valor_liquido),
            pAliqPis=_fmt(pis_cofins.aliquota_pis),
            pAliqCofins=_fmt(pis_cofins.aliquota_cofins),
            vPis=_fmt(pis_cofins.valor_pis),
            vCofins=_fmt(pis_cofins.valor_cofins),
            tpRetPisCofins=getattr(ts.TstipoRetPiscofins, f"VALUE_{tp_ret_code}"),
        )

    trib_fed = tc.TctribNacional(
        piscofins=piscofins_node,
        vRetIRRF=_fmt(retencoes.valor_irrf) if retencoes.valor_irrf else None,
        vRetCSLL=_fmt(v_ret_csll_total) if v_ret_csll_total else None,
        vRetCP=_fmt(retencoes.valor_inss) if retencoes.valor_inss else None,
    )

    valor_pis = pis_cofins.valor_pis if pis_cofins else Decimal("0")
    valor_cofins = pis_cofins.valor_cofins if pis_cofins else Decimal("0")
    valor_trib_fed = (
        valor_pis
        + valor_cofins
        + retencoes.valor_csll
        + retencoes.valor_irrf
        + retencoes.valor_inss
    )
    valor_trib_mun = iss.valor

    e_simples_ou_mei = nota.prestador.regime_tributario in (
        RegimeTributario.SIMPLES_NACIONAL,
        RegimeTributario.MEI,
    )

    if valor_trib_fed > 0 or valor_trib_mun > 0:
        tot_trib = tc.TctribTotal(
            vTotTrib=tc.TctribTotalMonet(
                vTotTribFed=_fmt(valor_trib_fed),
                vTotTribEst="0.00",
                vTotTribMun=_fmt(valor_trib_mun),
            ),
        )
    elif e_simples_ou_mei:
        tot_trib = tc.TctribTotal(indTotTrib=ts.TstipoIndTotTrib.VALUE_0)
    else:
        tot_trib = tc.TctribTotal(
            vTotTrib=tc.TctribTotalMonet(
                vTotTribFed="0.00",
                vTotTribEst="0.00",
                vTotTribMun="0.00",
            ),
        )

    descontos = None
    if (
        nota.valores.desconto_incondicional
        or nota.valores.desconto_condicional
    ):
        descontos = tc.TcvdescCondIncond(
            vDescIncond=_fmt(nota.valores.desconto_incondicional),
            vDescCond=_fmt(nota.valores.desconto_condicional),
        )

    ded_red = None
    if iss.deducoes:
        ded_red = tc.TcinfoDedRed(vDR=_fmt(iss.deducoes))

    return tc.TcinfoValores(
        vServPrest=tc.TcvservPrest(vServ=_fmt(nota.valores.valor_bruto)),
        vDescCondIncond=descontos,
        vDedRed=ded_red,
        trib=tc.TcinfoTributacao(tribMun=trib_mun, tribFed=trib_fed, totTrib=tot_trib),
    )


def _gerar_id_dps(cod_mun_emi: str, cnpj: str, serie: str, numero: str) -> str:
    tp_insc = "2"
    n_insc = cnpj.zfill(14)
    serie_id = serie.zfill(5)
    ndps_id = numero.zfill(15)
    return f"DPS{cod_mun_emi.zfill(7)}{tp_insc}{n_insc}{serie_id}{ndps_id}"


def _agora_brt_iso() -> str:
    agora = datetime.now(timezone(timedelta(hours=-3))) - timedelta(minutes=5)
    return agora.strftime("%Y-%m-%dT%H:%M:%S-03:00")


def _fmt(valor: Decimal | int | float | str | None) -> str:
    return f"{Decimal(str(valor or 0)):.2f}"
