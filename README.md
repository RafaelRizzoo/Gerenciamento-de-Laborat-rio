# Gestão de Produtos Químicos — Tenaris

Aplicação web para centralizar o cadastro, a aprovação e a consulta dos produtos
químicos utilizados na planta, incluindo a busca de Fichas de Dados de Segurança (FDS).

Desenvolvida em **FastHTML** (Python) com **SQLAlchemy**, rodando em SQLite no
desenvolvimento e em **SQL Server** em produção (troca feita apenas no arquivo `.env`).

---

## 1. Como executar no Windows

**Duplo clique em `iniciar.bat`.** Ele cuida de tudo: procura o Python (e
oferece instalar, se faltar), cria o ambiente virtual, instala as
bibliotecas, prepara o banco e sobe a aplicação em
**http://localhost:5001**.

Guia passo a passo para quem vai instalar do zero: **`INSTALAR.md`**.
Para rodar em contêiner: **`DOCKER.md`** (`recreate.bat`).

<details>
<summary>Fazendo na mão, comando por comando</summary>

```powershell
:: 1) dentro da pasta do projeto
py -3 -m venv .venv

:: 2) instalar as dependencias (o .venv\Scripts\activate pode ser bloqueado
::    pela politica do PowerShell; chamar o python direto evita isso)
.venv\Scripts\python.exe -m pip install -r requirements.txt

:: 3) preparar o banco (cria tabelas e, se estiver vazio, carrega exemplos)
.venv\Scripts\python.exe preparar.py

:: 4) subir a aplicacao
.venv\Scripts\python.exe main.py
```

> Se aparecer erro de `pyodbc` na instalação e você ainda estiver usando
> SQLite, tire a linha `pyodbc` do `requirements.txt` — ela só é necessária
> para o SQL Server.

</details>

### Usuários de teste (senha `tenaris123`)

| E-mail | Papel no fluxo |
|---|---|
| ana.silva@tenaris.com | Solicitante |
| bruno.costa@tenaris.com | Meio Ambiente |
| carla.mendes@tenaris.com | Saúde |
| fabio.nunes@tenaris.com | Segurança |
| diego.ramos@tenaris.com | Químico Responsável |
| eduardo.lima@tenaris.com | Aprovador Final |
| rafael.rizzo@tenaris.com | Administrador (vê tudo) |

As quatro áreas (Meio Ambiente, Saúde, Segurança e Químico Responsável)
avaliam **em paralelo, sem ordem entre elas**. O Aprovador Final só entra
depois que todas concluíram; qualquer reprovação encerra o processo.

Para testar o fluxo completo: cadastre um produto (não precisa de login),
depois entre como Bruno, Carla, Fábio e Diego, aprove em cada área, e feche
como Eduardo.

Para testar a parte pública, basta **não entrar** (ou clicar em *Sair*) e
navegar pela página inicial.

## 1.1 Modelo de acesso (site público na rede interna)

O sistema é **aberto para qualquer pessoa da rede interna**, sem login. A
identificação só é exigida onde alguém precisa assinar o que fez.

| Área | Acesso |
|---|---|
| Página inicial, busca, `/produtos`, `/classificacao`, `/fds`, `/historico` | **Aberto** — sem login |
| Download de FDS e Ficha de Emergência de produtos aprovados | **Aberto** |
| Ficha completa de produto aprovado | **Aberto** |
| Nova solicitação (`/solicitacoes/nova`), biblioteca (`/recursos`), kit ambiental | **Aberto** — sem login |
| Registrar parecer / aprovar etapa | Exige login + ser o responsável da etapa |
| Aprovações pendentes, Minhas solicitações, Painel | Exige login |
| Descontinuar / reativar produto | Exige login + Químico Responsável, Aprovador Final ou Admin |
| Usuários e papéis (`/usuarios`) | Exige login + Admin |

O que o visitante **sem login** não vê: solicitações em análise, reprovadas e
descontinuadas; pareceres em aberto; log de alterações do produto; e-mail do
solicitante; e documentos que não sejam FDS ou Ficha de Emergência.

A barra superior contém apenas a marca e o nome do sistema. A navegação é feita
pelos cartões da página inicial; quem está logado ganha uma faixa fina com
atalhos e o botão *Sair*.

### Imagem de fundo do hero

Fica em `static/img/hero.jpg` — hoje é um gradiente provisório. Para trocar,
substitua o arquivo por uma imagem de **2560 × 720 px** (JPG, até ~400 KB), com o
terço esquerdo escuro e sem detalhe, porque o texto branco fica sobre ele.

---

## 2. O que já está implementado

- **Cadastro de produto químico** com formulário completo e anexos (FDS obrigatória)
- **Fluxo de aprovação em 4 etapas**: Meio Ambiente → Saúde e Segurança → Químico
  Responsável → Aprovador Final, cada uma com parecer registrado
- **Controle de status**: Em análise, Aprovado, Reprovado, Descontinuado
- **Notificações por e-mail** em cada etapa (com caixa de saída quando não há SMTP)
- **Site público na rede interna** — consulta e FDS sem login (ver seção 1.1)
- **Consulta e download de FDS** (`/fds`), com regra pública de visibilidade
- **Consulta de classificação de perigo** (`/classificacao`) — GHS, ONU e EPI
- **Dashboard** com indicadores, produtos por categoria e pendências por etapa
- **Histórico completo** e **log de auditoria** de todas as ações
- **Cadastro de usuários e papéis**
- **Documentos obrigatórios** validados no envio da solicitação

## 3. Estrutura dos arquivos

| Arquivo | Papel |
|---|---|
| `main.py` | Aplicação FastHTML: todas as rotas, telas e regras de acesso |
| `models.py` | Modelo de dados (tabelas, status, categorias, papéis) |
| `database.py` | Conexão com o banco e criação das tabelas |
| `servicos.py` | Regras de negócio: fluxo de aprovação, indicadores, buscas |
| `notificacoes.py` | Envio e registro dos e-mails |
| `ui.py` | Componentes visuais (layout, menu, cards, tabelas, timeline) |
| `security.py` | Hash de senha (PBKDF2-SHA256) |
| `seed.py` | Dados de exemplo para testes |
| `static/styles.css` | Identidade visual Tenaris |
| `static/img/hero.jpg` | Imagem de fundo da página inicial (substituível) |
| `config.py` / `.env` | Configuração (banco, SMTP, uploads) |
| `extracao.py` | Leitura do PDF da FDS (preenche parte do cadastro) |
| `preparar.py` | Cria/atualiza tabelas e carrega exemplos se o banco estiver vazio |
| `migrar_fluxo.py` | Converte bancos de versões anteriores do fluxo |
| `iniciar.bat` | **Sem Docker:** instala o que falta e liga o sistema |
| `recreate.bat` | **Com Docker:** atualiza, reconstrói e liga o contêiner |
| `INSTALAR.md` / `DOCKER.md` | Guias de instalação para quem só vai usar |

### Paleta aplicada (cores oficiais Tenaris)

| Cor | HEX | Uso no sistema |
|---|---|---|
| Azul Tenaris | `#0051A5` | Barra superior, botões principais, links |
| Verde Tenaris | `#009E60` | Aprovações, status aprovado |
| Roxo Tenaris | `#920083` | Indicadores e gráficos |
| Azul claro | `#00AEC9` | Etapa em andamento, avatar |
| Verde claro | `#8DC63F` | Gráficos |
| Cinzas / branco | `#58595B` … `#FFFFFF` | Textos, bordas, fundos |

---

## 4. Trocar SQLite por SQL Server

Só o `.env` muda — nenhuma linha de código:

```ini
DB_ENGINE=mssql
MSSQL_HOST=servidor-sql
MSSQL_PORT=1433
MSSQL_DATABASE=GestaoQuimicos
MSSQL_USER=usuario_app
MSSQL_PASSWORD=senha
MSSQL_DRIVER=ODBC Driver 17 for SQL Server
```

Pré-requisitos:

1. Instalar o **Microsoft ODBC Driver for SQL Server** na máquina que roda a aplicação.
2. `pip install pyodbc`
3. Criar o banco vazio no SQL Server (`CREATE DATABASE GestaoQuimicos;`).
   As tabelas são criadas automaticamente na primeira execução.

Para usar autenticação integrada do Windows (login de domínio, sem senha no arquivo):
`MSSQL_TRUSTED=1`.

Os campos de texto usam `NVARCHAR` (tipo `Unicode`), então acentuação é preservada.

---

## 5. Sobre "servidor SMTP"

**SMTP** (*Simple Mail Transfer Protocol*) é o protocolo usado para **enviar** e-mails.
Um "servidor SMTP" é o computador da rede que recebe a mensagem do sistema e a entrega
nas caixas de entrada dos destinatários — na prática, é o servidor de e-mail corporativo
da Tenaris (algo como `smtp.tenaris.com`) ou o serviço do Microsoft 365
(`smtp.office365.com`). Sozinha, a aplicação não consegue entregar e-mail: ela precisa
"entregar a carta" a esse servidor.

O que pedir para a equipe de TI/Infra:

- endereço do servidor SMTP e porta (normalmente 587 com TLS, ou 25 na rede interna);
- se é necessário usuário e senha, ou se o IP do servidor da aplicação pode enviar sem
  autenticação (*relay* interno);
- um endereço remetente institucional, por exemplo `gestao.quimicos@tenaris.com`.

Com essas informações preenchidas no `.env`, os e-mails passam a sair de verdade:

```ini
SMTP_HOST=smtp.tenaris.com
SMTP_PORT=587
SMTP_USER=gestao.quimicos@tenaris.com
SMTP_PASSWORD=senha
SMTP_TLS=1
SMTP_FROM=gestao.quimicos@tenaris.com
```

**Enquanto o SMTP não for configurado, nada é perdido:** cada e-mail que o sistema
tentaria enviar fica gravado na tabela `notificacoes` e pode ser conferido na tela
**Notificações** (`/notificacoes`). Isso permite validar todo o fluxo de aprovação antes
de envolver a Infra.

---

## 6. Próximos passos sugeridos

1. **Autenticação corporativa** (AD / Entra ID) em lugar do login com senha no banco.
2. **Armazenamento das FDS**: hoje o arquivo fica no próprio banco (simples e seguro
   para backup). Se o volume crescer muito, migrar para uma pasta de rede ou SharePoint
   guardando apenas o caminho no banco.
3. **Edição da solicitação reprovada** para reenvio (hoje é necessário cadastrar de novo).
4. **Controle de validade da FDS** (alerta para revisão a cada X anos).
5. **Exportação para Excel/PDF** das consultas e do inventário de produtos.
6. **Publicação em servidor interno** (IIS + waitress/uvicorn, ou serviço do Windows).
