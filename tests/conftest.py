"""Fixtures compartilhadas da suíte de testes do ECLSS."""

from types import MappingProxyType
from unittest.mock import MagicMock

import pytest

from src.gerenciador_recursos import GerenciadorRecursosMarte
from src.servico_telemetria import ServicoTelemetriaEspacial


@pytest.fixture(scope="session")
def parametros_habitat():
    """Parâmetros iniciais do habitat, carregados uma única vez por sessão.

    MappingProxyType deixa o dicionário somente leitura: nenhum teste consegue
    alterar os parâmetros e contaminar os demais.
    """
    parametros = MappingProxyType(
        {
            "oxigenio_kg": 500.0,
            "agua_litros": 2000.0,
            "astronautas": 4,
            "consumo_oxigenio_kg": 0.84,
            "consumo_agua_litros": 3.5,
        }
    )
    yield parametros


@pytest.fixture
def gerenciador(parametros_habitat):
    """Instância limpa do gerenciador (sem telemetria) para cada teste.

    Usada nos testes de lógica real: nenhum mock envolvido.
    """
    instancia = GerenciadorRecursosMarte(**parametros_habitat)
    yield instancia
    # Limpeza: descarta o estado acumulado durante o teste.
    instancia.historico_solicitacoes.clear()
    instancia.alertas_pendentes.clear()


@pytest.fixture
def telemetria_mock():
    """Dublê da telemetria que simula respostas da estação terrestre."""
    mock = MagicMock(spec=ServicoTelemetriaEspacial)
    mock.enviar_relatorio_status.return_value = {"status": "recebido", "protocolo": "REL-001"}
    mock.enviar_alerta_emergencia.return_value = {"status": "recebido", "protocolo": "ALR-001"}
    yield mock
    mock.reset_mock()


@pytest.fixture
def gerenciador_com_telemetria(parametros_habitat, telemetria_mock):
    """Gerenciador real com a dependência externa (telemetria) isolada por mock."""
    instancia = GerenciadorRecursosMarte(**parametros_habitat, servico_telemetria=telemetria_mock)
    yield instancia
    instancia.historico_solicitacoes.clear()
    instancia.alertas_pendentes.clear()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Guarda o resultado de cada fase (setup/call/teardown) no item do teste.

    Permite que a fixture do WebDriver saiba, no teardown, se o teste falhou
    e então capture o screenshot de evidência.
    """
    resultado = yield
    relatorio = resultado.get_result()
    setattr(item, f"rep_{relatorio.when}", relatorio)
