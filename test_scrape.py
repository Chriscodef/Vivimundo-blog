#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
from bs4 import BeautifulSoup
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
}

def test_scrape():
    # Tenta buscar um site de esportes (que já funcionou)
    site = "https://ge.globo.com/"
    
    try:
        print(f"Tentando {site}...")
        resp = requests.get(site, headers=HEADERS, timeout=10, verify=False)
        resp.encoding = 'utf-8'
        print(f"Status: {resp.status_code}")
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        links = soup.find_all('a', href=True)[:10]
        
        print(f"Encontrados {len(links)} links")
        
        for i, link in enumerate(links[:5]):
            href = link.get('href', '')
            titulo = link.get_text(strip=True)[:60]
            print(f"  {i+1}. {titulo}")
            print(f"     URL: {href[:60]}")
    
    except Exception as e:
        print(f"Erro: {e}")

if __name__ == "__main__":
    test_scrape()
