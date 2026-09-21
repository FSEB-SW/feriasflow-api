"""Contratos de entrada e saida (Pydantic)."""
from datetime import date, datetime
from enum import Enum
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

EMAIL = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"


class StatusPedido(str, Enum):
    solicitado = "solicitado"
    aprovado = "aprovado"
    recusado = "recusado"
    cancelado = "cancelado"


# ----- Colaborador -----------------------------------------------------------


class ColaboradorCriar(BaseModel):
    nome: str = Field(min_length=2, max_length=120, examples=["Carla Souza"])
    email: str = Field(pattern=EMAIL, max_length=160, examples=["carla@empresa.com"])
    equipe: str | None = Field(default=None, max_length=80, examples=["Engenharia"])
    saldo_dias: int = Field(default=30, ge=0, le=60, description="Saldo de dias de ferias")


class ColaboradorAtualizar(BaseModel):
    nome: str | None = Field(default=None, min_length=2, max_length=120)
    email: str | None = Field(default=None, pattern=EMAIL, max_length=160)
    equipe: str | None = Field(default=None, max_length=80)
    saldo_dias: int | None = Field(default=None, ge=0, le=60)
    ativo: bool | None = None


class ColaboradorResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nome: str
    email: str
    equipe: str | None
    saldo_dias: int
    dias_reservados: int = Field(description="Soma dos dias de pedidos ainda em analise")
    saldo_disponivel: int = Field(description="saldo_dias - dias_reservados")
    ativo: bool


class ColaboradorResumo(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nome: str
    equipe: str | None


# ----- Pedido de ferias ------------------------------------------------------


class PedidoCriar(BaseModel):
    colaborador_id: int
    inicio: date = Field(examples=["2026-11-09"])
    fim: date = Field(examples=["2026-11-20"])
    observacao: str | None = Field(default=None, max_length=500)


class PedidoAtualizar(BaseModel):
    inicio: date | None = None
    fim: date | None = None
    observacao: str | None = Field(default=None, max_length=500)


class Recusa(BaseModel):
    motivo: str = Field(min_length=3, max_length=500, examples=["Sobreposicao com a parada da unidade"])


class PedidoResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    colaborador: ColaboradorResumo
    inicio: date
    fim: date
    dias_corridos: int
    dias_uteis: int
    status: StatusPedido
    observacao: str | None
    motivo_recusa: str | None
    aviso_calendario: str | None
    criado_em: datetime
    atualizado_em: datetime


T = TypeVar("T")


class Pagina(BaseModel, Generic[T]):
    itens: list[T]
    total: int
    pagina: int
    tamanho: int
    paginas: int


# ----- Operacao --------------------------------------------------------------


class HealthResposta(BaseModel):
    status: Literal["ok", "degradado"]
    servico: str
    versao: str
    banco: Literal["ok", "erro"]
    calendario_api: Literal["ok", "indisponivel"]
