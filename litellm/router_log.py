import json
import os
from pathlib import Path

from litellm.integrations.custom_logger import CustomLogger

LOG = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "opencode-free-router" / "requetes.jsonl"


def _write(kwargs, start, end, ok):
    try:
        params = kwargs.get("litellm_params") or {}
        meta = params.get("metadata") or {}
        row = {
            "heure": start.strftime("%Y-%m-%d %H:%M:%S"),
            "groupe": kwargs.get("model") or meta.get("model_group"),
            "fournisseur": (kwargs.get("model_info") or {}).get("id") and params.get("model") or kwargs.get("model"),
            "api_base": params.get("api_base"),
            "duree_s": round((end - start).total_seconds(), 1),
            "ok": ok,
        }
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


class RouterLog(CustomLogger):
    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        _write(kwargs, start_time, end_time, True)

    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
        _write(kwargs, start_time, end_time, False)


proxy_handler_instance = RouterLog()
