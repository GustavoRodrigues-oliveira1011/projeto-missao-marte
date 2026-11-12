"""Testes E2E do painel Web (web/painel.html) com Selenium WebDriver em modo headless.

* Nenhum ``time.sleep``: toda sincronização usa WebDriverWait + expected_conditions.
* Em caso de falha, um screenshot é salvo automaticamente em ``screenshots/``.
"""

import os
import re
from pathlib import Path

import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
URL_PAINEL = (RAIZ_PROJETO / "web" / "painel.html").as_uri()
PASTA_SCREENSHOTS = RAIZ_PROJETO / "screenshots"
TEMPO_MAXIMO_ESPERA = 10


def capturar_evidencia(driver, nome_teste, pasta=PASTA_SCREENSHOTS):
    """Salva um screenshot do navegador e devolve o caminho do arquivo."""
    pasta.mkdir(parents=True, exist_ok=True)
    nome_arquivo = re.sub(r"[^\w.-]", "_", nome_teste) + ".png"
    caminho = pasta / nome_arquivo
    driver.save_screenshot(str(caminho))
    return caminho


@pytest.fixture
def driver(request):
    """Inicializa o Chrome headless e garante driver.quit() ao final.

    No GitHub Actions, a variável CHROME_BIN aponta para o Chrome instalado
    pela action setup-chrome. O chromedriver é resolvido pelo Selenium Manager.
    """
    opcoes = webdriver.ChromeOptions()
    opcoes.add_argument("--headless=new")
    opcoes.add_argument("--no-sandbox")
    opcoes.add_argument("--disable-dev-shm-usage")
    opcoes.add_argument("--disable-gpu")
    opcoes.add_argument("--window-size=1280,1024")
    if os.environ.get("CHROME_BIN"):
        opcoes.binary_location = os.environ["CHROME_BIN"]

    navegador = webdriver.Chrome(options=opcoes)
    try:
        yield navegador
        relatorio = getattr(request.node, "rep_call", None)
        if relatorio is not None and relatorio.failed:
            caminho = capturar_evidencia(navegador, request.node.name)
            print(f"\nScreenshot da falha salvo em: {caminho}")
    finally:
        navegador.quit()


@pytest.fixture
def painel(driver):
    """Abre o painel e aguarda o carregamento dos níveis iniciais."""
    driver.get(URL_PAINEL)
    espera = WebDriverWait(driver, TEMPO_MAXIMO_ESPERA)
    espera.until(EC.text_to_be_present_in_element((By.ID, "nivel-oxigenio"), "500.00"))
    return driver


def solicitar_oxigenio(driver, astronauta, quantidade):
    """Preenche e envia o formulário; aguarda o fim do processamento."""
    espera = WebDriverWait(driver, TEMPO_MAXIMO_ESPERA)
    campo_astronauta = espera.until(EC.element_to_be_clickable((By.ID, "astronauta")))
    campo_astronauta.clear()
    campo_astronauta.send_keys(astronauta)
    campo_quantidade = driver.find_element(By.ID, "quantidade")
    campo_quantidade.clear()
    campo_quantidade.send_keys(quantidade)
    driver.find_element(By.ID, "btn-solicitar").click()
    # A mensagem final recebe a classe "sucesso" ou "erro" quando o processamento termina.
    espera.until(
        EC.any_of(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "#mensagem-status.sucesso")),
            EC.visibility_of_element_located((By.CSS_SELECTOR, "#mensagem-status.erro")),
        )
    )
    espera.until(EC.element_to_be_clickable((By.ID, "btn-solicitar")))
    return driver.find_element(By.ID, "mensagem-status")


def texto(driver, id_elemento):
    return driver.find_element(By.ID, id_elemento).text


class TestPainelControleWeb:
    def test_painel_exibe_niveis_iniciais(self, painel):
        assert "ECLSS" in painel.title
        assert texto(painel, "nivel-oxigenio") == "500.00"
        assert texto(painel, "nivel-agua") == "2000.00"
        assert texto(painel, "total-astronautas") == "4"
        assert texto(painel, "consumo-oxigenio") == "3.36"
        assert texto(painel, "dias-autonomia") == "142.9"
        assert not painel.find_element(By.ID, "alerta-emergencia").is_displayed()

    def test_solicitacao_normal_atualiza_nivel_no_dom(self, painel):
        mensagem = solicitar_oxigenio(painel, "Watney", "25")

        WebDriverWait(painel, TEMPO_MAXIMO_ESPERA).until(
            EC.text_to_be_present_in_element((By.ID, "nivel-oxigenio"), "475.00")
        )
        assert "Solicitação aprovada: 25.00 kg concedidos a Watney" in mensagem.text
        assert "Alerta" not in mensagem.text
        itens = painel.find_elements(By.CSS_SELECTOR, "#historico li")
        assert [item.text for item in itens] == ["Watney: 25.00 kg (NORMAL)"]

    def test_solicitacoes_sucessivas_acumulam(self, painel):
        solicitar_oxigenio(painel, "Lewis", "100")
        solicitar_oxigenio(painel, "Vogel", "50.5")

        WebDriverWait(painel, TEMPO_MAXIMO_ESPERA).until(
            EC.text_to_be_present_in_element((By.ID, "nivel-oxigenio"), "349.50")
        )
        assert len(painel.find_elements(By.CSS_SELECTOR, "#historico li")) == 2

    def test_solicitacao_em_crise_com_racionamento(self, painel):
        espera = WebDriverWait(painel, TEMPO_MAXIMO_ESPERA)
        Select(painel.find_element(By.ID, "nivel-emergencia")).select_by_value("CRITICO")
        espera.until(EC.visibility_of_element_located((By.ID, "alerta-emergencia")))
        assert "CRITICO" in texto(painel, "alerta-emergencia")

        campo_racionamento = painel.find_element(By.ID, "cota-racionamento")
        campo_racionamento.clear()
        campo_racionamento.send_keys("25", Keys.TAB)  # TAB dispara o evento "change"
        # 0,84 x 1,5 x 0,75 x 4 = 3,78 kg/dia
        espera.until(EC.text_to_be_present_in_element((By.ID, "consumo-oxigenio"), "3.78"))

        mensagem = solicitar_oxigenio(painel, "Lewis", "40")

        espera.until(EC.text_to_be_present_in_element((By.ID, "nivel-oxigenio"), "470.00"))
        assert "30.00 kg concedidos a Lewis" in mensagem.text
        assert "Alerta de emergência enviado à Terra" in mensagem.text

    def test_solicitacao_acima_do_estoque_e_recusada(self, painel):
        mensagem = solicitar_oxigenio(painel, "Beck", "750")

        assert "erro" in mensagem.get_attribute("class")
        assert "Oxigênio insuficiente" in mensagem.text
        assert texto(painel, "nivel-oxigenio") == "500.00"
        assert painel.find_elements(By.CSS_SELECTOR, "#historico li") == []

    @pytest.mark.parametrize(
        "astronauta, quantidade, trecho_mensagem",
        [
            ("Martinez", "0", "quantidade deve ser maior que zero"),
            ("Martinez", "-15", "quantidade deve ser maior que zero"),
            ("Martinez", "", "quantidade deve ser maior que zero"),
            ("", "10", "informe o astronauta"),
        ],
    )
    def test_solicitacao_invalida_exibe_erro(self, painel, astronauta, quantidade, trecho_mensagem):
        mensagem = solicitar_oxigenio(painel, astronauta, quantidade)

        assert "Solicitação inválida" in mensagem.text
        assert trecho_mensagem in mensagem.text
        assert texto(painel, "nivel-oxigenio") == "500.00"

    def test_captura_de_evidencia_gera_png(self, painel, tmp_path):
        caminho = capturar_evidencia(painel, "evidencia teste/1", pasta=tmp_path)
        assert caminho.name == "evidencia_teste_1.png"
        assert caminho.read_bytes().startswith(b"\x89PNG")
