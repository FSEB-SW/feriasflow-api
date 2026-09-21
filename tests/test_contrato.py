"""Teste de contrato (lado do CONSUMIDOR).

`contratos/dias-uteis.schema.json` descreve o que a feriasflow-api espera de GET /dias-uteis
da feriasflow-calendario-api. O produtor testa a resposta real contra o mesmo arquivo. Aqui:
1. o exemplo gravado da resposta real do produtor respeita o contrato;
2. o cliente HTTP consome esse exemplo corretamente;
3. respostas fora do contrato ou indisponibilidade viram excecoes tipadas (502/503 nas rotas).
"""
import json
from datetime import date
from pathlib import Path

import httpx
import pytest
from jsonschema import Draft202012Validator, FormatChecker

from app.calendario import CalendarioContratoInvalido, CalendarioIndisponivel, ClienteCalendario

CONTRATO = json.loads(
    (Path(__file__).resolve().parents[1] / "contratos" / "dias-uteis.schema.json").read_text("utf-8")
)
validador = Draft202012Validator(CONTRATO, format_checker=FormatChecker())

# Resposta real do produtor (feriasflow-calendario-api) gravada em 21/09/2026
EXEMPLO_PRODUTOR = {
    "inicio": "2026-09-01",
    "fim": "2026-09-30",
    "dias_corridos": 30,
    "dias_uteis": 21,
    "fins_de_semana": 8,
    "feriados": [{"data": "2026-09-07", "nome": "Independencia do Brasil", "origem": "nacional"}],
    "fonte_nacional": "brasilapi",
    "aviso": None,
}


def _cliente(handler) -> ClienteCalendario:
    return ClienteCalendario(base_url="http://calendario.test", transport=httpx.MockTransport(handler))


def test_exemplo_do_produtor_respeita_o_contrato():
    erros = list(validador.iter_errors(EXEMPLO_PRODUTOR))
    assert not erros, [e.message for e in erros]


def test_cliente_consome_o_exemplo():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/dias-uteis"
        assert request.url.params["inicio"] == "2026-09-01"
        return httpx.Response(200, json=EXEMPLO_PRODUTOR)

    resposta = _cliente(handler).dias_uteis(date(2026, 9, 1), date(2026, 9, 30))
    assert resposta.dias_uteis == 21
    assert resposta.feriados[0].data == date(2026, 9, 7)
    assert resposta.aviso is None


def test_resposta_fora_do_contrato_e_rejeitada():
    quebrado = {**EXEMPLO_PRODUTOR}
    del quebrado["dias_uteis"]
    assert list(validador.iter_errors(quebrado)), "o schema tambem pega o campo ausente"

    cliente = _cliente(lambda r: httpx.Response(200, json=quebrado))
    with pytest.raises(CalendarioContratoInvalido):
        cliente.dias_uteis(date(2026, 9, 1), date(2026, 9, 30))


def test_indisponibilidade_vira_excecao_tipada():
    cliente = _cliente(lambda r: httpx.Response(503, text="fora"))
    with pytest.raises(CalendarioIndisponivel):
        cliente.dias_uteis(date(2026, 9, 1), date(2026, 9, 30))

    def timeout(_: httpx.Request):
        raise httpx.ReadTimeout("simulado")

    with pytest.raises(CalendarioIndisponivel):
        _cliente(timeout).dias_uteis(date(2026, 9, 1), date(2026, 9, 30))
    assert _cliente(timeout).disponivel() is False
