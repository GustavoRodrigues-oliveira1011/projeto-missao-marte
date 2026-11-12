[![Pipeline de Testes ECLSS](https://github.com/GustavoRodrigues-oliveira1011/projeto-missao-marte/actions/workflows/pipeline.yml/badge.svg)](https://github.com/GustavoRodrigues-oliveira1011/projeto-missao-marte/actions/workflows/pipeline.yml)

# Missão Marte: ECLSS — Automação de Testes Integrada

Suíte de testes automatizados do **ECLSS (Environmental Control and Life Support System)** do Habitat de Marte, cobrindo testes unitários e de integração com **pytest**, isolamento com **mocks**, testes **E2E com Selenium headless**, cenários **BDD em Gherkin** e execução contínua no **GitHub Actions**.

## A missão

O ECLSS mantém a tripulação viva: controla o estoque de oxigênio e água, calcula o consumo diário, reage a emergências e aplica racionamento quando necessário. Toda situação de crise precisa ser comunicada à estação na Terra.

### Objetivo do sistema

| Componente | Responsabilidade |
|---|---|
| `GerenciadorRecursosMarte` | Regra de negócio: estoque de O₂ e água, consumo por astronauta/dia, taxa de emergência, cotas de racionamento e validação de estoque. |
| `ServicoTelemetriaEspacial` | Dependência externa: envia relatórios de status e alertas de crise para a Terra (HTTP). |
| `PainelControleWeb` (`web/painel.html`) | Painel para consultar recursos e solicitar cota extra de oxigênio. |

## Tecnologias

- Python 3.12 (testado também em 3.14)
- pytest, pytest-mock, pytest-bdd, pytest-cov
- Selenium WebDriver + Google Chrome headless
- GitHub Actions

## Estrutura

```
projeto-missao-marte/
├── .github/workflows/pipeline.yml       # CI no GitHub Actions
├── src/
│   ├── gerenciador_recursos.py          # Regras de negócio + exceções
│   └── servico_telemetria.py            # Comunicação com a Terra
├── tests/
│   ├── conftest.py                      # Fixtures e hook de screenshot
│   ├── test_gerenciador.py              # Unitários, integração e mocks
│   ├── test_selenium_e2e.py             # E2E do painel Web
│   ├── test_bdd.py                      # Passos do BDD
│   └── features/solicitacao_oxigenio.feature
├── web/painel.html                      # Painel de controle
├── requirements.txt
└── README.md
```

## Módulos

### `src/gerenciador_recursos.py`

Regras de cálculo:

- **Consumo por astronauta/dia** = consumo base × taxa de emergência × (1 − cota de racionamento)
  - consumo base: 0,84 kg de O₂ e 3,5 L de água
- **Taxa de emergência**: `NORMAL` = 1,0 · `ALERTA` = 1,25 · `CRITICO` = 1,5
- **Cota de racionamento**: de 0 a 50%; reduz o consumo diário e a quantidade concedida em cada solicitação extra.
- **Dias de autonomia**: tempo até o primeiro recurso acabar.
- Mudança para nível de crise, solicitações durante crise e autonomia abaixo de 30 dias **disparam alertas** para a Terra.
- Se a comunicação com a Terra falhar, o alerta fica em `alertas_pendentes` e pode ser reenviado com `reenviar_alertas_pendentes()`. O habitat não para por falta de sinal.

Exceções: `OxigenioInsuficienteError`, `AguaInsuficienteError`, `NivelEmergenciaInvalidoError`, `QuantidadeInvalidaError` e `CotaRacionamentoInvalidaError` (todas herdam de `RecursoMarteError`).

### `src/servico_telemetria.py`

`ServicoTelemetriaEspacial` envia JSON via HTTP POST para a estação terrestre (`enviar_relatorio_status`, `enviar_alerta_emergencia`, `verificar_conexao`). Erros de rede viram `FalhaComunicacaoError`. O serviço é injetado no gerenciador, por isso pode ser trocado por um mock nos testes.

## Como executar localmente

### 1. Clonar o repositório

```bash
git clone https://github.com/GustavoRodrigues-oliveira1011/projeto-missao-marte.git
cd projeto-missao-marte
```

### 2. Criar o ambiente virtual e instalar as dependências

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows
.venv\Scripts\activate

pip install -r requirements.txt
```

Os testes Selenium precisam do **Google Chrome** instalado. O `chromedriver` é baixado automaticamente pelo Selenium Manager.

### 3. Executar os testes

```bash
pytest
```

Executar só um grupo:

```bash
pytest tests/test_gerenciador.py     # unitários, integração e mocks
pytest tests/test_selenium_e2e.py    # E2E com Selenium
pytest tests/test_bdd.py             # cenários BDD
```

### 4. Executar com cobertura

```bash
pytest --cov=src --cov-report=term-missing
```

## Como os testes estão organizados

### Pytest: fixtures, parametrização e exceções

- `parametros_habitat` (escopo `session`): carrega os parâmetros iniciais do habitat uma vez, em um dicionário somente leitura.
- `gerenciador` (escopo `function`): uma instância limpa do `GerenciadorRecursosMarte` por teste, com `yield` para preparação e limpeza.
- `@pytest.mark.parametrize` cobre consumo diário com diferentes números de astronautas, níveis de emergência e cotas de racionamento, além de limites de estoque e entradas inválidas.
- `with pytest.raises(...)` valida cada exceção personalizada e confirma que o estado não muda após um erro.

Os testes de regra de negócio usam o gerenciador real, sem mocks.

### Mocks (pytest-mock)

- `telemetria_mock` é um `MagicMock(spec=ServicoTelemetriaEspacial)` que simula as respostas da estação terrestre.
- `assert_called_once_with` confere o código, a mensagem e os dados de cada alerta.
- `side_effect` simula falhas de comunicação (tempestade solar, sem sinal) e o reenvio de alertas.
- `mocker.patch` substitui `urllib.request.urlopen` e `_transmitir` para testar o serviço real sem acessar a rede.

### Selenium E2E

- A fixture `driver` abre o Chrome em modo **headless** e chama `driver.quit()` no `finally`.
- Os testes preenchem o formulário de solicitação de oxigênio e verificam a atualização dos níveis no DOM.
- O painel processa as solicitações de forma assíncrona; a sincronização usa somente `WebDriverWait` + `expected_conditions`. **Não há `time.sleep()` no projeto.**
- **Evidências**: um hook no `conftest.py` registra o resultado de cada teste. Se um teste Selenium falhar, a fixture salva `driver.save_screenshot()` em `screenshots/<nome_do_teste>.png`. No GitHub Actions, essa pasta é publicada como artefato quando há falha.

### BDD (pytest-bdd)

O arquivo `tests/features/solicitacao_oxigenio.feature` está escrito em Gherkin em português (`# language: pt`), com os cenários:

1. Solicitação de oxigênio em condições normais
2. Solicitação de oxigênio em situação de crise (com racionamento e alerta à Terra)
3. Solicitação de quantidade superior ao estoque disponível
4. Solicitação inválida (Esquema do Cenário com vários exemplos)

Em `tests/test_bdd.py`, os passos `Dado`/`Quando`/`Então` são mapeados com `@given`, `@when` e `@then`, usando o gerenciador real.

## Integração contínua (GitHub Actions)

O workflow `.github/workflows/pipeline.yml` roda em todo `push` e `pull_request`:

1. `actions/checkout@v4`: baixa o código.
2. `actions/setup-python@v5`: configura o Python 3.12.
3. Instala as dependências do `requirements.txt`.
4. `browser-actions/setup-chrome@v1`: instala o Chrome estável para os testes headless.
5. Executa `pytest -v --cov=src --cov-report=term-missing`, que mostra o relatório de cobertura no console.
6. Se houver falha, publica os screenshots do Selenium como artefato.

