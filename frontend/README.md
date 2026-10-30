# RedisRAG frontend

React 19 + TypeScript + Vite: the page where you analyze a GitHub profile and chat
about it. See the [main README](../README.md) for how the whole app works.

## Run locally

```bash
npm install
npm run dev        # http://localhost:5173
```

The app calls the backend at `VITE_API_URL`, or `http://localhost:8000` when it isn't set.
To use the deployed backend instead, create `frontend/.env.local` (git ignores it):

```env
VITE_API_URL=https://redis-rag-1.onrender.com
```

Vite builds `VITE_` variables into the JavaScript at build time, so after changing
one on Vercel you must redeploy.

## Checks

```bash
npm run lint       # oxlint
npm run build      # type-check (tsc -b) + production build
```
