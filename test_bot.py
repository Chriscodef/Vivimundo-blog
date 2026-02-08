#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testes para o bot.py"""

import sys
import os
import re
from pathlib import Path
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

# Configurar variável de ambiente antes de importar bot
os.environ['GROQ_API_KEY'] = 'test-key-for-validation-only'

# Importar funções do bot
sys.path.insert(0, '.')
from bot import (

    limpar_titulo, 
    normalizar_url, 
    normalizar_titulo, 
    classificar_subcategoria,
    eh_titulo_valido,
    TEMAS
)

def test_limpar_titulo():
    """Testa a função de limpeza de títulos"""
    print('=== Teste limpar_titulo() ===')
    testes = [
        ('Michael JacksonVeja o trailer', 'Michael Jackson Veja o trailer'),
        ('HPComo funciona', 'HP Como funciona'),
        ('AÍ!Baldur\'s Gate', 'AÍ! Baldur\'s Gate'),
        ('VEM AÍ!Baldur\'s Gate 3', 'VEM AÍ! Baldur\'s Gate 3'),
        ('SegurançaChina revela projeto', 'Segurança China revela projeto'),
    ]
    
    passed = 0
    for entrada, esperado in testes:
        resultado = limpar_titulo(entrada)
        status = '✅' if resultado == esperado else '❌'
        print(f'  {status} "{entrada}" -> "{resultado}"')
        if resultado == esperado:
            passed += 1
        else:
            print(f'      Esperado: "{esperado}"')
    
    print(f'  Resultado: {passed}/{len(testes)} testes passaram\n')
    return passed == len(testes)

def test_normalizar_url():
    """Testa a normalização de URLs"""
    print('=== Teste normalizar_url() ===')
    testes = [
        ('https://example.com/path/', 'https://example.com/path'),
        ('HTTPS://Example.COM/Path', 'https://example.com/path'),
        ('https://example.com/path?utm_source=test', 'https://example.com/path'),
        ('https://example.com/path?utm_source=test&fbclid=123', 'https://example.com/path'),
    ]
    
    passed = 0
    for entrada, esperado in testes:
        resultado = normalizar_url(entrada)
        status = '✅' if resultado == esperado else '❌'
        print(f'  {status} URL normalizada corretamente')
        if resultado == esperado:
            passed += 1
        else:
            print(f'      Entrada:  "{entrada}"')
            print(f'      Resultado: "{resultado}"')
            print(f'      Esperado:  "{esperado}"')
    
    print(f'  Resultado: {passed}/{len(testes)} testes passaram\n')
    return passed == len(testes)

def test_normalizar_titulo():
    """Testa a normalização de títulos para cache"""
    print('=== Teste normalizar_titulo() ===')
    testes = [
        ('  Flamengo VENCE Palmeiras!!!  ', 'flamengo vence palmeiras'),
        ('Novo Filme da MARVEL', 'novo filme da marvel'),
        ('ChatGPT: Nova Versão', 'chatgpt nova versão'),
    ]
    
    passed = 0
    for entrada, esperado in testes:
        resultado = normalizar_titulo(entrada)
        status = '✅' if resultado == esperado else '❌'
        print(f'  {status} "{entrada[:40]}" -> "{resultado}"')
        if resultado == esperado:
            passed += 1
    
    print(f'  Resultado: {passed}/{len(testes)} testes passaram\n')
    return passed == len(testes)

def test_classificar_subcategoria():
    """Testa a classificação automática de subcategorias"""
    print('=== Teste classificar_subcategoria() ===')
    testes = [
        ('Flamengo vence Palmeiras no Maracanã', 'esportes', 'futebol'),
        ('Verstappen vence GP do Brasil', 'esportes', 'automobilismo'),
        ('Novo filme da Marvel estreia em breve', 'entretenimento', 'cinema-series'),

        ('ChatGPT ganha nova versão', 'tecnologia', 'inteligencia-artificial'),
        ('Lula anuncia novo projeto', 'politica-nacional', 'governo-federal'),
        ('Biden se reúne com Putin', 'politica-internacional', 'eua'),
        ('Crime no Rio de Janeiro', 'rio-de-janeiro', 'seguranca'),
        ('Metrô de São Paulo', 'sao-paulo', 'transporte'),
    ]
    
    passed = 0
    for titulo, categoria, esperado in testes:
        resultado = classificar_subcategoria(titulo, categoria)
        status = '✅' if resultado == esperado else '❌'
        print(f'  {status} "{titulo[:40]}" ({categoria}) -> {resultado}')
        if resultado == esperado:
            passed += 1
    
    print(f'  Resultado: {passed}/{len(testes)} testes passaram\n')
    return passed == len(testes)

def test_eh_titulo_valido():
    """Testa a validação de títulos"""
    print('=== Teste eh_titulo_valido() ===')
    testes = [
        ('Câmara aprova MP importante', True),
        ('Game Rant Advance', False),  # Genérico
        ('Esportes a Motor', False),   # Genérico
        ('123456789', False),          # Só números
        ('Fla', False),                # Muito curto
    ]
    
    passed = 0
    for titulo, esperado in testes:
        resultado = eh_titulo_valido(titulo)
        status = '✅' if resultado == esperado else '❌'
        print(f'  {status} "{titulo[:50]}" -> {"Válido" if resultado else "Inválido"}')
        if resultado == esperado:
            passed += 1
    
    print(f'  Resultado: {passed}/{len(testes)} testes passaram\n')
    return passed == len(testes)

def test_temas():
    """Verifica se o array TEMAS está correto"""
    print('=== Teste TEMAS ===')
    print(f'  Total de categorias: {len(TEMAS)}')
    
    for tema in TEMAS:
        nome = tema['nome']
        cat = tema['categoria']
        sites = len(tema['sites'])
        print(f'  ✅ {nome} ({cat}) - {sites} sites')
    
    # Verificar se tem 8 categorias
    assert len(TEMAS) == 8, f"Esperado 8 categorias, encontrado {len(TEMAS)}"
    
    # Verificar se Rio e São Paulo existem
    cats = [t['categoria'] for t in TEMAS]
    assert 'rio-de-janeiro' in cats, "Categoria rio-de-janeiro não encontrada"
    assert 'sao-paulo' in cats, "Categoria sao-paulo não encontrada"
    
    print('  ✅ Todas as 8 categorias presentes')
    print('  ✅ Rio de Janeiro e São Paulo adicionados\n')
    return True

def main():
    """Executa todos os testes"""
    print('='*60)
    print('TESTES DO VIVIMUNDO BOT')
    print('='*60 + '\n')
    
    resultados = []
    
    resultados.append(test_limpar_titulo())
    resultados.append(test_normalizar_url())
    resultados.append(test_normalizar_titulo())
    resultados.append(test_classificar_subcategoria())
    resultados.append(test_eh_titulo_valido())
    resultados.append(test_temas())
    
    print('='*60)
    print('RESUMO DOS TESTES')
    print('='*60)
    total = len(resultados)
    passaram = sum(resultados)
    print(f'Testes passados: {passaram}/{total}')
    
    if passaram == total:
        print('✅ TODOS OS TESTES PASSARAM!')
        return 0
    else:
        print('❌ ALGUNS TESTES FALHARAM')
        return 1

if __name__ == '__main__':
    sys.exit(main())
