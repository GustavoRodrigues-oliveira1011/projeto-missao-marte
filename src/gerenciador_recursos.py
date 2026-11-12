"""Regras de negócio do ECLSS: estoque de oxigênio e água do Habitat de Marte.

Regras principais
-----------------
* Consumo por astronauta/dia = consumo base x taxa de emergência x (1 - cota de racionamento).
* Taxa de emergência depende do nível do habitat (NORMAL, ALERTA, CRITICO): em crise
  o consumo aumenta (reparos, EVAs, sistemas de backup).
* Cota de racionamento: percentual (0 a 50%) que reduz o consumo diário e também a
  quantidade concedida em cada solicitação extra de recursos.
* Solicitações durante crise (nível diferente de NORMAL) disparam alerta para a Terra.
* Falhas de comunicação com a Terra não interrompem o habitat: o alerta fica em
  ``alertas_pendentes`` para reenvio (decisão de projeto: a vida a bordo vem primeiro).
"""

import math

from src.servico_telemetria import FalhaComunicacaoError

CONSUMO_OXIGENIO_PADRAO_KG = 0.84  # referência NASA: ~0,84 kg de O2 por astronauta/dia
CONSUMO_AGUA_PADRAO_LITROS = 3.5
TAXAS_EMERGENCIA = {"NORMAL": 1.0, "ALERTA": 1.25, "CRITICO": 1.5}
COTA_RACIONAMENTO_MAXIMA = 0.5
CAPACIDADE_MAXIMA_ASTRONAUTAS = 12
DIAS_AUTONOMIA_MINIMA = 30


class RecursoMarteError(Exception):
    """Exceção base do ECLSS."""


class OxigenioInsuficienteError(RecursoMarteError):
    """Estoque de oxigênio não atende à solicitação."""

    def __init__(self, solicitado, disponivel):
        self.solicitado = solicitado
        self.disponivel = disponivel
        super().__init__(
            f"Oxigênio insuficiente: solicitado {solicitado:.2f} kg, disponível {disponivel:.2f} kg"
        )


class AguaInsuficienteError(RecursoMarteError):
    """Estoque de água não atende à solicitação."""

    def __init__(self, solicitado, disponivel):
        self.solicitado = solicitado
        self.disponivel = disponivel
        super().__init__(
            f"Água insuficiente: solicitado {solicitado:.2f} L, disponível {disponivel:.2f} L"
        )


class NivelEmergenciaInvalidoError(RecursoMarteError):
    """Nível de emergência não reconhecido."""


class QuantidadeInvalidaError(RecursoMarteError, ValueError):
    """Quantidade negativa, zero, não numérica ou não finita."""


class CotaRacionamentoInvalidaError(RecursoMarteError, ValueError):
    """Cota de racionamento fora do intervalo permitido."""


def _validar_quantidade(valor, descricao, permitir_zero=False):
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not math.isfinite(valor):
        raise QuantidadeInvalidaError(f"{descricao} deve ser um número finito: {valor!r}")
    if valor < 0 or (valor == 0 and not permitir_zero):
        raise QuantidadeInvalidaError(f"{descricao} deve ser maior que zero: {valor!r}")
    return float(valor)


class GerenciadorRecursosMarte:
    """Controla o estoque de oxigênio e água do habitat."""

    def __init__(
        self,
        oxigenio_kg,
        agua_litros,
        astronautas,
        consumo_oxigenio_kg=CONSUMO_OXIGENIO_PADRAO_KG,
        consumo_agua_litros=CONSUMO_AGUA_PADRAO_LITROS,
        servico_telemetria=None,
    ):
        self.oxigenio_kg = _validar_quantidade(oxigenio_kg, "Estoque de oxigênio", permitir_zero=True)
        self.agua_litros = _validar_quantidade(agua_litros, "Estoque de água", permitir_zero=True)
        self.consumo_oxigenio_kg = _validar_quantidade(consumo_oxigenio_kg, "Consumo base de oxigênio")
        self.consumo_agua_litros = _validar_quantidade(consumo_agua_litros, "Consumo base de água")
        self.astronautas = 0
        self.registrar_astronautas(astronautas)
        self.nivel_emergencia = "NORMAL"
        self.cota_racionamento = 0.0
        self.dia_missao = 0
        self.historico_solicitacoes = []
        self.alertas_pendentes = []
        self.servico_telemetria = servico_telemetria

    # ------------------------------------------------------------------ tripulação
    def registrar_astronautas(self, quantidade):
        if isinstance(quantidade, bool) or not isinstance(quantidade, int) or quantidade < 0:
            raise QuantidadeInvalidaError(f"Número de astronautas inválido: {quantidade!r}")
        if quantidade > CAPACIDADE_MAXIMA_ASTRONAUTAS:
            raise QuantidadeInvalidaError(
                f"O habitat suporta no máximo {CAPACIDADE_MAXIMA_ASTRONAUTAS} astronautas"
            )
        self.astronautas = quantidade

    # ------------------------------------------------------------------ emergência
    @staticmethod
    def calcular_taxa_emergencia(nivel):
        if not isinstance(nivel, str) or nivel.strip().upper() not in TAXAS_EMERGENCIA:
            raise NivelEmergenciaInvalidoError(
                f"Nível de emergência inválido: {nivel!r}. Use um de {sorted(TAXAS_EMERGENCIA)}"
            )
        return TAXAS_EMERGENCIA[nivel.strip().upper()]

    def definir_nivel_emergencia(self, nivel):
        self.calcular_taxa_emergencia(nivel)
        novo_nivel = nivel.strip().upper()
        nivel_anterior, self.nivel_emergencia = self.nivel_emergencia, novo_nivel
        if novo_nivel != "NORMAL" and novo_nivel != nivel_anterior:
            self._emitir_alerta(
                "NIVEL_EMERGENCIA_ALTERADO",
                f"Habitat mudou de {nivel_anterior} para {novo_nivel}",
                {"nivel_anterior": nivel_anterior, "nivel_atual": novo_nivel},
            )

    @property
    def em_crise(self):
        return self.nivel_emergencia != "NORMAL"

    # ------------------------------------------------------------------ racionamento
    def aplicar_cota_racionamento(self, percentual):
        if isinstance(percentual, bool) or not isinstance(percentual, (int, float)) or not (
            0 <= percentual <= COTA_RACIONAMENTO_MAXIMA
        ):
            raise CotaRacionamentoInvalidaError(
                f"Cota de racionamento deve estar entre 0 e {COTA_RACIONAMENTO_MAXIMA}: {percentual!r}"
            )
        self.cota_racionamento = float(percentual)

    def _fator_consumo(self):
        return self.calcular_taxa_emergencia(self.nivel_emergencia) * (1 - self.cota_racionamento)

    # ------------------------------------------------------------------ consumo
    def calcular_consumo_oxigenio_astronauta(self):
        return self.consumo_oxigenio_kg * self._fator_consumo()

    def calcular_consumo_agua_astronauta(self):
        return self.consumo_agua_litros * self._fator_consumo()

    def calcular_consumo_oxigenio_diario(self):
        return self.calcular_consumo_oxigenio_astronauta() * self.astronautas

    def calcular_consumo_agua_diario(self):
        return self.calcular_consumo_agua_astronauta() * self.astronautas

    def calcular_dias_autonomia(self):
        """Dias até o primeiro recurso acabar (infinito se não há tripulação)."""
        if self.astronautas == 0:
            return math.inf
        return min(
            self.oxigenio_kg / self.calcular_consumo_oxigenio_diario(),
            self.agua_litros / self.calcular_consumo_agua_diario(),
        )

    def consumir_dia(self):
        """Desconta um dia de consumo. Não altera nada se faltar algum recurso."""
        oxigenio = self.calcular_consumo_oxigenio_diario()
        agua = self.calcular_consumo_agua_diario()
        self.validar_estoque_oxigenio(oxigenio)
        self.validar_estoque_agua(agua)
        self.oxigenio_kg -= oxigenio
        self.agua_litros -= agua
        self.dia_missao += 1
        dias_restantes = self.calcular_dias_autonomia()
        if dias_restantes < DIAS_AUTONOMIA_MINIMA:
            self._emitir_alerta(
                "RESERVA_CRITICA",
                f"Autonomia de apenas {dias_restantes:.1f} dias",
                {"dias_autonomia": round(dias_restantes, 2)},
            )
        return {"oxigenio_kg": oxigenio, "agua_litros": agua}

    # ------------------------------------------------------------------ estoque
    def validar_estoque_oxigenio(self, quantidade_kg):
        quantidade_kg = _validar_quantidade(quantidade_kg, "Quantidade de oxigênio", permitir_zero=True)
        if quantidade_kg > self.oxigenio_kg:
            raise OxigenioInsuficienteError(quantidade_kg, self.oxigenio_kg)
        return True

    def validar_estoque_agua(self, quantidade_litros):
        quantidade_litros = _validar_quantidade(quantidade_litros, "Quantidade de água", permitir_zero=True)
        if quantidade_litros > self.agua_litros:
            raise AguaInsuficienteError(quantidade_litros, self.agua_litros)
        return True

    def abastecer_oxigenio(self, quantidade_kg):
        self.oxigenio_kg += _validar_quantidade(quantidade_kg, "Abastecimento de oxigênio")

    def abastecer_agua(self, quantidade_litros):
        self.agua_litros += _validar_quantidade(quantidade_litros, "Abastecimento de água")

    # ------------------------------------------------------------------ solicitações
    def solicitar_oxigenio(self, quantidade_kg, astronauta="desconhecido"):
        """Concede cota extra de oxigênio (reduzida pelo racionamento vigente)."""
        concedido = _validar_quantidade(quantidade_kg, "Quantidade de oxigênio") * (1 - self.cota_racionamento)
        self.validar_estoque_oxigenio(concedido)
        self.oxigenio_kg -= concedido
        return self._registrar_solicitacao("oxigenio", astronauta, quantidade_kg, concedido)

    def solicitar_agua(self, quantidade_litros, astronauta="desconhecido"):
        """Concede cota extra de água (reduzida pelo racionamento vigente)."""
        concedido = _validar_quantidade(quantidade_litros, "Quantidade de água") * (1 - self.cota_racionamento)
        self.validar_estoque_agua(concedido)
        self.agua_litros -= concedido
        return self._registrar_solicitacao("agua", astronauta, quantidade_litros, concedido)

    def _registrar_solicitacao(self, recurso, astronauta, solicitado, concedido):
        registro = {
            "recurso": recurso,
            "astronauta": astronauta,
            "solicitado": float(solicitado),
            "concedido": concedido,
            "nivel_emergencia": self.nivel_emergencia,
        }
        self.historico_solicitacoes.append(registro)
        if self.em_crise:
            self._emitir_alerta(
                "SOLICITACAO_EM_CRISE",
                f"{astronauta} recebeu {concedido:.2f} de {recurso} durante nível {self.nivel_emergencia}",
                registro,
            )
        return registro

    # ------------------------------------------------------------------ telemetria
    def obter_status(self):
        return {
            "oxigenio_kg": round(self.oxigenio_kg, 2),
            "agua_litros": round(self.agua_litros, 2),
            "astronautas": self.astronautas,
            "nivel_emergencia": self.nivel_emergencia,
            "taxa_emergencia": self.calcular_taxa_emergencia(self.nivel_emergencia),
            "cota_racionamento": self.cota_racionamento,
            "consumo_oxigenio_diario": round(self.calcular_consumo_oxigenio_diario(), 3),
            "consumo_agua_diario": round(self.calcular_consumo_agua_diario(), 3),
            "dias_autonomia": round(self.calcular_dias_autonomia(), 2),
            "dia_missao": self.dia_missao,
        }

    def enviar_relatorio_status(self):
        """Envia o status para a Terra. Retorna a resposta da estação ou None se offline."""
        if self.servico_telemetria is None:
            return None
        try:
            return self.servico_telemetria.enviar_relatorio_status(self.obter_status())
        except FalhaComunicacaoError:
            return None

    def _emitir_alerta(self, codigo, mensagem, dados):
        alerta = {"codigo": codigo, "mensagem": mensagem, "dados": dados}
        if self.servico_telemetria is None:
            self.alertas_pendentes.append(alerta)
            return
        try:
            self.servico_telemetria.enviar_alerta_emergencia(codigo, mensagem, dados)
        except FalhaComunicacaoError:
            self.alertas_pendentes.append(alerta)

    def reenviar_alertas_pendentes(self):
        """Tenta reenviar alertas guardados. Retorna quantos foram entregues."""
        if self.servico_telemetria is None:
            return 0
        pendentes, self.alertas_pendentes = self.alertas_pendentes, []
        entregues = 0
        for alerta in pendentes:
            try:
                self.servico_telemetria.enviar_alerta_emergencia(
                    alerta["codigo"], alerta["mensagem"], alerta["dados"]
                )
                entregues += 1
            except FalhaComunicacaoError:
                self.alertas_pendentes.append(alerta)
        return entregues
