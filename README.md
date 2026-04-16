# ARCADIANS — BBC Micro Edition
## A Galaxian-style retro game demo on OpenShift

Faithful clone of the 1982 Acornsoft Arcadians (BBC Micro) — itself a clone of Namco's Galaxian.
Features swooping dive-bombing aliens, four alien ranks with escort dive rules, authentic BBC
audio extracted from the original game binary, and a PostgreSQL high score table. Built as a
full Kubernetes demo stack on OpenShift.

---

### Stack

| Component  | Technology                                         |
|------------|----------------------------------------------------|
| Game       | Vanilla HTML5 Canvas + Web Audio API               |
| API        | FastAPI (Python 3.12) + asyncpg                    |
| Database   | PostgreSQL 16 StatefulSet                          |
| Backup     | Kanister non-exclusive BP (`postgres-non-exclusive-backup`) |
| Registry   | Harbor (`harbor.apps.openshift2.lab.home`)         |
| Platform   | OpenShift (`rke2-prod`)                            |
| Namespace  | `retro-game`                                       |

---

### Directory Structure

```
arcadians/
├── README.md
├── game/
│   ├── index.html       # Full self-contained game (215KB) — Canvas, Web Audio, scores
│   ├── nginx.conf       # Proxies /api/ → arcadians-api ClusterIP service
│   └── Dockerfile       # nginx:alpine
├── api/
│   ├── main.py          # FastAPI — GET /api/scores, POST /api/scores, GET /healthz
│   ├── requirements.txt # fastapi, uvicorn, asyncpg, pydantic
│   └── Dockerfile       # python:3.12-slim
└── k8s/
    ├── 00-namespace.yaml           # retro-game namespace
    ├── 01-postgresql.yaml          # StatefulSet + headless svc + ClusterIP svc + Secret
    ├── 02-api.yaml                 # FastAPI Deployment + Service
    ├── 03-frontend.yaml            # nginx Deployment + Service + OpenShift Route (TLS edge)
    └── 04-kanister-actionset.yaml  # Manual backup trigger
```

---

### Game Features

**Formation**
- 46 aliens across 6 rows, each row centred independently:
  - 2 × **Generals** (yellow/red flagship — 100pts static, 800pts diving)
  - 6 × **Majors** (red body, blue wings — 50pts static, 400pts diving)
  - 8 × **Captains** (blue with yellow highlights — 20pts static, 160pts diving)
  - 30 × **Infantry** (10 per row × 3 rows — 10pts static, 80pts diving)
- All point values increase with wave number

**Dive Behaviour**
- Galaxian-style wide sweeping arcs — aliens peel off strongly sideways before curving down
- Divers wrap off the bottom and glide back into their formation slot from the top
- **Generals never dive alone** — always escorted by 2 others (Majors preferred, then Captains, then Infantry)
- Normal dives prefer higher-rank leaders; wingmen peel off in opposite directions

**Gameplay**
- Shoot enemy bombs out of the air (player bullet intercepts falling bombs)
- Extra life awarded every 10,000 points
- Wave progression — faster formation sweep, faster shooting, more aggressive dives
- Player death animation — 12-frame debris explosion with expanding ring

**Audio** — all sourced from original BBC Micro recordings
- Intro music (39-note melody extracted via FFT from original Arcadians audio)
- Mission briefing sound effect
- Shoot sound (real BBC Micro laser)
- Alien death explosion (real BBC Micro audio)
- Player death (real BBC Micro audio)
- New life fanfare
- Formation march tick (4-frequency cycle extracted from 6502 binary)
- Dive warble (synthesised from extracted BBC pitch values)

**Hi-Score Table**
- Top 8 scores with player initials and wave reached
- Persisted in PostgreSQL, displayed on title screen

---

### Controls

| Key       | Action                                          |
|-----------|-------------------------------------------------|
| `←` / `Z` | Move left                                       |
| `→` / `X` | Move right                                      |
| `SPACE`   | Fire (also intercepts falling enemy bombs)      |
| Any key   | Start intro music on title screen               |
| `SPACE`   | Skip intro / start game immediately             |

---

### Build & Push Images

```bash
# Game frontend
cd game
docker build --no-cache -t harbor.apps.openshift2.lab.home/retro-game/arcadians-game:latest .
docker push harbor.apps.openshift2.lab.home/retro-game/arcadians-game:latest

# API backend
cd ../api
docker build --no-cache -t harbor.apps.openshift2.lab.home/retro-game/arcadians-api:latest .
docker push harbor.apps.openshift2.lab.home/retro-game/arcadians-api:latest
```

> Always use `--no-cache` to ensure the updated `index.html` is picked up.

---

### Deploy to OpenShift

```bash
# Apply manifests in order
oc apply -f k8s/00-namespace.yaml
oc apply -f k8s/01-postgresql.yaml

# Wait for PostgreSQL before deploying the API
oc -n retro-game rollout status statefulset/arcadians-postgresql

oc apply -f k8s/02-api.yaml
oc apply -f k8s/03-frontend.yaml

# Verify all rollouts
oc -n retro-game rollout status deployment/arcadians-api
oc -n retro-game rollout status deployment/arcadians-game

# Get the route URL
oc -n retro-game get route arcadians
```

---

### Rebuild & Restart (day-to-day)

```bash
cd ~/projects/Arcadians
docker build --no-cache -t harbor.apps.openshift2.lab.home/retro-game/arcadians-game:latest ./game && \
docker push harbor.apps.openshift2.lab.home/retro-game/arcadians-game:latest && \
oc -n retro-game rollout restart deployment/arcadians-game && \
oc -n retro-game rollout status deployment/arcadians-game
```

---

### OpenShift SCC Note

If the PostgreSQL pod fails to start due to SCC restrictions:

```bash
oc adm policy add-scc-to-user anyuid -z default -n retro-game
```

For a cleaner approach with a dedicated service account:

```bash
oc create sa arcadians-sa -n retro-game
oc adm policy add-scc-to-user anyuid -z arcadians-sa -n retro-game
```

Then add `serviceAccountName: arcadians-sa` to the StatefulSet pod spec in `01-postgresql.yaml`.

---

### PostgreSQL & Kanister Backup

The StatefulSet is annotated and labelled to work with the `postgres-non-exclusive-backup`
Kanister blueprint in `kasten-io`. The blueprint uses the PostgreSQL 15+ non-exclusive API
(`pg_backup_start` / `pg_backup_stop`).

Required labels and secret naming:

```
app.kubernetes.io/instance: arcadians    # used to construct PGHOST in the blueprint
Secret name: arcadians-postgresql        # must follow {{ instance }}-postgresql convention
Secret key:  postgres-password
```

Annotate the StatefulSet for Kasten policy discovery:

```bash
oc -n retro-game annotate statefulset arcadians-postgresql \
  kanister.kasten.io/blueprint='postgres-non-exclusive-backup'
```

Trigger a manual backup:

```bash
# Edit 04-kanister-actionset.yaml to set your Kanister profile name, then:
oc apply -f k8s/04-kanister-actionset.yaml -n kasten-io
oc -n kasten-io get actionset arcadians-postgresql-backup -w
```

---

### ArgoCD Integration

Push the repo to Gitea and create an ArgoCD Application pointing at `k8s/`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: arcadians
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://YOUR_GITEA/YOUR_ORG/arcadians.git
    targetRevision: HEAD
    path: k8s
  destination:
    server: https://kubernetes.default.svc
    namespace: retro-game
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

---

### API Reference

| Method | Path          | Description                         |
|--------|---------------|-------------------------------------|
| GET    | `/api/scores` | Top 10 scores ordered by score desc |
| POST   | `/api/scores` | Submit a new score                  |
| GET    | `/healthz`    | Liveness/readiness health check     |

POST body:
```json
{ "initials": "JTT", "score": 24680, "wave": 5 }
```

The `scores` table is created automatically on API startup if it does not exist.

---

### Architecture Notes

The nginx frontend proxies all `/api/` requests to the `arcadians-api` ClusterIP service,
so only a single OpenShift Route is needed. The API reaches PostgreSQL via the
`arcadians-postgresql` ClusterIP service — no external database exposure.

The game is entirely self-contained in a single `index.html` (215KB) including all audio
embedded as base64 MP3. No CDN dependencies at runtime except the Press Start 2P font
from Google Fonts.

The full stack is isolated within `retro-game` and can be torn down cleanly:

```bash
oc delete namespace retro-game
```
