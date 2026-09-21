"""Regras de negocio do pedido de ferias (o "miolo" do dominio, sem HTTP).

Regras aplicadas ao solicitar/alterar um pedido:
1. fim >= inicio e inicio nao pode estar no passado;
2. periodo minimo de 5 dias corridos (CLT, art. 134, par. 1: nenhum periodo inferior a 5 dias);
3. inicio nao pode cair em sexta, sabado ou domingo nem nos 2 dias que antecedem feriado
   (CLT, art. 134, par. 3) - os feriados vem da API de calendario;
4. dias corridos nao podem exceder o saldo disponivel do colaborador
   (saldo - dias ja reservados por pedidos em analise);
5. sem sobreposicao com outro pedido solicitado/aprovado do mesmo colaborador.

Transicoes do agregado (maquina de estados):
  solicitado -> aprovado (debita saldo) | recusado (com motivo) | cancelado
  aprovado   -> cancelado (devolve saldo)
"""
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .calendario import ClienteCalendario, DiasUteis
from .config import settings
from .models import Colaborador, PedidoFerias

STATUS_ATIVOS = ("solicitado", "aprovado")
TRANSICOES = {
    "aprovar": {"solicitado": "aprovado"},
    "recusar": {"solicitado": "recusado"},
    "cancelar": {"solicitado": "cancelado", "aprovado": "cancelado"},
}


class RegraViolada(Exception):
    def __init__(self, mensagem: str, status_http: int = 422) -> None:
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status_http = status_http


@dataclass
class PeriodoValidado:
    dias_corridos: int
    dias_uteis: int
    aviso_calendario: str | None


def dias_reservados(db: Session, colaborador_id: int) -> int:
    return db.scalar(
        select(func.coalesce(func.sum(PedidoFerias.dias_corridos), 0)).where(
            PedidoFerias.colaborador_id == colaborador_id,
            PedidoFerias.status == "solicitado",
        )
    )


def validar_periodo(
    db: Session,
    calendario: ClienteCalendario,
    colaborador: Colaborador,
    inicio: date,
    fim: date,
    ignorar_pedido_id: int | None = None,
    hoje: date | None = None,
) -> PeriodoValidado:
    hoje = hoje or date.today()

    if not colaborador.ativo:
        raise RegraViolada("Colaborador inativo nao pode solicitar ferias")
    if fim < inicio:
        raise RegraViolada("fim deve ser igual ou posterior ao inicio")
    if inicio < hoje:
        raise RegraViolada("inicio nao pode estar no passado")

    dias_corridos = (fim - inicio).days + 1
    if dias_corridos < settings.minimo_dias_corridos:
        raise RegraViolada(
            f"periodo minimo de {settings.minimo_dias_corridos} dias corridos (CLT art. 134)"
        )

    if inicio.weekday() >= 4:
        raise RegraViolada(
            "inicio nao pode cair em sexta, sabado ou domingo: 2 dias antes do repouso semanal "
            "(CLT art. 134, par. 3)"
        )

    # Chamada sincrona a API secundaria (pode levantar CalendarioIndisponivel / ContratoInvalido)
    calendario_resp: DiasUteis = calendario.dias_uteis(inicio, fim)

    janela = {inicio + timedelta(days=d) for d in range(0, 3)}
    proximos = [f for f in calendario_resp.feriados if f.data in janela]
    if proximos:
        f = proximos[0]
        raise RegraViolada(
            f"inicio nos 2 dias que antecedem feriado ({f.data.isoformat()} - {f.nome}) "
            "(CLT art. 134, par. 3)"
        )

    disponivel = colaborador.saldo_dias - dias_reservados(db, colaborador.id)
    if ignorar_pedido_id is not None:
        atual = db.get(PedidoFerias, ignorar_pedido_id)
        if atual and atual.status == "solicitado":
            disponivel += atual.dias_corridos
    if dias_corridos > disponivel:
        raise RegraViolada(
            f"saldo insuficiente: pedido de {dias_corridos} dias, disponivel {disponivel}"
        )

    consulta = select(PedidoFerias).where(
        PedidoFerias.colaborador_id == colaborador.id,
        PedidoFerias.status.in_(STATUS_ATIVOS),
        PedidoFerias.inicio <= fim,
        PedidoFerias.fim >= inicio,
    )
    if ignorar_pedido_id is not None:
        consulta = consulta.where(PedidoFerias.id != ignorar_pedido_id)
    conflito = db.scalar(consulta)
    if conflito:
        raise RegraViolada(
            f"periodo sobrepoe o pedido #{conflito.id} ({conflito.inicio} a {conflito.fim}, "
            f"{conflito.status})",
            status_http=409,
        )

    return PeriodoValidado(
        dias_corridos=calendario_resp.dias_corridos,
        dias_uteis=calendario_resp.dias_uteis,
        aviso_calendario=calendario_resp.aviso,
    )


def transicionar(pedido: PedidoFerias, acao: str, motivo: str | None = None) -> None:
    """Aplica uma transicao da maquina de estados e o efeito no saldo do colaborador."""
    destino = TRANSICOES[acao].get(pedido.status)
    if destino is None:
        raise RegraViolada(
            f"nao e possivel {acao} um pedido com status '{pedido.status}'", status_http=409
        )
    origem = pedido.status
    pedido.status = destino
    if acao == "aprovar":
        pedido.colaborador.saldo_dias -= pedido.dias_corridos
    elif acao == "recusar":
        pedido.motivo_recusa = motivo
    elif acao == "cancelar" and origem == "aprovado":
        pedido.colaborador.saldo_dias += pedido.dias_corridos
