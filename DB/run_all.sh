#!/bin/bash
# docker exec -i startup_db psql -U admin -d startup_platform < 01_schema.sql
uv run python scripts/02_collect_tax_law.py
uv run python scripts/03_collect_gov24.py
uv run python scripts/04_collect_kstartup.py
uv run python scripts/05_collect_bizinfo.py
uv run python scripts/06_collect_ontong_youth.py
uv run python scripts/07_generate_calendar_events.py
docker exec -i startup_db psql -U admin -d startup_platform < scripts/08_link_policy_calendar.sql