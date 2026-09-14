"""Cobrança automática das solicitações paradas.

Regra: toda solicitação que continua em aberto há 7 dias ou mais gera um
e-mail para as áreas que ainda não deram parecer e uma cópia para o
solicitante. A cobrança se repete a cada 7 dias enquanto a solicitação
não for aprovada, reprovada ou descontinuada.

Como rodar:

1. Automático — o próprio `main.py` verifica ao subir e a cada 12 horas
   enquanto o servidor estiver no ar (desligue com LEMBRETES_ATIVOS=0).

2. Manual / Agendador de Tarefas do Windows:
       .venv\\Scripts\\python.exe lembretes.py

   Para simular sem enviar nada:
       .venv\\Scripts\\python.exe lembretes.py --simular
"""

import sys

import config
import servicos
from database import criar_tabelas, db_session


def executar(simular: bool = False) -> int:
    criar_tabelas()
    with db_session() as s:
        atrasadas = servicos.solicitacoes_atrasadas(s, config.LEMBRETE_DIAS)
        if not atrasadas:
            print("Nenhuma solicitação pendente há mais de "
                  f"{config.LEMBRETE_DIAS} dias. Nada a cobrar.")
            return 0

        print(f"{len(atrasadas)} solicitação(ões) pendente(s) há mais de "
              f"{config.LEMBRETE_DIAS} dias:")
        for produto in atrasadas:
            print(f"  {produto.codigo_interno} - {produto.nome_comercial} "
                  f"({produto.dias_em_aberto} dias) -> "
                  f"{', '.join(produto.areas_pendentes_labels) or '-'}")

        if simular:
            print("\nModo simulação: nenhum e-mail foi enviado ou registrado.")
            return 0

        enviados = servicos.enviar_lembretes(s, config.LEMBRETE_DIAS)
        destino = (
            f"enviados por {config.SMTP_HOST}"
            if config.SMTP_ATIVO
            else "registrados na caixa de saída (/notificacoes), pois o SMTP "
                 "ainda não está configurado"
        )
        print(f"\n{enviados} lembrete(s) {destino}.")
        return enviados


if __name__ == "__main__":
    executar("--simular" in sys.argv or "--dry-run" in sys.argv)
