"""Isolated worker: no dataset, gold, solver or evaluator imports. No SDK dependency."""
import base64
import fcntl
import hashlib
import io
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from PIL import Image
from .contract import canonical, digest, question, schema, strict_json, validate_output


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w") as stream:
        stream.write(canonical(value) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def config_valid(c, billing=False):
    keys = {"provider", "endpoint", "model", "credential_env", "settings", "image_detail", "timeout_seconds", "max_attempts",
            "max_spend_usd", "reserve_per_attempt_usd", "reserve_basis"}
    if set(c) != keys or c["provider"] not in ("openai", "openai_compatible"):
        raise ValueError("Unknown provider configuration fields")
    url = urllib.parse.urlsplit(c["endpoint"])
    if url.username or url.password or url.query or url.fragment or not url.hostname:
        raise ValueError("Endpoint must not contain secrets/query/fragment")
    if url.scheme != "https" and not (url.scheme == "http" and url.hostname in ("127.0.0.1", "localhost", "::1")):
        raise ValueError("Use HTTPS or an explicit loopback endpoint")
    if c["provider"] == "openai" and c["endpoint"] != "https://api.openai.com/v1/chat/completions":
        raise ValueError("OpenAI adapter requires the official endpoint")
    if not isinstance(c["model"], str) or not c["model"].strip():
        raise ValueError("An exact model identifier is required")
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", c["credential_env"]):
        raise ValueError("Invalid credential environment variable name")
    allowed = {"temperature", "max_completion_tokens", "reasoning_effort", "seed", "top_p"}
    if not isinstance(c["settings"], dict) or set(c["settings"])-allowed:
        raise ValueError("Only generation settings are permitted")
    if type(c["settings"].get("max_completion_tokens")) is not int or c["settings"]["max_completion_tokens"] < 1:
        raise ValueError("A positive output token ceiling is required")
    if c["image_detail"] not in ("low", "high", "auto") or type(c["max_attempts"]) is not int or not 1 <= c["max_attempts"] <= 3:
        raise ValueError("Invalid image/retry setting")
    if type(c["timeout_seconds"]) not in (int, float) or not 0 < c["timeout_seconds"] <= 300:
        raise ValueError("Invalid timeout")
    if billing:
        for k in ("max_spend_usd", "reserve_per_attempt_usd"):
            if type(c[k]) not in (int, float) or not math.isfinite(c[k]) or c[k] <= 0:
                raise ValueError("Positive finite spending limit and verified per-attempt reservation required")
        if not isinstance(c["reserve_basis"], str) or not c["reserve_basis"].strip():
            raise ValueError("Document the conservative reservation basis before inference")


def load_bundle(worker):
    bundle = strict_json((worker/"bundle.json").read_text())
    if set(bundle) != {"format", "config", "prompts", "requests", "images", "freeze"} or bundle["format"] != "topodelta-phase2a-worker-v1":
        raise ValueError("Unknown worker bundle fields")
    config_valid(bundle["config"])
    if set(bundle["prompts"]) != {"common", "direct", "parse"}:
        raise ValueError("Unknown prompt fields")
    for k,v in bundle["prompts"].items():
        if hashlib.sha256(v.encode()).hexdigest() != bundle["freeze"]["prompt_hashes"][k]:
            raise ValueError("Prompt hash mismatch")
    seen = set()
    for row in bundle["requests"]:
        if set(row) != {"id", "case_id", "baseline", "protocol", "question", "images"}:
            raise ValueError("Worker request fields are not allowlisted")
        if row["id"] in seen or row["id"] != digest([row["baseline"], row["protocol"], row["case_id"]]):
            raise ValueError("Duplicate or invalid request identity")
        seen.add(row["id"])
        question(row["question"])
        schema(row["baseline"], row["protocol"], row["question"])
        if len(row["images"]) != (1 if row["protocol"] == "single" else 2):
            raise ValueError("Incorrect number of images")
        for sha in row["images"]:
            if not re.fullmatch(r"[a-f0-9]{64}", sha) or sha not in bundle["images"]:
                raise ValueError("Invalid image hash")
    if digest([schema(r["baseline"], r["protocol"], r["question"]) for r in bundle["requests"]]) != bundle["freeze"]["schemas_sha256"]:
        raise ValueError("Schema implementation differs from frozen bundle")
    for name, sha in bundle["freeze"].get("implementation_hashes", {}).items():
        if Path(name).name != name or hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest() != sha:
            raise ValueError("Implementation differs from frozen bundle; prepare a new version")
    return bundle


def payload(worker, bundle, row):
    """Construct by allowlist, never merge exported records into provider fields."""
    c = bundle["config"]
    content = [{"type": "text", "text": "Question: " + row["question"]}]
    for letter, sha in zip("AB", row["images"]):
        data = (worker/f"images/{sha}.png").read_bytes()
        if hashlib.sha256(data).hexdigest() != sha:
            raise ValueError("Input image hash mismatch")
        with Image.open(io.BytesIO(data)) as im:
            if im.format != "PNG" or im.info:
                raise ValueError("Only metadata-free PNG inputs are allowed")
        content.extend([{"type": "text", "text": "Image " + letter},
                        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(data).decode(), "detail": c["image_detail"]}}])
    return {"model": c["model"], **c["settings"], "messages": [
        {"role": "system", "content": bundle["prompts"]["common"] + "\n" + bundle["prompts"][row["baseline"]]},
        {"role": "user", "content": content}],
        "response_format": {"type": "json_schema", "json_schema": {"name": "diagram_response", "strict": True,
                             "schema": schema(row["baseline"], row["protocol"], row["question"])}}}


def cache_key(config, body):
    # Includes ordered PNG bytes, all prompts/settings/schema/model, and endpoint identity.
    return digest({"provider": config["provider"], "endpoint": config["endpoint"], "body": body})


class TransientError(Exception):
    def __init__(self, status, raw):
        super().__init__(f"Transient HTTP {status}")
        self.status, self.raw = status, raw


class PermanentError(Exception):
    def __init__(self, status, raw):
        super().__init__(f"HTTP {status}")
        self.status, self.raw = status, raw


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ChatCompletionsAdapter:
    def __init__(self, config):
        self.config = config
        self.secret = os.environ.get(config["credential_env"], "")
        local = urllib.parse.urlsplit(config["endpoint"]).hostname in ("127.0.0.1", "localhost", "::1")
        if not self.secret and not local:
            raise ValueError("Provider credential is unavailable in the configured environment variable")

    def send(self, body, attempt_id):
        headers = {"Content-Type": "application/json", "X-Client-Request-Id": attempt_id}
        if self.secret:
            headers["Authorization"] = "Bearer " + self.secret
        req = urllib.request.Request(self.config["endpoint"], data=canonical(body).encode(), headers=headers, method="POST")
        try:
            # Reject redirects to avoid sending credentials or images to another host.
            with urllib.request.build_opener(NoRedirect()).open(req, timeout=self.config["timeout_seconds"]) as response:
                data = response.read().decode("utf-8", errors="replace")
                try:
                    return strict_json(data)
                except ValueError:
                    return {"unparsed_body": data}
        except urllib.error.HTTPError as exc:
            raw = {"http_status": exc.code, "body": exc.read().decode("utf-8", errors="replace")}
            kind = TransientError if exc.code in (408, 429) or 500 <= exc.code <= 599 else PermanentError
            raise kind(exc.code, raw) from None
        # Transport errors are ambiguous; the runner records terminal uncertainty, not an automatic retry.


class OpenAIAdapter(ChatCompletionsAdapter):
    pass


class OpenAICompatibleAdapter(ChatCompletionsAdapter):
    """Explicit endpoint must support images and strict Chat Completions JSON Schema."""


def redact(value, secret):
    sensitive = {"authorization", "api_key", "apikey", "access_token", "refresh_token", "password", "secret"}
    if isinstance(value, dict):
        return {k: "[REDACTED]" if k.lower() in sensitive else redact(v, secret) for k,v in value.items()}
    if isinstance(value, list):
        return [redact(v, secret) for v in value]
    if isinstance(value, str) and secret:
        return value.replace(secret, "[REDACTED]")
    return value


def extract(raw, row):
    try:
        choice = raw["choices"][0]
        if choice.get("finish_reason") != "stop" or choice["message"].get("refusal"):
            raise ValueError("Refused or truncated response")
        value = strict_json(choice["message"]["content"])
        return validate_output(value, row["baseline"], row["protocol"], row["question"])
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("Malformed provider response envelope") from exc


def run(worker, output, authorized=False, adapter=None, sleep=time.sleep):
    mode_file = Path(__file__).resolve().parents[2]/"configs/project_mode.json"
    if adapter is None and mode_file.exists() and strict_json(mode_file.read_text()).get("mode") == "dataset_only":
        raise ValueError("Model inference is disabled: dataset-only mode; Phase 2B was cancelled")
    bundle = load_bundle(worker)
    if not authorized and adapter is None:
        raise ValueError("No provider inference authorized; use --authorize-provider only after explicit approval")
    c = bundle["config"]
    config_valid(c, billing=True)
    if output.resolve().is_relative_to(worker.resolve()):
        raise ValueError("Keep outputs/cache separate from the frozen input bundle")
    output.mkdir(parents=True, exist_ok=True)
    with (output/"run.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Another runner owns this output") from None
        state_path = output/"checkpoint.json"
        identity = digest(bundle)
        mocked = adapter is not None
        state = strict_json(state_path.read_text()) if state_path.exists() else {
            "bundle_sha256": identity, "mock_only": mocked, "reserved_usd": 0.0, "requests": {}, "attempts": []}
        if state["bundle_sha256"] != identity or state["mock_only"] != mocked:
            raise ValueError("Resume configuration/input/mock identity differs; use a new run directory")
        if state.get("halt_reason") == "provider_cost_exceeded_reservation":
            raise ValueError("Reservation was exceeded; this run cannot dispatch more calls")
        # Persist recovery before any dispatch; ambiguous requests are never silently reissued.
        for ident, result in state["requests"].items():
            if result["status"] == "inflight":
                result["status"] = "uncertain"
        atomic(state_path, state)
        backend = adapter or {"openai": OpenAIAdapter, "openai_compatible": OpenAICompatibleAdapter}[c["provider"]](c)
        secret = getattr(backend, "secret", "")
        for row in bundle["requests"]:
            ident = row["id"]
            if ident in state["requests"]:
                continue
            body = payload(worker, bundle, row)
            key = cache_key(c, body)
            cache = output/f"cache/{key}.json"
            if cache.exists():
                saved = strict_json(cache.read_text())
                if saved["cache_key"] != key:
                    raise ValueError("Cache identity mismatch")
                validate_output(saved["output"], row["baseline"], row["protocol"], row["question"])
                state["requests"][ident] = {"status": "success", "output": saved["output"], "cache_hit": True, "cache_key": key}
                atomic(state_path, state)
                continue
            for attempt in range(c["max_attempts"]):
                reserve = c["reserve_per_attempt_usd"]
                if state["reserved_usd"] + reserve > c["max_spend_usd"] + 1e-12:
                    # Unattempted cases stay missing in scores. Resume only with the same contract; no hidden budget increase.
                    state["halt_reason"] = "budget_exhausted"
                    atomic(state_path, state)
                    return state
                attempt_id = digest([identity, ident, attempt])
                state["reserved_usd"] += reserve
                entry = {"request_id": ident, "attempt_id": attempt_id, "attempt": attempt + 1, "reserved_usd": reserve,
                         "status": "inflight", "latency_seconds": None, "usage": None, "provider_cost_usd": None}
                state["attempts"].append(entry)
                state["requests"][ident] = {"status": "inflight", "cache_key": key, "attempt_id": attempt_id}
                atomic(state_path, state)
                started = time.monotonic()
                raw, retry = None, False
                try:
                    raw = backend.send(body, attempt_id)
                    entry["usage"] = redact(raw.get("usage"), secret) if isinstance(raw, dict) else None
                    # Standard OpenAI does not return invoice costs; compatible adapters may explicitly do so.
                    cost = raw.get("cost_usd") if isinstance(raw, dict) else None
                    if type(cost) in (int, float) and math.isfinite(cost) and cost >= 0:
                        entry["provider_cost_usd"] = cost
                    try:
                        value = extract(raw, row)
                        result = {"status": "success", "output": value, "cache_hit": False, "cache_key": key}
                        atomic(cache, {"cache_key": key, "output": redact(value, secret), "source_attempt": attempt_id})
                    except (ValueError, TypeError) as exc:
                        result = {"status": "invalid", "error": type(exc).__name__, "cache_key": key}
                except TransientError as exc:
                    raw = exc.raw
                    retry = attempt + 1 < c["max_attempts"]
                    result = {"status": "failed", "http_status": exc.status, "cache_key": key}
                except PermanentError as exc:
                    raw = exc.raw
                    result = {"status": "failed", "http_status": exc.status, "cache_key": key}
                except (OSError, TimeoutError) as exc:
                    result = {"status": "uncertain", "error": type(exc).__name__, "cache_key": key}
                finally:
                    entry["latency_seconds"] = time.monotonic() - started
                if raw is not None:
                    atomic(output/f"raw/{attempt_id}.json", redact(raw, secret))
                entry["status"] = result["status"]
                state["requests"][ident] = redact(result, secret)
                atomic(state_path, state)
                if entry["provider_cost_usd"] is not None and entry["provider_cost_usd"] > reserve:
                    state["halt_reason"] = "provider_cost_exceeded_reservation"
                    atomic(state_path, state)
                    raise RuntimeError("Provider cost exceeded the configured reservation; stopped before further dispatch")
                if not retry:
                    break
                sleep(min(2 ** attempt, 4))
        state["halt_reason"] = "all_requests_terminal"
        atomic(state_path, state)
        return state
