"""FeriasFlow API.

Servico principal do MVP da Sprint 3 (Arquitetura de Software) da pos-graduacao em
Engenharia de Software da PUC-Rio. Contexto delimitado "Ferias": colaboradores, saldo e o
agregado Pedido de Ferias com sua maquina de estados. Consome a API secundaria de calendario
(feriasflow-calendario-api), que por sua vez consome a BrasilAPI.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from .config import settings
from .database import Base, engine
from .routers import colaboradores, health, pedidos

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="FeriasFlow API",
    version=settings.versao,
    description=(
        "Planejamento e aprovacao de ferias de equipes: cadastro de colaboradores com saldo, "
        "pedidos de ferias validados contra o calendario (dias uteis, feriados, regras da CLT) "
        "e decisao do gestor (aprovar, recusar, cancelar).\n\n"
        "MVP - Sprint Arquitetura de Software - Pos-graduacao em Engenharia de Software, PUC-Rio."
    ),
    lifespan=lifespan,
)

app.include_router(colaboradores.router)
app.include_router(pedidos.router)
app.include_router(health.router)


@app.get("/", include_in_schema=False)
def raiz():
    return RedirectResponse(url="/docs")
