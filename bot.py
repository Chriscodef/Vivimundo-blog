#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import json
import requests
from datetime import datetime, timedelta
import google.generativeai as genai
from pathlib import Path
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import random
from bs4 import BeautifulSoup

# Força prints aparecerem imediatamente nos logs
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

def log(msg):
    """Log com flush forçado"""
    print(msg, flush=True)

# Configurações
NEWS_API_KEY = os.getenv('NEWS_API_KEY', '802ea477f29d423f8b333d69a2271ab0')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'AIzaSyA8fqdomGBQ4f4ypqOn5k53W4JrCf7iZbI')
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN', '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')
REPO_PATH = os.getenv('REPO_PATH', '/opt/render/project/src')

# Configurar Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash-latest')

# Temas
TEMAS = [
    {"nome": "Esportes", "categoria": "esportes", "sites": ["https://ge.globo.com/", "https://www.espn.com.br/"]},
    {"nome": "Entretenimento", "categoria": "entretenimento", "sites": ["https://www.adorocinema.com/noticias/", "https://www.tecmundo.com.br/cultura"]},
    {"nome": "Tecnologia", "categoria": "tecnologia", "sites": ["https://www.tecmundo.com.br/", "https://olhardigital.com.br/"]},
    {"nome": "Videogames", "categoria": "videogames", "sites": ["https://www.theenemy.com.br/", "https://www.tecmundo.com.br/games"]},
    {"nome": "Política Nacional", "categoria": "politica-nacional", "sites": ["https://g1.globo.com/politica/", "https://noticias.uol.com.br/politica/"]},
    {"nome": "Política Internacional", "categoria": "politica-internacional", "sites": ["https://g1.globo.com/mundo/", "https://www.bbc.com/portuguese/internacional"]}
]

# Headers realistas para evitar bloqueio
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1'
}

tema_idx = 0
total_posts = 0

# Servidor HTTP minimalista
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Vivimundo Bot</title>
<style>body{{background:#1a1a1a;color:#d4af37;font-family:Arial;padding:40px;text-align:center}}</style>
</head><body>
<h1>🌍 VIVIMUNDO BOT ATIVO</h1>
<p>Posts: {total_posts} | Próximo: {TEMAS[tema_idx]['nome']}</p>
<p>{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</p>
</body></html>"""
        self.wfile.write(html.encode())
    def log_message(self, format, *args):
        pass

def start_server():
    port = int(os.getenv('PORT', 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    log(f"✅ Servidor HTTP ativo na porta {port}")
    server.serve_forever()

def setup_repo():
    """Configura repositório Git"""
    try:
        os.chdir(REPO_PATH)
        log("📂 Configurando Git...")
        
        subprocess.run(['git', 'config', 'user.name', 'Vivimundo Bot'], check=True, capture_output=True)
        subprocess.run(['git', 'config', 'user.email', 'bot@vivimundo.com'], check=True, capture_output=True)
        
        # Remove e recria remote com token
        subprocess.run(['git', 'remote', 'remove', 'origin'], capture_output=True)
        repo_url = f'https://{GITHUB_TOKEN}@github.com/Chriscodef/Vivimundo-blog.git'
        subprocess.run(['git', 'remote', 'add', 'origin', repo_url], check=True, capture_output=True)
        
        # Checkout main
        subprocess.run(['git', 'checkout', 'main'], capture_output=True)
        subprocess.run(['git', 'pull', 'origin', 'main'], check=True, capture_output=True)
        
        log("✅ Git configurado!")
        return True
    except Exception as e:
        log(f"❌ Erro Git: {e}")
        return False

def buscar_noticia(tema):
    """Busca notícia via NewsAPI"""
    try:
        # Usa everything com queries em português
        ontem = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        # Queries mais genéricas que funcionam
        queries = {
            'esportes': 'futebol OR basquete OR olimpiadas',
            'entretenimento': 'cinema OR música OR celebridade OR filme',
            'tecnologia': 'tecnologia OR inovação OR inteligência artificial',
            'videogames': 'videogame OR playstation OR xbox OR nintendo',
            'politica-nacional': 'brasil OR lula OR governo brasileiro',
            'politica-internacional': 'EUA OR europa OR china OR mundo'
        }
        
        query = queries.get(tema['categoria'], 'notícias')
        
        params = {
            'q': query,
            'language': 'pt',
            'from': ontem,
            'sortBy': 'publishedAt',
            'apiKey': NEWS_API_KEY,
            'pageSize': 10
        }
        
        resp = requests.get('https://newsapi.org/v2/everything', params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        if data.get('status') == 'ok' and data.get('articles'):
            # Pega a primeira com título e descrição
            for art in data['articles']:
                if art.get('title') and art.get('description') and len(art.get('description', '')) > 50:
                    return art
        
        return None
    except Exception as e:
        log(f"❌ Erro buscar notícia: {e}")
        return None

def gerar_texto(noticia):
    """Gera matéria com Gemini"""
    try:
        prompt = f"""Você é jornalista do portal Vivimundo. Escreva uma matéria de 500 palavras em português brasileiro sobre:

Título: {noticia['title']}
Informações: {noticia.get('description', '')} {noticia.get('content', '')}

IMPORTANTE:
- Exatamente 500 palavras
- Tom jornalístico profissional
- Em parágrafos (não use listas)
- NÃO mencione fontes externas
- Seja objetivo e informativo"""

        resp = model.generate_content(prompt)
        texto = resp.text.strip()
        
        if len(texto) < 300:
            return None
        return texto
    except Exception as e:
        log(f"❌ Erro Gemini: {e}")
        return None

def salvar_post(titulo, texto, img, cat, data):
    """Salva post HTML"""
    global total_posts
    total_posts += 1
    
    slug = titulo.lower()[:50].replace(' ', '-').replace('?', '').replace('!', '')
    fname = f"post-{total_posts:04d}-{slug}.html"
    
    paragrafos = '\n'.join([f'<p>{p.strip()}</p>' for p in texto.split('\n\n') if p.strip()])
    
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
<span class="categoria categoria-{cat}">{cat.replace('-', ' ').title()}</span>
<span class="data">{data}</span>
</div>
<h1>{titulo}</h1>
<p class="autor">Por Kevin Ribeiro</p>
<img src="{img}" alt="{titulo}" class="post-imagem">
<div class="post-conteudo">
{paragrafos}
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
    
    (Path(REPO_PATH) / "posts").mkdir(exist_ok=True)
    with open(Path(REPO_PATH) / "posts" / fname, 'w', encoding='utf-8') as f:
        f.write(html)
    
    return {
        'titulo': titulo,
        'url': f"posts/{fname}",
        'imagem': img,
        'categoria': cat,
        'data': data
    }

def atualizar_home(posts):
    """Atualiza index.html"""
    cards = ""
    for p in reversed(posts[-10:]):
        cards += f"""<article class="post-card">
<img src="{p['imagem']}" alt="{p['titulo']}">
<div class="post-info">
<span class="categoria categoria-{p['categoria']}">{p['categoria'].replace('-', ' ').title()}</span>
<h2><a href="{p['url']}">{p['titulo']}</a></h2>
<p class="meta">Por Kevin Ribeiro • {p['data']}</p>
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
{cards}
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

def publicar():
    """Git push"""
    try:
        os.chdir(REPO_PATH)
        subprocess.run(['git', 'add', '.'], check=True, capture_output=True)
        
        result = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
        if not result.stdout.strip():
            log("⚠️ Nada para commitar")
            return
        
        subprocess.run(['git', 'commit', '-m', f'Nova matéria - {datetime.now().strftime("%d/%m/%Y %H:%M")}'], check=True, capture_output=True)
        subprocess.run(['git', 'push', 'origin', 'main'], check=True, capture_output=True)
        log("✅ Publicado no GitHub!")
    except Exception as e:
        log(f"❌ Erro publicar: {e}")

def executar():
    """Executa um ciclo"""
    global tema_idx
    
    tema = TEMAS[tema_idx]
    log(f"\n{'='*60}")
    log(f"🔄 CICLO #{total_posts + 1} - {tema['nome']}")
    log(f"{'='*60}")
    
    # Busca
    log(f"🔍 Buscando notícia...")
    noticia = buscar_noticia(tema)
    if not noticia:
        log("❌ Nenhuma notícia encontrada")
        tema_idx = (tema_idx + 1) % len(TEMAS)
        return
    
    log(f"✅ Encontrada: {noticia['title'][:50]}...")
    
    # Gera
    log(f"✍️ Gerando matéria...")
    texto = gerar_texto(noticia)
    if not texto:
        log("❌ Falha ao gerar texto")
        tema_idx = (tema_idx + 1) % len(TEMAS)
        return
    
    log(f"✅ Matéria gerada ({len(texto.split())} palavras)")
    
    # Salva
    img = noticia.get('urlToImage') or 'https://via.placeholder.com/800x450/1a1a1a/d4af37?text=Vivimundo'
    data = datetime.now().strftime('%d/%m/%Y às %H:%M')
    
    info = salvar_post(noticia['title'], texto, img, tema['categoria'], data)
    log(f"💾 Post salvo: {info['url']}")
    
    # Atualiza posts.json
    pfile = Path(REPO_PATH) / "posts.json"
    posts = json.load(open(pfile)) if pfile.exists() else []
    posts.append(info)
    json.dump(posts, open(pfile, 'w'), ensure_ascii=False, indent=2)
    
    # Atualiza home
    atualizar_home(posts)
    log("📝 Index atualizado")
    
    # Publica
    publicar()
    
    tema_idx = (tema_idx + 1) % len(TEMAS)
    log(f"✅ CONCLUÍDO! Próximo: {TEMAS[tema_idx]['nome']}\n")

if __name__ == "__main__":
    log("\n╔══════════════════════════════════════════════╗")
    log("║       🌍 BOT VIVIMUNDO INICIADO 🌍          ║")
    log("║                                              ║")
    log("║  📰 24 matérias/dia (1 por hora)            ║")
    log("║  🤖 Powered by Gemini AI                    ║")
    log("╚══════════════════════════════════════════════╝\n")
    
    # Inicia servidor HTTP
    http = threading.Thread(target=start_server, daemon=True)
    http.start()
    
    # Setup Git
    if not setup_repo():
        log("❌ FALHA NO SETUP - ENCERRANDO")
        sys.exit(1)
    
    log("⏰ Iniciando loop (1 matéria/hora)...\n")
    
    # Loop principal
    while True:
        try:
            executar()
            prox = datetime.now() + timedelta(hours=1)
            log(f"😴 Aguardando 1 hora... (próximo: {prox.strftime('%H:%M')})")
            time.sleep(3600)
        except KeyboardInterrupt:
            log("\n👋 Encerrado")
            break
        except Exception as e:
            log(f"\n❌ ERRO: {e}")
            log("⏳ Aguardando 5min...\n")
            time.sleep(300)
