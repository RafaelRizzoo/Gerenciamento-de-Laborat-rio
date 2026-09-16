# Rodando o sistema com Docker

Serve para instalar em qualquer computador (Windows, Mac ou Linux) sem
precisar instalar Python, criar ambiente virtual nem lidar com a política
de execução do PowerShell. São dois comandos.

> **Não quer instalar o Docker?** Dá para rodar só com Python: duplo clique
> no `iniciar.bat`. O passo a passo está no `INSTALAR.md`.

---

## 1. Instalar o Docker Desktop

Baixe em <https://www.docker.com/products/docker-desktop/>, instale e abra.
Espere o ícone da baleia ficar estável ("Docker Desktop is running").

No Windows, o instalador pode pedir para ativar o WSL 2 e reiniciar a
máquina — aceite; é uma vez só.

## 2. Copiar a pasta do projeto

Leve a pasta `Gerenciamento de Laboratório` inteira para o outro
computador (pen drive, Git, OneDrive, o que for mais fácil).

Pode apagar antes, se quiser deixar a cópia mais leve:

- a pasta `.venv` (o Docker cria o ambiente sozinho)
- o arquivo `gestao_quimicos.db`, **se** você não quiser levar os dados
  junto (sem ele, o sistema sobe com os dados de exemplo)

## 3. Subir a aplicação

Duplo clique em **`recreate.bat`**, dentro da pasta do projeto.

Quem preferir digitar, o equivalente é abrir o PowerShell na pasta e rodar:

```powershell
docker compose up -d --build
```

A primeira vez demora alguns minutos, porque o Docker baixa o Python e
instala as bibliotecas. Depois disso, sobe em segundos.

Pronto: abra <http://localhost:5001>.

Login de teste: `rafael.rizzo@tenaris.com` / `tenaris123`
(a lista completa aparece no terminal com `docker compose logs app`).

---

## O atalho: recreate.bat

Na pasta existe um arquivo só, o **`recreate.bat`**. Duplo clique nele e
pronto — é o que ela executa toda vez que o código mudar.

O que ele faz, nesta ordem:

1. confere se o Docker Desktop está aberto (e avisa, se não estiver);
2. `git pull` — baixa o código novo do GitHub (se a pasta veio de um clone);
3. derruba o contêiner antigo e reconstrói a imagem;
4. sobe, espera a aplicação responder e abre o navegador.

**O banco não é apagado**: ele fica num volume do Docker, fora do
contêiner, e sobrevive a qualquer recriação.

O mesmo arquivo atende o resto do dia a dia, pelo terminal:

| Comando | Para quê |
|---|---|
| `recreate.bat` | Atualiza e recria (duplo clique faz isso) |
| `recreate.bat parar` | Para a aplicação |
| `recreate.bat logs` | Mostra o que a aplicação está fazendo |
| `recreate.bat backup` | Salva uma cópia do banco nesta pasta, com a data no nome |
| `recreate.bat zerar` | Apaga o banco e recomeça com os dados de exemplo (pede confirmação) |

Se a pasta veio de um ZIP em vez de `git clone`, o passo do `git pull` é
pulado com um aviso e ele reconstrói com o código que estiver ali — nesse
caso, baixe o ZIP novo antes de rodar.

## Comandos do dia a dia

| O que você quer | Comando |
|---|---|
| Subir | `docker compose up -d` |
| Parar | `docker compose down` |
| Ver o que está acontecendo | `docker compose logs -f` |
| Reiniciar | `docker compose restart` |
| Atualizar depois de mexer no código | `docker compose up -d --build` |
| Entrar no contêiner | `docker compose exec app sh` |

Depois de instalado, dá para subir e parar pelos botões do próprio Docker
Desktop, sem digitar nada — o contêiner aparece lá com o nome
**gestao-quimicos**.

Como o `restart: unless-stopped` está ligado, o sistema volta sozinho
toda vez que o computador for ligado (com o Docker Desktop aberto).

---

## Onde ficam os dados

O banco **não** fica dentro do contêiner: fica num volume do Docker
chamado `dados`. Isso significa que atualizar ou recriar o contêiner não
apaga nada.

**Fazer uma cópia de segurança do banco:**

```powershell
docker compose cp app:/dados/gestao_quimicos.db .\backup_quimicos.db
```

**Restaurar uma cópia (ou levar o banco daqui para lá):**

```powershell
docker compose cp .\backup_quimicos.db app:/dados/gestao_quimicos.db
docker compose restart
```

**Apagar tudo e começar do zero** (isso apaga os dados de verdade):

```powershell
docker compose down -v
docker compose up -d
```

---

## Configuração

Tudo o que você mudaria no `.env` está no `docker-compose.yml`, na seção
`environment`. As mais usadas:

| Variável | Para quê |
|---|---|
| `SECRET_KEY` | Chave da sessão. **Troque** por uma frase sua. |
| `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` | Servidor de e-mail. Em branco, os avisos ficam guardados em `/notificacoes` sem sair. |
| `LEMBRETES_ATIVOS` | `0` desliga a cobrança automática de 7 em 7 dias. |
| `MAX_UPLOAD_MB` | Tamanho máximo de cada arquivo anexado. |

Depois de mexer no arquivo: `docker compose up -d` (ele recria o
contêiner com os valores novos).

### Acessar de outro computador da casa/rede

Descubra o IP da máquina onde o Docker está rodando (`ipconfig` no
Windows) e acesse `http://IP-DA-MAQUINA:5001`. Pode ser necessário
liberar a porta 5001 no firewall do Windows na primeira vez.

### Usar SQL Server em vez de SQLite

No `docker-compose.yml`:

1. troque `SQLSERVER: "0"` por `SQLSERVER: "1"` (assim o `pyodbc` é
   instalado na imagem);
2. descomente o bloco do serviço `sqlserver` no fim do arquivo;
3. troque as variáveis do app para `DB_ENGINE: mssql`, `MSSQL_HOST: sqlserver`
   e o resto das credenciais.

Depois: `docker compose up -d --build`.

---

## O que acontece quando o contêiner sobe

O `docker-entrypoint.sh` roda antes da aplicação, sempre na mesma ordem:

1. `migrar_fluxo.py` — cria as tabelas que faltam e converte dados de
   versões anteriores do sistema (é seguro repetir);
2. se o banco estiver **vazio**, roda o `seed.py` para carregar produtos,
   usuários e a biblioteca de documentos de exemplo;
3. inicia o `main.py` na porta 5001.

Ou seja: num computador novo, `docker compose up -d --build` já entrega o
sistema funcionando com dados dentro.

---

## Se algo der errado

| Sintoma | O que fazer |
|---|---|
| `docker: command not found` | O Docker Desktop não está instalado ou não foi aberto. |
| `port is already allocated` | A porta 5001 está ocupada. Troque para `"5002:5001"` no compose e acesse pelo 5002. |
| A página não abre | `docker compose logs -f app` mostra o erro. |
| Mudei o código e nada mudou | Faltou o `--build`: `docker compose up -d --build`. |
