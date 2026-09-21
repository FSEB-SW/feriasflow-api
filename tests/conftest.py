"""Fixtures: banco SQLite em memoria e API de calendario simulada (sem rede nos testes)."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.calendario import (
    CalendarioContratoInvalido,
    CalendarioIndisponivel,
    DiasUteis,
    FeriadoNoPeriodo,
    get_cliente_calendario,
)
from app.database import Base, ativar_chaves_estrangeiras, get_db
from app.main import app


def proxima_segunda(minimo_dias: int = 30) -> date:
    """Segunda-feira pelo menos N dias a frente: datas deterministicas quanto ao dia da semana."""
    d = date.today() + timedelta(days=minimo_dias)
    while d.weekday() != 0:
        d += timedelta(days=1)
    return d


SEG = proxima_segunda()  # inicio padrao dos pedidos nos testes
FIM = SEG + timedelta(days=11)  # sexta da 2a semana: 12 corridos, 10 uteis


class CalendarioFalso:
    """Dubla da API secundaria: mesma interface do ClienteCalendario, sem HTTP."""

    def __init__(self) -> None:
        self.feriados: list[tuple[date, str]] = []
        self.modo = "ok"  # ok | fora | invalido | degradado
        self.chamadas = 0

    def dias_uteis(self, inicio: date, fim: date) -> DiasUteis:
        self.chamadas += 1
        if self.modo == "fora":
            raise CalendarioIndisponivel("simulado: timeout")
        if self.modo == "invalido":
            raise CalendarioContratoInvalido("simulado: campo dias_uteis ausente")
        datas_feriado = {d for d, _ in self.feriados}
        uteis = 0
        dia = inicio
        while dia <= fim:
            if dia.weekday() < 5 and dia not in datas_feriado:
                uteis += 1
            dia += timedelta(days=1)
        return DiasUteis(
            inicio=inicio,
            fim=fim,
            dias_corridos=(fim - inicio).days + 1,
            dias_uteis=uteis,
            feriados=[
                FeriadoNoPeriodo(data=d, nome=n, origem="nacional")
                for d, n in self.feriados
                if inicio <= d <= fim
            ],
            fonte_nacional="indisponivel" if self.modo == "degradado" else "brasilapi",
            aviso="BrasilAPI indisponivel (simulado)" if self.modo == "degradado" else None,
        )

    def disponivel(self) -> bool:
        return self.modo != "fora"


@pytest.fixture()
def calendario():
    return CalendarioFalso()


@pytest.fixture()
def client(calendario):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    ativar_chaves_estrangeiras(engine)
    Base.metadata.create_all(engine)
    sessao = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _db():
        db = sessao()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_cliente_calendario] = lambda: calendario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


CARLA = {"nome": "Carla Souza", "email": "carla@empresa.com", "equipe": "Engenharia"}


@pytest.fixture()
def carla_id(client) -> int:
    return client.post("/colaboradores", json=CARLA).json()["id"]


def pedido_padrao(colaborador_id: int, **extra) -> dict:
    return {
        "colaborador_id": colaborador_id,
        "inicio": SEG.isoformat(),
        "fim": FIM.isoformat(),
        **extra,
    }
