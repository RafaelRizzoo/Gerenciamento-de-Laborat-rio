# Começar do zero no seu notebook

Guia para instalar o sistema pela primeira vez, do nada até funcionando.
São quatro passos e leva uns 10 minutos, quase tudo esperando.

> Já tem uma pasta antiga do sistema no computador? Deixe onde está por
> enquanto. No fim deste guia tem o que fazer com ela.

---

## Passo 0 — Aceitar o convite do GitHub

O código fica num repositório privado, então antes de qualquer coisa você
precisa de acesso a ele.

1. Se ainda não tiver conta no GitHub, crie em <https://github.com/signup>
   (e-mail, senha e um nome de usuário — leva 2 minutos).
2. Passe o seu usuário do GitHub para o Rafael.
3. Ele te adiciona como colaboradora e você recebe **um convite por e-mail**.
   Abra o e-mail e clique em **Accept invitation**.

Dá para conferir se funcionou abrindo este endereço já logada no GitHub:

<https://github.com/RafaelRizzoo/Gerenciamento-de-Laborat-rio>

Se a página abrir mostrando os arquivos, está tudo certo. Se der
**404**, o convite ainda não foi aceito (ou ainda não foi enviado).

---

## Passo 1 — Instalar o Git

É o programa que baixa o código e, daqui pra frente, as atualizações.
Instala uma vez só.

1. Abra <https://git-scm.com/download/win>
2. O download começa sozinho. Abra o arquivo baixado.
3. Clique em **Next** em todas as telas e depois em **Install**.
   Não precisa mudar nada.
4. No fim, **feche qualquer janela de Prompt de Comando que estiver aberta.**

**Como saber se deu certo:** tecla Windows → digite `cmd` → Enter.
Na janela preta, digite:

```cmd
git --version
```

Se responder algo como `git version 2.47.0`, está pronto. Se disser
*"não é reconhecido como um comando"*, o Git não instalou — repita o
passo 1 e lembre de fechar e reabrir o `cmd`.

---

## Passo 2 — Baixar o projeto

Na mesma janela preta, cole as duas linhas abaixo (uma de cada vez,
Enter depois de cada):

```cmd
cd /d "%USERPROFILE%\Documents"
git clone https://github.com/RafaelRizzoo/Gerenciamento-de-Laborat-rio.git
```

### Vai abrir uma janela pedindo o login do GitHub

Isso é esperado — o repositório é privado. Clique em **Sign in with your
browser**, entre com a sua conta do GitHub e autorize. A janela fecha
sozinha e o download continua.

O Windows guarda esse acesso. **Só acontece desta vez.**

> Se em vez da janela aparecer o texto
> `Authentication failed` ou `repository not found`, o convite do Passo 0
> ainda não foi aceito. Volte lá.

### Terminou

Vai aparecer um monte de texto. Quando parar e voltar a piscar o cursor,
acabou.

Agora existe uma pasta nova em **Documentos**, chamada
`Gerenciamento-de-Laborat-rio`. É nela que o sistema vive.

---

## Passo 3 — Ligar o sistema

Abra a pasta `Gerenciamento-de-Laborat-rio` em Documentos e dê
**duplo clique em `iniciar.bat`**.

Abre uma janela preta e ela faz tudo sozinha:

1. procura o Python — **se não achar, pergunta se pode instalar.**
   Responda `S`, espere, e quando terminar **feche a janela e dê duplo
   clique no `iniciar.bat` de novo**;
2. baixa as atualizações do código;
3. instala as bibliotecas (uns 2 minutos, precisa de internet);
4. cria o banco de dados com alguns produtos de exemplo;
5. abre o navegador em <http://localhost:5001>.

Se o Windows avisar que o arquivo veio da internet, clique em
**Mais informações → Executar assim mesmo**.

> ### A janela preta é o sistema
> Enquanto ela estiver aberta, o site funciona. Fechou a janela,
> o site sai do ar. Para desligar, basta fechá-la.

---

## Passo 4 — Entrar

O endereço é <http://localhost:5001> — vale salvar nos favoritos.

Consultar produtos, fichas de segurança (FDS), biblioteca e kit ambiental
**não exige login**. Para aprovar solicitações, sim:

| E-mail | Senha |
|---|---|
| jusilva@tenaris.com | `123456` |

Troque essa senha assim que entrar.

---

## Daqui pra frente

**Para usar:** duplo clique no `iniciar.bat`.

**Para atualizar:** duplo clique no `iniciar.bat`. É o mesmo. Ele baixa as
novidades sozinho antes de ligar — você não precisa rodar nenhum comando
de Git nunca mais.

**Os seus cadastros não se perdem nas atualizações.** Eles ficam no arquivo
`gestao_quimicos.db`, que o Git não toca.

Dois comandos extras, para quando precisar. Para usá-los: clique na barra
de endereço da pasta, digite `cmd`, Enter, e escreva o comando ali.

| Comando | Para quê |
|---|---|
| `iniciar.bat backup` | Guarda uma cópia do banco nesta pasta, com a data no nome |
| `iniciar.bat zerar` | Apaga tudo e recomeça com os produtos de exemplo (pede confirmação e guarda uma cópia antes) |

---

## E a pasta antiga?

Se você já tinha uma pasta do sistema e **cadastrou coisas que quer manter**,
copie o banco da antiga para a nova:

1. Abra a pasta antiga e procure o arquivo `gestao_quimicos.db`
2. Copie (Ctrl+C)
3. Abra `Documentos\Gerenciamento-de-Laborat-rio` e cole (Ctrl+V)
4. Confirme a substituição
5. Duplo clique no `iniciar.bat`

Se era só teste e não faz falta, não precisa fazer nada — a pasta nova já
vem com produtos de exemplo.

Depois disso a pasta antiga não serve mais para nada. Pode apagar, ou
renomear para `Gerenciamento de Laboratório - ANTIGA` e deixar guardada
por uns dias, por garantia.

---

## Se der errado

**"'git' não é reconhecido como um comando"**
O Git não foi instalado, ou o `cmd` estava aberto antes da instalação.
Feche a janela preta, abra outra e tente de novo.

**"repository not found" ou "Authentication failed" no `git clone`**
O convite de colaboradora não foi aceito ainda, ou você entrou com outra
conta do GitHub. Confira abrindo
<https://github.com/RafaelRizzoo/Gerenciamento-de-Laborat-rio> no navegador:
se der 404, é isso.

**"a porta 5001 já está em uso" / erro 10048**
O sistema já está ligado em outra janela preta. Procure na barra de tarefas
e feche a antiga — ou deixe o `iniciar.bat` encerrar por você, ele pergunta.

**A janela preta abre e fecha na hora**
Clique na barra de endereço da pasta, digite `cmd`, Enter, e então digite
`iniciar.bat`. Assim a janela não fecha e dá para ler o erro.

**Qualquer outra coisa**
A mensagem está na própria janela preta. Tire um print dela e mande para o
Rafael.
