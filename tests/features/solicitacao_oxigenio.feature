# language: pt
Funcionalidade: Solicitação de cota extra de oxigênio
  Como astronauta do Habitat de Marte
  Quero solicitar uma cota extra de oxigênio ao ECLSS
  Para realizar minhas atividades sem colocar a tripulação em risco

  Contexto:
    Dado que o habitat possui 500 kg de oxigênio e 2000 litros de água
    E que a tripulação possui 4 astronautas

  Cenário: Solicitação de oxigênio em condições normais
    Dado que o habitat está em nível de emergência "NORMAL"
    Quando o astronauta "Watney" solicitar 20 kg de oxigênio
    Então a solicitação deve ser aprovada com 20 kg concedidos
    E o estoque de oxigênio deve ser de 480 kg
    E nenhum alerta de emergência deve ser enviado à Terra

  Cenário: Solicitação de oxigênio em situação de crise
    Dado que o habitat está em nível de emergência "CRITICO"
    E que uma cota de racionamento de 25% foi aplicada
    Quando o astronauta "Lewis" solicitar 40 kg de oxigênio
    Então a solicitação deve ser aprovada com 30 kg concedidos
    E o estoque de oxigênio deve ser de 470 kg
    E o alerta "SOLICITACAO_EM_CRISE" deve ser enviado à Terra para "Lewis"

  Cenário: Solicitação de quantidade superior ao estoque disponível
    Dado que o habitat está em nível de emergência "NORMAL"
    Quando o astronauta "Beck" solicitar 750 kg de oxigênio
    Então a solicitação deve ser recusada por oxigênio insuficiente
    E o estoque de oxigênio deve ser de 500 kg
    E nenhum alerta de emergência deve ser enviado à Terra

  Esquema do Cenário: Solicitação inválida
    Dado que o habitat está em nível de emergência "NORMAL"
    Quando o astronauta "Martinez" solicitar <quantidade> kg de oxigênio
    Então a solicitação deve ser recusada por quantidade inválida
    E o estoque de oxigênio deve ser de 500 kg

    Exemplos:
      | quantidade |
      | 0          |
      | -15        |
      | -0.5       |
