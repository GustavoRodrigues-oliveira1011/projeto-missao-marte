"""Passos (steps) do BDD para tests/features/solicitacao_oxigenio.feature.

O gerenciador usado é o REAL; apenas a telemetria (dependência externa) é um
MagicMock, para que os cenários possam verificar os alertas enviados à Terra.
"""

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from src.gerenciador_recursos import (
    GerenciadorRecursosMarte,
    OxigenioInsuficienteError,
    QuantidadeInvalidaError,
)

scenarios("features/solicitacao_oxigenio.feature")


# ------------------------------------------------------------------ Dado (Given)
@given(
    parsers.parse("que o habitat possui {oxigenio:g} kg de oxigênio e {agua:g} litros de água"),
    target_fixture="habitat",
)
def habitat_com_estoque(oxigenio, agua, telemetria_mock):
    return GerenciadorRecursosMarte(
        oxigenio_kg=oxigenio, agua_litros=agua, astronautas=0, servico_telemetria=telemetria_mock
    )


@given(parsers.parse("que a tripulação possui {quantidade:d} astronautas"))
def tripulacao(habitat, quantidade):
    habitat.registrar_astronautas(quantidade)


@given(parsers.parse('que o habitat está em nível de emergência "{nivel}"'))
def nivel_emergencia(habitat, nivel, telemetria_mock):
    habitat.definir_nivel_emergencia(nivel)
    # Os cenários avaliam apenas os alertas gerados pela solicitação.
    telemetria_mock.reset_mock()


@given(parsers.parse("que uma cota de racionamento de {percentual:d}% foi aplicada"))
def cota_racionamento(habitat, percentual):
    habitat.aplicar_cota_racionamento(percentual / 100)


# ------------------------------------------------------------------ Quando (When)
@when(
    parsers.parse('o astronauta "{astronauta}" solicitar {quantidade:g} kg de oxigênio'),
    target_fixture="resultado",
)
def solicitar_oxigenio(habitat, astronauta, quantidade):
    """Executa a solicitação e guarda o registro OU a exceção para os passos Então."""
    try:
        return {"registro": habitat.solicitar_oxigenio(quantidade, astronauta), "erro": None}
    except (OxigenioInsuficienteError, QuantidadeInvalidaError) as erro:
        return {"registro": None, "erro": erro}


# ------------------------------------------------------------------ Então (Then)
@then(parsers.parse("a solicitação deve ser aprovada com {concedido:g} kg concedidos"))
def solicitacao_aprovada(resultado, concedido):
    assert resultado["erro"] is None
    assert resultado["registro"]["concedido"] == pytest.approx(concedido)


@then("a solicitação deve ser recusada por oxigênio insuficiente")
def recusada_por_estoque(resultado):
    assert isinstance(resultado["erro"], OxigenioInsuficienteError)


@then("a solicitação deve ser recusada por quantidade inválida")
def recusada_por_quantidade(resultado):
    assert isinstance(resultado["erro"], QuantidadeInvalidaError)


@then(parsers.parse("o estoque de oxigênio deve ser de {estoque:g} kg"))
def estoque_oxigenio(habitat, estoque):
    assert habitat.oxigenio_kg == pytest.approx(estoque)


@then("nenhum alerta de emergência deve ser enviado à Terra")
def nenhum_alerta(telemetria_mock):
    telemetria_mock.enviar_alerta_emergencia.assert_not_called()


@then(parsers.parse('o alerta "{codigo}" deve ser enviado à Terra para "{astronauta}"'))
def alerta_enviado(telemetria_mock, resultado, codigo, astronauta):
    registro = resultado["registro"]
    telemetria_mock.enviar_alerta_emergencia.assert_called_once_with(
        codigo,
        f"{astronauta} recebeu {registro['concedido']:.2f} de oxigenio durante nível CRITICO",
        registro,
    )
