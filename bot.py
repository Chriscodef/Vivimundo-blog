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
ARTICLES_CACHE = Path(REPO_PATH) / "articles_cache.json"

def carregar_cache_artigos():
    """Carrega URLs e títulos já processados"""
    if ARTICLES_CACHE.exists():
        with open(ARTICLES_CACHE, 'r') as f:
            data = json.load(f)
            if isinstance(data, dict):
                return set(data.get('urls', [])), set(data.get('titulos', []))
            # Compatibilidade com formato antigo (apenas URLs)
            return set(data), set()
    return set(), set()

def salvar_cache_artigos(urls, titulos):
    """Salva URLs e títulos processados"""
    with open(ARTICLES_CACHE, 'w') as f:
        json.dump({'urls': list(urls), 'titulos': list(titulos)}, f)

def normalizar_url(url):
    """Normaliza URL para comparação consistente no cache"""
    from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
    
    # Converte para lowercase
    url = url.lower().strip()
    
    # Remove trailing slash
    if url.endswith('/'):
        url = url[:-1]
    
    # Parse URL
    parsed = urlparse(url)
    
    # Remove parâmetros de tracking comuns (utm_, fbclid, etc)
    query_params = parse_qs(parsed.query)
    params_limpos = {k: v for k, v in query_params.items() 
                     if not k.startswith(('utm_', 'fbclid', 'gclid', 'ref'))}
    
    # Reconstrói query string ordenada
    nova_query = urlencode(params_limpos, doseq=True) if params_limpos else ''
    
    # Reconstrói URL normalizada
    return urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        nova_query,
        ''  # Remove fragmento (#)
    ))

def normalizar_titulo(titulo):
    """Normaliza título para detecção de duplicatas"""
    import re
    # Remove espaços extras, converte para lowercase
    titulo = titulo.lower().strip()
    # Remove pontuação
    titulo = re.sub(r'[^\w\s]', '', titulo)
    # Remove espaços múltiplos
    titulo = re.sub(r'\s+', ' ', titulo)
    return titulo

def titulo_similar(titulo_novo, titulos_existentes, limiar=0.65):
    """Verifica se um título é similar a algum já existente usando comparação de palavras.
    Retorna True se encontrar um título com similaridade >= limiar (0.65 = 65%)."""
    palavras_novo = set(normalizar_titulo(titulo_novo).split())
    if len(palavras_novo) < 3:
        return False
    
    for titulo_existente in titulos_existentes:
        palavras_existente = set(titulo_existente.split())
        if len(palavras_existente) < 3:
            continue
        
        # Calcula similaridade de Jaccard (interseção / união)
        intersecao = palavras_novo & palavras_existente
        uniao = palavras_novo | palavras_existente
        similaridade = len(intersecao) / len(uniao) if uniao else 0
        
        if similaridade >= limiar:
            log(f"  🔄 Título similar ({similaridade:.0%}): {titulo_novo[:50]}...")
            return True
    
    return False

def eh_imagem_valida(img_url):
    """Verifica se a URL da imagem é real (não é placeholder, logo, etc)"""
    if not img_url:
        return False
    
    img_lower = img_url.lower()
    
    # Rejeita placeholders conhecidos
    placeholders_bloqueados = [
        'via.placeholder.com',
        'placeholder.com',
        'placehold.it',
        'placekitten.com',
        'picsum.photos',
        'dummyimage.com',
        'fakeimg.pl',
        'lorempixel.com',
        'loremflickr.com',
        'placeholderimage',
        'default-image',
        'no-image',
        'noimage',
        'sem-imagem',
        'image-not-found',
        'img-placeholder',
    ]
    
    if any(placeholder in img_lower for placeholder in placeholders_bloqueados):
        log(f"  🚫 Imagem placeholder rejeitada: {img_url[:60]}...")
        return False
    
    # Rejeita imagens muito pequenas (ícones, badges)
    extensoes_invalidas = ['.ico', '.svg', '.gif']
    if any(img_lower.endswith(ext) for ext in extensoes_invalidas):
        # SVGs e GIFs podem ser válidos se forem grandes, mas geralmente são logos
        if 'logo' in img_lower or 'icon' in img_lower or 'badge' in img_lower:
            log(f"  🚫 Imagem logo/ícone rejeitada: {img_url[:60]}...")
            return False
    
    # Rejeita data URIs (base64 inline images geralmente são ícones)
    if img_lower.startswith('data:'):
        return False
    
    # Rejeita URLs que são claramente logos ou avatares
    palavras_logo = ['logo', 'favicon', 'avatar', 'profile-pic', 'user-icon', 'brand']
    if any(palavra in img_lower for palavra in palavras_logo):
        log(f"  🚫 Imagem logo/avatar rejeitada: {img_url[:60]}...")
        return False
    
    return True


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
    {"nome": "Esportes", "categoria": "esportes", "sites": [
        "https://ge.globo.com/", "https://www.espn.com.br/", "https://www.uol.com.br/esporte/",
        "https://www.espn.com.br/futebol/", "https://www.grandepremio.com.br/",
        "https://www.lance.com.br/", "https://www.gazetaesportiva.com/",
    ]},
    {"nome": "Entretenimento", "categoria": "entretenimento", "sites": [
        "https://www.omelete.com.br/", "https://www.tecmundo.com.br/cultura",
        "https://noticiasdocinema.com.br/", "https://www.adorocinema.com/",
        "https://www.papelpop.com/", "https://rollingstone.com.br/",
    ]},
    {"nome": "Tecnologia", "categoria": "tecnologia", "sites": [
        "https://www.tecmundo.com.br/", "https://olhardigital.com.br/",
        "https://www.hardware.com.br/", "https://tecnoblog.net/",
        "https://canaltech.com.br/", "https://www.tudocelular.com/",
    ]},
    {"nome": "Videogames", "categoria": "videogames", "sites": [
        "https://www.gamerant.com/", "https://br.ign.com/",
        "https://www.thegamer.com.br/", "https://www.tecmundo.com.br/voxel",
        "https://www.theenemy.com.br/",
    ]},
    {"nome": "Política Nacional", "categoria": "politica-nacional", "sites": [
        "https://g1.globo.com/politica/", "https://noticias.uol.com.br/politica/",
        "https://www.poder360.com.br/", "https://www.cnnbrasil.com.br/politica/",
        "https://www.cartacapital.com.br/politica/",
    ]},
    {"nome": "Política Internacional", "categoria": "politica-internacional", "sites": [
        "https://g1.globo.com/mundo/", "https://www.bbc.com/portuguese/internacional",
        "https://noticias.uol.com.br/internacional/", "https://hojenomundomilitar.com.br/",
        "https://www.cnnbrasil.com.br/internacional/",
    ]},
    {"nome": "Rio de Janeiro", "categoria": "rio-de-janeiro", "sites": [
        "https://g1.globo.com/rj/rio-de-janeiro/", "https://odia.ig.com.br/",
        "https://diariodorio.com/", "https://www.band.uol.com.br/band-news-fm/rio",
        "https://extra.globo.com/noticias/rio/",
    ]},
    {"nome": "São Paulo", "categoria": "sao-paulo", "sites": [
        "https://g1.globo.com/sp/sao-paulo/", "https://www.band.uol.com.br/band-news-fm/sp",
        "https://noticias.r7.com/sao-paulo/", "https://agora.folha.uol.com.br/sao-paulo/",
    ]},
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

def limpar_titulo(titulo):
    """Limpa títulos com palavras grudadas (ex: 'JacksonVeja' -> 'Jackson Veja')"""
    import re
    
    # Padrão 1: letra minúscula seguida de maiúscula (ex: "jacksonVeja")
    titulo = re.sub(r'([a-zà-ú])([A-ZÀ-Ú])', r'\1 \2', titulo)
    
    # Padrão 2: pontuação seguida de letra sem espaço (ex: "AÍ!Baldur's", "ok.Veja")
    titulo = re.sub(r'([!?:.\)\]])([A-ZÀ-Úa-zà-ú])', r'\1 \2', titulo)
    
    # Padrão 3: palavra completamente maiúscula seguida de palavra capitalizada (ex: "HPComo")
    titulo = re.sub(r'([A-ZÀ-Ú]{2,})([A-ZÀ-Ú][a-zà-ú])', r'\1 \2', titulo)
    
    # Padrão 4: dígito seguido de letra maiúscula sem espaço (ex: "9Ganha")
    titulo = re.sub(r'(\d)([A-ZÀ-Ú])', r'\1 \2', titulo)
    
    # Padrão 5: letra seguida de dígito colado em contexto estranho (ex: "veja3motivos")
    titulo = re.sub(r'([a-zà-ú])(\d+)([A-ZÀ-Ú])', r'\1 \2 \3', titulo)
    
    # Padrão 6: fecha aspas/parênteses colado em próxima palavra
    titulo = re.sub(r'(["\'»])([A-ZÀ-Úa-zà-ú])', r'\1 \2', titulo)
    
    # Remove espaços múltiplos
    titulo = re.sub(r'\s+', ' ', titulo)
    
    return titulo.strip()

def eh_titulo_valido(titulo):
    """Valida se o título é real (não é número de telefone, sequência, etc)"""
    import re
    # Remove espaços extras
    titulo = titulo.strip()
    
    # Muito curto ou longo
    if len(titulo) < 20 or len(titulo) > 250:
        log(f"  🚫 Título rejeitado (tamanho {len(titulo)}): {titulo[:60]}...")
        return False
    
    # Parece número de telefone ou ID
    if titulo.replace('-', '').replace('(', '').replace(')', '').isdigit():
        return False
    
    # Muitos números (telefone, CEP, etc)
    num_count = sum(1 for c in titulo if c.isdigit())
    if num_count > len(titulo) * 0.3:  # Mais de 30% números
        return False
    
    # Palavras válidas mínimas (não é só números e símbolos)
    palavras = [p for p in titulo.split() if len(p) > 2 and not p.isdigit()]
    if len(palavras) < 3:  # Menos de 3 palavras válidas
        log(f"  🚫 Título rejeitado (poucas palavras): {titulo[:60]}...")
        return False
    
    # Rejeita títulos genéricos de seção (não são notícias reais)
    titulo_lower = titulo.lower()
    palavras_secao = [
        'advance', 'latest', 'more', 'daily', 'special', 'featured',
        'esportes a motor', 'game rant', 'puzzles and games',
        'trending', 'popular', 'recommended', 'breaking',
        'read more', 'see more', 'leia mais', 'veja mais', 'saiba mais',
        'menu principal', 'navegação', 'buscar', 'pesquisar',
        'home', 'início', 'voltar', 'anterior', 'próximo',
        'cookies', 'privacidade', 'termos de uso',
        'sign in', 'sign up', 'subscribe', 'follow us',
        'all rights reserved', 'todos os direitos',
        'notícias recentes', 'mais lidas', 'mais populares',
        'editor picks', 'top stories', 'highlights',
        'the gamer', 'ign brasil', 'tecmundo', 'olhar digital',
        'game reviews', 'movie reviews', 'tv reviews',
        'about us', 'contact us', 'advertise',
    ]
    for palavra in palavras_secao:
        if titulo_lower == palavra or titulo_lower.startswith(palavra + ' ') or titulo_lower.endswith(' ' + palavra):
            log(f"  🚫 Título rejeitado (seção genérica): {titulo[:60]}...")
            return False
        # Rejeita se o título inteiro é basicamente a palavra de seção
        if palavra in titulo_lower and len(titulo) < len(palavra) + 15:
            log(f"  🚫 Título rejeitado (seção genérica curta): {titulo[:60]}...")
            return False
    
    # Rejeita títulos que são apenas nomes de categorias/seções do site
    titulos_exatos_bloqueados = [
        'esportes', 'entretenimento', 'tecnologia', 'videogames', 'games',
        'política', 'economia', 'mundo', 'brasil', 'cultura', 'ciência',
        'saúde', 'educação', 'opinião', 'editorial', 'colunistas',
        'esportes a motor', 'automobilismo', 'futebol', 'basquete',
        'game rant advance', 'ign recommends', 'editor choice',
    ]
    if titulo_lower in titulos_exatos_bloqueados:
        log(f"  🚫 Título rejeitado (nome de categoria): {titulo[:60]}...")
        return False
    
    # Rejeita títulos muito curtos com poucas palavras significativas (provavelmente categorias)
    palavras_significativas = [p for p in titulo.split() if len(p) > 3 and p.isalpha()]
    if len(palavras_significativas) < 4:
        # Verifica se parece uma categoria (sem verbos de ação)
        verbos_acao = ['ganha', 'lança', 'confirma', 'aprova', 'revela', 'anuncia',
                       'chega', 'vence', 'perde', 'encontra', 'descobre', 'morre',
                       'nasce', 'cresce', 'cai', 'sobe', 'muda', 'fica', 'vai', 'vem',
                       'diz', 'afirma', 'declara', 'promete', 'nega', 'acusa',
                       'mostra', 'apresenta', 'estreia', 'lança', 'recebe',
                       'wins', 'loses', 'announces', 'reveals', 'launches', 'gets',
                       'shows', 'confirms', 'releases', 'updates', 'adds',
                       'pode', 'deve', 'será', 'está', 'foi', 'tem', 'faz',
                       'volta', 'entra', 'sai', 'abre', 'fecha', 'inicia',
                       'atinge', 'supera', 'bate', 'quebra', 'alcança']
        tem_verbo = any(verbo in titulo_lower for verbo in verbos_acao)
        if not tem_verbo:
            log(f"  🚫 Título rejeitado (sem verbo de ação): {titulo[:60]}...")
            return False
    
    # Rejeita títulos que parecem ser menus ou listas de navegação
    if titulo.count('|') > 1 or titulo.count('›') > 1 or titulo.count('»') > 1:
        log(f"  🚫 Título rejeitado (parece navegação): {titulo[:60]}...")
        return False
    
    # Rejeita títulos com muitas palavras em inglês em sites BR (provavelmente UI)
    palavras_en = ['the', 'and', 'for', 'with', 'from', 'this', 'that', 'your', 'our', 'their']
    contagem_en = sum(1 for p in titulo_lower.split() if p in palavras_en)
    if contagem_en >= 3 and len(titulo.split()) < 8:
        log(f"  🚫 Título rejeitado (parece UI em inglês): {titulo[:60]}...")
        return False
    
    return True


def buscar_noticia(tema):
    time.sleep(random.uniform(1, 3))
    urls_processadas, titulos_processados = carregar_cache_artigos()
    
    for site_url in tema['sites']:

        try:
            log(f"  🔍 Tentando {site_url}...")
            
            resp = requests.get(site_url, headers=HEADERS, timeout=20, verify=False)
            resp.encoding = 'utf-8'
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Busca links em artigos, posts ou seções de notícias
            links = soup.find_all('a', href=True)
            links = links[:80]  # Aumentar para buscar mais links
            
            for link in links:
                href = link.get('href', '')
                titulo = link.get_text(strip=True)
                
                # Limpa títulos grudados
                titulo = limpar_titulo(titulo)
                
                # Valida título
                if not eh_titulo_valido(titulo):

                    continue
                
                # Palavras-chave para excluir
                palavras_bloqueadas = [
                    'publicidade', 'anúncio', 'assine', 'login', 'cadastro', 'newsletter',
                    'amazon', 'aliexpress', 'mercado livre', 'shopee', 'custo', 'preço',
                    'compre', 'oferta', 'desconto', 'cupom', 'promoção', 'black friday',
                    'aviso', 'clique', 'compartilhe', 'siga', 'inscreva', 'download',
                    'vpn', 'antivírus', 'norton', 'testegrátis', 'teste grátis', '% off', '% offert',
                    'código', 'cupom', 'deal', 'cyber', 'viagem', 'hotel', 'passagem',
                    'fone', 'fones', 'headphone', 'smartphone', 'iphone', 'samsung'
                ]
                
                if any(palavra in titulo.lower() for palavra in palavras_bloqueadas):
                    continue
                
                # Formata URL relativa
                if href.startswith('/'):
                    from urllib.parse import urljoin
                    href = urljoin(site_url, href)
                
                if not href.startswith('http'):
                    continue
                
                # Normaliza URL para verificação
                href_normalizada = normalizar_url(href)
                
                # Pula URL já processada (verificação normalizada)
                if href_normalizada in urls_processadas:
                    log(f"  🔄 URL já processada: {href[:50]}...")
                    continue
                
                # Verifica duplicata por título normalizado (exato)
                titulo_normalizado = normalizar_titulo(titulo)
                if titulo_normalizado in titulos_processados:
                    log(f"  🔄 Título duplicado (exato): {titulo[:50]}...")
                    continue
                
                # Verifica duplicata por similaridade (fuzzy matching)
                if titulo_similar(titulo, titulos_processados):
                    continue
                
                # Bloqueia links para plataformas de compra
                urls_bloqueadas = ['amazon.com', 'aliexpress.com', 'mercadolivre.com', 'shopee.com', 'ebay.com']
                if any(bloqueado in href.lower() for bloqueado in urls_bloqueadas):
                    continue
                
                try:
                    time.sleep(random.uniform(0.7, 1.5))
                    
                    # Acessa artigo
                    art_resp = requests.get(href, headers=HEADERS, timeout=20, verify=False)
                    art_resp.encoding = 'utf-8'
                    art_soup = BeautifulSoup(art_resp.text, 'html.parser')
                    
                    # Remove lixo
                    for tag in art_soup(['script', 'style', 'nav', 'footer', 'aside']):
                        tag.decompose()
                    
                    # Busca conteúdo em parágrafos
                    # OBS: usar separator=" " evita palavras grudadas quando há tags inline (<a>, <strong>, etc.)
                    paragrafos = art_soup.find_all('p')
                    texto = ' '.join(
                        p.get_text(" ", strip=True)
                        for p in paragrafos
                        if len(p.get_text(" ", strip=True)) > 30
                    )
                    
                    # Se não encontrou em <p>, tenta em divs com classes de artigo
                    if len(texto) < 400:
                        article = art_soup.find(['article', 'div', 'main'], class_=lambda x: x and any(palavra in str(x).lower() for palavra in ['article', 'post', 'content', 'corpo', 'noticia', 'body', 'text']))
                        if article:
                            paragrafos = article.find_all('p')
                            texto = ' '.join(
                                p.get_text(" ", strip=True)
                                for p in paragrafos
                                if len(p.get_text(" ", strip=True)) > 30
                            )
                    
                    # Busca imagem com função melhorada
                    img_url = extrair_imagem_melhorada(art_soup, href)
                    
                    # Formata URL da imagem
                    if img_url and not img_url.startswith('http'):
                        from urllib.parse import urljoin
                        img_url = urljoin(href, img_url)
                    
                    # Rejeita notícias sem imagem real ou com placeholder
                    if not eh_imagem_valida(img_url):
                        log(f"  🚫 Notícia sem imagem válida, pulando: {titulo[:50]}...")
                        urls_processadas.add(href_normalizada)
                        titulos_processados.add(titulo_normalizado)
                        salvar_cache_artigos(urls_processadas, titulos_processados)
                        continue
                    
                    # Valida conteúdo
                    if len(texto) > 500:
                        log(f"  ✅ Encontrada: {titulo[:60]}...")
                        # Marca como processada (URL normalizada e título)
                        urls_processadas.add(href_normalizada)
                        titulos_processados.add(titulo_normalizado)
                        salvar_cache_artigos(urls_processadas, titulos_processados)
                        return {
                            'title': titulo, 
                            'content': texto, 
                            'urlToImage': img_url, 
                            'url': href
                        }

                    else:
                        # Marca como processada mesmo sem conteúdo suficiente
                        urls_processadas.add(href_normalizada)
                        salvar_cache_artigos(urls_processadas, titulos_processados)


                except requests.exceptions.Timeout:
                    log(f"  ⏱ Timeout em {href[:40]}")
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

    # Se o conteúdo extraído não parece PT-BR, melhor abortar do que publicar texto ruim.
    # (Isso evita posts "só scraped" em inglês ou com lixo.)
    if not parece_portugues(conteudo):
        log("  🚫 Fallback abortado: conteúdo extraído não parece PT-BR")
        return None
    
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


def parece_portugues(texto: str) -> bool:
    """Heurística simples para detectar se o texto parece PT-BR.
    Não é um detector perfeito; é só para bloquear casos óbvios de inglês/UI."""
    if not texto:
        return False

    t = texto.lower()
    # remove tags
    import re
    t = re.sub(r'<[^>]+>', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    if len(t) < 200:
        return False

    tokens = re.findall(r"[a-zà-ú]+", t)
    if len(tokens) < 40:
        return False

    pt_stop = {
        'que', 'de', 'do', 'da', 'em', 'para', 'com', 'não', 'uma', 'um', 'os', 'as',
        'por', 'mais', 'como', 'sobre', 'após', 'antes', 'entre', 'também', 'já',
        'foi', 'será', 'são', 'era', 'está', 'estão', 'disse', 'diz', 'ainda',
        'ao', 'aos', 'à', 'às', 'no', 'na', 'nos', 'nas', 'se', 'sua', 'seu'
    }
    en_stop = {
        'the', 'and', 'for', 'with', 'from', 'this', 'that', 'your', 'our', 'their',
        'you', 'they', 'we', 'was', 'were', 'are', 'is', 'in', 'on', 'of', 'to'
    }

    pt_hits = sum(1 for tok in tokens if tok in pt_stop)
    en_hits = sum(1 for tok in tokens if tok in en_stop)

    # presença de acentos ajuda
    acentos = sum(1 for ch in t if ch in 'áàâãéêíóôõúç')

    # decisões simples
    if en_hits > pt_hits * 2 and en_hits > 20:
        return False
    if pt_hits >= 8:
        return True
    if acentos >= 8:
        return True
    return False


def corrigir_espacamento(texto: str) -> str:
    """Correções leves de espaçamento/pontuação para reduzir 'palavras grudadas'."""
    import re
    if not texto:
        return texto
    # espaços após pontuação
    texto = re.sub(r'([,;:.!?])(\S)', r'\1 \2', texto)
    # minúscula+Maiúscula coladas
    texto = re.sub(r'([a-zà-ú])([A-ZÀ-Ú])', r'\1 \2', texto)
    # dígito+letra colados
    texto = re.sub(r'(\d)([A-Za-zÀ-Úà-ú])', r'\1 \2', texto)
    # remove espaços múltiplos
    texto = re.sub(r'\s+', ' ', texto)
    return texto.strip()


def remover_mencoes_de_fonte(texto: str) -> tuple[str, bool]:
    """Remove/neutraliza menções a veículos/fontes.
    Retorna (texto_limpo, houve_remocao)."""
    import re
    if not texto:
        return texto, False

    original = texto
    t = texto

    # remove padrões do tipo "Fonte: ..." em qualquer lugar
    t = re.sub(r'(?im)^\s*fonte\s*:\s*.*$', '', t)
    t = re.sub(r'(?im)^\s*source\s*:\s*.*$', '', t)

    # neutraliza menções explícitas a portais comuns
    veiculos = [
        'g1', 'uol', 'folha', 'folhapress', 'poder360', 'cnn brasil', 'bbc',
        'ge.globo', 'globo', 'oglobo', 'estadão', 'estadao', 'r7', 'ig',
        'omelete', 'tecmundo', 'olhar digital', 'tecnoblog', 'canaltech',
        'ign', 'game rant', 'thegamer', 'the enemy'
    ]
    for v in veiculos:
        # remove "segundo <veículo>", "de acordo com <veículo>", "conforme <veículo>"
        t = re.sub(rf'(?i)(segundo|de acordo com|conforme|reportou|informou)\s+{re.escape(v)}\b', r'\1 informações disponíveis', t)
        t = re.sub(rf'(?i)\b{re.escape(v)}\b', v)  # mantém a palavra se estiver no meio, mas reduz chance de apagar sentido

    # remove sobras de linhas vazias
    t = re.sub(r'\n{3,}', '\n\n', t).strip()

    return t, (t != original)


def remover_primeiro_paragrafo_se_repetir_titulo(texto: str, titulo: str) -> tuple[str, bool]:
    """Se o 1º parágrafo for basicamente o título (ou começar repetindo), remove."""
    import re
    if not texto or not titulo:
        return texto, False

    # quebra por parágrafos (linhas em branco)
    partes = [p.strip() for p in re.split(r'\n\s*\n', texto) if p.strip()]
    if len(partes) < 2:
        return texto, False

    t_norm = normalizar_titulo(titulo)
    p0_norm = normalizar_titulo(partes[0])

    # se o primeiro parágrafo contém o título (ou grande parte dele)
    if t_norm and (t_norm in p0_norm or p0_norm.startswith(t_norm[: max(20, len(t_norm) // 2)])):
        partes = partes[1:]
        return '\n\n'.join(partes).strip(), True

    # Jaccard simples com palavras
    palavras_t = set(t_norm.split())
    palavras_p0 = set(p0_norm.split())
    if palavras_t and palavras_p0:
        sim = len(palavras_t & palavras_p0) / len(palavras_t | palavras_p0)
        if sim >= 0.70:
            partes = partes[1:]
            return '\n\n'.join(partes).strip(), True

    return texto, False


def avaliar_qualidade_materia(titulo: str, texto: str) -> list[str]:
    """Retorna uma lista de flags com problemas detectados."""
    flags = []
    if not texto or len(texto) < 800:
        flags.append('curto')
    if not parece_portugues(texto):
        flags.append('nao_ptbr')

    # sinais de fonte
    tl = texto.lower()
    if 'fonte:' in tl or 'source:' in tl or 'segundo ' in tl or 'de acordo com ' in tl or 'conforme ' in tl:
        flags.append('menciona_fonte')

    # markdown (o prompt pede HTML simples)
    if any(x in texto for x in ['**', '__', '```']):
        flags.append('markdown')

    # título repetido no começo
    t_norm = normalizar_titulo(titulo) if titulo else ''
    inicio = normalizar_titulo(texto[:400])
    if t_norm and t_norm in inicio:
        flags.append('repete_titulo')

    return flags

def gerar_texto(noticia):
    prompt = f"""Escreva uma matéria jornalística completa em português brasileiro (mínimo 450 palavras, parágrafos, tom profissional) sobre:

Título: {noticia['title']}
Conteúdo: {noticia.get('content', '')[:3000]}

Regras obrigatórias:
- NÃO mencione nem cite veículos, jornais, sites, autores ou links.
- NÃO repita o título como primeiro parágrafo.
- Escreva somente em português brasileiro.
- Use apenas HTML simples (sem markdown)."""

    prompt_strito = f"""Reescreva e melhore a matéria abaixo em português brasileiro.

Título: {noticia['title']}
Conteúdo base: {noticia.get('content', '')[:3000]}

Regras obrigatórias (não quebre):
1) Texto 100% PT-BR (sem frases em inglês).
2) NÃO mencionar fontes/veículos (G1, UOL, Folha, BBC, etc.) nem expressões tipo "segundo o jornal".
3) NÃO repetir o título no primeiro parágrafo.
4) Corrigir palavras coladas e erros de espaçamento/pontuação.
5) Produzir parágrafos e usar somente HTML simples (<p>, <strong>, <em>) sem markdown.
"""
    try:
        def chamar_groq(conteudo_prompt: str, temperature: float, timeout: int):
            r = requests.post(
                'https://api.groq.com/openai/v1/chat/completions',
                headers={'Authorization': f'Bearer {GROQ_API_KEY}', 'Content-Type': 'application/json'},
                json={
                    'model': 'llama-3.3-70b-versatile',
                    'messages': [{'role': 'user', 'content': conteudo_prompt}],
                    'temperature': temperature,
                    'max_tokens': 2000
                },
                timeout=timeout
            )
            r.raise_for_status()
            return r.json()['choices'][0]['message']['content'].strip()

        # 1) Primeira tentativa (mais "criativa")
        texto = chamar_groq(prompt, temperature=0.7, timeout=60)
        texto = limpar_markdown(texto)
        texto = corrigir_espacamento(texto)

        # limpeza pós-processamento
        texto, removeu_fonte = remover_mencoes_de_fonte(texto)
        texto, removeu_titulo = remover_primeiro_paragrafo_se_repetir_titulo(texto, noticia.get('title', ''))

        flags = avaliar_qualidade_materia(noticia.get('title', ''), texto)
        if removeu_fonte:
            flags.append('pos_removeu_fonte')
        if removeu_titulo:
            flags.append('pos_removeu_titulo')

        # 2) Se a qualidade estiver ruim, tenta um segundo prompt mais rígido
        if any(f in flags for f in ['nao_ptbr', 'menciona_fonte', 'repete_titulo', 'curto']):
            log(f"  ⚠️ Qualidade detectada ({', '.join(flags)}). Tentando reescrita mais rígida...")
            texto2 = chamar_groq(prompt_strito, temperature=0.2, timeout=70)
            texto2 = limpar_markdown(texto2)
            texto2 = corrigir_espacamento(texto2)
            texto2, _ = remover_mencoes_de_fonte(texto2)
            texto2, _ = remover_primeiro_paragrafo_se_repetir_titulo(texto2, noticia.get('title', ''))
            flags2 = avaliar_qualidade_materia(noticia.get('title', ''), texto2)
            log(f"  🧪 Flags após reescrita rígida: {', '.join(flags2) if flags2 else 'ok'}")

            # escolhe o melhor texto (menos flags) e sempre rejeita se não for PT-BR
            if 'nao_ptbr' in flags2:
                log("  🚫 Matéria rejeitada: texto final ainda não parece PT-BR")
                return None
            if len(flags2) <= len(flags):
                texto = texto2
                flags = flags2

        # última validação: PT-BR obrigatório
        if not parece_portugues(texto):
            log("  🚫 Matéria rejeitada: não parece PT-BR")
            return None

        log(f"  ✅ Matéria gerada ({len(texto.split())} palavras) | flags: {', '.join(flags) if flags else 'ok'}")
        return texto
    except Exception as e:
        log(f"  ⚠️ Groq falhou: {str(e)[:60]}")
        log(f"  📝 Usando fallback (conteúdo extraído)...")
        return gerar_texto_fallback(noticia)

# Mapeamento global de subcategorias por categoria principal
SUBCATEGORIAS = {
    'esportes': {
        'futebol': ['futebol', 'flamengo', 'palmeiras', 'corinthians', 'são paulo', 'santos', 'vasco', 'botafogo', 'fluminense', 'gremio', 'internacional', 'cruzeiro', 'atletico', 'brasileirão', 'copa do brasil', 'libertadores', 'mundial', 'seleção brasileira', 'neymar', 'messi', 'cristiano ronaldo', 'mbappe', 'haaland'],
        'automobilismo': ['fórmula 1', 'formula 1', 'f1', 'stock car', 'nascar', 'rally', 'motogp', 'verstappen', 'hamilton', 'leclerc', 'pérez', 'alonso', 'sainz', 'norris', 'piastri', 'pilotos', 'gp', 'grande prêmio', 'corrida'],
        'basquete': ['nba', 'basquete', 'lebron', 'jordan', 'curry', 'durant', 'giannis', 'lakers', 'celtics', 'warriors', 'bulls', 'playoffs', 'finals'],
        'olimpiadas': ['olimpíadas', 'olimpiadas', 'paris 2024', 'los angeles 2028', 'atletismo', 'natação', 'ginástica', 'judô', 'vôlei', 'handebol']
    },
    'entretenimento': {
        'cinema-series': ['filme', 'cinema', 'série', 'netflix', 'hbo', 'disney+', 'amazon prime', 'star+', 'paramount', 'trailer', 'estreia', 'bilheteria', 'oscar', 'emmy', 'globo de ouro', 'ator', 'atriz', 'diretor', 'cinebiografia'],
        'musica': ['música', 'banda', 'cantor', 'cantora', 'show', 'turnê', 'álbum', 'single', 'grammy', 'rock', 'pop', 'sertanejo', 'funk', 'rap', 'hip hop', 'anitta', 'taylor swift', 'beyoncé', 'the weeknd', 'drake'],
        'cultura-pop': ['marvel', 'dc', 'star wars', 'harry potter', 'anime', 'mangá', 'cosplay', 'convenção', 'ccxp', 'comic con', 'super-herói', 'vingadores', 'batman', 'superman', 'homem-aranha'],
        'teatro': ['teatro', 'peça', 'musical', 'broadway', 'west end', 'drama', 'comédia', 'atuação', 'palco']
    },
    'tecnologia': {
        'hardware': ['hardware', 'processador', 'cpu', 'gpu', 'placa de vídeo', 'memória ram', 'ssd', 'hd', 'notebook', 'desktop', 'pc', 'gamer', 'intel', 'amd', 'nvidia', 'cooler', 'fonte'],
        'software': ['software', 'windows', 'linux', 'macos', 'android', 'ios', 'aplicativo', 'app', 'programa', 'sistema operacional', 'atualização', 'microsoft', 'google'],
        'inteligencia-artificial': ['inteligência artificial', 'ia', 'ai', 'chatgpt', 'gpt', 'llm', 'machine learning', 'deep learning', 'neural', 'openai', 'google gemini', 'claude', 'copilot', 'bard'],
        'ciberseguranca': ['cibersegurança', 'hacker', 'vírus', 'malware', 'ransomware', 'phishing', 'golpe', 'fraude', 'vazamento de dados', 'privacidade', 'senha', 'autenticação']
    },
    'videogames': {
        'noticias': ['jogo', 'novo jogo', 'lançamento', 'trailer', 'gameplay', 'revelado', 'anunciado', 'confirmado', 'adiado', 'cancelado'],
        'reviews': ['review', 'análise', 'nota', 'avaliação', 'impressões', 'primeiras impressões', 'testamos', 'jogamos'],
        'esports': ['esports', 'e-sports', 'campeonato', 'torneio', 'competitivo', 'valorant', 'cs2', 'counter-strike', 'lol', 'league of legends', 'dota', 'fortnite', 'free fire', 'rainbow six'],
        'indies': ['indie', 'jogo independente', 'steam', 'itch.io', 'pixel art', 'roguelike', 'metroidvania', 'desenvolvedor independente']
    },
    'politica-nacional': {
        'congresso': ['câmara', 'senado', 'congresso', 'deputado', 'senador', 'votação', 'projeto de lei', 'pec', 'impeachment', 'cpi', 'comissão'],
        'governo-federal': ['lula', 'bolsonaro', 'presidente', 'ministro', 'governo', 'planalto', 'pt', 'pl', 'psdb', 'mdb', 'união brasil', 'executivo'],
        'eleicoes': ['eleição', 'eleições', 'campanha', 'candidato', 'pesquisa', 'ibope', 'datafolha', 'urna eletrônica', 'voto', 'debate', 'horário eleitoral'],
        'justica': ['stf', 'supremo', 'alexandre de moraes', 'rosa weber', 'barroso', 'fachin', 'ministro do stf', 'pgr', 'polícia federal', 'lava jato', 'prisão', 'condenação']
    },
    'politica-internacional': {
        'eua': ['eua', 'estados unidos', 'biden', 'trump', 'casa branca', 'pentágono', 'congresso americano', 'republicanos', 'democratas', 'eleições americanas'],
        'europa': ['ue', 'união europeia', 'alemanha', 'frança', 'inglaterra', 'reino unido', 'italia', 'espanha', 'macron', 'scholz', 'sunak', 'meloni', 'brexit', 'nato', 'otan'],
        'asia': ['china', 'xi jinping', 'taiwan', 'japão', 'índia', 'coreia do norte', 'coreia do sul', 'putin', 'rússia', 'ucrânia', 'guerra', 'tensão', 'brics'],
        'america-latina': ['argentina', 'chile', 'colômbia', 'venezuela', 'nicarágua', 'cuba', 'mexico', 'milei', 'boric', 'maduro', 'ortega', 'lópez obrador']
    },
    'rio-de-janeiro': {
        'seguranca': ['crime', 'polícia', 'pm', 'bope', 'tráfico', 'milícia', 'violência', 'assalto', 'roubo', 'homicídio', 'favela', 'complexo', 'tiroteio'],
        'transporte': ['ônibus', 'metrô', 'brt', 'trem', 'supervia', 'linha amarela', 'linha vermelha', 'ponte', 'túnel', 'engarrafamento', 'transito'],
        'cultura-eventos': ['carnaval', 'réveillon', 'rock in rio', 'show', 'festa', 'praia', 'copacabana', 'ipanema', 'cristo', 'pão de açúcar', 'museu', 'teatro municipal']
    },
    'sao-paulo': {
        'economia-negocios': ['bolsa', 'bovespa', 'empresas', 'startup', 'faria lima', 'paulista', 'itaim', 'vila olímpia', 'economia', 'negócios', 'investimentos'],
        'transporte': ['metro', 'metrô', 'cptm', 'ônibus', 'marginal', 'paulista', 'congestionamento', 'rodízio', 'bilhete único', 'linha amarela', 'linha verde'],
        'cultura-lazer': ['parque', 'ibirapuera', 'museu', 'masp', 'pinacoteca', 'teatro', 'show', 'evento', 'exposição', 'bienal', 'parada gay', 'virada cultural']
    }
}

def classificar_subcategoria_ia(titulo, categoria_principal):
    """Classifica subcategoria usando IA (Groq) quando palavras-chave não funcionam"""
    if categoria_principal not in SUBCATEGORIAS:
        return None
    
    subcats_disponiveis = list(SUBCATEGORIAS[categoria_principal].keys())
    
    prompt = f"""Classifique o seguinte título de notícia em UMA das subcategorias listadas.

Título: "{titulo}"
Categoria principal: {categoria_principal}
Subcategorias disponíveis: {', '.join(subcats_disponiveis)}

Responda APENAS com o nome exato da subcategoria mais adequada, sem explicação. Se nenhuma se encaixar, responda "nenhuma"."""

    try:
        resp = requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers={'Authorization': f'Bearer {GROQ_API_KEY}', 'Content-Type': 'application/json'},
            json={
                'model': 'llama-3.3-70b-versatile',
                'messages': [{'role': 'user', 'content': prompt}],
                'temperature': 0.1,
                'max_tokens': 50
            },
            timeout=15
        )
        resp.raise_for_status()
        resultado = resp.json()['choices'][0]['message']['content'].strip().lower()
        
        # Valida se a resposta é uma subcategoria válida
        if resultado in subcats_disponiveis:
            log(f"  🤖 Subcategoria via IA: {resultado}")
            return resultado
        
        # Tenta match parcial (ex: "cinema e séries" -> "cinema-series")
        for subcat in subcats_disponiveis:
            if subcat in resultado or resultado in subcat:
                log(f"  🤖 Subcategoria via IA (parcial): {subcat}")
                return subcat
        
        log(f"  🤖 IA não classificou subcategoria: {resultado}")
        return None
    except Exception as e:
        log(f"  ⚠️ Classificação IA falhou: {str(e)[:40]}")
        return None

def classificar_subcategoria(titulo, categoria_principal):
    """Classifica automaticamente a subcategoria: primeiro por palavras-chave, depois por IA"""
    titulo_lower = titulo.lower()
    
    # Verifica se a categoria principal tem subcategorias definidas
    if categoria_principal not in SUBCATEGORIAS:
        return None
    
    # PASSO 1: Procura por palavras-chave no título (rápido e sem custo)
    cat_subs = SUBCATEGORIAS[categoria_principal]
    for subcat, palavras in cat_subs.items():
        if any(palavra in titulo_lower for palavra in palavras):
            log(f"  🏷️ Subcategoria via keywords: {subcat}")
            return subcat
    
    # PASSO 2: Fallback para classificação via IA (Groq)
    log(f"  🔍 Keywords não encontraram subcategoria, tentando IA...")
    return classificar_subcategoria_ia(titulo, categoria_principal)

def salvar_post(titulo, texto, img, cat, data, post_id, subcategoria=None):
    slug = titulo.lower()[:50].replace(' ', '-').replace('?', '').replace('!', '').replace('/', '-')
    fname = f"post-{post_id:04d}-{slug}.html"
    
    # Formata parágrafos com função melhorada
    paragrafos = formatar_paragrafos(texto)

    
    # HTML com styling melhorado
    subcat_html = f'<span class="post-subcategoria">{subcategoria.replace("-"," ").title()}</span>' if subcategoria else ''
    
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
<a href="../categoria-rio-de-janeiro.html">Rio de Janeiro</a>
<a href="../categoria-sao-paulo.html">São Paulo</a>
<a href="../sobre.html">Sobre</a>
</nav>
</div></header>
<main class="container">
<article class="post-completo">
<div class="post-header">
<span class="post-categoria">{cat.replace('-',' ').title()}</span>
{subcat_html}
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
    return {'titulo': titulo, 'url': f"posts/{fname}", 'imagem': img, 'categoria': cat, 'subcategoria': subcategoria, 'data': data}


def atualizar_home(posts):
    cards = ""
    # Lista todas as matérias (sem limite), em ordem decrescente (mais recentes primeiro)
    for p in reversed(posts):
        # Verifica se o arquivo HTML do post existe
        post_file = Path(p['url'])
        if not post_file.exists():
            log(f"  ⚠️ Post {p['titulo'][:40]} não tem arquivo HTML, pulando")
            continue
        
        # Adiciona subcategoria se existir
        subcat_html = f'<span class="subcategoria">{p.get("subcategoria", "").replace("-"," ").title()}</span>' if p.get('subcategoria') else ''
        
        cards += f"""<article class="post-card">
<img src="{p['imagem']}" alt="{p['titulo']}">
<div class="post-info">
<span class="categoria categoria-{p['categoria']}">{p['categoria'].replace('-',' ').title()}</span>
{subcat_html}
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
<a href="categoria-rio-de-janeiro.html">Rio de Janeiro</a>
<a href="categoria-sao-paulo.html">São Paulo</a>
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
    # Garante que todas as categorias do TEMAS tenham páginas (mesmo que vazias)
    categorias = {tema['categoria']: [] for tema in TEMAS}
    
    # Preenche com posts existentes
    for p in posts:
        cat = p['categoria']
        if cat in categorias:
            categorias[cat].append(p)
    
    for cat, artigos in categorias.items():

        cards = ""
        # Lista todas as matérias da categoria (sem limite), mais recentes primeiro
        for p in reversed(artigos):
            # Verifica se o arquivo HTML do post existe
            post_file = Path(p['url'])
            if not post_file.exists():
                continue
            
            # Adiciona subcategoria se existir
            subcat_html = f'<span class="subcategoria">{p.get("subcategoria", "").replace("-"," ").title()}</span>' if p.get('subcategoria') else ''
            
            cards += f"""<article class="post-card">
<img src="{p['imagem']}" alt="{p['titulo']}">
<div class="post-info">
<span class="categoria categoria-{p['categoria']}">{p['categoria'].replace('-',' ').title()}</span>
{subcat_html}
<h2><a href="{p['url']}">{p['titulo']}</a></h2>
<p class="meta">Por Kevin Ribeiro • {p['data']}</p>
</div>
</article>"""
        
        # Mensagem quando não há artigos
        if not artigos:
            cards = '<p class="sem-artigos">Nenhuma notícia nesta categoria ainda.</p>'
        
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
<a href="categoria-rio-de-janeiro.html">Rio de Janeiro</a>
<a href="categoria-sao-paulo.html">São Paulo</a>
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
        log("  ✅ Commit realizado! (Push será feito pelo GitHub Actions)")
    except Exception as e:
        log(f"  ❌ Commit: {e}")

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

    # Classifica subcategoria automaticamente
    subcategoria = classificar_subcategoria(noticia['title'], tema['categoria'])
    if subcategoria:
        log(f"  🏷️ Subcategoria: {subcategoria}")
    
    info = salvar_post(noticia['title'], texto, noticia.get('urlToImage'), tema['categoria'], datetime.now().strftime('%d/%m/%Y às %H:%M'), total_posts + 1, subcategoria)

    posts.append(info)
    json.dump(posts, open(pfile, 'w'), ensure_ascii=False, indent=2)
    atualizar_home(posts)
    gerar_paginas_categorias(posts)
    publicar()

    # Salva estado para próxima execução
    tema_idx = (tema_idx + 1) % len(TEMAS)
    salvar_estado(tema_idx, total_posts + 1)
    
    # Evitar disparos excessivos em curto intervalo (proteção contra loop infinito)
    # A cada 5 posts, espera 5 minutos antes do próximo ciclo
    if (total_posts + 1) % 5 == 0:
        log(f"  ⏳ Pausa de proteção: aguardando 5 minutos antes do próximo ciclo...")
        time.sleep(300)
    
    log("\n✅ CICLO CONCLUÍDO!")

if __name__ == "__main__":
    log("🌍 VIVIMUNDO BOT - GitHub Actions")
    setup_repo()
    executar()
