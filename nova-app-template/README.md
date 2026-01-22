# Nova App Template（最新版 Odyn 内部 API）

该模板用于在 Nova 平台构建可验证的 TEE 应用，已按最新的 Odyn Internal API 更新，并覆盖以下需求：

1. S3 读写 + 写入数据的哈希上链
2. 定时拉取公网数据并更新链上合约
3. 监听链上事件并写回链上
4. 外部可访问 API，支持 RA‑TLS 加密通信
5. 前端位于 /frontend
6. 简单封装 Odyn Mockup Service（odyn.py）

---

## 目录结构

```
|-- enclave/               # FastAPI (TEE)
|   |-- app.py             # 应用入口
|   |-- routes.py          # API 路由（业务入口）
|   |-- tasks.py           # 定时任务 & 事件监听
|   |-- odyn.py            # Odyn SDK (最新内部 API)
|   |-- chain.py           # 链上交互 & 交易签名工具
|   |-- requirements.txt
|-- contracts/             # Solidity 基础合约
|   |-- src/NovaAppBase.sol
|-- frontend/              # Next.js 前端
|-- enclaver.yaml          # Enclave 配置
|-- Makefile
```

---

## 核心能力说明

### 1) S3 读写 + Hash 上链
- `/api/storage` 写入 S3 后会：
	- 更新内存状态
	- 计算整体 state hash（keccak256）
	- 调用 `updateStateHash(bytes32)` 签名交易并可选广播

相关逻辑：
- [enclave/routes.py](enclave/routes.py)
- [enclave/chain.py](enclave/chain.py)
- [contracts/src/NovaAppBase.sol](contracts/src/NovaAppBase.sol)

### 2) 定时拉取公网数据 → 链上更新
`tasks.background_task()` 每 5 分钟执行：
- 拉取公网数据（默认示例：ETH 价格）
- 保存至 S3
- 计算 state hash
- 签名 `updateStateHash` 交易

相关逻辑：
- [enclave/tasks.py](enclave/tasks.py)

### 3) 监听链上事件 → 写回链上
合约新增事件：
```
StateUpdateRequested(bytes32 requestedHash, address requester)
```
Enclave 会轮询事件并响应：
- 监听 `StateUpdateRequested`
- 计算本地 state hash
- 触发 `updateStateHash` 交易签名（可广播）

相关逻辑：
- [enclave/tasks.py](enclave/tasks.py)
- [contracts/src/NovaAppBase.sol](contracts/src/NovaAppBase.sol)

### 4) 外部 API + RA‑TLS
- `/.well-known/attestation`：公开 attestation endpoint（CBOR）
- `/api/echo`：支持加密 payload（ECDH + AES-GCM）
- `/api/encryption/*`：提供 encrypt/decrypt 工具接口

前端使用 RA‑TLS 流程：
1. 拉取 attestation
2. 验证 PCR / public key
3. 建立 ECDH 共享密钥
4. 进行加密通信

相关逻辑：
- [enclave/routes.py](enclave/routes.py)
- [frontend/src/lib/crypto.ts](frontend/src/lib/crypto.ts)
- [frontend/src/lib/attestation.ts](frontend/src/lib/attestation.ts)

### 5) 前端
前端位于 `/frontend`，提供：
- RA‑TLS 连接体验
- S3 存储 demo
- Oracle demo
- Event 监听状态展示

### 6) Odyn Mockup Service
`odyn.py` 会根据 `IN_ENCLAVE` 自动切换：
- `IN_ENCLAVE=true` → http://localhost:18000
- `IN_ENCLAVE=false` → http://odyn.sparsity.cloud:18000

Mockup 兼容最新 Internal API：
- /v1/eth/address
- /v1/eth/sign / sign-tx
- /v1/attestation
- /v1/encryption/*
- /v1/s3/*

---

## 快速开始

### 本地开发（Mock）
```bash
cd nova-app-template
make install-enclave
make install-frontend
make build-frontend

# 运行 FastAPI（mock 模式）
cd enclave
python app.py
```

默认访问：
- API: http://localhost:8000
- Attestation: http://localhost:8000/.well-known/attestation
- UI: http://localhost:8000/frontend

### 部署到 Nova
1. 在 Nova Console 创建 App
2. 设置 App Listening Port = 8000
3. 填写合约地址（NovaAppBase 或自定义合约）
4. 平台会自动注入 S3 / Egress / RA‑TLS 配置

---

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `IN_ENCLAVE` | false | 是否运行在真实 enclave | 
| `RPC_URL` | https://sepolia.base.org | JSON-RPC 端点 |
| `CHAIN_ID` | 84532 | 链 ID (Base Sepolia) |
| `CONTRACT_ADDRESS` | (空) | NovaAppBase 合约地址 |
| `BROADCAST_TX` | false | 是否自动广播签名交易 |
| `ANCHOR_ON_WRITE` | true | 写入 S3 时自动上链 hash |

---

## 主要 API

| Endpoint | Method | 描述 |
|----------|--------|------|
| `/.well-known/attestation` | POST | 返回原始 CBOR attestation |
| `/api/attestation` | GET | base64 封装 attestation |
| `/api/echo` | POST | 支持加密/明文 echo |
| `/api/storage` | POST/GET | S3 读写 + hash 上链 |
| `/api/storage/{key}` | GET/DELETE | 单个 key 读写 |
| `/api/oracle/price` | GET | 公网数据 → 签名交易 |
| `/api/contract/update-state` | POST | 手动更新 stateHash |
| `/status` | GET | 当前 TEE 状态 |

---

## 合约说明

`NovaAppBase` 提供：
- `registerTeeWallet(address)`
- `updateStateHash(bytes32)`
- `requestStateUpdate(bytes32)` → 触发事件供 TEE 监听

如果你需要自定义逻辑：
- 继承 `NovaAppBase`
- 添加你自己的事件和函数

---

## FAQ

**Q: 为什么本地无法写入 S3？**
A: Mock service 不保证持久化。上链逻辑可测试，但 S3 需在真实 enclave。

**Q: RA‑TLS 如何验证？**
A: 前端会解析 attestation 文档并校验 PCR / Public Key。

**Q: 交易 nonce 如何获取？**
A: 模板内通过 JSON‑RPC 获取 nonce 和 gas。

---

## 参考
- Odyn Internal API: https://github.com/sparsity-xyz/enclaver/blob/sparsity/docs/odyn.md
- Internal API Reference: https://github.com/sparsity-xyz/enclaver/blob/sparsity/docs/internal_api.md
- Mockup Service: https://github.com/sparsity-xyz/enclaver/blob/sparsity/docs/internal_api_mockup.md
