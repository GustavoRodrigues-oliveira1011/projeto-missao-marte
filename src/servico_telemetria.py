"""Serviço de telemetria espacial: comunicação do habitat com a estação na Terra.

Esta classe é a dependência EXTERNA do sistema. Toda chamada passa pelo método
``_transmitir``, que faz uma requisição HTTP real para a estação terrestre.
Por isso, nos testes, ela é sempre isolada com mocks (pytest-mock).
"""

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone


class FalhaComunicacaoError(Exception):
    """Lançada quando não é possível falar com a estação terrestre."""


class ServicoTelemetriaEspacial:
    """Envia relatórios de status e alertas de crise para a estação na Terra."""

    URL_ESTACAO_PADRAO = "https://estacao-terrestre.missao-marte.example/api"

    def __init__(self, url_estacao=URL_ESTACAO_PADRAO, habitat_id="ARES-HAB-01", timeout=10):
        self.url_estacao = url_estacao.rstrip("/")
        self.habitat_id = habitat_id
        self.timeout = timeout

    def enviar_relatorio_status(self, status):
        """Envia o status atual dos recursos e devolve a resposta da estação."""
        payload = {
            "habitat_id": self.habitat_id,
            "tipo": "RELATORIO_STATUS",
            "enviado_em": self._agora(),
            "status": status,
        }
        return self._transmitir("relatorios", payload)

    def enviar_alerta_emergencia(self, codigo, mensagem, dados=None):
        """Dispara um alerta de crise para a estação terrestre."""
        payload = {
            "habitat_id": self.habitat_id,
            "tipo": "ALERTA_EMERGENCIA",
            "enviado_em": self._agora(),
            "codigo": codigo,
            "mensagem": mensagem,
            "dados": dados or {},
        }
        return self._transmitir("alertas", payload)

    def verificar_conexao(self):
        """Retorna True se a estação respondeu ao ping, False caso contrário."""
        try:
            resposta = self._transmitir("ping", {"habitat_id": self.habitat_id})
        except FalhaComunicacaoError:
            return False
        return resposta.get("status") == "online"

    def _transmitir(self, canal, payload):
        """Envia o payload em JSON (POST) para ``<url_estacao>/<canal>``."""
        requisicao = urllib.request.Request(
            f"{self.url_estacao}/{canal}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(requisicao, timeout=self.timeout) as resposta:
                return json.loads(resposta.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError) as erro:
            raise FalhaComunicacaoError(
                f"Falha ao transmitir para o canal '{canal}' da estação terrestre: {erro}"
            ) from erro

    @staticmethod
    def _agora():
        return datetime.now(timezone.utc).isoformat()
