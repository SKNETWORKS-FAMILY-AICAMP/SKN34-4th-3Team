@echo off
REM ---------------------------------------------------------------------------
REM  Local run script for the startup support platform (Windows cmd.exe)
REM
REM    setup.bat                 start the containers, then the Frontend dev server
REM    setup.bat --no-frontend   start the containers only (CI / headless)
REM
REM  db, backend and llm run under Docker Compose. Only the Frontend runs on the
REM  host: vite.config.js proxies /api to a host address, so docker-compose.yml
REM  has no frontend service.
REM
REM  This script never creates .env. It holds secrets, is not shared through git,
REM  and has to be copied into the repository root by hand.
REM
REM  Requires Docker Compose v2.1.1 or newer (--wait).
REM
REM  Messages are ASCII only on purpose. cmd.exe reads batch files in the OEM
REM  code page, so non-ASCII text breaks the output and the parser with it.
REM ---------------------------------------------------------------------------

cd /d "%~dp0"

set "FRONTEND=1"
if "%~1"=="" goto :args_done
if /i "%~1"=="--no-frontend" ( set "FRONTEND=0" & goto :args_done )
echo   X  Unknown option: %~1  ^(supported: --no-frontend^)
exit /b 2
:args_done

if not exist ".env" (
    echo.
    echo   X  .env not found in %CD%
    echo      Ask the team for the file and put it in the repository root.
    echo      Required: POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB,
    echo                OPENAI_API_KEY, LLM_MODEL, EMBEDDING_MODEL
    echo.
    exit /b 1
)

REM If any of these three is empty the db healthcheck never passes and
REM backend/llm wait forever on depends_on: service_healthy.
REM "KEY=." means the key needs at least one character after "=". Do not use a
REM negated class such as [^ ] here, findstr does not handle those reliably.
findstr /b /r "POSTGRES_USER=." .env >nul || goto :env_empty
findstr /b /r "POSTGRES_PASSWORD=." .env >nul || goto :env_empty
findstr /b /r "POSTGRES_DB=." .env >nul || goto :env_empty
findstr /b /r "OPENAI_API_KEY=." .env >nul || echo   *  OPENAI_API_KEY is not set. AI answers fall back to mock data.

set "RETRY=--connect-timeout 5 --retry 30 --retry-delay 2 --retry-connrefused --retry-max-time 90"

echo [1/4] Building images ^(the first run takes a few minutes^)
docker compose build || goto :fail

echo [2/4] Starting db and applying the schema add-ons
docker compose up -d --wait db || goto :fail
REM initdb only runs on an empty volume, so a volume created before the
REM app_extras mount was added is missing those columns and backend dies on
REM users.phone. Every statement is IF NOT EXISTS, so re-running is safe.
REM The user and database names come from the db container's own environment.
docker compose exec -T db sh -c "psql -U $POSTGRES_USER -d $POSTGRES_DB -v ON_ERROR_STOP=1 -q" < DB\app_extras.sql || goto :fail

echo [3/4] Starting backend and llm
docker compose up -d backend llm || goto :fail

echo [4/4] Health check
curl -fsS -o nul %RETRY% http://127.0.0.1:8001/health || goto :fail_llm
curl -fsS %RETRY% http://127.0.0.1:8000/health || goto :fail_backend
echo.
curl -fsS http://127.0.0.1:8000/health | findstr /c:"\"storage\":\"postgres\"" >nul || echo   *  Backend fell back to SQLite. Check DATABASE_URL.
curl -fsS http://127.0.0.1:8000/health | findstr /c:"\"ragReady\":true" >nul || echo   *  RAG index is empty, so AI answers are mock. POST :8001/rag/reindex to build it.

echo.
echo   Backend  http://localhost:8000/docs
echo   LLM      http://localhost:8001/docs
echo   Stop     docker compose down

if "%FRONTEND%"=="0" exit /b 0

cd Frontend
REM npm ci wipes node_modules. A running Vite locks esbuild.exe and the install
REM then fails with EPERM, so only run it when the folder is missing. After a
REM git pull that changed package-lock.json, run npm ci yourself.
if not exist "node_modules" (
    call npm ci || goto :fail
)

echo.
echo   App      http://localhost:5173  ^(opens automatically^)
echo   Demo     demo@demo.com / demo123     Admin  admin@demo.com / admin123
echo   Ctrl+C stops the Frontend only.
echo.
call npm run dev
exit /b %errorlevel%

:env_empty
echo.
echo   X  POSTGRES_USER, POSTGRES_PASSWORD and POSTGRES_DB must have values in .env
echo      Without them the db container never becomes healthy and backend and
echo      llm wait forever.
echo.
exit /b 1

:fail_llm
docker compose logs --tail=30 llm
echo   X  llm did not respond. See the log above.
exit /b 1

:fail_backend
docker compose logs --tail=30 backend
echo   X  backend did not respond. See the log above.
exit /b 1

:fail
echo.
echo   X  Failed. See the error above.
exit /b 1
