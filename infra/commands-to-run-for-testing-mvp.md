# Commands To Run For Testing MVP

## 1. Start container and enter shell
```bash
cd ~/zklora-punica-mvp/infra/docker
docker compose up -d dev
docker compose exec dev bash
cd /workspace
```

## 2. Quick sanity test (no model load)
```bash
python3 - <<'PY'
from mvp_server.api.server import MVPServer
from mvp_server.config import AppConfig
from mvp_server.runtime.model_runtime import InferenceResult

class FakeRuntime:
    loaded = True
    def infer_prefill(self, prompt, generation_params=None):
        return InferenceResult(
            output=f"echo:{prompt}",
            module_id="transformer.h.0.attn.c_attn",
            h_x="hx",
            h_delta="hd",
            hash_schema_version=1,
        )

srv = MVPServer(config=AppConfig.from_dict({}), runtime=FakeRuntime())
resp = srv.post_infer({"prompt": "hola"})
print(resp)
print(srv.get_proof(resp["receipt"]["request_id"]))
PY
```

## 3. Real runtime test (`distilgpt2`)
```bash
python3 - <<'PY'
from mvp_server.api.server import MVPServer
from mvp_server.config import AppConfig

srv = MVPServer(config=AppConfig.from_dict({}))
resp = srv.post_infer({"prompt": "Hello from MVP"})
print(resp["receipt"])
print(srv.get_health())
print(srv.get_metrics())
PY
```

## 4. Run test suite
```bash
python3 -m pytest -q mvp_server/tests
```

