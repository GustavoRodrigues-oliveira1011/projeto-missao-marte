"""Testes unitários e de integração do GerenciadorRecursosMarte e da telemetria.

* Classes ``TestConsumo``, ``TestEstoque`` etc. validam a lógica REAL do gerenciador,
  sem nenhum mock (fixture ``gerenciador``).
* Classes ``TestIsolamentoTelemetria`` e ``TestServicoTelemetriaEspacial`` usam
  pytest-mock / MagicMock apenas para isolar a comunicação com a Terra.
"""

import json
import math
import urllib.error
from unittest.mock import MagicMock, call

import pytest

from src.gerenciador_recursos import (
    AguaInsuficienteError,
    CotaRacionamentoInvalidaError,
    GerenciadorRecursosMarte,
    NivelEmergenciaInvalidoError,
    OxigenioInsuficienteError,
    QuantidadeInvalidaError,
)
from src.servico_telemetria import FalhaComunicacaoError, ServicoTelemetriaEspacial


# ============================================================ criação e tripulação
class TestCriacao:
    def test_carrega_parametros_iniciais(self, gerenciador, parametros_habitat):
        assert gerenciador.oxigenio_kg == parametros_habitat["oxigenio_kg"]
        assert gerenciador.agua_litros == parametros_habitat["agua_litros"]
        assert gerenciador.astronautas == parametros_habitat["astronautas"]
        assert gerenciador.nivel_emergencia == "NORMAL"
        assert gerenciador.cota_racionamento == 0.0

    def test_fixture_entrega_instancia_limpa_a_cada_teste(self, gerenciador):
        # Se outro teste tivesse vazado estado, o histórico não estaria vazio.
        assert gerenciador.historico_solicitacoes == []
        gerenciador.solicitar_oxigenio(10, "Watney")
        assert len(gerenciador.historico_solicitacoes) == 1

    def test_parametros_habitat_sao_somente_leitura(self, parametros_habitat):
        with pytest.raises(TypeError):
            parametros_habitat["oxigenio_kg"] = 0

    @pytest.mark.parametrize(
        "campo, valor",
        [
            ("oxigenio_kg", -1),
            ("agua_litros", -0.5),
            ("oxigenio_kg", "500"),
            ("agua_litros", math.nan),
            ("consumo_oxigenio_kg", 0),
            ("consumo_agua_litros", -3.5),
        ],
    )
    def test_criacao_com_valores_invalidos(self, parametros_habitat, campo, valor):
        parametros = {**parametros_habitat, campo: valor}
        with pytest.raises(QuantidadeInvalidaError):
            GerenciadorRecursosMarte(**parametros)

    def test_criacao_com_estoque_zerado_e_permitida(self):
        habitat = GerenciadorRecursosMarte(oxigenio_kg=0, agua_litros=0, astronautas=0)
        assert habitat.oxigenio_kg == 0
        assert habitat.agua_litros == 0

    @pytest.mark.parametrize("quantidade", [0, 1, 6, 12])
    def test_registrar_astronautas_validos(self, gerenciador, quantidade):
        gerenciador.registrar_astronautas(quantidade)
        assert gerenciador.astronautas == quantidade

    @pytest.mark.parametrize("quantidade", [-1, 13, 2.5, "4", None, True])
    def test_registrar_astronautas_invalidos(self, gerenciador, quantidade):
        with pytest.raises(QuantidadeInvalidaError):
            gerenciador.registrar_astronautas(quantidade)
        assert gerenciador.astronautas == 4  # estado preservado


# ============================================================ taxas de emergência
class TestTaxaEmergencia:
    @pytest.mark.parametrize(
        "nivel, taxa_esperada",
        [
            ("NORMAL", 1.0),
            ("ALERTA", 1.25),
            ("CRITICO", 1.5),
            ("critico", 1.5),
            ("  alerta ", 1.25),
        ],
    )
    def test_calcular_taxa_emergencia(self, nivel, taxa_esperada):
        assert GerenciadorRecursosMarte.calcular_taxa_emergencia(nivel) == taxa_esperada

    @pytest.mark.parametrize("nivel", ["PANICO", "", "NORMAL!", None, 2, ["CRITICO"]])
    def test_nivel_emergencia_invalido(self, gerenciador, nivel):
        with pytest.raises(NivelEmergenciaInvalidoError):
            gerenciador.definir_nivel_emergencia(nivel)
        assert gerenciador.nivel_emergencia == "NORMAL"

    def test_definir_nivel_emergencia_normaliza_texto(self, gerenciador):
        gerenciador.definir_nivel_emergencia("alerta")
        assert gerenciador.nivel_emergencia == "ALERTA"
        assert gerenciador.em_crise is True


# ============================================================ cotas de racionamento
class TestRacionamento:
    @pytest.mark.parametrize("percentual", [0, 0.1, 0.25, 0.5])
    def test_aplicar_cota_valida(self, gerenciador, percentual):
        gerenciador.aplicar_cota_racionamento(percentual)
        assert gerenciador.cota_racionamento == percentual

    @pytest.mark.parametrize("percentual", [-0.1, 0.51, 1, 50, "0.2", None, True])
    def test_aplicar_cota_invalida(self, gerenciador, percentual):
        with pytest.raises(CotaRacionamentoInvalidaError):
            gerenciador.aplicar_cota_racionamento(percentual)
        assert gerenciador.cota_racionamento == 0.0


# ============================================================ consumo diário
class TestConsumo:
    @pytest.mark.parametrize(
        "astronautas, nivel, racionamento, oxigenio_esperado, agua_esperada",
        [
            (1, "NORMAL", 0.0, 0.84, 3.5),
            (4, "NORMAL", 0.0, 3.36, 14.0),
            (6, "ALERTA", 0.0, 6.30, 26.25),
            (4, "CRITICO", 0.0, 5.04, 21.0),
            (4, "CRITICO", 0.2, 4.032, 16.8),
            (10, "NORMAL", 0.5, 4.20, 17.5),
            (12, "ALERTA", 0.25, 9.45, 39.375),
            (0, "CRITICO", 0.0, 0.0, 0.0),
        ],
    )
    def test_consumo_diario_do_habitat(
        self, gerenciador, astronautas, nivel, racionamento, oxigenio_esperado, agua_esperada
    ):
        gerenciador.registrar_astronautas(astronautas)
        gerenciador.definir_nivel_emergencia(nivel)
        gerenciador.aplicar_cota_racionamento(racionamento)

        assert gerenciador.calcular_consumo_oxigenio_diario() == pytest.approx(oxigenio_esperado)
        assert gerenciador.calcular_consumo_agua_diario() == pytest.approx(agua_esperada)

    @pytest.mark.parametrize(
        "nivel, racionamento, oxigenio_por_astronauta",
        [("NORMAL", 0.0, 0.84), ("ALERTA", 0.0, 1.05), ("CRITICO", 0.0, 1.26), ("CRITICO", 0.5, 0.63)],
    )
    def test_consumo_por_astronauta(self, gerenciador, nivel, racionamento, oxigenio_por_astronauta):
        gerenciador.definir_nivel_emergencia(nivel)
        gerenciador.aplicar_cota_racionamento(racionamento)
        assert gerenciador.calcular_consumo_oxigenio_astronauta() == pytest.approx(oxigenio_por_astronauta)

    @pytest.mark.parametrize(
        "oxigenio, agua, astronautas, dias_esperados",
        [
            (500, 2000, 4, 2000 / 14),  # água é o recurso limitante
            (84, 2000, 1, 100.0),  # oxigênio é o recurso limitante
            (0, 2000, 4, 0.0),
        ],
    )
    def test_dias_autonomia(self, oxigenio, agua, astronautas, dias_esperados):
        habitat = GerenciadorRecursosMarte(oxigenio, agua, astronautas)
        assert habitat.calcular_dias_autonomia() == pytest.approx(dias_esperados)

    def test_autonomia_infinita_sem_tripulacao(self, gerenciador):
        gerenciador.registrar_astronautas(0)
        assert gerenciador.calcular_dias_autonomia() == math.inf

    def test_consumir_dia_desconta_estoque(self, gerenciador):
        consumo = gerenciador.consumir_dia()
        assert consumo == {"oxigenio_kg": pytest.approx(3.36), "agua_litros": pytest.approx(14.0)}
        assert gerenciador.oxigenio_kg == pytest.approx(496.64)
        assert gerenciador.agua_litros == pytest.approx(1986.0)
        assert gerenciador.dia_missao == 1

    def test_consumir_dia_sem_oxigenio_suficiente(self):
        habitat = GerenciadorRecursosMarte(oxigenio_kg=3.0, agua_litros=2000, astronautas=4)
        with pytest.raises(OxigenioInsuficienteError):
            habitat.consumir_dia()
        assert habitat.oxigenio_kg == 3.0
        assert habitat.agua_litros == 2000
        assert habitat.dia_missao == 0

    def test_consumir_dia_sem_agua_suficiente(self):
        habitat = GerenciadorRecursosMarte(oxigenio_kg=500, agua_litros=10, astronautas=4)
        with pytest.raises(AguaInsuficienteError):
            habitat.consumir_dia()
        assert habitat.oxigenio_kg == 500  # nada é descontado se faltar qualquer recurso

    def test_consumir_dia_ate_esgotar_exatamente(self):
        habitat = GerenciadorRecursosMarte(oxigenio_kg=0.84 * 2, agua_litros=3.5 * 2, astronautas=1)
        habitat.consumir_dia()
        habitat.consumir_dia()
        assert habitat.oxigenio_kg == pytest.approx(0)
        with pytest.raises(OxigenioInsuficienteError):
            habitat.consumir_dia()


# ============================================================ estoque e solicitações
class TestEstoque:
    @pytest.mark.parametrize("quantidade", [0, 1, 250, 499.99, 500])
    def test_validar_estoque_oxigenio_dentro_do_limite(self, gerenciador, quantidade):
        assert gerenciador.validar_estoque_oxigenio(quantidade) is True

    @pytest.mark.parametrize("quantidade", [500.01, 501, 10_000])
    def test_validar_estoque_oxigenio_acima_do_limite(self, gerenciador, quantidade):
        with pytest.raises(OxigenioInsuficienteError) as erro:
            gerenciador.validar_estoque_oxigenio(quantidade)
        assert erro.value.solicitado == quantidade
        assert erro.value.disponivel == 500.0
        assert "Oxigênio insuficiente" in str(erro.value)

    @pytest.mark.parametrize("quantidade", [0, 2000])
    def test_validar_estoque_agua_dentro_do_limite(self, gerenciador, quantidade):
        assert gerenciador.validar_estoque_agua(quantidade) is True

    @pytest.mark.parametrize("quantidade", [2000.01, 5000])
    def test_validar_estoque_agua_acima_do_limite(self, gerenciador, quantidade):
        with pytest.raises(AguaInsuficienteError, match="Água insuficiente"):
            gerenciador.validar_estoque_agua(quantidade)

    @pytest.mark.parametrize(
        "quantidade, racionamento, concedido, estoque_final",
        [
            (20, 0.0, 20.0, 480.0),
            (500, 0.0, 500.0, 0.0),  # limite exato do estoque
            (40, 0.25, 30.0, 470.0),
            (600, 0.5, 300.0, 200.0),  # acima do estoque, mas o racionamento reduz a cota
        ],
    )
    def test_solicitar_oxigenio_valido(self, gerenciador, quantidade, racionamento, concedido, estoque_final):
        gerenciador.aplicar_cota_racionamento(racionamento)
        registro = gerenciador.solicitar_oxigenio(quantidade, "Watney")
        assert registro["concedido"] == pytest.approx(concedido)
        assert registro["astronauta"] == "Watney"
        assert gerenciador.oxigenio_kg == pytest.approx(estoque_final)
        assert gerenciador.historico_solicitacoes == [registro]

    def test_solicitar_oxigenio_acima_do_estoque(self, gerenciador):
        with pytest.raises(OxigenioInsuficienteError):
            gerenciador.solicitar_oxigenio(500.01, "Beck")
        assert gerenciador.oxigenio_kg == 500.0
        assert gerenciador.historico_solicitacoes == []

    @pytest.mark.parametrize("quantidade", [0, -5, -0.01, "10", None, math.inf, math.nan, True])
    def test_solicitar_oxigenio_quantidade_invalida(self, gerenciador, quantidade):
        with pytest.raises(QuantidadeInvalidaError):
            gerenciador.solicitar_oxigenio(quantidade, "Martinez")
        assert gerenciador.oxigenio_kg == 500.0

    def test_solicitacoes_sucessivas_ate_esgotar(self, gerenciador):
        gerenciador.solicitar_oxigenio(300, "Lewis")
        gerenciador.solicitar_oxigenio(200, "Vogel")
        assert gerenciador.oxigenio_kg == pytest.approx(0)
        with pytest.raises(OxigenioInsuficienteError):
            gerenciador.solicitar_oxigenio(0.01, "Johanssen")

    @pytest.mark.parametrize(
        "quantidade, racionamento, estoque_final", [(100, 0.0, 1900.0), (2000, 0.0, 0.0), (100, 0.1, 1910.0)]
    )
    def test_solicitar_agua_valido(self, gerenciador, quantidade, racionamento, estoque_final):
        gerenciador.aplicar_cota_racionamento(racionamento)
        gerenciador.solicitar_agua(quantidade, "Watney")
        assert gerenciador.agua_litros == pytest.approx(estoque_final)

    def test_solicitar_agua_acima_do_estoque(self, gerenciador):
        with pytest.raises(AguaInsuficienteError):
            gerenciador.solicitar_agua(2500, "Watney")
        assert gerenciador.agua_litros == 2000.0

    @pytest.mark.parametrize("quantidade", [0, -1, "x"])
    def test_solicitar_agua_quantidade_invalida(self, gerenciador, quantidade):
        with pytest.raises(QuantidadeInvalidaError):
            gerenciador.solicitar_agua(quantidade)

    def test_abastecimento(self, gerenciador):
        gerenciador.abastecer_oxigenio(100)
        gerenciador.abastecer_agua(250.5)
        assert gerenciador.oxigenio_kg == 600.0
        assert gerenciador.agua_litros == 2250.5

    @pytest.mark.parametrize("quantidade", [0, -10, "100"])
    def test_abastecimento_invalido(self, gerenciador, quantidade):
        with pytest.raises(QuantidadeInvalidaError):
            gerenciador.abastecer_oxigenio(quantidade)
        with pytest.raises(QuantidadeInvalidaError):
            gerenciador.abastecer_agua(quantidade)

    def test_obter_status(self, gerenciador):
        gerenciador.definir_nivel_emergencia("CRITICO")
        gerenciador.aplicar_cota_racionamento(0.2)
        assert gerenciador.obter_status() == {
            "oxigenio_kg": 500.0,
            "agua_litros": 2000.0,
            "astronautas": 4,
            "nivel_emergencia": "CRITICO",
            "taxa_emergencia": 1.5,
            "cota_racionamento": 0.2,
            "consumo_oxigenio_diario": 4.032,
            "consumo_agua_diario": 16.8,
            "dias_autonomia": 119.05,
            "dia_missao": 0,
        }


# ============================================================ modo offline (sem telemetria)
class TestModoOffline:
    def test_alertas_ficam_pendentes_sem_telemetria(self, gerenciador):
        gerenciador.definir_nivel_emergencia("CRITICO")
        assert [a["codigo"] for a in gerenciador.alertas_pendentes] == ["NIVEL_EMERGENCIA_ALTERADO"]

    def test_relatorio_sem_telemetria_retorna_none(self, gerenciador):
        assert gerenciador.enviar_relatorio_status() is None

    def test_reenvio_sem_telemetria_nao_entrega(self, gerenciador):
        gerenciador.definir_nivel_emergencia("ALERTA")
        assert gerenciador.reenviar_alertas_pendentes() == 0
        assert len(gerenciador.alertas_pendentes) == 1


# ============================================================ mocks: telemetria isolada
class TestIsolamentoTelemetria:
    def test_relatorio_status_enviado_com_dados_corretos(self, gerenciador_com_telemetria, telemetria_mock):
        resposta = gerenciador_com_telemetria.enviar_relatorio_status()

        telemetria_mock.enviar_relatorio_status.assert_called_once_with(
            gerenciador_com_telemetria.obter_status()
        )
        assert resposta == {"status": "recebido", "protocolo": "REL-001"}

    def test_alerta_disparado_ao_entrar_em_crise(self, gerenciador_com_telemetria, telemetria_mock):
        gerenciador_com_telemetria.definir_nivel_emergencia("CRITICO")

        telemetria_mock.enviar_alerta_emergencia.assert_called_once_with(
            "NIVEL_EMERGENCIA_ALTERADO",
            "Habitat mudou de NORMAL para CRITICO",
            {"nivel_anterior": "NORMAL", "nivel_atual": "CRITICO"},
        )

    @pytest.mark.parametrize("nivel", ["NORMAL", "normal"])
    def test_nenhum_alerta_em_nivel_normal(self, gerenciador_com_telemetria, telemetria_mock, nivel):
        gerenciador_com_telemetria.definir_nivel_emergencia(nivel)
        gerenciador_com_telemetria.solicitar_oxigenio(10, "Watney")
        telemetria_mock.enviar_alerta_emergencia.assert_not_called()

    def test_alerta_nao_repetido_para_mesmo_nivel(self, gerenciador_com_telemetria, telemetria_mock):
        gerenciador_com_telemetria.definir_nivel_emergencia("ALERTA")
        gerenciador_com_telemetria.definir_nivel_emergencia("ALERTA")
        assert telemetria_mock.enviar_alerta_emergencia.call_count == 1

    def test_solicitacao_em_crise_dispara_alerta(self, gerenciador_com_telemetria, telemetria_mock):
        gerenciador_com_telemetria.definir_nivel_emergencia("CRITICO")
        gerenciador_com_telemetria.aplicar_cota_racionamento(0.25)
        telemetria_mock.reset_mock()  # interessa só o alerta da solicitação

        registro = gerenciador_com_telemetria.solicitar_oxigenio(40, "Lewis")

        telemetria_mock.enviar_alerta_emergencia.assert_called_once_with(
            "SOLICITACAO_EM_CRISE",
            "Lewis recebeu 30.00 de oxigenio durante nível CRITICO",
            {
                "recurso": "oxigenio",
                "astronauta": "Lewis",
                "solicitado": 40.0,
                "concedido": 30.0,
                "nivel_emergencia": "CRITICO",
            },
        )
        assert registro["concedido"] == 30.0

    def test_solicitacao_recusada_nao_dispara_alerta(self, gerenciador_com_telemetria, telemetria_mock):
        gerenciador_com_telemetria.definir_nivel_emergencia("CRITICO")
        telemetria_mock.reset_mock()
        with pytest.raises(OxigenioInsuficienteError):
            gerenciador_com_telemetria.solicitar_oxigenio(1000, "Beck")
        telemetria_mock.enviar_alerta_emergencia.assert_not_called()

    def test_alerta_reserva_critica_ao_consumir_dia(self, telemetria_mock):
        habitat = GerenciadorRecursosMarte(
            oxigenio_kg=100, agua_litros=2000, astronautas=4, servico_telemetria=telemetria_mock
        )
        habitat.consumir_dia()  # restam 96,64 kg -> 28,76 dias (< 30)

        telemetria_mock.enviar_alerta_emergencia.assert_called_once_with(
            "RESERVA_CRITICA", "Autonomia de apenas 28.8 dias", {"dias_autonomia": 28.76}
        )

    def test_sem_alerta_quando_reserva_confortavel(self, gerenciador_com_telemetria, telemetria_mock):
        gerenciador_com_telemetria.consumir_dia()
        telemetria_mock.enviar_alerta_emergencia.assert_not_called()

    def test_falha_de_comunicacao_guarda_alerta_pendente(self, gerenciador_com_telemetria, telemetria_mock):
        telemetria_mock.enviar_alerta_emergencia.side_effect = FalhaComunicacaoError("tempestade solar")

        gerenciador_com_telemetria.definir_nivel_emergencia("ALERTA")

        assert gerenciador_com_telemetria.nivel_emergencia == "ALERTA"
        assert [a["codigo"] for a in gerenciador_com_telemetria.alertas_pendentes] == [
            "NIVEL_EMERGENCIA_ALTERADO"
        ]

    def test_reenvio_de_alertas_apos_restabelecer_conexao(self, gerenciador_com_telemetria, telemetria_mock):
        telemetria_mock.enviar_alerta_emergencia.side_effect = [
            FalhaComunicacaoError("sem sinal"),  # alerta de mudança de nível
            FalhaComunicacaoError("sem sinal"),  # alerta da solicitação
            {"status": "recebido"},  # reenvio 1
            FalhaComunicacaoError("sem sinal"),  # reenvio 2 falha de novo
        ]
        gerenciador_com_telemetria.definir_nivel_emergencia("CRITICO")
        gerenciador_com_telemetria.solicitar_oxigenio(10, "Vogel")

        entregues = gerenciador_com_telemetria.reenviar_alertas_pendentes()

        assert entregues == 1
        assert [a["codigo"] for a in gerenciador_com_telemetria.alertas_pendentes] == ["SOLICITACAO_EM_CRISE"]
        assert telemetria_mock.enviar_alerta_emergencia.call_count == 4

    def test_relatorio_com_falha_de_comunicacao_retorna_none(self, gerenciador_com_telemetria, telemetria_mock):
        telemetria_mock.enviar_relatorio_status.side_effect = FalhaComunicacaoError("antena desalinhada")
        assert gerenciador_com_telemetria.enviar_relatorio_status() is None
        telemetria_mock.enviar_relatorio_status.assert_called_once()

    def test_integracao_com_servico_real_isolando_transmissao(self, mocker, parametros_habitat):
        """Gerenciador + ServicoTelemetriaEspacial reais; só a rede é substituída."""
        transmitir = mocker.patch.object(
            ServicoTelemetriaEspacial, "_transmitir", return_value={"status": "recebido"}
        )
        mocker.patch.object(ServicoTelemetriaEspacial, "_agora", return_value="2035-07-04T12:00:00+00:00")
        servico = ServicoTelemetriaEspacial(habitat_id="ARES-3")
        habitat = GerenciadorRecursosMarte(**parametros_habitat, servico_telemetria=servico)

        habitat.definir_nivel_emergencia("ALERTA")

        transmitir.assert_called_once_with(
            "alertas",
            {
                "habitat_id": "ARES-3",
                "tipo": "ALERTA_EMERGENCIA",
                "enviado_em": "2035-07-04T12:00:00+00:00",
                "codigo": "NIVEL_EMERGENCIA_ALTERADO",
                "mensagem": "Habitat mudou de NORMAL para ALERTA",
                "dados": {"nivel_anterior": "NORMAL", "nivel_atual": "ALERTA"},
            },
        )


# ============================================================ mocks: serviço de telemetria
def _resposta_http(corpo):
    """Simula a resposta de urlopen (usada como context manager)."""
    resposta = MagicMock()
    resposta.read.return_value = json.dumps(corpo).encode("utf-8")
    resposta.__enter__.return_value = resposta
    return resposta


class TestServicoTelemetriaEspacial:
    @pytest.fixture
    def urlopen_mock(self, mocker):
        return mocker.patch(
            "src.servico_telemetria.urllib.request.urlopen",
            return_value=_resposta_http({"status": "recebido", "protocolo": "TERRA-42"}),
        )

    @pytest.fixture
    def servico(self, mocker):
        mocker.patch.object(ServicoTelemetriaEspacial, "_agora", return_value="2035-07-04T12:00:00+00:00")
        return ServicoTelemetriaEspacial(url_estacao="https://terra.example/api/", habitat_id="ARES-3", timeout=5)

    def test_enviar_relatorio_status(self, servico, urlopen_mock):
        resposta = servico.enviar_relatorio_status({"oxigenio_kg": 500.0})

        assert resposta == {"status": "recebido", "protocolo": "TERRA-42"}
        urlopen_mock.assert_called_once()
        requisicao = urlopen_mock.call_args.args[0]
        assert urlopen_mock.call_args.kwargs == {"timeout": 5}
        assert requisicao.full_url == "https://terra.example/api/relatorios"
        assert requisicao.get_method() == "POST"
        assert json.loads(requisicao.data) == {
            "habitat_id": "ARES-3",
            "tipo": "RELATORIO_STATUS",
            "enviado_em": "2035-07-04T12:00:00+00:00",
            "status": {"oxigenio_kg": 500.0},
        }

    def test_enviar_alerta_emergencia(self, servico, mocker):
        transmitir = mocker.patch.object(servico, "_transmitir", return_value={"status": "recebido"})

        servico.enviar_alerta_emergencia("VAZAMENTO", "Vazamento no módulo B")

        transmitir.assert_called_once_with(
            "alertas",
            {
                "habitat_id": "ARES-3",
                "tipo": "ALERTA_EMERGENCIA",
                "enviado_em": "2035-07-04T12:00:00+00:00",
                "codigo": "VAZAMENTO",
                "mensagem": "Vazamento no módulo B",
                "dados": {},
            },
        )

    @pytest.mark.parametrize(
        "erro", [urllib.error.URLError("sem rota"), TimeoutError("timeout"), urllib.error.URLError("DNS")]
    )
    def test_falha_de_rede_vira_falha_comunicacao(self, servico, mocker, erro):
        mocker.patch("src.servico_telemetria.urllib.request.urlopen", side_effect=erro)
        with pytest.raises(FalhaComunicacaoError, match="alertas"):
            servico.enviar_alerta_emergencia("TESTE", "teste")

    @pytest.mark.parametrize(
        "resposta_estacao, esperado", [({"status": "online"}, True), ({"status": "manutencao"}, False)]
    )
    def test_verificar_conexao(self, servico, mocker, resposta_estacao, esperado):
        urlopen = mocker.patch(
            "src.servico_telemetria.urllib.request.urlopen", return_value=_resposta_http(resposta_estacao)
        )
        assert servico.verificar_conexao() is esperado
        assert urlopen.call_args.args[0].full_url == "https://terra.example/api/ping"

    def test_verificar_conexao_offline(self, servico, mocker):
        mocker.patch(
            "src.servico_telemetria.urllib.request.urlopen", side_effect=urllib.error.URLError("sem sinal")
        )
        assert servico.verificar_conexao() is False

    def test_timestamp_em_utc(self):
        assert ServicoTelemetriaEspacial._agora().endswith("+00:00")

    def test_relatorio_do_gerenciador_chega_ao_servico(self, gerenciador):
        """Verifica a ordem e os argumentos das chamadas entre gerenciador e telemetria."""
        servico = MagicMock(spec=ServicoTelemetriaEspacial)
        gerenciador.servico_telemetria = servico

        gerenciador.definir_nivel_emergencia("ALERTA")
        gerenciador.enviar_relatorio_status()

        assert servico.mock_calls == [
            call.enviar_alerta_emergencia(
                "NIVEL_EMERGENCIA_ALTERADO",
                "Habitat mudou de NORMAL para ALERTA",
                {"nivel_anterior": "NORMAL", "nivel_atual": "ALERTA"},
            ),
            call.enviar_relatorio_status(gerenciador.obter_status()),
        ]
