# Quickstart

## Docker (recommended)

Prerequisites: Docker with the Compose plugin and OpenSSL.

```bash
git clone <repository-url>
cd SwiftGenerator
make quickstart
```

The command creates `.env` from safe deterministic defaults when absent, generates local
session/cache/encryption secrets, builds images, runs migrations, starts both services and
waits for readiness. Open <http://localhost:3000>. No AI key and no knowledge bundle are
required for the 23 configured messages.

```bash
make stop       # keep the Docker data volume
make reset-dev  # remove containers and the Docker data volume
```

Use `BACKEND_PORT=8021 FRONTEND_PORT=3021 make quickstart` when the default ports are
occupied. Compose passes the selected ports through CORS and the browser API build.

An approved knowledge bundle can be supplied on the same command; see
[knowledge-distribution.md](knowledge-distribution.md). AI remains disabled unless an
operator explicitly configures a provider and credentials.

## Local developer mode

Prerequisites: Python 3.13 and Node 22.

```bash
make install
make migrate
make dev
```

`make dev` runs the API on `127.0.0.1:8000` and Next.js on `localhost:3000`. Copy
`.env.example` to `.env` only when changing defaults. The example defaults to deterministic
operation.

## Probes

```bash
curl http://localhost:8000/api/health/live
curl http://localhost:8000/api/health/ready
```

Readiness requires the application database and configured MT/MX registries. Knowledge, AI
and embeddings are optional states and cannot block configured Create Message startup.

If Create Message shows only configured messages after a knowledge sync, ensure the server
process has `KNOWLEDGE_MODE=local` or `local_uat`, then restart it.
