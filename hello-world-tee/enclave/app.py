import logging
import os
from html import escape

import requests
import uvicorn
from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse, JSONResponse

from nova_python_sdk.capsule-runtime import Capsule-Runtime


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

IN_ENCLAVE = os.getenv("IN_ENCLAVE", "false").lower() == "true"

app = FastAPI(title="Hello World TEE", version="1.0.0")
capsule-runtime = Capsule-Runtime()


def read_identity() -> dict:
    eth_res = requests.get(f"{capsule-runtime.endpoint}/v1/eth/address", timeout=10)
    eth_res.raise_for_status()
    eth_identity = eth_res.json()
    encryption_identity = capsule-runtime.get_encryption_public_key()

    return {
        "wallet_address": eth_identity.get("address"),
        "wallet_public_key": eth_identity.get("public_key"),
        "tee_public_key_der": encryption_identity.get("public_key_der"),
        "tee_public_key_pem": encryption_identity.get("public_key_pem"),
    }


@app.get("/")
async def root():
    identity = {}
    error = None

    try:
        identity = read_identity()
    except Exception as exc:
        logger.exception("Failed to fetch identity from capsule-runtime")
        error = str(exc)

    wallet_address = escape(identity.get("wallet_address") or "N/A")
    tee_public_key = escape(identity.get("tee_public_key_der") or "N/A")
    in_enclave = "true" if IN_ENCLAVE else "false"
    error_block = ""
    if error:
        error_block = (
            "<p class='error'>Failed to load identity from capsule-runtime: "
            f"{escape(error)}</p>"
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Hello World TEE</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5f7fb;
      --card: #ffffff;
      --text: #0b1320;
      --muted: #465066;
      --border: #d8e0ee;
      --accent: #0b5fff;
      --error: #b42318;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 24px;
      background: radial-gradient(circle at top, #e9f0ff, var(--bg) 55%);
      color: var(--text);
      font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif;
    }}
    .card {{
      width: min(860px, 100%);
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 24px;
      box-shadow: 0 12px 40px rgba(15, 23, 42, 0.08);
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: clamp(1.6rem, 2.5vw, 2rem);
    }}
    .subtitle {{
      margin: 0 0 20px;
      color: var(--muted);
    }}
    .field {{
      margin-bottom: 14px;
    }}
    .label {{
      margin-bottom: 6px;
      font-size: 0.85rem;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
    .value {{
      margin: 0;
      padding: 10px 12px;
      border-radius: 10px;
      border: 1px solid var(--border);
      background: #f9fbff;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 0.86rem;
      line-height: 1.5;
      word-break: break-all;
      white-space: pre-wrap;
    }}
    .meta {{
      margin-top: 18px;
      color: var(--muted);
      font-size: 0.9rem;
    }}
    .meta b {{ color: var(--text); }}
    .error {{
      margin: 0 0 16px;
      padding: 10px 12px;
      border-radius: 10px;
      border: 1px solid #fecaca;
      background: #fef2f2;
      color: var(--error);
      font-size: 0.9rem;
      word-break: break-word;
    }}
    a {{
      color: var(--accent);
      text-decoration: none;
    }}
  </style>
</head>
<body>
  <main class="card">
    <h1>Hello World from TEE!</h1>
    <p class="subtitle">A minimal greeting card served by your enclave app.</p>
    {error_block}
    <section class="field">
      <div class="label">Wallet Address</div>
      <pre class="value">{wallet_address}</pre>
    </section>
    <section class="field">
      <div class="label">TEE Public Key (DER Hex)</div>
      <pre class="value">{tee_public_key}</pre>
    </section>
    <p class="meta">
      <b>IN_ENCLAVE:</b> {in_enclave}
    </p>
  </main>
</body>
</html>"""

    return HTMLResponse(content=html, status_code=500 if error else 200)



if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
