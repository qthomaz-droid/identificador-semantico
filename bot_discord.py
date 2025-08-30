# Arquivo: bot_discord.py

import os
import sys
# A biblioteca dotenv é importada primeiro
from dotenv import load_dotenv

# --- LÓGICA DE CARREGAMENTO DO .ENV CORRIGIDA E NO LUGAR CERTO ---
# Garante que o .env seja carregado ANTES de qualquer outro script nosso ser importado
caminho_script = os.path.dirname(os.path.abspath(__file__))
caminho_env = os.path.join(caminho_script, '.env')
load_dotenv(dotenv_path=caminho_env)
# --- FIM DA CORREÇÃO ---

# Agora, importamos nossas outras bibliotecas e módulos
import discord
import shutil
import subprocess
import datetime
import asyncio
from trello import TrelloClient
from identificador import identificar_layout, recarregar_modelo, extrair_texto_do_arquivo, retreinar_modelo_completo

# Carrega as variáveis de ambiente APÓS o load_dotenv
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
TRELLO_API_KEY = os.getenv('TRELLO_API_KEY')
TRELLO_API_TOKEN = os.getenv('TRELLO_API_TOKEN')
TRELLO_BOARD_ID = os.getenv('TRELLO_BOARD_ID')

# --- Configurações e Criação de Pastas ---
PASTA_TEMP = 'temp_files'
PASTA_TREINAMENTO = 'arquivos_de_treinamento'
PASTA_CACHE = 'cache_de_texto'
for pasta in [PASTA_TEMP, PASTA_TREINAMENTO, PASTA_CACHE]:
    if not os.path.exists(pasta):
        os.makedirs(pasta)

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

EXTENSOES_SUPORTADAS = ['.pdf', '.xlsx', '.xls', '.txt', '.csv', '.xml']
arquivos_recentes = {}
treinamento_em_andamento = False

@client.event
async def on_ready():
    print(f'Bot está online como {client.user}')

@client.event
async def on_message(message):
    global treinamento_em_andamento
    if message.author == client.user: return

    msg_lower = message.content.lower()
    
    if msg_lower == 'ajuda':
        embed = discord.Embed(
            title="🤖 Ajuda do Identificador de Layouts",
            description="Olá! Eu sou um bot treinado para identificar layouts de arquivos. Veja como me usar:",
            color=discord.Color.blue()
        )
        embed.add_field(name="📄 1. Para Identificar um Arquivo", value="Simplesmente **anexe um arquivo** (PDF, XLSX, TXT, etc.) a uma mensagem neste canal. Eu irei analisá-lo automaticamente.", inline=False)
        embed.add_field(name="🔍 Para Melhorar a Precisão (Opcional)", value="No campo de **comentário do anexo**, escreva o nome do **sistema** (ex: `Dominio`, `SCI`). Isso me ajuda a dar preferência aos layouts corretos.", inline=False)
        embed.add_field(name="🔒 2. Arquivos com Senha", value="Se você enviar um arquivo PDF protegido, eu pedirei a senha no chat. Apenas responda com a senha e eu continuarei a análise.", inline=False)
        await message.channel.send(embed=embed)
        return

    elif msg_lower == 'ajudax':
        embed = discord.Embed(
            title="⚙️ Ajuda Avançada (Comandos de Admin)",
            description="Estes comandos são usados para aprimorar a minha inteligência e integrar com outros sistemas.",
            color=discord.Color.orange()
        )
        embed.add_field(name="🧠 1. Para me Ensinar o Layout Correto", value="Se eu errar uma análise, você pode me treinar! Após eu dar uma resposta, envie uma nova mensagem com o comando:\n`Treinar layout <código_correto>`\n*(Exemplo: `Treinar layout 123`)*", inline=False)
        embed.add_field(name="✅ 2. Criar Tarefa no Trello", value="Para criar um card com o último arquivo enviado, use o comando:\n`trello-criar-sistema-relatorio-cliente-movimento-chamado-nomedalista`\n*(Dica: se o nome da lista tiver espaços, use `_`, ex: `Novos_Layouts`)*", inline=False)
        await message.channel.send(embed=embed)
        return

    elif msg_lower.startswith('trello-criar'):
        await message.channel.send("Recebi o comando para criar um card no Trello. Processando...")
        try:
            partes = message.content.split('-')
            if len(partes) != 8:
                await message.channel.send("❌ Formato do comando incorreto. A estrutura deve ser: `trello-criar-sistema-relatorio-cliente-movimento-chamado-nomedalista`")
                return
            _, _, nome_sistema, nome_relatorio, cliente, tipo_movimento, chamado, nome_lista = partes
            if message.channel.id not in arquivos_recentes:
                await message.channel.send("Não há nenhum arquivo recente neste canal para anexar. Por favor, envie o arquivo primeiro.")
                return
            trello = TrelloClient(api_key=TRELLO_API_KEY, token=TRELLO_API_TOKEN)
            board = trello.get_board(TRELLO_BOARD_ID)
            lista_destino_nome = nome_lista.replace('_', ' ')
            lista_trello = next((l for l in board.list_lists() if l.name.lower() == lista_destino_nome.lower()), None)
            if not lista_trello:
                await message.channel.send(f"❌ Não encontrei a lista '{lista_destino_nome}' no seu quadro do Trello. Verifique o nome e tente novamente.")
                return
            card_title = f"NOVO LAYOUT - {nome_sistema.upper()} - {nome_relatorio.upper()} - {cliente}"
            card_desc = (f"Tipo de movimento: {tipo_movimento.upper()}\nAnexar arquivo - OK\nAnexar mapeamento - OK\nNome do sistema: {nome_sistema.upper()}\nChamado: #{chamado}")
            novo_card = lista_trello.add_card(name=card_title, desc=card_desc)
            info_arquivo = arquivos_recentes[message.channel.id]
            with open(info_arquivo['caminho'], 'rb') as f:
                novo_card.attach(name=info_arquivo['nome'], file=f)
            await message.channel.send(f"✅ **Card criado com sucesso na lista '{lista_trello.name}'!**\n{novo_card.url}")
        except Exception as e:
            await message.channel.send(f"❌ Ocorreu um erro ao criar o card no Trello. Detalhes: `{e}`")
        return

    elif msg_lower.startswith('treinar layout'):
        if treinamento_em_andamento:
            await message.channel.send("Já existe um treinamento em andamento. Por favor, aguarde.")
            return
        try:
            codigo_correto = message.content.split()[2]
        except IndexError:
            await message.channel.send("Formato incorreto. Use: `Treinar layout <código>`")
            return
        if message.channel.id not in arquivos_recentes:
            await message.channel.send("Nenhum arquivo recente para treinar. Envie um arquivo primeiro.")
            return
        info_arquivo = arquivos_recentes[message.channel.id]
        caminho_original, nome_original = info_arquivo['caminho'], info_arquivo['nome']
        texto_teste = extrair_texto_do_arquivo(caminho_original, senha_manual=info_arquivo.get('senha_fornecida'))
        if not texto_teste or "SENHA_" in texto_teste:
            await message.channel.send(f"Não consegui ler o conteúdo de `{nome_original}`. Treinamento cancelado.")
            return
        treinamento_em_andamento = True
        try:
            await message.channel.send(f"✅ Usando `{nome_original}` para aprimorar o layout `{codigo_correto}`.")
            timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            novo_nome_base = f"{codigo_correto}_{timestamp}_{nome_original}"
            caminho_destino = os.path.join(PASTA_TREINAMENTO, novo_nome_base)
            shutil.copy(caminho_original, caminho_destino)
            caminho_cache = os.path.join(PASTA_CACHE, novo_nome_base + '.txt')
            with open(caminho_cache, 'w', encoding='utf-8') as f:
                f.write(texto_teste)
            await message.channel.send(f"Arquivo e texto salvos para o treinamento.")
            await message.channel.send("⚙️ Iniciando o retreinamento completo do modelo...")
            python_executable = sys.executable
            processo = await asyncio.create_subprocess_exec(python_executable, 'treinador_em_massa.py', stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = await processo.communicate()
            if processo.returncode == 0:
                recarregar_modelo()
                await message.channel.send("🎉 **Treinamento concluído!** Meu cérebro foi atualizado.")
            else:
                await message.channel.send(f"❌ Erro durante o retreinamento: ```{stderr.decode()}```")
        finally:
            treinamento_em_andamento = False
        return
        
    if message.attachments:
        for attachment in message.attachments:
            if os.path.splitext(attachment.filename)[1].lower() in EXTENSOES_SUPORTADAS:
                sistema_alvo = message.content.strip()
                aviso_sistema = f" com preferência para **{sistema_alvo}**" if sistema_alvo else ""
                msg_processando = await message.channel.send(f"Analisando `{attachment.filename}`{aviso_sistema}...")
                caminho_arquivo_temp = os.path.join(PASTA_TEMP, attachment.filename)
                await attachment.save(caminho_arquivo_temp)
                arquivos_recentes[message.channel.id] = {'caminho': caminho_arquivo_temp, 'nome': attachment.filename}
                resultados = identificar_layout(caminho_arquivo_temp, sistema_alvo=sistema_alvo)
                if resultados == "SENHA_NECESSARIA":
                    await msg_processando.edit(content=f"🔒 `{attachment.filename}` está protegido. Por favor, envie a senha.")
                    def check(m): return m.author == message.author and m.channel == message.channel
                    try:
                        senha_msg = await client.wait_for('message', timeout=120.0, check=check)
                        senha_manual = senha_msg.content
                        arquivos_recentes[message.channel.id]['senha_fornecida'] = senha_manual
                        await msg_processando.edit(content=f"Senha recebida. Processando novamente...")
                        resultados = identificar_layout(caminho_arquivo_temp, sistema_alvo=sistema_alvo, senha_manual=senha_manual)
                    except asyncio.TimeoutError:
                        await msg_processando.edit(content="Tempo esgotado."); return
                
                await msg_processando.delete()
                if not resultados or isinstance(resultados, dict):
                    await message.channel.send(f"Não encontrei um layout compatível para `{attachment.filename}`.")
                elif resultados == "SENHA_INCORRETA":
                    await message.channel.send(f"❌ A senha para `{attachment.filename}` está incorreta.")
                else:
                    if resultados and isinstance(resultados, list) and len(resultados) > 0 and resultados[0]['pontuacao'] >= 85:
                        titulo_resposta = f"**🏆 Análise de `{attachment.filename}` concluída!**"
                    else:
                        titulo_resposta = f"**🔎 Análise de `{attachment.filename}` concluída.** Estes são os resultados:"
                    await message.channel.send(titulo_resposta)
                    for i, res in enumerate(resultados):
                        rank = i + 1
                        if res['pontuacao'] >= 85:
                            emoji = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"**{rank}º**"
                        else:
                            emoji = f"**{rank}º**"
                        embed = discord.Embed(title=f"{emoji} {res['banco']}", color=discord.Color.green() if res['pontuacao'] >= 85 else discord.Color.light_gray())
                        embed.add_field(name="Código", value=f"`{res['codigo_layout']}`", inline=True)
                        embed.add_field(name="Confiança", value=f"**{round(res['pontuacao'])}%**", inline=True)
                        if res.get("url_previa"):
                            embed.set_thumbnail(url=res['url_previa'])
                        await message.channel.send(embed=embed)
                    await message.channel.send("\nPara me ensinar o correto, use o comando: `Treinar layout <código>`")
client.run(DISCORD_TOKEN)