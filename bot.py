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
import urllib3

# Desabilitar SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

sys.stdout.reconfigure(line_buffering=True, encoding='utf-8')
sys.stderr.reconfigure(line_buffering=True, encoding='utf-8')
os.environ['PYTHONIOENCODING'] = 'utf-8'

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
    {"nome": "Esportes", "categoria": "esportes", "sites": ["https://ge.globo.com/", "https://www.espn.com.br/", "https://www.uol.com.br/esporte/"]},
    {"nome": "Entretenimento", "categoria": "entretenimento", "sites": ["https://www.omelete.com.br/", "https://www.tecmundo.com.br/cultura", "https://noticiasdocinema.com.br/"]},
    {"nome": "Tecnologia", "categoria": "tecnologia", "sites": ["https://www.tecmundo.com.br/", "https://olhardigital.com.br/", "https://www.hardware.com.br/"]},
    {"nome": "Videogames", "categoria": "videogames", "sites": ["https://www.gamerant.com/", "https://www.ign.com.br/", "https://www.thegamer.com.br/"]},
    {"nome": "Política Nacional", "categoria": "politica-nacional", "sites": ["https://g1.globo.com/politica/", "https://noticias.uol.com.br/politica/", "https://www.folhapress.com.br/"]},
    {"nome": "Política Internacional", "categoria": "politica-internacional", "sites": ["https://g1.globo.com/mundo/", "https://www.bbc.com/portuguese/internacional", "https://noticias.uol.com.br/internacional/"]}
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

def extrair_imagem_meta(soup, url):
    """Extrai imagem de meta tags (og:image, twitter:image)"""
    try:
        # Tenta og:image primeiro
        img = soup.find('meta', property='og:image')
        if img and img.get('content'):
            return img['content']
        
        # Tenta twitter:image
        img = soup.find('meta', attrs={'name': 'twitter:image'})
        if img and img.get('content'):
            return img['content']
        
        # Tenta img com classe específica
        img = soup.find('img', class_=lambda x: x and any(palavra in str(x).lower() for palavra in ['article', 'post', 'destaque', 'noticia', 'manchete']))
        if img and img.get('src'):
            return img['src']
    except:
        pass
    return None

def buscar_noticia(tema):
    time.sleep(random.uniform(1, 3))
    
    # Palavras-chave por categoria para validação semântica
    palavras_categoria = {
        'esportes': ['futebol', 'basquete', 'tênis', 'voley', 'natação', 'atletismo', 'olimpíada', 'campeonato', 'jogo', 'time', 'jogador', 'gol', 'jogadores', 'partida', 'sport', 'football', 'basketball', 'soccer', 'nfl', 'nba', 'champions'],
        'entretenimento': ['filme', 'série', 'ator', 'atriz', 'cinema', 'netflix', 'novela', 'música', 'cantor', 'artista', 'show', 'teatro', 'premiação', 'oscar', 'grammy', 'music', 'movie', 'streaming', 'pop', 'rock', 'episódio', 'produção'],
        'tecnologia': ['tecnologia', 'app', 'software', 'hardware', 'computador', 'smartphone', 'inteligência artificial', 'ia', 'programação', 'data', 'tech', 'digital', 'inovação', 'startup', 'código', 'sistema', 'programa', 'internet', 'web', 'nuvem', 'banco de dados'],
        'videogames': ['jogo', 'game', 'console', 'xbox', 'playstation', 'nintendo', 'pc gaming', 'esports', 'twitch', 'gamer', 'rpg', 'ação', 'multiplayer', 'lançamento', 'videogame', 'ps5', 'ps4', 'switch', 'elden ring'],
        'politica-nacional': ['brasil', 'congresso', 'senado', 'câmara', 'presidente', 'eleição', 'voto', 'lei', 'decreto', 'governo', 'ministro', 'política', 'democracia', 'brasileiro', 'nacional', 'estado', 'deputado', 'senador'],
        'politica-internacional': ['país', 'presidente', 'premier', 'chanceler', 'eleição', 'guerra', 'diplomacia', 'onu', 'tratado', 'internacional', 'relações', 'exterior', 'conflito', 'global', 'mundial', 'união europeia', 'rússia', 'china', 'eua', 'geopolítica']
    }
    
    for site_url in tema['sites']:
        try:
            log(f"  🔍 Tentando {site_url}...")
            
            resp = requests.get(site_url, headers=HEADERS, timeout=20, verify=False)
            resp.encoding = 'utf-8'
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Busca links em artigos, posts ou seções de notícias
            links = soup.find_all('a', href=True)
            links = links[:60]  # Busca em mais links
            
            for link in links:
                href = link.get('href', '')
                titulo = link.get_text(strip=True)
                
                # Filtros de qualidade
                if not titulo or len(titulo) < 15 or len(titulo) > 250:
                    continue
                
                # Palavras-chave para excluir
                palavras_bloqueadas = [
                    'publicidade', 'anúncio', 'assine', 'login', 'cadastro', 'newsletter',
                    'amazon', 'aliexpress', 'mercado livre', 'shopee', 'custo', 'preço',
                    'compre', 'oferta', 'desconto', 'cupom', 'promoção', 'black friday',
                    'aviso', 'clique', 'compartilhe', 'siga', 'inscreva', 'download',
                    'vpn', 'antivírus', 'norton', 'testegrátis', 'teste grátis', '% off', '% offert',
                    'código', 'cupom', 'deal', 'cyber', 'viagem', 'hotel', 'passagem',
                    'fone', 'fones', 'headphone', 'smartphone', 'iphone', 'samsung',
                    'termos', 'condições', 'privacidade', 'cookies', 'contato'
                ]
                
                if any(palavra in titulo.lower() for palavra in palavras_bloqueadas):
                    continue
                
                # Formata URL relativa
                if href.startswith('/'):
                    from urllib.parse import urljoin
                    href = urljoin(site_url, href)
                
                if not href.startswith('http'):
                    continue
                
                # Bloqueia links para plataformas de compra
                urls_bloqueadas = ['amazon.com', 'aliexpress.com', 'mercadolivre.com', 'shopee.com', 'ebay.com']
                if any(bloqueado in href.lower() for bloqueado in urls_bloqueadas):
                    continue
                
                try:
                    time.sleep(random.uniform(0.7, 1.5))
                    
                    # Acessa artigo
                    art_resp = requests.get(href, headers=HEADERS, timeout=10, verify=False)
                    art_resp.encoding = 'utf-8'
                    art_soup = BeautifulSoup(art_resp.text, 'html.parser')
                    
                    # Extrai título real da página (não do link)
                    titulo_real = None
                    
                    # Tenta title tag primeiro
                    title_tag = art_soup.find('title')
                    if title_tag:
                        titulo_real = title_tag.get_text(strip=True)
                        # Remove sufixo comum de sites
                        for sufixo in [' - ', ' | ', ' - UOL', ' - G1', ' - Globo']:
                            if sufixo in titulo_real:
                                titulo_real = titulo_real.split(sufixo)[0]
                    
                    # Se não conseguiu, tenta og:title
                    if not titulo_real:
                        og_title = art_soup.find('meta', property='og:title')
                        if og_title and og_title.get('content'):
                            titulo_real = og_title['content']
                    
                    # Se ainda não tem, tenta h1
                    if not titulo_real:
                        h1 = art_soup.find('h1')
                        if h1:
                            titulo_real = h1.get_text(strip=True)
                    
                    # Usa o título original se não conseguiu extrair
                    if not titulo_real:
                        titulo_real = titulo
                    
                    # Valida o título real
                    if not titulo_real or len(titulo_real) < 15 or len(titulo_real) > 250:
                        continue
                    
                    # Remove lixo
                    for tag in art_soup(['script', 'style', 'nav', 'footer', 'aside']):
                        tag.decompose()
                    
                    # Busca conteúdo em parágrafos
                    paragrafos = art_soup.find_all('p')
                    texto = ' '.join(p.get_text(strip=True) for p in paragrafos if len(p.get_text(strip=True)) > 30)
                    
                    # Se não encontrou em <p>, tenta em divs com classes de artigo
                    if len(texto) < 400:
                        article = art_soup.find(['article', 'div', 'main'], class_=lambda x: x and any(palavra in str(x).lower() for palavra in ['article', 'post', 'content', 'corpo', 'noticia', 'body', 'text']))
                        if article:
                            paragrafos = article.find_all('p')
                            texto = ' '.join(p.get_text(strip=True) for p in paragrafos if len(p.get_text(strip=True)) > 30)
                    
                    # Validação semântica: verifica se o conteúdo corresponde à categoria
                    categoria_nome = tema['categoria']
                    palavras_validas = palavras_categoria.get(categoria_nome, [])
                    conteudo_baixo = (titulo_real + ' ' + texto).lower()
                    
                    # Conta quantas palavras-chave da categoria estão presentes
                    palavras_encontradas = sum(1 for palavra in palavras_validas if palavra in conteudo_baixo)
                    
                    # Precisa ter pelo menos 1-2 palavras-chave da categoria
                    minimo_palavras = max(1, len(palavras_validas) // 10)
                    if palavras_encontradas < minimo_palavras:
                        continue
                    
                    # Verifica comprimento mínimo do conteúdo
                    if len(texto) < 400:
                        continue
                    
                    # Busca imagem com função melhorada
                    img_url = extrair_imagem_meta(art_soup, href)
                    
                    # Formata URL da imagem
                    if img_url and not img_url.startswith('http'):
                        from urllib.parse import urljoin
                        img_url = urljoin(href, img_url)

                    
                    # Valida conteúdo
                    if len(texto) > 500:
                        log(f"  ✅ Encontrada: {titulo_real[:60]}...")
                        return {
                            'title': titulo_real, 
                            'content': texto, 
                            'urlToImage': img_url or 'https://via.placeholder.com/800x450/1a1a1a/d4af37?text=Vivimundo', 
                            'url': href
                        }
                except (requests.exceptions.Timeout, TimeoutError):
                    continue
                except Exception as e:
                    continue
            
            log(f"  ⚠️ Nada encontrado em {site_url}")
        except Exception as e:
            log(f"  ❌ Erro em {site_url}: {str(e)[:60]}")
            continue
    
    return None

def limpar_markdown(texto):
    """Remove formatação markdown do texto"""
    import re
    # Remove **texto** -> texto
    texto = re.sub(r'\*\*(.*?)\*\*', r'\1', texto)
    # Remove *texto* -> texto
    texto = re.sub(r'\*(.*?)\*', r'\1', texto)
    # Remove __texto__ -> texto
    texto = re.sub(r'__(.*?)__', r'\1', texto)
    # Remove # titulo -> titulo
    texto = re.sub(r'^#+\s+', '', texto, flags=re.MULTILINE)
    # Remove tags HTML malformadas
    texto = re.sub(r'<p><h\d>(.*?)</h\d></p>', r'\1', texto)
    texto = re.sub(r'<p><p>(.*?)</p></p>', r'\1', texto)
    # Remove tags HTML abertas
    texto = re.sub(r'<h\d>|</h\d>', '', texto)
    return texto

def formatar_paragrafos(texto):
    """Formata texto em parágrafos HTML bem estruturados"""
    import re
    # Limpa markdown primeiro
    texto = limpar_markdown(texto)
    
    # Remove tags HTML restantes
    texto = re.sub(r'<[^>]+>', '', texto)
    
    # Divide em parágrafos por quebras duplas ou por pontos finais
    blocos = texto.split('\n\n')
    
    html = ""
    for bloco in blocos:
        bloco = bloco.strip()
        if len(bloco) > 50:  # Ignora blocos muito pequenos
            # Remove espaços múltiplos
            bloco = re.sub(r'\s+', ' ', bloco)
            html += f'<p>{bloco}</p>\n'
    
    return html

def extrair_imagem_melhorada(soup, url):
    """Extrai a melhor imagem do artigo"""
    try:
        # Tenta og:image primeiro (mais confiável)
        img = soup.find('meta', property='og:image')
        if img and img.get('content'):
            img_url = img['content']
            # Evita logos e ícones
            if not any(x in img_url.lower() for x in ['logo', 'icon', 'badge', 'avatar', 'profile']):
                return img_url
        
        # Tenta twitter:image
        img = soup.find('meta', attrs={'name': 'twitter:image'})
        if img and img.get('content'):
            return img['content']
        
        # Procura por imagem grande no artigo
        imgs = soup.find_all('img')
        melhor_img = None
        melhor_tamanho = 0
        
        for img in imgs:
            src = img.get('src', '')
            alt = img.get('alt', '')
            
            # Ignora logos, ícones, banners pequenos
            if any(x in src.lower() or x in alt.lower() for x in ['logo', 'icon', 'badge', 'avatar', 'gif', 'svg', 'button']):
                continue
            
            # Prefere imagens com atributos de tamanho
            width = img.get('width', '0')
            height = img.get('height', '0')
            try:
                tamanho = int(width) * int(height) if width and height else 0
                if tamanho > melhor_tamanho:
                    melhor_tamanho = tamanho
                    melhor_img = src
            except:
                if src and not melhor_img:
                    melhor_img = src
        
        return melhor_img
    except:
        pass
    return None

def gerar_texto_fallback(noticia):
    """Gera texto com fallback quando Groq falha"""
    titulo = noticia['title']
    conteudo = noticia.get('content', '')[:2000]
    
    # Estrutura básica de matéria
    paragrafos = conteudo.split('\n\n')
    texto = f"{titulo}\n\n"
    
    for i, p in enumerate(paragrafos[:10]):
        if len(p.strip()) > 50:
            texto += f"{p.strip()}\n\n"
    
    # Se ficou muito curto, repete o conteúdo
    if len(texto) < 800:
        texto += "\n" + conteudo
    
    return texto[:3000]  # Limita a 3000 caracteres

def gerar_texto(noticia):
    prompt = f"""Escreva uma matéria jornalística completa em português brasileiro (mínimo 450 palavras, parágrafos, tom profissional) sobre:

Título: {noticia['title']}
Conteúdo: {noticia.get('content', '')[:3000]}

Não mencione fontes. Seja objetivo. Use apenas HTML simples (sem markdown)."""
    try:
        resp = requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers={'Authorization': f'Bearer {GROQ_API_KEY}', 'Content-Type': 'application/json'},
            json={'model': 'llama-3.3-70b-versatile', 'messages': [{'role': 'user', 'content': prompt}], 'temperature': 0.7, 'max_tokens': 2000},
            timeout=60
        )
        resp.raise_for_status()
        texto = resp.json()['choices'][0]['message']['content'].strip()
        # Limpa markdown do texto gerado
        texto = limpar_markdown(texto)
        log(f"  ✅ Matéria gerada ({len(texto.split())} palavras)")
        return texto
    except Exception as e:
        log(f"  ⚠️ Groq falhou: {str(e)[:60]}")
        log(f"  📝 Usando fallback (conteúdo extraído)...")
        return gerar_texto_fallback(noticia)

def salvar_post(titulo, texto, img, cat, data, post_id):
    slug = titulo.lower()[:50].replace(' ', '-').replace('?', '').replace('!', '').replace('/', '-')
    fname = f"post-{post_id:04d}-{slug}.html"
    
    # Formata parágrafos com função melhorada
    paragrafos = formatar_paragrafos(texto)
    
    # HTML com styling melhorado
    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta property="og:title" content="{titulo}">
<meta property="og:image" content="{img}">
<meta property="og:type" content="article">
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
<div class="post-header">
<span class="post-categoria">{cat.replace('-',' ').title()}</span>
<h1 class="post-titulo">{titulo}</h1>
<div class="post-data">Por Kevin Ribeiro • {data}</div>
</div>
<img src="{img}" class="post-principal-imagem" alt="{titulo}" loading="lazy">
<div class="post-conteudo">
{paragrafos}
</div>
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
<a href="categoria-esportes.html">Esportes</a>
<a href="categoria-entretenimento.html">Entretenimento</a>
<a href="categoria-tecnologia.html">Tecnologia</a>
<a href="categoria-videogames.html">Videogames</a>
<a href="categoria-politica-nacional.html">Política Nacional</a>
<a href="categoria-politica-internacional.html">Política Internacional</a>
<a href="sobre.html">Sobre</a>
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

def gerar_paginas_categorias(posts):
    """Gera páginas para cada categoria com artigos filtrados"""
    categorias = {}
    for p in posts:
        cat = p['categoria']
        if cat not in categorias:
            categorias[cat] = []
        categorias[cat].append(p)
    
    for cat, artigos in categorias.items():
        cards = ""
        for p in reversed(artigos[-20:]):
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
<title>{cat.replace('-',' ').title()} - Vivimundo</title><link rel="stylesheet" href="style.css"></head>
<body>
<header><div class="container"><h1 class="logo">VIVIMUNDO</h1>
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
</div></header>
<main class="container">
<h2 class="secao-titulo">{cat.replace('-',' ').title()}</h2>
<div class="posts-grid">{cards}</div>
</main>
<footer><div class="container"><p>© 2026 Vivimundo</p><a href="https://x.com/Kevin_RSP0" target="_blank">Twitter</a></div></footer>
</body></html>"""
        
        fname = f"categoria-{cat}.html"
        with open(fname, 'w', encoding='utf-8') as f:
            f.write(html)
        log(f"  📚 Categoria '{cat}' atualizada")

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
        log("⚠️ Sem conteúdo para salvar")
        return

    info = salvar_post(noticia['title'], texto, noticia.get('urlToImage'), tema['categoria'], datetime.now().strftime('%d/%m/%Y às %H:%M'), total_posts + 1)
    posts.append(info)
    json.dump(posts, open(pfile, 'w'), ensure_ascii=False, indent=2)
    atualizar_home(posts)
    gerar_paginas_categorias(posts)
    publicar()

    # Salva estado para próxima execução
    tema_idx = (tema_idx + 1) % len(TEMAS)
    salvar_estado(tema_idx, total_posts + 1)
    log("\n✅ CICLO CONCLUÍDO!")

if __name__ == "__main__":
    log("🌍 VIVIMUNDO BOT - GitHub Actions")
    setup_repo()
    executar()
