# Security policy

Please report security issues privately through GitHub: **Security → Report a vulnerability** on this repository. Don't open a public issue for them.

Things worth knowing:

- API keys live only in `.env`, which is gitignored. Never commit keys, and never paste them into issues.
- SiteScore is built to run locally. If you host it with `OPENROUTER_API_KEY` set, anyone who can reach it can spend that key's credit through the analyst: put it behind authentication and set a spending limit on the key.
