# AI Chat-bot Makefile

# Load environment variables from .env
ifneq (,$(wildcard ./.env))
    include .env
    export
endif

# EC2 Configuration (from .env)
SSH_CMD = ssh -i $(EC2_KEY) $(EC2_HOST)
SCP_CMD = scp -i $(EC2_KEY)

# Image names
APP_IMAGE = chat-bot:latest
ENCLAVE_IMAGE = chat-bot-enclave:latest

.PHONY: all build deploy-enclave get-address status logs stop help

help:
	@echo "AI Chat-bot - Makefile Commands"
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
	$(SSH_CMD) "mkdir -p ~/chat-bot"
	$(SCP_CMD) -r app.py enclave.py requirements.txt Dockerfile enclaver.yaml ai_models $(EC2_HOST):~/chat-bot/
	@echo "Building Docker image on EC2..."
	$(SSH_CMD) "cd ~/chat-bot && docker build -t $(APP_IMAGE) ."
	@echo "Building enclave image on EC2..."
	$(SSH_CMD) "cd ~/chat-bot && ~/enclaver build -f enclaver.yaml"
	@echo "Starting enclave..."
	$(SSH_CMD) "docker stop chat-bot 2>/dev/null || true && \
		docker rm chat-bot 2>/dev/null || true && \
		docker run -d --name chat-bot -p 8000:8000 --privileged --device=/dev/nitro_enclaves:/dev/nitro_enclaves $(ENCLAVE_IMAGE)"
	@EC2_IP=$$(echo $(EC2_HOST) | cut -d'@' -f2); \
	echo "Enclave deployed! Access at http://$$EC2_IP:8000"

# Get enclave wallet address
get-address:
	@echo "Fetching enclave wallet address..."
	@EC2_IP=$$(echo $(EC2_HOST) | cut -d'@' -f2); \
	curl -s http://$$EC2_IP:8000/ | jq -r '.enclave_address'

# Check enclave status
status:
	@EC2_IP=$$(echo $(EC2_HOST) | cut -d'@' -f2); \
	curl -s http://$$EC2_IP:8000/ | jq .

# Get attestation
attestation:
	@EC2_IP=$$(echo $(EC2_HOST) | cut -d'@' -f2); \
	curl -s http://$$EC2_IP:8000/attestation | jq .

# Test chat endpoint
test-chat:
	@EC2_IP=$$(echo $(EC2_HOST) | cut -d'@' -f2); \
	curl -s -X POST http://$$EC2_IP:8000/talk \
		-H "Content-Type: application/json" \
		-d '{"api_key": "$(TEST_API_KEY)", "message": "Hello!", "platform": "openai", "ai_model": "gpt-4"}' | jq .

# View enclave logs on EC2
logs:
	$(SSH_CMD) "docker logs -f chat-bot"

# Stop enclave on EC2
stop:
	$(SSH_CMD) "docker stop chat-bot"

# Clean up
clean:
	docker rmi $(APP_IMAGE) 2>/dev/null || true
	docker rmi $(ENCLAVE_IMAGE) 2>/dev/null || true
