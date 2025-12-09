# Coin Price Bot Makefile

# Load environment variables from .env
ifneq (,$(wildcard ./.env))
    include .env
    export
endif

# EC2 Configuration (from .env)
SSH_CMD = ssh -i $(EC2_KEY) $(EC2_HOST)
SCP_CMD = scp -i $(EC2_KEY)

# Image names
APP_IMAGE = coin-price-bot:latest
ENCLAVE_IMAGE = coin-price-bot-enclave:latest

.PHONY: all build deploy-enclave get-address status logs stop help

help:
	@echo "Coin Price Bot - Makefile Commands"
	@echo ""
	@echo "  make build            - Build Docker image locally"
	@echo "  make deploy-enclave   - Deploy enclave to EC2"
	@echo "  make get-address      - Get enclave wallet address"
	@echo "  make status           - Check enclave status"
	@echo "  make logs             - View enclave logs"
	@echo "  make stop             - Stop enclave on EC2"
	@echo ""
	@echo "Setup: cp .env.example .env && fill in EC2_KEY and EC2_HOST"
	@echo ""
	@echo "Workflow:"
	@echo "  1. make build"
	@echo "  2. make deploy-enclave"
	@echo "  3. make status"

# Build Docker image locally
build:
	@echo "Building Docker image..."
	docker build -t $(APP_IMAGE) .
	@echo "Docker image built: $(APP_IMAGE)"

# Deploy enclave to EC2
deploy-enclave:
	@echo "Transferring source files to EC2..."
	$(SSH_CMD) "mkdir -p ~/coin-price-bot"
	$(SCP_CMD) app.py enclave.py utils.py tee_client.py requirements.txt Dockerfile enclaver.yaml $(EC2_HOST):~/coin-price-bot/
	@echo "Building Docker image on EC2..."
	$(SSH_CMD) "cd ~/coin-price-bot && docker build -t $(APP_IMAGE) ."
	@echo "Building enclave image on EC2..."
	$(SSH_CMD) "cd ~/coin-price-bot && ~/enclaver build -f enclaver.yaml"
	@echo "Starting enclave..."
	$(SSH_CMD) "docker stop coin-price-bot 2>/dev/null || true && \
		docker rm coin-price-bot 2>/dev/null || true && \
		docker run -d --name coin-price-bot -p 8001:8000 --privileged --device=/dev/nitro_enclaves:/dev/nitro_enclaves $(ENCLAVE_IMAGE)"
	@EC2_IP=$$(echo $(EC2_HOST) | cut -d'@' -f2); \
	echo "Enclave deployed! Access at http://$$EC2_IP:8001"

# Get enclave wallet address
get-address:
	@echo "Fetching enclave wallet address..."
	@EC2_IP=$$(echo $(EC2_HOST) | cut -d'@' -f2); \
	curl -s http://$$EC2_IP:8001/ | jq -r '.enclave_address'

# Check enclave status
status:
	@EC2_IP=$$(echo $(EC2_HOST) | cut -d'@' -f2); \
	curl -s http://$$EC2_IP:8001/ | jq .

# Get attestation
attestation:
	@EC2_IP=$$(echo $(EC2_HOST) | cut -d'@' -f2); \
	curl -s http://$$EC2_IP:8001/attestation | jq .

# Test query endpoint
test-query:
	@EC2_IP=$$(echo $(EC2_HOST) | cut -d'@' -f2); \
	curl -s http://$$EC2_IP:8001/query | jq .

# Test talk endpoint
test-talk:
	@EC2_IP=$$(echo $(EC2_HOST) | cut -d'@' -f2); \
	curl -s -X POST http://$$EC2_IP:8001/talk \
		-H "Content-Type: application/json" \
		-d '{"api_key": "$(TEST_API_KEY)", "message": "What is the current price of Bitcoin?", "platform": "openai", "ai_model": "gpt-4"}' | jq .

# View enclave logs on EC2
logs:
	$(SSH_CMD) "docker logs -f coin-price-bot"

# Stop enclave on EC2
stop:
	$(SSH_CMD) "docker stop coin-price-bot"

# Clean up
clean:
	docker rmi $(APP_IMAGE) 2>/dev/null || true
	docker rmi $(ENCLAVE_IMAGE) 2>/dev/null || true
