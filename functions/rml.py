"""Mapping execution, DS retrieval and DS validation — via the OpenDataGermany APIs or locally.

Two modes, chosen by `mode` in config.yaml:

- ``api`` (default): RCK executes the mapping, VER validates (`/rdf/verify-ds`), DVS serves DSs.
  Needs OpenDataGermany / Onlim API keys.
- ``local``: no API keys. The mapping runs on open-source RocketRML + yarrrml-parser
  (``local_engine/run.js``, Node.js), DSs come from the public semantify.it endpoint, and
  verification is limited to a standard SHACL check against the public DS
  (``functions/local_validate.py``) — it is not VER.

Every function keeps the same signature and return conventions in both modes.

Must be initialised from a config dict before use:

    import yaml
    from functions import rml

    with open("config.yaml") as f:
        config = yaml.safe_load(f)
    rml.init(config)

In ``api`` mode the config dict must contain an "api" block with dvs_url, rck_url, ver_url,
dvs_api_key (for DVS), and prod_api_key (for RCK and VER) keys, matching the structure of
config.yaml.example. In ``local`` mode the "api" block is ignored.
"""

import json
import os
import subprocess

import requests

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOCAL_ENGINE = os.path.join(_HERE, "local_engine", "run.js")

_MODE: str = ""
_DVS_URL: str = ""
_RCK_URL: str = ""
_VER_URL: str = ""
_DVS_API_KEY: str = ""
_PROD_API_KEY: str = ""


def init(config: dict) -> None:
    """Initialise the module from a config dict loaded from config.yaml."""
    global _MODE, _DVS_URL, _RCK_URL, _VER_URL, _DVS_API_KEY, _PROD_API_KEY
    _MODE = (config.get("mode") or "api").strip().lower()
    if _MODE not in ("api", "local"):
        raise ValueError(f"config mode must be 'api' or 'local', got {_MODE!r}")
    if _MODE == "local":
        if not os.path.isdir(os.path.join(_HERE, "local_engine", "node_modules")):
            raise RuntimeError("local mode: run `npm install --prefix local_engine` first")
        return
    api = config["api"]
    _DVS_URL = api["dvs_url"]
    _RCK_URL = api["rck_url"]
    _VER_URL = api["ver_url"]
    _DVS_API_KEY = api["dvs_api_key"]
    _PROD_API_KEY = api["prod_api_key"]


def mode() -> str:
    """The active mode: "api" or "local"."""
    _require_init()
    return _MODE


def _require_init() -> None:
    if not _MODE:
        raise RuntimeError("rml module not initialised — call rml.init(config) first")


def _map_local(json_data: str, yarrrml_mapping: str, dataset_id: str, functions: dict | None) -> str:
    request = {"mapping": yarrrml_mapping, "inputs": {dataset_id: json_data}}
    if functions is not None:
        request["functions"] = functions
    try:
        proc = subprocess.run(["node", _LOCAL_ENGINE], input=json.dumps(request),
                              capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"RCK API local engine error: {e}"
    if proc.returncode != 0:
        return f"RCK API local engine error: {proc.stderr.strip()}"
    return proc.stdout


def map_json_to_rdf(
    json_data: str,
    yarrrml_mapping: str,
    dataset_id: str = "input",
    functions: dict | None = None,
) -> str:
    """Execute a YARRRML mapping against JSON input data via the RCK API.

    Returns a JSON-LD string on success, or an error message starting with
    "RCK API" on failure. In local mode the same result comes from RocketRML run locally.
    """
    _require_init()
    if _MODE == "local":
        return _map_local(json_data, yarrrml_mapping, dataset_id, functions)
    dataset_entry = {"value": json_data, "type": "json", "id": dataset_id}
    mapping_config = {"toRDF": False, "replace": True, "ignoreEmptyStrings": True}
    if functions is not None:
        mapping_config["functions"] = functions

    payload = {
        "mappingFile": yarrrml_mapping,
        "mappingFileType": "yarrrml",
        "mappingConfig": mapping_config,
        "testDataSet": [dataset_entry],
        "dataSet": [dataset_entry],
    }
    headers = {
        "x-api-key": _PROD_API_KEY,
        "content-type": "application/json",
        "accept": "application/json",
    }

    try:
        resp = requests.post(_RCK_URL + "map", headers=headers, json=payload)
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        return f"RCK API HTTP error: {e.response.text}"
    except requests.exceptions.RequestException as e:
        return f"RCK API request error: {e}"

    return json.dumps(resp.json(), indent=4)


def verify_rdf(rdf_data: str) -> str:
    """Validate a JSON-LD document against a Domain Specification via the VER API.

    Returns "Verification successful." on success, or an error description on failure.
    Not available in local mode — use verify_rdf_ds().
    """
    _require_init()
    if _MODE == "local":
        return "VER API not available in local mode — use verify_rdf_ds()"
    headers = {
        "x-api-key": _PROD_API_KEY,
        "content-type": "application/json",
        "accept": "application/json",
    }
    payload = {"rdf": rdf_data, "contentType": "application/ld+json"}

    try:
        resp = requests.post(_VER_URL + "rdf/verify", headers=headers, json=payload)
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        return f"VER API HTTP error: {e.response.text}"
    except requests.exceptions.RequestException as e:
        return f"VER API request error: {e}"

    result = resp.json()
    if result.get("success"):
        return "Verification successful."
    return result.get("error", str(result))


def verify_rdf_ds(rdf_data: str, include_pointers: bool = True) -> dict:
    """Validate JSON-LD against its Domain Specification via VER /rdf/verify-ds.

    Unlike verify_rdf() (POST /rdf/verify), this returns the FULL per-entity DS
    verification report - the same structure the TS import performs - including
    errorCode / name / dsPath / dataPath for every violation.

    IMPORTANT: /rdf/verify reports success for documents this endpoint rejects
    (e.g. a bare "http://" value against xsd:anyURI). Prefer this function.

    Returns the parsed report dict, or {"__error": "..."} on transport failure.

    In local mode the report comes from a standard SHACL check against the public DS
    (functions/local_validate.py, limited — not VER) and carries "engine": "local-shacl".
    """
    _require_init()
    if _MODE == "local":
        from functions.local_validate import verify_rdf_ds_local
        return verify_rdf_ds_local(rdf_data)
    headers = {
        "x-api-key": _PROD_API_KEY,
        "content-type": "application/json",
        "accept": "application/json",
    }
    payload = {
        "rdf": rdf_data,
        "contentType": "application/ld+json",
        "config": {"includeErrorPointers": include_pointers},
    }
    try:
        resp = requests.post(_VER_URL + "rdf/verify-ds", headers=headers, json=payload)
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        return {"__error": f"VER API HTTP error: {e.response.text}"}
    except requests.exceptions.RequestException as e:
        return {"__error": f"VER API request error: {e}"}
    return resp.json()


def list_domain_specifications(ds_list_url: str) -> str:
    """Fetch the list of available Domain Specifications from a given URL.

    Returns the list as a JSON string on success, or an error message starting
    with "DS list" on failure.
    """
    headers = {"accept": "application/json"}

    try:
        resp = requests.get(ds_list_url, headers=headers)
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        return f"DS list HTTP error: {e.response.text}"
    except requests.exceptions.RequestException as e:
        return f"DS list request error: {e}"

    return json.dumps(resp.json(), indent=4)


def get_domain_specification(org_id: str, ds_id: str, populate: bool = True) -> str:
    """Fetch a full Domain Specification from DVS.

    Returns the DS as a JSON string on success, or an error message starting
    with "DVS API" on failure. In local mode the DS comes from the public semantify.it
    endpoint and org_id is ignored.
    """
    _require_init()
    if _MODE == "local":
        try:
            resp = requests.get(f"https://semantify.it/ds/{ds_id}",
                                params={"populate": "true" if populate else "false"},
                                headers={"accept": "application/json"}, timeout=60)
            resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            return f"DVS API (public semantify.it) HTTP error: {e.response.text}"
        except requests.exceptions.RequestException as e:
            return f"DVS API (public semantify.it) request error: {e}"
        # Same @graph as DVS; wrap it the way DVS does so callers read d["content"]["@graph"].
        return json.dumps({"id": ds_id, "iri": f"https://semantify.it/ds/{ds_id}",
                           "content": resp.json()}, indent=4)
    url = _DVS_URL + f"domain-specifications/{ds_id}?populate={'true' if populate else 'false'}"
    headers = {
        "x-api-key": _DVS_API_KEY,
        "accept": "application/json",
        "x-organization-id": org_id,
    }

    try:
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        return f"DVS API HTTP error: {e.response.text}"
    except requests.exceptions.RequestException as e:
        return f"DVS API request error: {e}"

    return json.dumps(resp.json(), indent=4)
