#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Vivimundo Editor Bot

Objetivo: revisar TODOS os posts já publicados e corrigir problemas de qualidade
que eventualmente passam pelo publicador.

Regras (obrigatórias):
- PT-BR (bloquear/reescrever se sair em inglês)
- Sem menções a fonte/veículo ("segundo G1", "Fonte:")
- Não repetir título como 1º parágrafo
- Corrigir palavras grudadas/espacamento
- Corrigir título bugado (grudado) quando possível
- Pode excluir posts irrecuperáveis

Este bot faz commit/push automaticamente via workflow.
"""

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup


def log(msg: str) -> None:
    print(msg, flush=True)


GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    log("❌ GROQ_API_KEY não encontrada! (Editor precisa para reescrita)")
    raise SystemExit(1)


POSTS_JSON = Path("posts.json")
POSTS_DIR = Path("posts")
REPORT_MD = Path("EDITOR_REPORT.md")
QUARANTINE_DIR = POSTS_DIR / "_quarantine"


@dataclass
class EditResult:
    changed: bool = False
    deleted: bool = False
    quarantined: bool = False
    reasons: list[str] | None = None


def normalizar_titulo(titulo: str) -> str:
    titulo = (titulo or "").lower().strip()
    titulo = re.sub(r"[^\w\s]", "", titulo)
    titulo = re.sub(r"\s+", " ", titulo)
    return titulo


def limpar_titulo(titulo: str) -> str:
    """Mesma ideia do publicador: separa palavras grudadas."""
    titulo = (titulo or "").strip()
    titulo = re.sub(r"([a-zà-ú])([A-ZÀ-Ú])", r"\1 \2", titulo)
    titulo = re.sub(r"([!?:.\)\]])([A-ZÀ-Úa-zà-ú])", r"\1 \2", titulo)
    titulo = re.sub(r"([A-ZÀ-Ú]{2,})([A-ZÀ-Ú][a-zà-ú])", r"\1 \2", titulo)
    titulo = re.sub(r"(\d)([A-ZÀ-Ú])", r"\1 \2", titulo)
    titulo = re.sub(r"\s+", " ", titulo)
    return titulo.strip()


def parece_portugues(texto: str) -> bool:
    if not texto:
        return False
    t = texto.lower()
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) < 200:
        return False
    tokens = re.findall(r"[a-zà-ú]+", t)
    if len(tokens) < 40:
        return False

    pt_stop = {
        "que",
        "de",
        "do",
        "da",
        "em",
        "para",
        "com",
        "não",
        "uma",
        "um",
        "os",
        "as",
        "por",
        "mais",
        "como",
        "sobre",
        "também",
        "já",
        "foi",
        "será",
        "são",
        "era",
        "está",
        "estão",
        "disse",
        "diz",
        "ao",
        "aos",
        "à",
        "às",
        "no",
        "na",
        "nos",
        "nas",
    }
    en_stop = {
        "the",
        "and",
        "for",
        "with",
        "from",
        "this",
        "that",
        "your",
        "our",
        "their",
        "you",
        "they",
        "we",
        "was",
        "were",
        "are",
        "is",
        "in",
        "on",
        "of",
        "to",
    }

    pt_hits = sum(1 for tok in tokens if tok in pt_stop)
    en_hits = sum(1 for tok in tokens if tok in en_stop)
    acentos = sum(1 for ch in t if ch in "áàâãéêíóôõúç")

    if en_hits > pt_hits * 2 and en_hits > 20:
        return False
    if pt_hits >= 8:
        return True
    if acentos >= 8:
        return True
    return False


def corrigir_espacamento(texto: str) -> str:
    if not texto:
        return texto
    texto = re.sub(r"([,;:.!?])(\S)", r"\1 \2", texto)
    texto = re.sub(r"([a-zà-ú])([A-ZÀ-Ú])", r"\1 \2", texto)
    texto = re.sub(r"(\d)([A-Za-zÀ-Úà-ú])", r"\1 \2", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def limpar_boilerplate(texto: str) -> str:
    """Remove linhas/frases muito comuns de UI/CTA que poluem o conteúdo."""
    if not texto:
        return texto

    # remove alguns padrões comuns (PT/EN)
    pads = [
        r"(?i)\bleia também\b.*$",
        r"(?i)\bveja também\b.*$",
        r"(?i)\bsaiba mais\b.*$",
        r"(?i)\bclique aqui\b.*$",
        r"(?i)\bcompartilhe\b.*$",
        r"(?i)\bsiga\s+o\s+canal\b.*$",
        r"(?i)\binscreva-?se\b.*$",
        r"(?i)\bnewsletter\b.*$",
        r"(?i)\bclick here\b.*$",
        r"(?i)\bread more\b.*$",
        r"(?i)\bwatch\b.*$",
    ]
    t = texto
    for p in pads:
        t = re.sub(p, "", t, flags=re.MULTILINE)

    # remove repetição excessiva de espaços/linhas
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def resumir_regra(texto: str, max_sentencas: int = 10) -> str:
    """Fallback sem IA: tenta gerar uma versão mais "jornalística" usando regras.

    Estratégia: limpar boilerplate, quebrar em sentenças, manter as primeiras sentenças
    que tenham tamanho razoável e não sejam duplicadas.
    """
    if not texto:
        return texto

    t = limpar_boilerplate(texto)
    t = corrigir_espacamento(t)

    # quebra grosseira por pontuação + quebras
    partes = re.split(r"(?<=[.!?])\s+|\n\n+", t)
    sentencas: list[str] = []
    vistos: set[str] = set()
    for s in partes:
        s = s.strip()
        if len(s) < 60:
            continue
        k = normalizar_titulo(s)[:120]
        if k in vistos:
            continue
        vistos.add(k)
        sentencas.append(s)
        if len(sentencas) >= max_sentencas:
            break

    if not sentencas:
        return t

    # volta em parágrafos
    return "\n\n".join(sentencas).strip()


def remover_mencoes_de_fonte(texto: str) -> tuple[str, bool]:
    if not texto:
        return texto, False
    original = texto

    texto = re.sub(r"(?im)^\s*fonte\s*:\s*.*$", "", texto)
    texto = re.sub(r"(?im)^\s*source\s*:\s*.*$", "", texto)

    # remove frases muito típicas
    texto = re.sub(
        r"(?i)\b(segundo|de acordo com|conforme)\s+o\s+(site|jornal|portal)\b[^,.!?:;]{0,80}",
        "",
        texto,
    )
    texto = re.sub(r"\n{3,}", "\n\n", texto).strip()

    return texto, (texto != original)


def remover_primeiro_paragrafo_se_repetir_titulo(texto: str, titulo: str) -> tuple[str, bool]:
    if not texto or not titulo:
        return texto, False

    partes = [p.strip() for p in re.split(r"\n\s*\n", texto) if p.strip()]
    if len(partes) < 2:
        return texto, False

    t_norm = normalizar_titulo(titulo)
    p0_norm = normalizar_titulo(partes[0])
    if t_norm and (t_norm in p0_norm or p0_norm.startswith(t_norm[: max(20, len(t_norm) // 2)])):
        return "\n\n".join(partes[1:]).strip(), True

    palavras_t = set(t_norm.split())
    palavras_p0 = set(p0_norm.split())
    if palavras_t and palavras_p0:
        sim = len(palavras_t & palavras_p0) / len(palavras_t | palavras_p0)
        if sim >= 0.70:
            return "\n\n".join(partes[1:]).strip(), True
    return texto, False


def extrair_texto_post_html(html: str) -> tuple[str, str, str]:
    """Retorna (titulo_h1, img_src, texto_plano)"""
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    titulo = h1.get_text(" ", strip=True) if h1 else ""

    img = soup.find("img", class_="post-principal-imagem")
    img_src = img.get("src", "") if img else ""

    conteudo = soup.find(class_="post-conteudo")
    texto = conteudo.get_text("\n\n", strip=True) if conteudo else soup.get_text("\n\n", strip=True)
    return titulo, img_src, texto


def substituir_conteudo_html(html: str, novo_titulo: str | None, novo_conteudo_html: str | None) -> str:
    soup = BeautifulSoup(html, "html.parser")
    if novo_titulo:
        h1 = soup.find("h1", class_="post-titulo") or soup.find("h1")
        if h1:
            h1.string = novo_titulo
        title_tag = soup.find("title")
        if title_tag:
            title_tag.string = f"{novo_titulo} - Vivimundo"
        ogt = soup.find("meta", property="og:title")
        if ogt:
            ogt["content"] = novo_titulo

    if novo_conteudo_html:
        container = soup.find(class_="post-conteudo")
        if container:
            container.clear()
            frag = BeautifulSoup(novo_conteudo_html, "html.parser")
            for el in frag.contents:
                container.append(el)

    return str(soup)


def formatar_em_paragrafos_html(texto_plano: str) -> str:
    """Transforma texto plano em <p>..."""
    blocos = [b.strip() for b in re.split(r"\n\s*\n", texto_plano) if b.strip()]
    ps: list[str] = []
    for b in blocos:
        b = corrigir_espacamento(b)
        if len(b) >= 50:
            ps.append(f"<p>{b}</p>")
    return "\n".join(ps)


def chamar_groq_reescrita(titulo: str, texto_base: str) -> str:
    prompt = f"""Reescreva e melhore a matéria abaixo em português brasileiro.

Título: {titulo}
Conteúdo base: {texto_base[:3500]}

Regras obrigatórias:
1) Texto 100% PT-BR (sem frases em inglês).
2) NÃO mencionar fontes/veículos nem expressões tipo "segundo o jornal".
3) NÃO repetir o título no primeiro parágrafo.
4) Corrigir palavras coladas e erros de espaçamento/pontuação.
5) Produzir parágrafos e usar somente HTML simples (<p>, <strong>, <em>) sem markdown.
"""

    last_err: Exception | None = None
    # retries com backoff para instabilidade momentânea
    for tentativa in range(1, 4):
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                    "max_tokens": 2000,
                },
                timeout=70,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            last_err = e
            espera = 2 * tentativa
            log(f"  ⚠️ Groq tentativa {tentativa}/3 falhou ({str(e)[:60]}). Aguardando {espera}s...")
            time.sleep(espera)
    assert last_err is not None
    raise last_err


def avaliar_flags(titulo: str, texto: str) -> list[str]:
    flags: list[str] = []
    if not texto or len(texto) < 800:
        flags.append("curto")
    if not parece_portugues(texto):
        flags.append("nao_ptbr")
    tl = texto.lower()
    if "fonte:" in tl or "source:" in tl or "segundo " in tl or "de acordo com " in tl or "conforme " in tl:
        flags.append("menciona_fonte")
    t_norm = normalizar_titulo(titulo)
    inicio = normalizar_titulo(texto[:400])
    if t_norm and t_norm in inicio:
        flags.append("repete_titulo")
    if any(x in texto for x in ["**", "__", "```"]):
        flags.append("markdown")
    return flags


def editar_um_post(post: dict[str, Any]) -> EditResult:
    url = post.get("url", "")
    if not url:
        return EditResult(changed=False, deleted=True, reasons=["sem_url"])

    html_path = Path(url)
    if not html_path.exists():
        return EditResult(changed=False, deleted=True, reasons=["arquivo_nao_existe"])

    html = html_path.read_text(encoding="utf-8", errors="ignore")
    h1, img_src, texto = extrair_texto_post_html(html)

    # 1) Corrige título (metadado + h1) se grudado
    titulo_atual = post.get("titulo") or h1
    titulo_corrigido = limpar_titulo(titulo_atual)

    mudou = False
    reasons: list[str] = []
    if titulo_corrigido and titulo_corrigido != titulo_atual:
        post["titulo"] = titulo_corrigido
        html = substituir_conteudo_html(html, novo_titulo=titulo_corrigido, novo_conteudo_html=None)
        mudou = True
        reasons.append("titulo_corrigido")

    # 2) Limpeza rápida do texto existente
    texto = limpar_boilerplate(texto)
    texto = corrigir_espacamento(texto)
    texto, rm_fonte = remover_mencoes_de_fonte(texto)
    if rm_fonte:
        mudou = True
        reasons.append("removeu_fonte")

    texto, rm_rep = remover_primeiro_paragrafo_se_repetir_titulo(texto, post.get("titulo", ""))
    if rm_rep:
        mudou = True
        reasons.append("removeu_rep_titulo")

    flags = avaliar_flags(post.get("titulo", ""), texto)
    if flags:
        log(f"  🧷 Flags detectadas em {html_path.name}: {', '.join(flags)}")

    # 3) Se falhou PT-BR ou está muito ruim, reescreve via Groq
    if any(f in flags for f in ["nao_ptbr", "menciona_fonte", "repete_titulo", "curto", "markdown"]):
        try:
            log(f"  ✍️ Reescrevendo via Groq: {post.get('titulo','')[:60]}...")
            novo = chamar_groq_reescrita(post.get("titulo", ""), texto)
            novo = corrigir_espacamento(novo)
            novo, _ = remover_mencoes_de_fonte(novo)
            novo, _ = remover_primeiro_paragrafo_se_repetir_titulo(novo, post.get("titulo", ""))

            # valida final
            flags2 = avaliar_flags(post.get("titulo", ""), novo)
            if "nao_ptbr" in flags2:
                # irrecuperável -> deletar
                log("  🗑️ Irrecuperável (não PT-BR após reescrita). Deletando post.")
                return EditResult(changed=False, deleted=True, reasons=["nao_ptbr_irrecuperavel"])

            # aplica (se veio texto sem <p>, transforma)
            if "<p" not in novo:
                novo = formatar_em_paragrafos_html(novo)

            html = substituir_conteudo_html(html, novo_titulo=None, novo_conteudo_html=novo)
            mudou = True
            reasons.append("reescrito_groq")
        except Exception as e:
            log(f"  ⚠️ Groq reescrita falhou: {str(e)[:80]}")

            # Fallback sem IA: tenta melhorar por regras.
            # Se o texto parecer PT-BR, tenta resumir/limpar e padronizar em <p>.
            if parece_portugues(texto):
                candidato = resumir_regra(texto, max_sentencas=12)
                candidato, _ = remover_mencoes_de_fonte(candidato)
                candidato, _ = remover_primeiro_paragrafo_se_repetir_titulo(candidato, post.get("titulo", ""))
                flags3 = avaliar_flags(post.get("titulo", ""), candidato)
                if "nao_ptbr" not in flags3 and len(candidato) >= 800:
                    if "<p" not in candidato:
                        candidato = formatar_em_paragrafos_html(candidato)
                    html = substituir_conteudo_html(html, novo_titulo=None, novo_conteudo_html=candidato)
                    mudou = True
                    reasons.append("fallback_regra_sem_groq")
                else:
                    # Se ainda estiver ruim (curto/nao_ptbr), quarentena.
                    log("  🟧 Quarentenando: sem Groq e qualidade insuficiente")
                    return EditResult(changed=False, deleted=True, quarantined=True, reasons=["quarentena_sem_groq"])
            else:
                # Texto não PT-BR e sem Groq -> quarentena
                log("  🟧 Quarentenando: nao_ptbr e Groq indisponível")
                return EditResult(changed=False, deleted=True, quarantined=True, reasons=["quarentena_nao_ptbr_sem_groq"])

    if mudou:
        html_path.write_text(html, encoding="utf-8")

    return EditResult(changed=mudou, deleted=False, reasons=reasons or None)


def remover_post(posts: list[dict[str, Any]], idx: int) -> None:
    p = posts[idx]
    url = p.get("url")
    if url:
        try:
            Path(url).unlink(missing_ok=True)
        except Exception:
            pass
    posts.pop(idx)


def quarentenar_post(arquivo: Path) -> Path:
    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
    destino = QUARANTINE_DIR / arquivo.name
    # evita sobrescrever
    if destino.exists():
        destino = QUARANTINE_DIR / f"{arquivo.stem}-{int(time.time())}{arquivo.suffix}"
    arquivo.replace(destino)
    return destino


def escrever_relatorio(linhas: list[str]) -> None:
    cabecalho = [
        "# Vivimundo Editor Report",
        "",
        "Relatório gerado automaticamente pelo editor.",
        "",
    ]
    REPORT_MD.write_text("\n".join(cabecalho + linhas) + "\n", encoding="utf-8")


def main() -> None:
    if not POSTS_JSON.exists():
        log("❌ posts.json não encontrado")
        raise SystemExit(1)

    posts: list[dict[str, Any]] = json.loads(POSTS_JSON.read_text(encoding="utf-8"))
    if not isinstance(posts, list):
        log("❌ posts.json inválido")
        raise SystemExit(1)

    max_edits = int(os.getenv("EDITOR_MAX_EDITS_PER_RUN", "25"))
    max_deletes = int(os.getenv("EDITOR_MAX_DELETES_PER_RUN", "10"))
    apply_fixes = os.getenv("EDITOR_APPLY_FIXES", "0").strip() == "1"

    edits = 0
    deletes = 0
    relatorio: list[str] = []
    relatorio.append(f"- Modo: {'APLICANDO correções' if apply_fixes else 'AUDITORIA (sem alterar posts)'}")
    relatorio.append(f"- Limites: max_edits={max_edits}, max_deletes={max_deletes}")
    relatorio.append("")
    i = len(posts) - 1
    while i >= 0:
        if edits >= max_edits and deletes >= max_deletes:
            break

        if apply_fixes:
            res = editar_um_post(posts[i])
            if res.deleted:
                if deletes < max_deletes:
                    log(f"  🗑️ Removendo do índice: {posts[i].get('titulo','')[:60]} | {res.reasons}")
                    url = posts[i].get('url','')
                    if res.quarantined and url:
                        try:
                            destino = quarentenar_post(Path(url))
                            relatorio.append(f"- 🟧 QUARENTENA: **{posts[i].get('titulo','')[:80]}** ({url}) -> `{destino.as_posix()}` | motivos={res.reasons}")
                        except Exception as e:
                            relatorio.append(f"- 🟧 QUARENTENA (falhou mover): **{posts[i].get('titulo','')[:80]}** ({url}) | err={str(e)[:60]} | motivos={res.reasons}")
                    else:
                        relatorio.append(f"- 🗑️ DELETE: **{posts[i].get('titulo','')[:80]}** ({url}) | motivos={res.reasons}")
                    remover_post(posts, i)
                    deletes += 1
                else:
                    log("  ⛔ Limite de deletions por execução atingido")
                    relatorio.append(f"- ⛔ DELETE (bloqueado por limite): **{posts[i].get('titulo','')[:80]}** ({posts[i].get('url','')})")
            elif res.changed:
                edits += 1
                relatorio.append(f"- ✏️ EDIT: **{posts[i].get('titulo','')[:80]}** ({posts[i].get('url','')}) | ações={res.reasons}")
        else:
            # Auditoria: não altera nada, só detecta flags
            url = posts[i].get("url", "")
            p = Path(url) if url else None
            if not url or not p or not p.exists():
                relatorio.append(f"- ❌ ARQUIVO AUSENTE: **{posts[i].get('titulo','')[:80]}** ({url})")
                i -= 1
                continue
            html = p.read_text(encoding="utf-8", errors="ignore")
            h1, _img, texto = extrair_texto_post_html(html)
            titulo_ref = posts[i].get("titulo") or h1
            flags = avaliar_flags(titulo_ref, texto)
            titulo_limpo = limpar_titulo(titulo_ref)
            if titulo_limpo != titulo_ref:
                flags.append("titulo_grudado")
            if flags:
                relatorio.append(f"- ⚠️ FLAGS: **{titulo_ref[:80]}** ({url}) | {', '.join(flags)}")
        i -= 1

    # Sempre escreve relatório
    relatorio.append("")
    relatorio.append(f"- Resumo: edits={edits} deletes={deletes}")
    escrever_relatorio(relatorio)

    # Só altera índice/páginas se estiver aplicando correções
    if apply_fixes:
        POSTS_JSON.write_text(json.dumps(posts, ensure_ascii=False, indent=2), encoding="utf-8")

    # Regera home e categorias usando o mesmo gerador do projeto
    if apply_fixes:
        try:
            import bot as publicador

            publicador.atualizar_home(posts)
            publicador.gerar_paginas_categorias(posts)
            log("✅ Páginas regeneradas")
        except Exception as e:
            log(f"⚠️ Não consegui regenerar páginas via bot.py: {str(e)[:120]}")

    log(f"✅ Editor finalizado | modo={'apply' if apply_fixes else 'audit'} | edits={edits} deletes={deletes} | max_edits={max_edits} max_deletes={max_deletes}")

    # Pausa curta para reduzir chance de execuções encavalarem em push-trigger
    time.sleep(3)


if __name__ == "__main__":
    main()

