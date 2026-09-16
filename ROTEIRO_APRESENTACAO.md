# Roteiro da apresentação — Gestão de Produtos Químicos

Uns 8 minutos, com o sistema aberto em <http://localhost:5001>.

---

## Antes de começar

1. Duplo clique no **`iniciar.bat`** e espere o navegador abrir.
2. Os três exemplos **já estão cadastrados**, cada um num ponto diferente do
   fluxo — assim as telas de aprovação não aparecem vazias:

   | Produto | Situação |
   |---|---|
   | PQ-2026-0008 · Coagulante Suall Nanocog 220E | **Aprovado** — passou pelas 5 etapas |
   | PQ-2026-0009 · Qualypav Demarcação Branco e Cores | **Em análise** — Meio Ambiente e Segurança já opinaram |
   | PQ-2026-0010 · Ratol Granulado GS | **Pendente** — acabou de ser enviado |

   Se algum dia precisar recriá-los (depois de um `iniciar.bat zerar`, por
   exemplo), rode `iniciar.bat exemplos` no terminal da pasta.

3. Deixe as três FDS à mão, na pasta **`exemplos`** do projeto. A do
   **Qualypav** é a melhor para demonstrar ao vivo: é a que a leitura
   automática preenche melhor (14 campos).
4. Senha de todos os usuários de teste: **`tenaris123`**.

> Deixe a janela preta aberta durante toda a apresentação. Ela é o sistema.

---

## 1. A página inicial (1 min)

Mostre que **consulta não exige login**: qualquer pessoa da rede abre o
sistema, procura um produto, baixa a FDS. Os três cartões do topo —
aprovados, pendentes, reprovados — dão o retrato do momento.

Frase de apoio: *"hoje isso é um formulário do Forms e uma pasta de rede;
aqui é uma coisa só, com histórico."*

---

## 2. Cadastrar um produto novo — ao vivo (3 min)

**Cadastro → Nova solicitação.** Não precisa entrar com usuário.

**Passo 1 — anexar a FDS.** Escolha `exemplos/FDS_Qualypav_Demarcacao.pdf`
e clique em *Ler a FDS e continuar*.

**Passo 2 — conferir.** Aqui está o ponto alto: a faixa verde no topo diz
**"14 campo(s) preenchidos pela FDS"**, e cada campo lido traz a etiqueta
*"Preenchido pela FDS - confira"*. Vale apontar três:

- **Inflamável: Sim** e **Ponto de fulgor: > 35 °C** — tirados da seção 9;
- **Cancerígeno: Sim** — a ficha diz "suspeito de provocar câncer", seção 11;
- **Classificação GHS** e **Número ONU** — seções 2 e 14.

Complete o que só a planta sabe (é rápido, são 8 campos):

| Campo | Sugestão |
|---|---|
| Seu nome / e-mail | o dela |
| Fornecedor | Distribuidora Vale Tintas |
| Unidade solicitante | Pinda Tubos |
| Área solicitante | Manutenção |
| Necessidade de uso | repintura da sinalização de piso das rotas de pedestres |
| Motivo do desenvolvimento | plano de segurança viária interna revisado |
| Prazo / quantidade / unidade | Até 6 meses · 200 · L/mês |
| Funcionários expostos / função | 6 · pintor industrial, ajudante de pintura |
| Observações | aplicação externa, com exaustão natural |

Clique em **Enviar para aprovação**.

**Passo 3 — comprovante.** Aparece o protocolo (PQ-2026-00xx), para quem
foi enviado e o que acontece em seguida. Diga em voz alta: *"as quatro
áreas receberam agora, ao mesmo tempo — não existe fila."*

> Se aparecer o aviso de produto duplicado, é porque o exemplo do Qualypav
> já está cadastrado. É só clicar em **Enviar** de novo, que confirma que é
> outro produto — ou usar a FDS do Ratol.

---

## 3. Aprovar — a parte que todo mundo vai perguntar (3 min)

**Entrar** no canto superior direito, com **`bruno.costa@tenaris.com`** /
`tenaris123` (Meio Ambiente).

**Aprovações** no menu: a fila dele, só com o que depende da área dele.
Clique no produto **Ratol Granulado GS** (ou no que ela acabou de cadastrar).

> Se for aprovar o produto cadastrado ao vivo, lembre que ele começa em
> 0/5: dá para mostrar uma área e seguir para o Qualypav, que já tem duas.

Na ficha, à direita, três blocos:

1. **Fluxo de aprovação** — as quatro áreas lado a lado com "Aguardando
   análise", e o Aprovador Final embaixo, em "Aguarda as demais áreas".
   O contador mostra **0/5 etapas**.
2. **Registrar parecer** — escreva o parecer (é obrigatório) e clique em
   **Aprovar**. Ex.: *"Produto compatível com o plano de gerenciamento de
   resíduos. Embalagem vazia segue para resíduos classe I."*
   Para **Reprovar**, o sistema exige também escolher o motivo — e uma
   reprovação encerra o processo inteiro, venha da área que vier.
3. **Solicitar correção** — devolve ao solicitante sem reprovar. Ele corrige,
   reenvia, e a análise volta para a mesma área. Vale mencionar, não precisa
   demonstrar.

Assim que aprova, o cartão de Meio Ambiente fica **verde**, com o nome, a
data e o parecer à vista de todos. O contador vai para 1/5.

**Para mostrar o fim do fluxo sem repetir quatro logins**, use o produto
**Qualypav** dos exemplos, que já tem duas áreas aprovadas — ou abra
direto o **Coagulante Suall**, que está **Aprovado**, e mostre:

- as cinco etapas verdes, com os cinco pareceres;
- o **Histórico de alterações** no rodapé, com quem fez o quê, quando, e o
  status antes → depois;
- que o produto agora aparece na **consulta pública** e na **busca de FDS**.

*Regra em uma frase:* as quatro áreas analisam em paralelo, em qualquer
ordem; basta um aprovador de cada área; concluídas as quatro, o Aprovador
Final fecha; qualquer reprovação encerra.

---

## 4. Os avisos por e-mail (1 min)

Menu **Notificações** (entrando como `rafael.rizzo@tenaris.com`).

Mostre que o sistema já gerou tudo o que seria enviado: os quatro avisos às
áreas, a confirmação ao solicitante, um a cada parecer, a chamada do
Aprovador Final e a conclusão.

Diga com todas as letras: **os e-mails ainda não saem** — falta o servidor
de e-mail da Tenaris. Até lá tudo fica registrado nessa tela. E que
solicitações paradas são cobradas automaticamente a cada 7 dias.

---

## 5. O resto, em 30 segundos cada

- **Consulta de FDS** — busca por produto, situação da ficha (vigente,
  vencendo, vencida) e download.
- **Recursos e Documentos** — biblioteca de rótulos, procedimentos,
  formulários e normas, com controle de versão.
- **Kit Ambiental** — o que cada kit tem, para que serve e onde coletar.
- **Aprovações → Aprovadores por área** — adicionar ou tirar gente de cada
  área sem mexer em código. Bom fechamento: *"quando mudar quem responde
  por Segurança, ninguém precisa chamar a TI."*

---

## Perguntas que provavelmente virão

**"Os dados ficam onde?"**
Num banco no próprio computador. Para todos verem a mesma base, o sistema
precisa ficar num servidor — é o próximo passo.

**"Dá para usar com o SQL Server da empresa?"**
Sim, a troca é de configuração, sem mexer no código.

**"E se a FDS for um PDF escaneado?"**
A leitura automática avisa que não conseguiu ler e o formulário segue,
preenchido à mão. Nada trava.

**"Precisa de login para cadastrar?"**
Não. Só para aprovar. Quem cadastra informa nome e e-mail e recebe os avisos.
