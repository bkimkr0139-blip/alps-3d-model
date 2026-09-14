COMPOSE = docker compose --env-file .env -f infra/docker-compose.yml

.PHONY: up down ps logs env

env:
	test -f .env || cp .env.example .env

up: env
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f --tail=200
