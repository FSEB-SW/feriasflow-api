"""Configuracao por variaveis de ambiente (12-factor: config fora do codigo)."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/feriasflow.db")
    calendario_url: str = os.getenv("CALENDARIO_URL", "http://localhost:8001")
    calendario_timeout: float = float(os.getenv("CALENDARIO_TIMEOUT", "5"))
    saldo_inicial_dias: int = int(os.getenv("SALDO_INICIAL_DIAS", "30"))
    minimo_dias_corridos: int = int(os.getenv("MINIMO_DIAS_CORRIDOS", "5"))
    versao: str = "1.0.0"


settings = Settings()
