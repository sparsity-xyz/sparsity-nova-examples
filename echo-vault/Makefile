.PHONY: dev-backend dev-frontend build-frontend build-enclave

dev-backend:
	cd enclave && IN_ENCLAVE=false python3 -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload

dev-frontend:
	cd frontend && npm run dev

build-frontend:
	cd frontend && npm run build
	rm -rf enclave/frontend
	mkdir -p enclave/frontend
	cp -r frontend/dist/* enclave/frontend/

build-enclave:
	enclaver build
