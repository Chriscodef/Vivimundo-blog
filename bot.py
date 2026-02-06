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
    {"nome": "Esportes", "categoria": "esportes", "sites": ["https://ge.globo.com/", "https://www.espn.com.br/", "https://www.uol.com.br/esporte/", "https://www.espn.com.br/futebol/", "https://www.grandepremio.com.br/"]},
    {"nome": "Entretenimento", "categoria": "entretenimento", "sites": ["https://www.omelete.com.br/", "https://www.tecmundo.com.br/cultura", "https://noticiasdocinema.com.br/"]},
    {"nome": "Tecnologia", "categoria": "tecnologia", "sites": ["https://www.tecmundo.com.br/", "https://olhardigital.com.br/", "https://www.hardware.com.br/", "https://www.tecmundo.com.br/voxel", "https://tecnoblog.net/"]},
    {"nome": "Videogames", "categoria": "videogames", "sites": ["https://www.gamerant.com/", "https://www.ign.com.br/", "https://www.thegamer.com.br/", "https://br.ign.com/"]},
    {"nome": "Política Nacional", "categoria": "politica-nacional", "sites": ["https://g1.globo.com/politica/", "https://noticias.uol.com.br/politica/", "https://www.folhapress.com.br/", "https://www.poder360.com.br/"]},
    {"nome": "Política Internacional", "categoria": "politica-internacional", "sites": ["https://g1.globo.com/mundo/", "https://www.bbc.com/portuguese/internacional", "https://noticias.uol.com.br/internacional/", "https://hojenomundomilitar.com.br/"]},
    {"nome": "Rio de Janeiro", "categoria": "rio-de-janeiro", "sites": ["https://g1.globo.com/rj/rio-de-janeiro/", "https://odia.ig.com.br/"]},
    {"nome": "São Paulo", "categoria": "sao-paulo", "sites": ["https://g1.globo.com/sp/sao-paulo/"]}
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
    
    # Padrão 1: letra minúscula seguida de maiúscula (ex: "JacksonVeja")
    titulo = re.sub(r'([a-z])([A-Z])', r'\1 \2', titulo)
    
    # Padrão 2: pontuação seguida de letra maiúscula sem espaço (ex: "AÍ!Baldur's")
    titulo = re.sub(r'([!?:.])([A-Z])', r'\1 \2', titulo)
    
    # Padrão 3: palavra completamente maiúscula seguida de palavra capitalizada (ex: "HPComo")
    titulo = re.sub(r'([A-Z]{2,})([A-Z][a-z])', r'\1 \2', titulo)
    
    # Remove espaços múltiplos
    titulo = re.sub(r'\s+', ' ', titulo)
    
    return titulo.strip()

def eh_titulo_valido(titulo):
    """Valida se o título é real (não é número de telefone, sequência, etc)"""
    # Remove espaços extras
    titulo = titulo.strip()
    
    # Muito curto ou longo
    if len(titulo) < 15 or len(titulo) > 250:
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
        return False
    
    # Rejeita títulos genéricos de seção (não são notícias reais)
    titulo_lower = titulo.lower()
    palavras_secao = [
        'advance', 'latest', 'more', 'daily', 'special', 'featured',
        'esportes a motor', 'game rant', 'puzzles and games',
        'trending', 'popular', 'recommended', 'breaking'
    ]
    for palavra in palavras_secao:
        if palavra in titulo_lower:
            log(f"  🚫 Título rejeitado (seção genérica): {titulo[:60]}...")
            return False
    
    # Rejeita títulos muito curtos com poucas palavras significativas (provavelmente categorias)
    palavras_significativas = [p for p in titulo.split() if len(p) > 3 and p.isalpha()]
    if len(palavras_significativas) < 4:
        # Verifica se parece uma categoria (sem verbos de ação)
        verbos_acao = ['ganha', 'lança', 'confirma', 'aprova', 'revela', 'anuncia', 
                       'chega', 'vence', 'perde', 'encontra', 'descobre', 'morre',
                       'nasce', 'cresce', 'cai', 'sobe', 'muda', 'fica', 'vai', 'vem']
        tem_verbo = any(verbo in titulo_lower for verbo in verbos_acao)
        if not tem_verbo:
            log(f"  🚫 Título rejeitado (sem verbo de ação): {titulo[:60]}...")
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
                
                # Verifica duplicata por título normalizado
                titulo_normalizado = normalizar_titulo(titulo)
                if titulo_normalizado in titulos_processados:
                    log(f"  🔄 Título duplicado: {titulo[:50]}...")
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
                    paragrafos = art_soup.find_all('p')
                    texto = ' '.join(p.get_text(strip=True) for p in paragrafos if len(p.get_text(strip=True)) > 30)
                    
                    # Se não encontrou em <p>, tenta em divs com classes de artigo
                    if len(texto) < 400:
                        article = art_soup.find(['article', 'div', 'main'], class_=lambda x: x and any(palavra in str(x).lower() for palavra in ['article', 'post', 'content', 'corpo', 'noticia', 'body', 'text']))
                        if article:
                            paragrafos = article.find_all('p')
                            texto = ' '.join(p.get_text(strip=True) for p in paragrafos if len(p.get_text(strip=True)) > 30)
                    
                    # Busca imagem com função melhorada
                    img_url = extrair_imagem_melhorada(art_soup, href)
                    
                    # Formata URL da imagem
                    if img_url and not img_url.startswith('http'):
                        from urllib.parse import urljoin
                        img_url = urljoin(href, img_url)
                    
                    # Rejeita notícias sem imagem real
                    if not img_url:
                        log(f"  🚫 Notícia sem imagem, pulando: {titulo[:50]}...")
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

def classificar_subcategoria(titulo, categoria_principal):
    """Classifica automaticamente a subcategoria usando regras de palavras-chave"""
    titulo_lower = titulo.lower()
    
    # Mapeamento de subcategorias por categoria principal
    subcategorias = {
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
    
    # Verifica se a categoria principal tem subcategorias definidas
    if categoria_principal not in subcategorias:
        return None
    
    # Procura por palavras-chave no título
    cat_subs = subcategorias[categoria_principal]
    for subcat, palavras in cat_subs.items():
        if any(palavra in titulo_lower for palavra in palavras):
            return subcat
    
    # Se não encontrou, retorna None (sem subcategoria)
    return None

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
    for p in reversed(posts[-10:]):
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
        for p in reversed(artigos[-20:]):
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
    log("\n✅ CICLO CONCLUÍDO!")

if __name__ == "__main__":
    log("🌍 VIVIMUNDO BOT - GitHub Actions")
    setup_repo()
    executar()
