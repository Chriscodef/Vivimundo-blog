import os
import time
import json
import requests
from datetime import datetime, timedelta
import google.generativeai as genai
from pathlib import Path
import subprocess
import shutil

# Configurações das APIs
NEWS_API_KEY = os.getenv('NEWS_API_KEY', '802ea477f29d423f8b333d69a2271ab0')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'AIzaSyA8fqdomGBQ4f4ypqOn5k53W4JrCf7iZbI')
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN', '')
REPO_PATH = os.getenv('REPO_PATH', '/opt/render/project/src')

# Configurar Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')

# Temas em rotação
TEMAS = [
    {"nome": "Esportes", "query": "esportes Brasil", "categoria": "esportes"},
    {"nome": "Entretenimento", "query": "entretenimento Brasil", "categoria": "entretenimento"},
    {"nome": "Tecnologia", "query": "tecnologia", "categoria": "tecnologia"},
    {"nome": "Videogames", "query": "videogames", "categoria": "videogames"},
    {"nome": "Política Nacional", "query": "política Brasil", "categoria": "politica-nacional"},
    {"nome": "Política Internacional", "query": "política internacional", "categoria": "politica-internacional"}
]

tema_atual = 0
contador_posts = 0

def setup_git():
    """Configura Git"""
    try:
        # Vai para o diretório do projeto
        os.chdir(REPO_PATH)
        
        # Configura credenciais
        subprocess.run(['git', 'config', 'user.name', 'Vivimundo Bot'], check=True)
        subprocess.run(['git', 'config', 'user.email', 'bot@vivimundo.com'], check=True)
        
        # Configura remote com token
        repo_url = f'https://{GITHUB_TOKEN}@github.com/Chriscodef/Vivimundo-blog.git'
        
        # Remove remote antigo se existir
        subprocess.run(['git', 'remote', 'remove', 'origin'], capture_output=True)
        
        # Adiciona remote com token
        subprocess.run(['git', 'remote', 'add', 'origin', repo_url], check=True)
        
        # Garante que está na branch main
        subprocess.run(['git', 'checkout', 'main'], capture_output=True)
        
        # Pull das últimas mudanças
        subprocess.run(['git', 'pull', 'origin', 'main'], check=True)
        
        print("Git configurado com sucesso!")
        return True
    except Exception as e:
        print(f"Erro ao configurar Git: {e}")
        return False

def buscar_noticia(tema):
    """Busca notícia recente via NewsAPI em português brasileiro"""
    url = "https://newsapi.org/v2/everything"
    ontem = (datetime.now() - timedelta(hours=24)).strftime('%Y-%m-%dT%H:%M:%S')
    
    params = {
        'q': tema['query'],
        'language': 'pt',
        'from': ontem,
        'sortBy': 'publishedAt',
        'apiKey': NEWS_API_KEY,
        'pageSize': 10
    }
    
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        if data.get('articles') and len(data['articles']) > 0:
            # Filtra artigos que tenham conteúdo
            for article in data['articles']:
                if article.get('description') and article.get('content'):
                    return article
            # Se não encontrou com filtro, retorna o primeiro
            return data['articles'][0]
        return None
    except Exception as e:
        print(f"Erro ao buscar notícia: {e}")
        return None

def gerar_materia(noticia, tema):
    """Gera matéria de 500 palavras usando Gemini"""
    titulo = noticia.get('title', 'Notícia')
    descricao = noticia.get('description', '')
    conteudo = noticia.get('content', '')
    
    prompt = f"""Você é um jornalista profissional brasileiro escrevendo para o portal Vivimundo.

IMPORTANTE: Escreva EXATAMENTE 500 palavras em português brasileiro, sem nunca mencionar a fonte original ou outros sites.

Baseado nas informações abaixo, crie uma matéria jornalística completa:

Título: {titulo}
Informações: {descricao} {conteudo}

FORMATO:
- Escreva em parágrafos bem estruturados (não use listas ou bullets)
- Tom jornalístico e profissional
- Seja objetivo e informativo
- NÃO mencione fontes ou outros sites
- Conte com EXATAMENTE 500 palavras"""
    
    try:
        response = model.generate_content(prompt)
        texto = response.text.strip()
        
        # Valida se tem conteúdo
        if len(texto) < 200:
            print("Texto gerado muito curto, tentando novamente...")
            return None
            
        return texto
    except Exception as e:
        print(f"Erro ao gerar matéria: {e}")
        return None

def criar_slug(titulo):
    """Cria slug para URL da matéria"""
    import unicodedata
    import re
    
    titulo = unicodedata.normalize('NFKD', titulo)
    titulo = titulo.encode('ascii', 'ignore').decode('ascii')
    titulo = titulo.lower()
    titulo = re.sub(r'[^a-z0-9\s-]', '', titulo)
    titulo = re.sub(r'[\s]+', '-', titulo)
    
    return titulo[:60]

def salvar_materia(titulo, conteudo, imagem_url, categoria, data):
    """Salva matéria como HTML"""
    global contador_posts
    contador_posts += 1
    
    slug = criar_slug(titulo)
    filename = f"post-{contador_posts:04d}-{slug}.html"
    
    # Formata conteúdo em parágrafos
    paragrafos = conteudo.split('\n\n')
    conteudo_html = '\n'.join([f'<p>{p.strip()}</p>' for p in paragrafos if p.strip()])
    
    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{titulo} - Vivimundo</title>
    <link rel="stylesheet" href="../style.css">
</head>
<body>
    <header>
        <div class="container">
            <h1 class="logo">VIVIMUNDO</h1>
            <nav>
                <a href="../index.html">Início</a>
                <a href="../categoria-esportes.html">Esportes</a>
                <a href="../categoria-entretenimento.html">Entretenimento</a>
                <a href="../categoria-tecnologia.html">Tecnologia</a>
                <a href="../categoria-videogames.html">Videogames</a>
                <a href="../categoria-politica-nacional.html">Política Nacional</a>
                <a href="../categoria-politica-internacional.html">Política Internacional</a>
                <a href="../sobre.html">Sobre</a>
            </nav>
        </div>
    </header>

    <main class="container">
        <article class="post-completo">
            <div class="post-meta">
                <span class="categoria categoria-{categoria}">{categoria.replace('-', ' ').title()}</span>
                <span class="data">{data}</span>
            </div>
            <h1>{titulo}</h1>
            <p class="autor">Por Kevin Ribeiro</p>
            
            <img src="{imagem_url}" alt="{titulo}" class="post-imagem">
            
            <div class="post-conteudo">
                {conteudo_html}
            </div>
        </article>
    </main>

    <footer>
        <div class="container">
            <p>&copy; 2026 Vivimundo - Todos os direitos reservados</p>
            <a href="https://x.com/Kevin_RSP0" target="_blank">Twitter</a>
        </div>
    </footer>
</body>
</html>"""
    
    posts_dir = Path(REPO_PATH) / "posts"
    posts_dir.mkdir(exist_ok=True)
    
    filepath = posts_dir / filename
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)
    
    return {
        'titulo': titulo,
        'url': f"posts/{filename}",
        'imagem': imagem_url,
        'categoria': categoria,
        'data': data
    }

def atualizar_index(posts_recentes):
    """Atualiza página inicial com últimas 10 matérias"""
    posts_html = ""
    for post in reversed(posts_recentes[-10:]):
        posts_html += f"""
        <article class="post-card">
            <img src="{post['imagem']}" alt="{post['titulo']}">
            <div class="post-info">
                <span class="categoria categoria-{post['categoria']}">{post['categoria'].replace('-', ' ').title()}</span>
                <h2><a href="{post['url']}">{post['titulo']}</a></h2>
                <p class="meta">Por Kevin Ribeiro • {post['data']}</p>
            </div>
        </article>"""
    
    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vivimundo - Portal de Notícias</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <header>
        <div class="container">
            <h1 class="logo">VIVIMUNDO</h1>
            <nav>
                <a href="index.html">Início</a>
                <a href="categoria-esportes.html">Esportes</a>
                <a href="categoria-entretenimento.html">Entretenimento</a>
                <a href="categoria-tecnologia.html">Tecnologia</a>
                <a href="categoria-videogames.html">Videogames</a>
                <a href="categoria-politica-nacional.html">Política Nacional</a>
                <a href="categoria-politica-internacional.html">Política Internacional</a>
                <a href="sobre.html">Sobre</a>
            </nav>
        </div>
    </header>

    <main class="container">
        <h2 class="secao-titulo">Últimas Notícias</h2>
        <div class="posts-grid">
            {posts_html}
        </div>
    </main>

    <footer>
        <div class="container">
            <p>&copy; 2026 Vivimundo - Todos os direitos reservados</p>
            <a href="https://x.com/Kevin_RSP0" target="_blank">Twitter</a>
        </div>
    </footer>
</body>
</html>"""
    
    with open(Path(REPO_PATH) / "index.html", 'w', encoding='utf-8') as f:
        f.write(html)

def fazer_deploy():
    """Faz push para GitHub"""
    try:
        os.chdir(REPO_PATH)
        
        subprocess.run(['git', 'add', '.'], check=True)
        
        # Verifica se tem algo para commitar
        result = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
        if not result.stdout.strip():
            print("Nada para commitar")
            return
            
        subprocess.run(['git', 'commit', '-m', f'Nova matéria - {datetime.now().strftime("%d/%m/%Y %H:%M")}'], check=True)
        subprocess.run(['git', 'push'], check=True)
        print("✅ Deploy realizado com sucesso!")
    except Exception as e:
        print(f"❌ Erro no deploy: {e}")

def executar_ciclo():
    """Executa um ciclo completo do bot"""
    global tema_atual
    
    print(f"\n{'='*60}")
    print(f"🔄 NOVO CICLO - Tema: {TEMAS[tema_atual]['nome']}")
    print(f"{'='*60}\n")
    
    # Busca notícia
    print(f"🔍 Buscando notícia sobre {TEMAS[tema_atual]['nome']}...")
    noticia = buscar_noticia(TEMAS[tema_atual])
    if not noticia:
        print("❌ Nenhuma notícia encontrada")
        tema_atual = (tema_atual + 1) % len(TEMAS)
        return
    
    print(f"✅ Notícia encontrada: {noticia['title'][:60]}...")
    
    # Gera matéria
    print(f"✍️  Gerando matéria com Gemini...")
    conteudo = gerar_materia(noticia, TEMAS[tema_atual])
    if not conteudo:
        print("❌ Erro ao gerar matéria")
        tema_atual = (tema_atual + 1) % len(TEMAS)
        return
    
    print(f"✅ Matéria gerada ({len(conteudo.split())} palavras)")
    
    # Pega imagem
    imagem_url = noticia.get('urlToImage')
    if not imagem_url or not imagem_url.startswith('http'):
        imagem_url = 'https://via.placeholder.com/800x450/1a1a1a/d4af37?text=Vivimundo'
    
    # Salva matéria
    data_br = datetime.now().strftime('%d/%m/%Y às %H:%M')
    post_info = salvar_materia(
        noticia['title'],
        conteudo,
        imagem_url,
        TEMAS[tema_atual]['categoria'],
        data_br
    )
    
    print(f"💾 Matéria salva: {post_info['url']}")
    
    # Carrega posts existentes
    posts_file = Path(REPO_PATH) / "posts.json"
    if posts_file.exists():
        with open(posts_file, 'r', encoding='utf-8') as f:
            posts = json.load(f)
    else:
        posts = []
    
    posts.append(post_info)
    
    # Salva lista de posts
    with open(posts_file, 'w', encoding='utf-8') as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)
    
    # Atualiza index
    print("📝 Atualizando index...")
    atualizar_index(posts)
    
    # Faz deploy
    print("🚀 Fazendo deploy...")
    fazer_deploy()
    
    # Próximo tema
    tema_atual = (tema_atual + 1) % len(TEMAS)
    
    print(f"\n✅ CICLO CONCLUÍDO!")
    print(f"⏭️  Próximo tema: {TEMAS[tema_atual]['nome']}\n")

if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════╗
║           🌍 BOT VIVIMUNDO INICIADO 🌍                  ║
║                                                          ║
║  📰 24 matérias/dia - Uma a cada hora                   ║
║  🔄 Rotação automática de temas                         ║
║  🤖 Powered by Gemini AI                                ║
╚══════════════════════════════════════════════════════════╝
    """)
    
    # Setup inicial
    if not setup_git():
        print("❌ Falha ao configurar Git. Encerrando...")
        exit(1)
    
    print("✅ Git configurado!")
    print("⏰ Executando ciclo a cada 1 hora...\n")
    
    # Loop infinito
    while True:
        try:
            executar_ciclo()
            print(f"⏳ Aguardando 1 hora para próxima matéria...")
            print(f"   Próxima execução: {(datetime.now() + timedelta(hours=1)).strftime('%d/%m/%Y às %H:%M')}\n")
            time.sleep(3600)  # 1 hora
        except KeyboardInterrupt:
            print("\n\n👋 Bot encerrado pelo usuário")
            break
        except Exception as e:
            print(f"\n❌ ERRO NO CICLO: {e}")
            print("⏳ Aguardando 5 minutos antes de tentar novamente...\n")
            time.sleep(300)
