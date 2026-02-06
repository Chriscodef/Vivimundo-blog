# TODO - Vivimundo Blog

## ✅ FASE 1: Correções dos 4 Problemas (CONCLUÍDA)

### ✅ Problema 1: Títulos Grudados
- [x] Criar função `limpar_titulo()` com regex para separar palavras grudadas
- [x] Padrão 1: letra minúscula + maiúscula (ex: "JacksonVeja" → "Jackson Veja")
- [x] Padrão 2: pontuação + maiúscula (ex: "AÍ!Baldur's" → "AÍ! Baldur's")
- [x] Padrão 3: ALLCAPS + Capitalized (ex: "HPComo" → "HP Como")
- [x] Integrar chamada em `buscar_noticia()` após extração do título

### ✅ Problema 2: Títulos Genéricos
- [x] Expandir `eh_titulo_valido()` com blacklist de nomes de seção
- [x] Adicionar palavras bloqueadas: "advance", "latest", "more", "daily", "special", "esportes a motor", "game rant"
- [x] Adicionar detecção de verbos de ação para evitar categorias sem conteúdo jornalístico real
- [x] Adicionar logs detalhados dos títulos rejeitados

### ✅ Problema 3: Posts Duplicados
- [x] Criar `normalizar_url()` para padronizar URLs (lowercase, remove trailing slash, remove tracking params)
- [x] Criar `normalizar_titulo()` para detecção por título
- [x] Modificar cache para armazenar URLs e títulos separadamente
- [x] Atualizar `carregar_cache_artigos()` e `salvar_cache_artigos()` para formato novo
- [x] Adicionar verificação de duplicata por título em `buscar_noticia()`
- [x] Manter compatibilidade com formato antigo do cache

### ✅ Problema 4: Imagens Placeholder
- [x] Modificar lógica para rejeitar notícias sem imagem real (não usa mais via.placeholder.com)
- [x] Notícias sem imagem são puladas e marcadas como processadas para não tentar novamente
- [x] Adicionar log: "🚫 Notícia sem imagem, pulando..."

---

## ✅ FASE 2: Expansão de Sites e Categorias (CONCLUÍDA)

### ✅ Novos Sites por Categoria
- [x] **Esportes**: Adicionado ESPN Futebol, Grande Prêmio (automobilismo)
- [x] **Tecnologia**: Adicionado TecMundo Voxel, Tecnoblog
- [x] **Videogames**: Adicionado br.ign.com
- [x] **Política Nacional**: Adicionado Poder360
- [x] **Política Internacional**: Adicionado Hoje no Mundo Militar

### ✅ Novas Categorias Locais
- [x] **Rio de Janeiro**: Sites G1 Rio e O Dia
- [x] **São Paulo**: Site G1 São Paulo
- [x] Atualizar array TEMAS de 6 para 8 elementos
- [x] Atualizar todos os templates HTML com novos links de navegação

### ✅ Correção de Estrutura
- [x] `gerar_paginas_categorias()` agora gera páginas para TODAS as categorias do TEMAS, mesmo vazias
- [x] Adicionada mensagem "Nenhuma notícia nesta categoria ainda" para categorias sem posts
- [x] Evita links quebrados para Rio de Janeiro e São Paulo antes de terem posts

---

## ✅ FASE 3: Sistema de Subcategorias (CONCLUÍDA)

### ✅ Implementação Técnica
- [x] Criar função `classificar_subcategoria()` com regras de palavras-chave para todas as 8 categorias
- [x] Definir mapeamento de subcategorias para todas as 8 categorias principais
- [x] Modificar `salvar_post()` para aceitar e armazenar subcategoria
- [x] Atualizar `posts.json` para incluir campo "subcategoria"
- [x] Atualizar templates HTML para exibir subcategoria nos cards
- [x] Integrar classificação automática em `executar()`

### ✅ Subcategorias Definidas
- [x] **Esportes**: futebol, automobilismo, basquete, olimpiadas
- [x] **Entretenimento**: cinema-series, musica, cultura-pop, teatro
- [x] **Tecnologia**: hardware, software, inteligencia-artificial, ciberseguranca
- [x] **Videogames**: noticias, reviews, esports, indies
- [x] **Política Nacional**: congresso, governo-federal, eleicoes, justica
- [x] **Política Internacional**: eua, europa, asia, america-latina
- [x] **Rio de Janeiro**: seguranca, transporte, cultura-eventos
- [x] **São Paulo**: economia-negocios, transporte, cultura-lazer

### ✅ Compatibilidade Retroativa
- [x] Usar `.get('subcategoria')` para posts antigos sem o campo
- [x] Subcategoria é opcional (None quando não classificada)

---

## 📋 Resumo das Alterações no bot.py

### Funções Adicionadas:
1. `limpar_titulo(titulo)` - Limpa títulos grudados
2. `normalizar_url(url)` - Normaliza URLs para cache
3. `normalizar_titulo(titulo)` - Normaliza títulos para detecção de duplicatas
4. `classificar_subcategoria(titulo, categoria)` - Classificação automática de subcategorias

### Funções Modificadas:
1. `carregar_cache_artigos()` - Suporte a formato novo (dict) e antigo (list)
2. `salvar_cache_artigos()` - Salva URLs e títulos separadamente
3. `eh_titulo_valido()` - Adicionada detecção de títulos genéricos
4. `buscar_noticia()` - Verificação dupla de cache (URL + título), rejeição de notícias sem imagem
5. `salvar_post()` - Aceita subcategoria, atualiza templates com novos links
6. `atualizar_home()` - Exibe subcategoria nos cards
7. `gerar_paginas_categorias()` - Gera páginas para TODAS as categorias (mesmo vazias), exibe subcategoria, templates com novos links
8. `executar()` - Integra classificação de subcategoria

### Dados Modificados:
- `TEMAS` - Expandido de 6 para 8 categorias com novos sites
- `posts.json` - Novo campo "subcategoria" opcional
- `articles_cache.json` - Novo formato com "urls" e "titulos"

---

## 🎯 Status Final

✅ **TODAS AS FASES CONCLUÍDAS E CORRIGIDAS**

O bot.py foi completamente atualizado com:
- 4 correções de problemas (PARTE 6)
- Expansão de sites e 2 novas categorias locais (PARTE 7) - **com correção de estrutura**
- Sistema completo de subcategorias com classificação automática (PARTE 8) - **com compatibilidade retroativa**

**Correções de Estrutura Aplicadas:**
- ✅ Todas as 8 categorias agora têm páginas HTML geradas automaticamente
- ✅ Posts antigos sem subcategoria são tratados com `.get()` defensivo
- ✅ Navegação consistente em todos os templates

Pronto para deploy e testes em produção.
