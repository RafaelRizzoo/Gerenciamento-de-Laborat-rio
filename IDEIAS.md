# Ideias e decisões pendentes

Lista do que já foi conversado mas ainda não foi feito. Cada item traz a
decisão já tomada (quando houve) e o que precisa mudar no código.

---

## 1. Parecer restrito ao técnico da área

**Status: FEITO.** Implementado em 08/10/2026. O registro abaixo fica como
histórico da decisão e do que foi mexido.

O que mudou no código:

- `servicos.areas_do_usuario()` — removido o atalho que dava todas as áreas
  ao ADMIN. O administrador só assina parecer se estiver cadastrado como
  aprovador da área.
- `servicos.areas_gerenciaveis()` — **não** mudou: ADMIN e Aprovador Final
  continuam cuidando da lista de aprovadores de todas as áreas.
- `main.py`, POST `/produtos/{id}/decisao` — uma área preenchida que não é
  do usuário passa a ser **recusada**. Antes era trocada em silêncio pela
  área dele, o que gravava o parecer na área errada.
- `main.py`, ficha do produto — aviso para o administrador explicando por
  que não existe botão de parecer para o cargo dele.

Ainda pendente, mas é cadastro e não código: **cadastrar um suplente em cada
área**. Hoje cada área tem um nome só e, com o administrador sem poder
destravar, a área para quando o titular sai de férias.
**Pedido da Julia:** "não permitir que qualquer colaborador dê um parecer
químico — o parecer de cada área deve ser exclusivo do login do técnico
daquela área."

### O que já existe hoje

O vínculo pessoa → área já está no banco, na tabela `area_aprovadores`,
mantida pela tela **Aprovações › Novo aprovador**. Hoje está assim:

| Área | Técnico |
|---|---|
| Meio Ambiente | Bruno Costa |
| Saúde | Carla Mendes |
| Segurança | Fábio Nunes |
| Químico Responsável | Diego Ramos |
| Aprovador Final | Eduardo Lima |

A função `servicos.areas_para_decidir()` já filtra: o Fábio só consegue
registrar parecer de Segurança, mesmo digitando a URL na mão. E como ele
responde por uma área só, o campo **"Registrar parecer como" nem aparece**
para ele — o sistema já envia a área escondida no formulário.

Ou seja: a regra pedida **já vale para os técnicos**. O que falta é fechar
a exceção do administrador.

### O que falta mudar

O administrador hoje responde por **todas** as áreas. É por isso que o
dropdown aparece quando a Julia abre uma solicitação: ela vê as áreas que
ainda faltam e pode assinar por qualquer uma delas.

**Decisão:** o administrador passa a só administrar. Ele cadastra pessoas,
produtos, kits e documentos, mas não assina parecer de área nenhuma. Se a
Julia precisar aprovar alguma coisa, ela tem que estar cadastrada como
técnica daquela área, igual a todo mundo.

Ponto de mudança (uma função só):

```python
# servicos.py - areas_do_usuario()
if usuario.papel == "ADMIN":                       # <- remover este atalho
    return [chave for chave, _ in FLUXO_APROVACAO]
```

Cuidados ao mexer:

- `servicos.areas_gerenciaveis()` chama `areas_do_usuario()` e precisa
  continuar devolvendo **todas** as áreas para o ADMIN — senão a Julia
  perde a tela de gestão de aprovadores. Essa função passa a precisar do
  seu próprio tratamento de ADMIN.
- `contar_pendencias()`, a fila de `/aprovacoes` e o formulário de parecer
  seguem sozinhos: todos derivam de `areas_do_usuario()`.
- Depois da mudança, a Julia deixa de ver botão de Aprovar/Reprovar. Ela
  continua vendo o fluxo, o histórico e os documentos.
- Validar também o POST de `/produtos/{id}/decisao` (não só esconder o
  formulário): a área enviada tem que estar na lista de áreas da pessoa.
  Hoje isso já é verificado, mas vale um teste depois da mudança.

### Acúmulo de áreas

**Decisão:** continua permitido uma pessoa responder por duas áreas, mas é
exceção (planta pequena, acumulação de função). Então o dropdown
"Registrar parecer como" **continua no código**, só que na prática deixa de
aparecer, porque ninguém acumula. Nada a fazer.

### Férias e substituição

**Decisão:** suplente da mesma área. A área passa a ter dois nomes
cadastrados e qualquer um dos dois assina — a área é concluída com uma
assinatura só.

Isso **já funciona** hoje: `area_aprovadores` aceita várias pessoas por
área, e o e-mail de aviso vai para todas elas. Não precisa de código, só
cadastrar o segundo nome em cada área na tela de Aprovações.

A ideia de "o administrador destrava quando o técnico está de férias" foi
descartada — é justamente o que a Julia quer evitar.

---

## 2. Login pelo Microsoft Entra ID

**Status:** em aberto, depende da TI da Tenaris.

Substituir o cadastro de e-mail e senha pelo login corporativo da Microsoft.
Hoje o sistema tem cadastro próprio com senha (PBKDF2) e troca obrigatória
no primeiro acesso.

**Pergunta em aberto, para decidir junto com a TI:** depois que o login da
Microsoft entrar, de onde vem a **área** de cada pessoa?

- *Opção A* — do grupo de segurança do AD (ex.: `GRP-PQ-Seguranca`). Quem
  sai da equipe perde o acesso sozinho, sem ninguém lembrar de descadastrar.
  A tabela `area_aprovadores` viraria só um espelho do que veio do AD.
- *Opção B* — continua na tela de Aprovadores, mantida pela Julia. O Entra
  ID só diz **quem** é a pessoa; **o que ela pode fazer** continua sendo
  decidido dentro do sistema.

Vale decidir isso antes de começar, porque muda o desenho da tela de
Aprovadores.

---

## 3. Servidor de e-mail (SMTP)

**Status:** em aberto.

Enquanto o endereço do servidor não for preenchido no arquivo `.env`, os
avisos ficam gravados na **Caixa de saída** dentro do sistema em vez de
sair por e-mail. Precisa do endereço do servidor de e-mail corporativo da
Tenaris e de uma conta de envio.

---

## 4. "Tipo de produto" × "Categoria química"

**Status:** em aberto.

Os dois campos se sobrepõem e as pessoas não sabem qual preencher com o
quê. Vale olhar com a Julia se dá para juntar em um só, ou deixar claro na
tela o que vai em cada um.

---

## 5. Onde o sistema vai rodar

**Status:** em aberto.

Hoje roda na máquina de quem abre o `iniciar.bat`, com banco SQLite local.
Para a planta inteira usar, precisa de um servidor só, rodando o tempo todo,
com o banco em um lugar só e backup. A opção com Docker já está preparada
(`DOCKER.md`).

---

## 6. Repositório no GitHub

**Status:** em aberto.

O código está em uma conta pessoal. Como a aplicação é da Julia, vale
transferir o repositório para a conta dela ou para a organização da Tenaris.
