# Calendari d'Advent de Running 2026

Bot de Telegram 100% gratuït, sense dependències (només Python 3.9+).

## Posada en marxa (10 min)
1. A Telegram, parla amb **@BotFather** → `/newbot` → copia el **token**.
2. Envia `/start` al teu bot nou i obre `https://api.telegram.org/bot<TOKEN>/getUpdates` → copia `chat.id`.
3. Crea un repositori **públic** a GitHub, puja aquests fitxers (`advent.py`, `.github/`) i afegeix a
   *Settings → Secrets and variables → Actions*: `TELEGRAM_TOKEN` i `TELEGRAM_CHAT_ID`.
4. *Actions → Advent Running → Run workflow* per provar. A partir d'aquí s'executa cada 10 min:
   respon les comandes i envia el missatge del dia a les 07:30 (07:00 el 31).
5. (Opcional) `TELEGRAM_TOKEN=... TELEGRAM_CHAT_ID=... python advent.py setup` per tenir el menú de comandes.

> Les comandes es contesten amb un retard de fins a ~10-15 min (GitHub Actions no és en temps real).
> Si vols resposta immediata: `python advent.py loop` en un PC/Raspberry sempre encès.
> `state.json` guarda el bombo (spoiler si algú mira el repo). Repo privat: canvia el cron a `*/30`.

## Proves
`python advent.py simulate 400` verifica totes les regles en 400 calendaris aleatoris (inclou comodins aleatoris).
`python advent.py preview` mostra un calendari d'exemple (spoiler).
