.PHONY: build-frontend clean

build-frontend:
	cd frontend && npm ci && npm run build
	mkdir -p enclave/frontend
	cp -r frontend/out/* enclave/frontend/

clean:
	rm -rf enclave/frontend
	rm -rf frontend/out
	rm -rf frontend/node_modules
