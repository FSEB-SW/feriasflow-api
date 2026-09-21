"""Modelo persistido do contexto "Ferias": Colaborador e o agregado PedidoFerias.

O PedidoFerias e o agregado raiz deste servico: e ele quem guarda a maquina de estados
(solicitado -> aprovado | recusado; solicitado/aprovado -> cancelado) e so este servico a altera.
"""
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _agora() -> datetime:
    return datetime.now(timezone.utc)


class Colaborador(Base):
    __tablename__ = "colaboradores"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True, nullable=False)
    equipe: Mapped[str | None] = mapped_column(String(80))
    saldo_dias: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=_agora, nullable=False)

    pedidos: Mapped[list["PedidoFerias"]] = relationship(
        back_populates="colaborador", cascade="all, delete-orphan"
    )


class PedidoFerias(Base):
    __tablename__ = "pedidos_ferias"

    id: Mapped[int] = mapped_column(primary_key=True)
    colaborador_id: Mapped[int] = mapped_column(
        ForeignKey("colaboradores.id", ondelete="CASCADE"), index=True, nullable=False
    )
    inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fim: Mapped[date] = mapped_column(Date, nullable=False)
    dias_corridos: Mapped[int] = mapped_column(Integer, nullable=False)
    dias_uteis: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="solicitado", index=True)
    observacao: Mapped[str | None] = mapped_column(Text)
    motivo_recusa: Mapped[str | None] = mapped_column(Text)
    aviso_calendario: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=_agora, nullable=False)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, default=_agora, onupdate=_agora, nullable=False
    )

    colaborador: Mapped[Colaborador] = relationship(back_populates="pedidos")
