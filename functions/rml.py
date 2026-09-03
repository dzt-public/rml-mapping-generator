"""API wrapper functions for RCK, VER, and DVS services.

Must be initialised from a config dict before use:

    import yaml
    from functions import rml

    with open("config.yaml") as f:
        config = yaml.safe_load(f)
    rml.init(config)

The config dict must contain an "api" block with dvs_url, rck_url, ver_url,
dvs_api_key (for DVS), and prod_api_key (for RCK and VER) keys, matching
the structure of the rml-cli config.yaml.
"""

import json

import requests

_DVS_URL: str = ""
_RCK_URL: str = ""
_VER_URL: str = ""
_DVS_API_KEY: str = ""
_PROD_API_KEY: str = ""


def init(config: dict) -> None:
    """Initialise the module from a config dict loaded from config.yaml."""
    global _DVS_URL, _RCK_URL, _VER_URL, _DVS_API_KEY, _PROD_API_KEY
    api = config["api"]
    _DVS_URL = api["dvs_url"]
    _RCK_URL = api["rck_url"]
    _VER_URL = api["ver_url"]
    _DVS_API_KEY = api["dvs_api_key"]
    _PROD_API_KEY = api["prod_api_key"]


def _require_init() -> None:
    if not _PROD_API_KEY:
        raise RuntimeError("rml module not initialised — call rml.init(config) first")


def map_json_to_rdf(
    json_data: str,
    yarrrml_mapping: str,
    dataset_id: str = "input",
    functions: dict | None = None,
) -> str:
    """Execute a YARRRML mapping against JSON input data via the RCK API.

    Returns a JSON-LD string on success, or an error message starting with
    "RCK API" on failure.
    """
    _require_init()
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
    """
    _require_init()
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
    """
    _require_init()
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
    with "DVS API" on failure.
    """
    _require_init()
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
