#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import json
import requests
from datetime import datetime
from pathlib import Path
import subprocess
import random
from bs4 import BeautifulSoup

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

def log(msg):
    print(msg, flush=True)

# Configurações
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
REPO_PATH = os.getenv('GITHUB_WORKSPACE', '.')
if not GROQ_API_KEY:
    log("❌ GROQ_API_KEY não encontrada!")
    sys.exit(1)

# Arquivo para salvar estado
STATE_FILE = Path(REPO_PATH) / "bot_state.json"

def carregar_estado():
    """Carrega o índice do último tema executado"""
    if STATE_FILE.exists():
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
            return state.get('tema_idx', 0), state.get('total_posts', 0)
    return 0, 0

def salvar_estado(tema_idx, total_posts):
    """Salva o índice do tema para próxima execução"""
    with open(STATE_FILE, 'w') as f:
        json.dump({'tema_idx': tema_idx, 'total_posts': total_posts}, f)

TEMAS = [
    {"nome": "Esportes", "categoria": "esportes", "sites": ["https://ge.globo.com/", "https://www.espn.com.br/"]},
    {"nome": "Entretenimento", "categoria": "entretenimento", "sites": ["https://www.adorocinema.com/noticias/", "https://www.tecmundo.com.br/cultura"]},
    {"nome": "Tecnologia", "categoria": "tecnologia", "sites": ["https://www.tecmundo.com.br/", "https://olhardigital.com.br/"]},
    {"nome": "Videogames", "categoria": "videogames", "sites": ["https://www.theenemy.com.br/", "https://www.tecmundo.com.br/games"]},
    {"nome": "Política Nacional", "categoria": "politica-nacional", "sites": ["https://g1.globo.com/politica/", "https://noticias.uol.com.br/politica/"]},
    {"nome": "Política Internacional", "categoria": "politica-internacional", "sites": ["https://g1.globo.com/mundo/", "https://www.bbc.com/portuguese/internacional"]}
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
}

def setup_repo():
    try:
        log("📂 Configurando Git...")
        subprocess.run(['git', 'config', 'user.name', 'Vivimundo Bot'], check=True)
        subprocess.run(['git', 'config', 'user.email', 'bot@vivimundo.com'], check=True)
        if GITHUB_TOKEN:
            repo_url = f'https://{GITHUB_TOKEN}@github.com/Chriscodef/Vivimundo-blog.git'
            subprocess.run(['git', 'remote', 'remove', 'origin'], capture_output=True)
            subprocess.run(['git', 'remote', 'add', 'origin', repo_url], check=True, capture_output=True)
        subprocess.run(['git', 'pull', 'origin', 'main', '--rebase'], check=False)
        log("✅ Git OK")
        return True
    except Exception as e:
        log(f"⚠️ {e}")
        return True

def buscar_noticia(tema):
    time.sleep(random.uniform(1, 3))
    for site_url in tema['sites']:
        try:
            log(f"  🔍 Tentando {site_url}...")
            resp = requests.get(site_url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'html.parser')
            links = soup.find_all('a', href=True)
            for link in links[:30]:
                href = link.get('href', '')
                titulo = link.get_text(strip=True)
                if not titulo or len(titulo) < 20 or len(titulo) > 200:
                    continue
                if href.startswith('/'):
                    from urllib.parse import urljoin
                    href = urljoin(site_url, href)
                if not href.startswith('http'):
                    continue
                try:
                    time.sleep(random.uniform(0.3, 0.8))
                    art_resp = requests.get(href, headers=HEADERS, timeout=15)
                    art_soup = BeautifulSoup(art_resp.text, 'html.parser')
                    for script in art_soup(['script', 'style']): script.decompose()
                    texto = ' '.join(p.get_text(strip=True) for p in art_soup.find_all('p'))
                    img = art_soup.find('img')
                    img_url = img.get('src') if img else ''
                    if img_url and not img_url.startswith('http'):
                        from urllib.parse import urljoin
                        img_url = urljoin(href, img_url)
                    if len(texto) > 400:
                        log(f"  ✅ Encontrada: {titulo[:50]}...")
                        return {'title': titulo, 'content': texto, 'urlToImage': img_url or 'https://via.placeholder.com/800x450/1a1a1a/d4af37?text=Vivimundo', 'url': href}
                except Exception as e:
                    continue
            log(f"  ⚠️ Nada encontrado em {site_url}")
        except Exception as e:
            log(f"  ❌ Erro em {site_url}: {str(e)[:50]}")
            continue
    return None

def gerar_texto(noticia):
    prompt = f"""Escreva uma matéria jornalística completa em português brasileiro (mínimo 450 palavras, parágrafos, tom profissional) sobre:

Título: {noticia['title']}
Conteúdo: {noticia.get('content', '')[:3000]}

Não mencione fontes. Seja objetivo."""
    try:
        resp = requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers={'Authorization': f'Bearer {GROQ_API_KEY}', 'Content-Type': 'application/json'},
            json={'model': 'llama-3.3-70b-versatile', 'messages': [{'role': 'user', 'content': prompt}], 'temperature': 0.7, 'max_tokens': 2000},
            timeout=60
        )
        resp.raise_for_status()
        texto = resp.json()['choices'][0]['message']['content'].strip()
        log(f"  ✅ Matéria gerada ({len(texto.split())} palavras)")
        return texto
    except Exception as e:
        log(f"  ❌ Groq: {e}")
        return None

def salvar_post(titulo, texto, img, cat, data, post_id):
    slug = titulo.lower()[:50].replace(' ', '-').replace('?', '').replace('!', '').replace('/', '-')
    fname = f"post-{post_id:04d}-{slug}.html"
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
<header><div class="container"><h1 class="logo">VIVIMUNDO</h1>
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
</div></header>
<main class="container">
<article class="post-completo">
<div class="post-meta"><span class="categoria categoria-{cat}">{cat.replace('-',' ').title()}</span> <span>{data}</span></div>
<h1>{titulo}</h1>
<p class="autor">Por Kevin Ribeiro</p>
<img src="{img}" class="post-imagem" alt="{titulo}">
<div class="post-conteudo">{paragrafos}</div>
</article>
</main>
<footer><div class="container"><p>© 2026 Vivimundo</p><a href="https://x.com/Kevin_RSP0" target="_blank">Twitter</a></div></footer>
</body></html>"""
    
    Path("posts").mkdir(exist_ok=True)
    with open(Path("posts") / fname, 'w', encoding='utf-8') as f:
        f.write(html)
    log(f"  💾 Post salvo: {fname}")
    return {'titulo': titulo, 'url': f"posts/{fname}", 'imagem': img, 'categoria': cat, 'data': data}

def atualizar_home(posts):
    cards = ""
    for p in reversed(posts[-10:]):
        cards += f"""<article class="post-card">
<img src="{p['imagem']}" alt="{p['titulo']}">
<div class="post-info">
<span class="categoria categoria-{p['categoria']}">{p['categoria'].replace('-',' ').title()}</span>
<h2><a href="{p['url']}">{p['titulo']}</a></h2>
<p class="meta">Por Kevin Ribeiro • {p['data']}</p>
</div>
</article>"""
    
    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Vivimundo - Portal de Notícias</title><link rel="stylesheet" href="style.css"></head>
<body>
<header><div class="container"><h1 class="logo">VIVIMUNDO</h1>
<nav>
<a href="index.html">Início</a>
<a href="../categoria-esportes.html">Esportes</a>
<a href="../categoria-entretenimento.html">Entretenimento</a>
<a href="../categoria-tecnologia.html">Tecnologia</a>
<a href="../categoria-videogames.html">Videogames</a>
<a href="../categoria-politica-nacional.html">Política Nacional</a>
<a href="../categoria-politica-internacional.html">Política Internacional</a>
<a href="../sobre.html">Sobre</a>
</nav>
</div></header>
<main class="container">
<h2 class="secao-titulo">Últimas Notícias</h2>
<div class="posts-grid">{cards}</div>
</main>
<footer><div class="container"><p>© 2026 Vivimundo</p><a href="https://x.com/Kevin_RSP0" target="_blank">Twitter</a></div></footer>
</body></html>"""
    with open("index.html", 'w', encoding='utf-8') as f:
        f.write(html)
    log("  📝 Index atualizado")

def publicar():
    try:
        result = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
        if not result.stdout.strip():
            log("  ⚠️ Nada para commitar")
            return
        subprocess.run(['git', 'add', '.'], check=True)
        subprocess.run(['git', 'commit', '-m', f'Nova matéria - {datetime.now().strftime("%d/%m/%Y %H:%M")}'], check=True)
        subprocess.run(['git', 'push', 'origin', 'main'], check=True, timeout=30)
        log("  ✅ Push realizado!")
    except Exception as e:
        log(f"  ❌ Push: {e}")

def executar():
    pfile = Path("posts.json")
    posts = json.load(open(pfile)) if pfile.exists() else []
    tema_idx, total_posts = carregar_estado()
    tema = TEMAS[tema_idx]

    log(f"\n{'='*60}")
    log(f"🔄 POST #{total_posts + 1} - {tema['nome']}")
    log(f"{'='*60}")
    
    noticia = buscar_noticia(tema)
    if not noticia:
        log("❌ Nenhuma notícia encontrada")
        return
    
    texto = gerar_texto(noticia)
    if not texto:
        log("❌ Falha ao gerar texto")
        return

    info = salvar_post(noticia['title'], texto, noticia.get('urlToImage'), tema['categoria'], datetime.now().strftime('%d/%m/%Y às %H:%M'), total_posts + 1)
    posts.append(info)
    json.dump(posts, open(pfile, 'w'), ensure_ascii=False, indent=2)
    atualizar_home(posts)
    publicar()

    # Salva estado para próxima execução
    tema_idx = (tema_idx + 1) % len(TEMAS)
    salvar_estado(tema_idx, total_posts + 1)
    log("\n✅ CICLO CONCLUÍDO!")

if __name__ == "__main__":
    log("🌍 VIVIMUNDO BOT - GitHub Actions")
    setup_repo()
    executar()
