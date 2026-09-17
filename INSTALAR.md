# Instalação — Gestão de Produtos Químicos

Há dois jeitos de rodar o sistema. **Escolha um só.**

| | Precisa instalar | Quando usar |
|---|---|---|
| **A. Sem Docker** (recomendado) | Python (e Git, opcional) | Computador pessoal, uso normal |
| **B. Com Docker** | Docker Desktop + Git | Quem já usa Docker ou vai colocar num servidor |

O jeito A é o mais leve: o Python ocupa uns 100 MB e não mexe em nada do
Windows. O passo a passo do jeito B está no `DOCKER.md`.

---

# A. Rodar sem Docker

## 1. Baixar o projeto

**Se tiver Git** (ou o GitHub Desktop) — abra o PowerShell (tecla Windows,
digite `powershell`, Enter) e cole:

```powershell
cd ~\Documents
git clone https://github.com/RafaelRizzoo/Gerenciamento-de-Laborat-rio.git
```

**Se não tiver Git** — na página do projeto no GitHub, botão verde
**Code → Download ZIP**, e extraia a pasta em Documentos. Funciona igual;
a única diferença é que, para atualizar, é preciso baixar o ZIP novo.

## 2. Ligar o sistema

Abra a pasta e dê **duplo clique em `iniciar.bat`**.

Na primeira vez ele faz tudo sozinho:

1. procura o Python — **se não achar, pergunta se pode instalar** (responda
   `S`; ao terminar, feche a janela e rode o `iniciar.bat` de novo);
2. baixa as atualizações do código, se a pasta veio de um `git clone`;
3. prepara o ambiente e instala as bibliotecas (uns 2 minutos, com internet);
4. cria o banco com os dados de exemplo;
5. liga o sistema e abre o navegador em <http://localhost:5001>.

Nas vezes seguintes leva alguns segundos.

> **Deixe a janela preta aberta enquanto estiver usando.** Ela é o sistema.
> Para desligar, feche a janela (ou Ctrl+C).

Se o Windows avisar que o arquivo veio da internet, clique em
**Mais informações → Executar assim mesmo**.

## 3. Instalar o Python na mão (só se o passo 1 não der certo)

<https://www.python.org/downloads/> → **Download Python**.

Na **primeira tela** do instalador, marque a caixinha
**"Add python.exe to PATH"** antes de clicar em *Install Now*. É o detalhe
que faz o `iniciar.bat` encontrar o Python depois.

---

## Comandos do dia a dia (jeito A)

| Comando | Para quê |
|---|---|
| duplo clique em `iniciar.bat` | Atualiza, prepara e liga o sistema |
| fechar a janela preta | Desliga o sistema |
| `iniciar.bat backup` | Salva uma cópia do banco nesta pasta, com a data no nome |
| `iniciar.bat zerar` | Apaga o banco e recomeça com os dados de exemplo (pede confirmação e guarda uma cópia antes) |

Para usar os dois últimos: clique na barra de endereço da pasta, digite
`cmd`, Enter, e escreva o comando ali.

**Quando sair uma versão nova:** duplo clique no `iniciar.bat` de novo — ele
baixa as novidades sozinho. **Os dados cadastrados não são apagados.**

---

# B. Rodar com Docker

Passo a passo completo no **`DOCKER.md`**. Em resumo: instalar o Docker
Desktop, instalar o Git, clonar o projeto e dar duplo clique no
`recreate.bat`.

---

# Como usar (vale para os dois jeitos)

**Para abrir o sistema:** <http://localhost:5001> — vale salvar nos
favoritos.

**De outro computador da mesma rede:** descubra o IP da máquina onde o
sistema está rodando (`ipconfig` no PowerShell, linha *Endereço IPv4*) e
acesse `http://ESSE-IP:5001`. Na primeira vez o Windows pode perguntar se
libera a porta — responda que sim para redes privadas.

**Consulta não exige login:** produtos, fichas de segurança (FDS),
biblioteca de documentos, kit ambiental e até o cadastro de um produto novo
funcionam sem entrar com usuário.

**Para aprovar solicitações** é preciso entrar. Usuários de teste:

| E-mail | Senha | Papel |
|---|---|---|
| jusilva@tenaris.com | `123456` | Administradora (vê tudo) |
| ana.silva@tenaris.com | `tenaris123` | Solicitante |
| bruno.costa@tenaris.com | `tenaris123` | Meio Ambiente |
| carla.mendes@tenaris.com | `tenaris123` | Saúde |
| fabio.nunes@tenaris.com | `tenaris123` | Segurança |
| diego.ramos@tenaris.com | `tenaris123` | Químico Responsável |
| eduardo.lima@tenaris.com | `tenaris123` | Aprovador Final |

---

## Perguntas rápidas

**Preciso de internet para usar?**
Só na instalação e nas atualizações. No uso normal, não — tudo roda no
próprio computador.

**Os dados ficam onde?**
Sem Docker: no arquivo `gestao_quimicos.db`, dentro da pasta do projeto.
Com Docker: num volume do Docker, fora do contêiner. Nos dois casos,
atualizar o sistema não apaga nada.

**O que eu cadastrar aparece para a Julia?**
Não. Cada instalação tem o seu próprio banco, separado. Para todos verem os
mesmos dados, o sistema precisaria ficar num servidor único — é um passo
seguinte, se fizer sentido.

**Os e-mails de aprovação são enviados?**
Ainda não. Enquanto o servidor de e-mail da empresa não estiver
configurado, tudo o que seria enviado fica registrado na tela
**Notificações**, dentro do sistema.

**Apareceu "a porta 5001 já está em uso" / erro 10048?**
Quer dizer que outro programa já está ocupando o endereço `localhost:5001` —
quase sempre o contêiner do Docker ligado, ou o próprio sistema já aberto em
outra janela preta. O `iniciar.bat` detecta isso e pergunta se pode
encerrar o outro; se preferir resolver na mão, pare o contêiner pelo Docker
Desktop (aba *Containers*, item **gestao-quimicos**) ou feche a janela
antiga.

**Deu erro, e agora?**
A própria janela preta mostra a mensagem. Tire um print dela e mande para o
Julia.

**Posso ter os dois jeitos no mesmo computador?**
Pode, mas não ao mesmo tempo: os dois usam a porta 5001, e cada um tem o seu
próprio banco.
