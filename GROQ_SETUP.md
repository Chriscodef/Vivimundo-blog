# 🔑 Como Gerar Nova Chave Groq e Atualizar no GitHub

## Passo 1: Gerar Nova Chave na Groq

1. Acesse: https://console.groq.com/keys
2. Clique em **"Create API Key"** ou **"New API Key"**
3. Copie a chave gerada (começa com `gsk_`)
4. ⚠️ Guarde em um lugar seguro - ela só aparece UMA VEZ

## Passo 2: Atualizar no GitHub Secrets

1. Acesse seu repositório: https://github.com/Chriscodef/Vivimundo-blog
2. Clique em **Settings** > **Secrets and variables** > **Actions**
3. Encontre `GROQ_API_KEY` e clique em **Update**
4. Cole a nova chave no campo "Secret value"
5. Clique em **Update secret**

## Passo 3: Testar

Depois de atualizar:
1. Vá em **Actions** > **Vivimundo Bot**
2. Clique em **Run workflow** (botão azul)
3. Selecione **main** e clique em **Run workflow**
4. Aguarde a execução (deve demorar ~30 segundos)
5. Verifique se a matéria aparece no site

## ✅ Se der tudo certo:

- O bot encontrará notícias ✅
- Gerará textos com a Groq ✅
- Salvará os posts automaticamente ✅
- Atualizará seu site ✅

## ⚠️ Casos de Erro:

Se ainda falhar, verifique:
- Chave copiada SEM espaços em branco
- Chave não está expirada/revogada
- Sua conta Groq tem créditos disponíveis
- A chave começa com `gsk_`

## 📝 Nota sobre o Fallback:

Se a Groq falhar por qualquer motivo (quota esgotada, API down, etc),
o bot agora usa um **fallback automático** que:
- Extrai o conteúdo do site
- Cria uma matéria com estrutura correta
- Continua funcionando normalmente

Isso significa que mesmo sem a Groq, o bot vai publicar algo!
