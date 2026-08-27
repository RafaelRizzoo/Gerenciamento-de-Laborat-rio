# Trabalhando em duas máquinas — Git + GitHub

Projeto: **Gestão de Produtos Químicos** (Tenaris) — FastHTML + SQLAlchemy.

O repositório guarda **somente o código**. Cada máquina tem o seu próprio `.env`,
o seu próprio ambiente virtual (`.venv`) e o seu próprio banco SQLite
(`gestao_quimicos.db`), que é recriado com o `seed.py`.

---

## 0. Caminho recomendado: GitHub Desktop

Se você tem o **GitHub Desktop** instalado, use este caminho — ele resolve a
autenticação sozinho, sem token e sem `gh`. As seções 1 a 7 são a versão por
linha de comando, para consulta.

### 0.1 Garanta que a conta ativa é a pessoal

1. GitHub Desktop → menu **File → Options → Accounts**
2. Se estiver logado na conta do trabalho, clique em **Sign out**
3. **Sign in** → o navegador abre. **Atenção:** se o navegador já estiver logado
   no GitHub do trabalho, ele autoriza essa conta sem perguntar — faça logout
   antes ou use uma janela anônima
4. Ainda em Options, abra a aba **Git** e confirme *Name* e *Email* com os dados
   da conta pessoal (é o que aparece no histórico dos commits)

### 0.2 Crie o repositório a partir da pasta do projeto

1. **File → Add local repository**
2. Escolha a pasta `C:\Users\Rafael\Desktop\Gerenciamento de Laboratório`
3. Vai aparecer o aviso *"this directory does not appear to be a Git
   repository"* — clique em **create a repository**
4. Preencha:
   - **Name:** `gestao-produtos-quimicos`
   - **Git ignore:** **None** — já existe um `.gitignore` na pasta, feito para
     este projeto; escolher um da lista sobrescreve o nosso
   - **License:** None
5. **Create repository**

### 0.3 Confira o que vai ser enviado

Na aba **Changes** (esquerda) devem aparecer cerca de 13 arquivos: `main.py`,
`models.py`, `database.py`, `servicos.py`, `notificacoes.py`, `ui.py`,
`security.py`, `config.py`, `seed.py`, `requirements.txt`, `.env.example`,
`.gitignore`, `README.md`, `GIT_SETUP.md` e `static/styles.css`.

**NÃO** devem aparecer: `.env`, `.venv/`, `gestao_quimicos.db`,
`__pycache__/`. Se aparecerem, pare e verifique o `.gitignore`.

### 0.4 Commit e publicação

1. Em *Summary*, escreva `Versao inicial do sistema de gestao de produtos quimicos`
2. **Commit to main**
3. Botão **Publish repository** (topo)
4. Confirme que **"Keep this code private" está marcado** e que o *Organization*
   é `None` (sua conta pessoal)
5. **Publish repository**

### 0.5 Na segunda máquina

1. Instale o GitHub Desktop e faça login na mesma conta pessoal
2. **File → Clone repository → aba GitHub.com** → escolha
   `gestao-produtos-quimicos` → defina a pasta local → **Clone**
3. No PowerShell, dentro da pasta clonada, monte o ambiente local (isso não vem
   do Git):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python seed.py
python main.py
```

### 0.6 Rotina do dia a dia no GitHub Desktop

- **Ao começar:** clique em **Fetch origin** e, se aparecer **Pull origin**,
  clique nele — traz o que foi feito na outra máquina
- **Ao terminar:** aba *Changes* → escreva o *Summary* → **Commit to main** →
  **Push origin**

A regra de ouro é a mesma: *pull* antes de começar, *push* antes de sair da
máquina.

---

## 1. Primeira vez — na máquina onde o código já está

Abra o **PowerShell** dentro da pasta do projeto:

```powershell
cd "$env:USERPROFILE\Desktop\Gerenciamento de Laboratório"
```

### 1.1 Identifique-se no Git (só na primeira vez em cada máquina)

Use aqui o nome e o **e-mail da conta pessoal do GitHub** — é esse e-mail que
liga os commits ao seu perfil:

```powershell
git config --global user.name "SEU_NOME"
git config --global user.email "seu-email-pessoal@exemplo.com"
```

Se você usa a conta do trabalho em outros repositórios desta máquina, configure
apenas neste projeto (sem `--global`), rodando os mesmos comandos de dentro da
pasta do projeto e trocando `--global` por `--local`. Veja a seção 7 para trocar
a conta que autentica o `push`.

### 1.2 Crie o repositório local e o primeiro commit

```powershell
git init
git add .
git status
```

Confira no `git status` que **NÃO** aparecem: `.venv/`, `.env`,
`gestao_quimicos.db` nem `__pycache__/`. Se aparecerem, o `.gitignore` não
foi lido — verifique se o arquivo está na raiz da pasta.

```powershell
git commit -m "Versao inicial do sistema de gestao de produtos quimicos"
git branch -M main
```

### 1.3 Crie o repositório no GitHub

**Opção A — pelo site** (https://github.com/new):

- Repository name: `gestao-produtos-quimicos`
- Visibilidade: **Private** (importante: é código interno da empresa)
- **NÃO** marque "Add a README file" nem "Add .gitignore" — já existem aqui

Depois, na pasta do projeto:

```powershell
git remote add origin https://github.com/SEU_USUARIO/gestao-produtos-quimicos.git
git push -u origin main
```

**Opção B — pelo GitHub CLI** (se tiver o `gh` instalado, é um comando só):

```powershell
gh auth login
gh repo create gestao-produtos-quimicos --private --source=. --remote=origin --push
```

### 1.4 Autenticação no push

O Windows costuma abrir uma janela do **Git Credential Manager** pedindo login
no GitHub — basta autorizar pelo navegador. Se ele pedir usuário e senha no
terminal, a "senha" **não** é a senha da conta: gere um
*Personal Access Token* em GitHub → Settings → Developer settings →
Personal access tokens → Tokens (classic) → escopo `repo`, e use o token como senha.

---

## 2. Na segunda máquina — primeira configuração

```powershell
cd "$env:USERPROFILE\Desktop"
git clone https://github.com/SEU_USUARIO/gestao-produtos-quimicos.git
cd gestao-produtos-quimicos
```

Monte o ambiente local (isso **não** vem do Git, é por máquina):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python seed.py
python main.py
```

Acesse http://127.0.0.1:5001 — usuários de teste no `seed.py`, senha `tenaris123`.

> Se o `Activate.ps1` for bloqueado pelo PowerShell, rode uma vez:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

---

## 3. Rotina do dia a dia

**Ao começar a trabalhar em qualquer máquina** (traz o que foi feito na outra):

```powershell
git pull
```

**Ao terminar** (envia o seu trabalho):

```powershell
git add .
git commit -m "Descreva o que mudou"
git push
```

A regra de ouro: **sempre `git pull` antes de começar e `git push` antes de sair
da máquina.** Isso evita 99% dos conflitos.

---

## 4. Situações comuns

| Situação | O que fazer |
|---|---|
| `git push` recusado: "rejected... fetch first" | A outra máquina enviou algo antes. Rode `git pull --rebase` e depois `git push`. |
| Esqueceu de dar push e mexeu nas duas máquinas | Faça commit nas duas, depois `git pull --rebase` na segunda e resolva os arquivos marcados com `<<<<<<<`. |
| Quer ver o que mudou antes de commitar | `git diff` (mudanças não adicionadas) e `git status`. |
| Instalou uma biblioteca nova | Atualize o `requirements.txt` (`pip freeze > requirements.txt`) e commite junto. |
| Mudou algo no `.env` que a outra máquina também precisa | Reflita a mudança no `.env.example` (sem senhas reais) e commite esse arquivo. |
| Precisa desfazer tudo o que não foi commitado | `git checkout -- .` (cuidado: perde as alterações locais). |

---

## 5. O que fica fora do Git — e por quê

| Item | Motivo |
|---|---|
| `.env` | Contém credenciais (banco, SMTP). Nunca vai para o GitHub. O modelo é o `.env.example`. |
| `.venv/` | Ambiente virtual é específico da máquina e pesado. Recriado com `pip install -r requirements.txt`. |
| `gestao_quimicos.db` | Banco SQLite local. Arquivo binário — daria conflito toda hora. Recriado com `python seed.py`. |
| `__pycache__/` | Cache do Python, gerado automaticamente. |

Quando migrarmos para **SQL Server**, o banco passa a ser compartilhado no
servidor e as duas máquinas apontam para ele pelo `.env` — aí os dados também
ficam iguais nas duas, não só o código.

---

## 6. Antes do primeiro push — checagem de segurança

O `.env` está no `.gitignore`, mas vale confirmar que nenhuma senha real foi
para o `.env.example`:

```powershell
git ls-files | Select-String "env"
```

Deve listar apenas `.env.example`. Se por acidente o `.env` já tiver sido
commitado, remova-o do controle de versão (o arquivo continua no disco):

```powershell
git rm --cached .env
git commit -m "Remove .env do controle de versao"
```

---

## 7. Trocar a conta do GitHub (usar a conta pessoal)

Há duas coisas separadas — mude as duas.

### 7.1 A identidade dos commits

```powershell
git config --global user.name "SEU_NOME"
git config --global user.email "seu-email-pessoal@exemplo.com"
git config --global --list | Select-String "user"
```

Só neste projeto, em vez de global: rode de dentro da pasta com `--local`.

### 7.2 A credencial que autentica o push

O Windows guarda o login do GitHub no **Gerenciador de Credenciais**. Se lá
estiver a conta do trabalho, o push vai para a conta errada (ou é recusado).

Pelo terminal:

```powershell
cmdkey /list:git:https://github.com          # ver o que está salvo
cmdkey /delete:git:https://github.com        # apagar
```

Ou pela interface: menu Iniciar → **Gerenciador de Credenciais** →
*Credenciais do Windows* → procure `git:https://github.com` → **Remover**.

No próximo `git push`, o Git abre o navegador e você entra com a conta pessoal.
Atenção: se o navegador já estiver logado no GitHub do trabalho, ele autoriza
essa conta sem perguntar — faça logout antes, ou use uma janela anônima.

Alternativa sem navegador: gere um *Personal Access Token* na conta pessoal
(GitHub → Settings → Developer settings → Personal access tokens → Tokens
classic → escopo `repo`) e cole o token quando o Git pedir a senha.

### 7.3 Se usa o GitHub CLI (`gh`)

```powershell
gh auth logout                # sai da conta atual
gh auth login                 # entra com a pessoal
gh auth status                # confirma qual conta está ativa
```

Se as duas contas estiverem autenticadas: `gh auth switch`.

### 7.4 Se o repositório remoto já aponta para a conta errada

```powershell
git remote -v
git remote set-url origin https://github.com/SEU_USUARIO_PESSOAL/gestao-produtos-quimicos.git
```

### 7.5 Se os primeiros commits saíram com o e-mail errado

Antes do push, dá para reescrever o autor do último commit:

```powershell
git commit --amend --reset-author --no-edit
```

Se foram vários commits e nada foi enviado ainda, o mais simples é apagar a
pasta `.git` e começar o `git init` de novo — o código não é afetado.
