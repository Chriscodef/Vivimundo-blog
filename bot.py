import os
import time
import json
import requests
from datetime import datetime, timedelta
import google.generativeai as genai
from pathlib import Path
import subprocess

# Configurações
NEWS_API_KEY = "802ea477f29d423f8b333d69a2271ab0"
GEMINI_API_KEY = "AIzaSyA8fqdomGBQ4f4ypqOn5k53W4JrCf7iZbI"
REPO_PATH = "/opt/render/project/src/Vivimundo-blog"

# Configurar Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')

# Temas em rotação
TEMAS = [
    {"nome": "Esportes", "query": "esportes OR futebol OR basquete", "categoria": "esportes"},
    {"nome": "Entretenimento", "query": "entretenimento OR cinema OR música OR celebridades", "categoria": "entretenimento"},
    {"nome": "Tecnologia", "query": "tecnologia OR inovação OR ciência", "categoria": "tecnologia"},
    {"nome": "Videogames", "query": "videogames OR games OR esports", "categoria": "videogames"},
    {"nome": "Política Nacional", "query": "política brasil", "categoria": "politica-nacional"},
    {"nome": "Política Internacional", "query": "política internacional OR mundial", "categoria": "politica-internacional"}
]

tema_atual = 0
contador_posts = 0

def buscar_noticia(tema):
    """Busca notícia recente via NewsAPI"""
    url = "https://newsapi.org/v2/everything"
    ontem = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    params = {
        'q': tema['query'],
        'language': 'pt',
        'from': ontem,
        'sortBy': 'publishedAt',
        'apiKey': NEWS_API_KEY,
        'pageSize': 5
    }
    
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        if data.get('articles'):
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
    
    prompt = f"""Você é um jornalista profissional brasileiro. Reescreva esta notícia em português brasileiro com exatamente 500 palavras, mantendo um tom jornalístico e profissional.

Título original: {titulo}
Descrição: {descricao}
Conteúdo: {conteudo}

Crie uma matéria completa, bem estruturada, com introdução, desenvolvimento e conclusão. Não invente informações, apenas reescreva de forma profissional o conteúdo fornecido."""
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Erro ao gerar matéria: {e}")
        return None

def criar_slug(titulo):
    """Cria slug para URL da matéria"""
    import unicodedata
    import re
    
    # Remove acentos
    titulo = unicodedata.normalize('NFKD', titulo)
    titulo = titulo.encode('ascii', 'ignore').decode('ascii')
    
    # Converte para minúsculas e remove caracteres especiais
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
                {conteudo.replace(chr(10), '</p><p>')}
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
    
    # Salva arquivo
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
    for post in posts_recentes[-10:]:
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
        subprocess.run(['git', 'commit', '-m', f'Nova matéria - {datetime.now().strftime("%Y-%m-%d %H:%M")}'], check=True)
        subprocess.run(['git', 'push'], check=True)
        print("Deploy realizado com sucesso!")
    except Exception as e:
        print(f"Erro no deploy: {e}")

def executar_ciclo():
    """Executa um ciclo completo do bot"""
    global tema_atual
    
    print(f"\n{'='*50}")
    print(f"Iniciando ciclo - Tema: {TEMAS[tema_atual]['nome']}")
    print(f"{'='*50}\n")
    
    # Busca notícia
    noticia = buscar_noticia(TEMAS[tema_atual])
    if not noticia:
        print("Nenhuma notícia encontrada")
        tema_atual = (tema_atual + 1) % len(TEMAS)
        return
    
    print(f"Notícia encontrada: {noticia['title'][:60]}...")
    
    # Gera matéria
    conteudo = gerar_materia(noticia, TEMAS[tema_atual])
    if not conteudo:
        print("Erro ao gerar matéria")
        tema_atual = (tema_atual + 1) % len(TEMAS)
        return
    
    print("Matéria gerada com sucesso")
    
    # Pega imagem
    imagem_url = noticia.get('urlToImage', 'https://via.placeholder.com/800x450?text=Vivimundo')
    
    # Salva matéria
    data_br = datetime.now().strftime('%d/%m/%Y %H:%M')
    post_info = salvar_materia(
        noticia['title'],
        conteudo,
        imagem_url,
        TEMAS[tema_atual]['categoria'],
        data_br
    )
    
    print(f"Matéria salva: {post_info['url']}")
    
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
    atualizar_index(posts)
    
    # Faz deploy
    fazer_deploy()
    
    # Próximo tema
    tema_atual = (tema_atual + 1) % len(TEMAS)
    
    print(f"\nCiclo concluído! Próximo tema: {TEMAS[tema_atual]['nome']}")

if __name__ == "__main__":
    print("Bot Vivimundo iniciado!")
    print("Executando uma matéria por hora, 24/7")
    
    while True:
        try:
            executar_ciclo()
            print("\nAguardando 1 hora para próxima matéria...")
            time.sleep(3600)  # 1 hora
        except Exception as e:
            print(f"Erro no ciclo: {e}")
            print("Aguardando 5 minutos antes de tentar novamente...")
            time.sleep(300)