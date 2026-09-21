"""Cliente da API secundaria (feriasflow-calendario-api).

E o unico ponto do servico que fala com o calendario. O contrato esperado esta em
`contratos/dias-uteis.schema.json` (copia identica no repositorio do produtor).
Falhas viram excecoes tipadas que a camada de rotas traduz em 503 (fora do ar / timeout)
ou 502 (respondeu, mas fora do contrato).
"""
import logging
from datetime import date

import httpx
from pydantic import BaseModel, ValidationError

from .config import settings

log = logging.getLogger("feriasflow.calendario")


class FeriadoNoPeriodo(BaseModel):
    data: date
    nome: str
    origem: str


class DiasUteis(BaseModel):
    """Modelo do consumidor: so os campos que a API principal realmente usa."""

    inicio: date
    fim: date
    dias_corridos: int
    dias_uteis: int
    feriados: list[FeriadoNoPeriodo]
    fonte_nacional: str
    aviso: str | None = None


class CalendarioIndisponivel(Exception):
    """A API de calendario nao respondeu (rede, timeout, 5xx)."""


class CalendarioContratoInvalido(Exception):
    """A API de calendario respondeu algo fora do contrato esperado."""


class ClienteCalendario:
    def __init__(
        self,
        base_url: str = settings.calendario_url,
        timeout: float = settings.calendario_timeout,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(timeout=timeout, transport=transport)

    def dias_uteis(self, inicio: date, fim: date) -> DiasUteis:
        try:
            resposta = self._http.get(
                f"{self.base_url}/dias-uteis",
                params={"inicio": inicio.isoformat(), "fim": fim.isoformat()},
            )
        except httpx.HTTPError as exc:
            log.error("calendario inacessivel: %s", exc)
            raise CalendarioIndisponivel(str(exc)) from exc

        if resposta.status_code >= 500:
            raise CalendarioIndisponivel(f"HTTP {resposta.status_code}")
        if resposta.status_code != 200:
            # 4xx: a requisicao que montamos e invalida para o produtor -> contrato quebrado
            raise CalendarioContratoInvalido(f"HTTP {resposta.status_code}: {resposta.text[:200]}")
        try:
            return DiasUteis.model_validate(resposta.json())
        except (ValueError, ValidationError) as exc:
            raise CalendarioContratoInvalido(str(exc)) from exc

    def disponivel(self) -> bool:
        try:
            r = self._http.get(f"{self.base_url}/health", timeout=3)
            return r.status_code == 200
        except httpx.HTTPError:
            return False


cliente = ClienteCalendario()


def get_cliente_calendario() -> ClienteCalendario:
    """Dependencia FastAPI (substituida nos testes por um cliente simulado)."""
    return cliente
