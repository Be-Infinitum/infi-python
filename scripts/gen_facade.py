"""Generates src/beinfi/_generated/resources.py from the SDK contract (ADR 0055, D2/D3).

Standard library only. Mirrors scripts/gen-facade.ts of the TypeScript SDK: the same
validation rules and the same messages. Besides `resources.py`, it works out which
pydantic models the operations need (parameters, bodies and inline responses of the
contract) and builds the document that datamodel-code-generator turns into
`models.py` (see `scripts/generate.py`).

Usage (normally via `make generate`): python scripts/gen_facade.py
"""

from __future__ import annotations

import json
import keyword
import re
import sys
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

METHODS = ("get", "put", "post", "delete", "patch", "options", "head")
NAME = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")
# Headers the transport handles (they become idempotency_key, if_match and channel).
TRANSPORT_HEADERS = {"idempotency-key", "if-match", "x-infi-channel"}

ROOT = Path(__file__).resolve().parent.parent
CONTRACT = ROOT / "api" / "openapi.sdk.json"
RESOURCES_OUT = ROOT / "src" / "beinfi" / "_generated" / "resources.py"


@dataclass(frozen=True)
class Op:
    operation_id: str
    tag: str
    action: str
    method: str
    path: str
    scope: str
    summary: str = ""


class ContractError(Exception):
    """Invalid contract; the message says where."""


def pascal(s: str) -> str:
    return "".join(w[:1].upper() + w[1:] for w in s.split("_"))


def collect_ops(doc: Any) -> List[Op]:
    """Validates the contract and returns the operations. Raises ContractError with a clear message."""
    ops: List[Op] = []
    seen = set()
    paths = (doc or {}).get("paths") or {}
    for path, item in paths.items():
        for method in METHODS:
            op = (item or {}).get(method)
            if not op:
                continue
            where = f"{method.upper()} {path}"
            op_id = op.get("operationId")
            if not isinstance(op_id, str) or not op_id:
                raise ContractError(f"{where}: missing operationId")
            tags = op.get("tags") or []
            if len(tags) != 1 or not isinstance(tags[0], str):
                raise ContractError(f"{where} ({op_id}): needs exactly one tag, has {len(tags)}")
            tag = tags[0]
            if not NAME.match(tag):
                raise ContractError(f'{where}: tag "{tag}" is not snake_case')
            prefix = f"{tag}_"
            action = op_id[len(prefix):] if op_id.startswith(prefix) else ""
            if not action or not NAME.match(action):
                raise ContractError(f'{where}: operationId "{op_id}" must be "{tag}_<snake_case action>"')
            # Python-specific: the action becomes a method name, the tag becomes an attribute name.
            if keyword.iskeyword(action) or keyword.iskeyword(tag):
                raise ContractError(f'{where}: "{op_id}" uses a Python reserved word')
            if op_id in seen:
                raise ContractError(f'{where}: duplicate operationId "{op_id}"')
            seen.add(op_id)
            if op.get("x-infi-facade") is not True:
                raise ContractError(f"{where} ({op_id}): missing x-infi-facade: true")
            scope = op.get("x-infi-scope")
            if not isinstance(scope, str) or not scope:
                raise ContractError(f"{where} ({op_id}): missing x-infi-scope")
            ops.append(Op(op_id, tag, action, method.upper(), path, scope, str(op.get("summary") or "")))
    if not ops:
        raise ContractError("contract has no operations")
    return ops


# --------------------------------------------------------------------------- types


def _deref(doc: Any, node: Any) -> Any:
    """Follows local `$ref`s (#/components/...) to a concrete node."""
    for _ in range(32):
        if not (isinstance(node, dict) and "$ref" in node):
            return node
        ref = node["$ref"]
        if not ref.startswith("#/"):
            raise ContractError(f"non-local $ref: {ref}")
        cur: Any = doc
        for part in ref[2:].split("/"):
            cur = cur[part.replace("~1", "/").replace("~0", "~")]
        node = cur
    raise ContractError("circular $ref")


@dataclass
class Part:
    """A group of parameters (path, query or headers) of the operation."""

    model: str
    required: bool


@dataclass
class Sig:
    op: Op
    path: Optional[Part] = None
    query: Optional[Part] = None
    headers: Optional[Part] = None
    body: Optional[str] = None
    body_required: bool = False
    # 2xx status -> type expression (None = no body)
    responses: Dict[int, Optional[str]] = field(default_factory=dict)


class Planner:
    """Accumulates the synthesized schemas (parameters, bodies and inline responses)."""

    def __init__(self, doc: Any) -> None:
        self.doc = doc
        self.existing = set((doc.get("components") or {}).get("schemas") or {})
        self.extra: Dict[str, Any] = {}

    def synth(self, name: str, schema: Any) -> str:
        if name in self.existing or name in self.extra:
            raise ContractError(f"synthesized schema {name} collides with a contract name")
        self.extra[name] = deepcopy(schema)
        return f"m.{name}"

    def expr(self, schema: Any, name: str) -> str:
        """Type expression (with the `m.` prefix) for a body or response schema."""
        if "$ref" in schema:
            ref = schema["$ref"]
            prefix = "#/components/schemas/"
            if not ref.startswith(prefix):
                raise ContractError(f"unexpected schema $ref: {ref}")
            return f"m.{ref[len(prefix):]}"
        for key in ("oneOf", "anyOf"):
            if key in schema and "type" not in schema and "properties" not in schema:
                members = [self.expr(s, f"{name}Variant{i}") for i, s in enumerate(schema[key], 1)]
                uniq = list(dict.fromkeys(members))
                return uniq[0] if len(uniq) == 1 else f"Union[{', '.join(uniq)}]"
        return self.synth(name, schema)

    def input_expr(self, schema: Any, name: str) -> str:
        """Like `expr`, for bodies: when the schema is a union, it also accepts each variant.

        datamodel-codegen wraps the union in a RootModel (`Name`) and names the
        variants `Name1`, `Name2`... (the contract uses `oneOf: [{required: [a]}, {required: [b]}]`
        for "a or b"); whoever builds the body by hand uses the variant, which has the fields.
        """
        top = self.expr(schema, name)
        if "$ref" in schema:
            target = self.doc["components"]["schemas"][schema["$ref"].rsplit("/", 1)[1]]
        else:
            target = schema
        for key in ("oneOf", "anyOf"):
            if key in target and ("properties" in target or "type" in target):
                variants = [f"{top}{i}" for i, _ in enumerate(target[key], 1)]
                return f"Union[{', '.join([top, *variants])}]"
        return top

    def params(self, op_id: str, params: List[Any]) -> Tuple[Optional[Part], Optional[Part], Optional[Part]]:
        parts: Dict[str, Optional[Part]] = {"path": None, "query": None, "header": None}
        suffix = {"path": "Path", "query": "Query", "header": "Headers"}
        for where in ("path", "query", "header"):
            props: Dict[str, Any] = {}
            required: List[str] = []
            for p in params:
                if p["in"] != where:
                    continue
                if where == "header" and p["name"].lower() in TRANSPORT_HEADERS:
                    continue
                schema = deepcopy(p.get("schema") or {})
                if p.get("description") and "$ref" not in schema:
                    schema.setdefault("description", p["description"])
                props[p["name"]] = schema
                if p.get("required") or where == "path":
                    required.append(p["name"])
            if not props:
                continue
            model = self.synth(f"{pascal(op_id)}{suffix[where]}", {"type": "object", "properties": props, "required": required})
            parts[where] = Part(model, bool(required))
        return parts["path"], parts["query"], parts["header"]


def plan_signatures(doc: Any, ops: List[Op]) -> Tuple[List[Sig], Dict[str, Any]]:
    planner = Planner(doc)
    sigs: List[Sig] = []
    for op in ops:
        item = doc["paths"][op.path]
        node = item[op.method.lower()]
        merged: Dict[Tuple[str, str], Any] = {}
        for p in list(item.get("parameters") or []) + list(node.get("parameters") or []):
            p = _deref(doc, p)
            merged[(p["in"], p["name"])] = p
        sig = Sig(op)
        sig.path, sig.query, sig.headers = planner.params(op.operation_id, list(merged.values()))
        rb = node.get("requestBody")
        if rb is not None:
            rb = _deref(doc, rb)
            schema = (rb.get("content") or {}).get("application/json", {}).get("schema")
            if schema is not None:
                sig.body = planner.input_expr(schema, f"{pascal(op.operation_id)}Body")
                sig.body_required = bool(rb.get("required"))
        twoxx = [c for c in node.get("responses", {}) if re.fullmatch(r"2\d\d", c)]
        for code in sorted(twoxx):
            r = _deref(doc, node["responses"][code])
            schema = (r.get("content") or {}).get("application/json", {}).get("schema")
            if schema is None:
                sig.responses[int(code)] = None
            else:
                suffix = "Response" if len(twoxx) == 1 else f"Response{code}"
                sig.responses[int(code)] = planner.expr(schema, f"{pascal(op.operation_id)}{suffix}")
        sigs.append(sig)
    return sigs, planner.extra


def models_input(doc: Any, extra: Dict[str, Any]) -> Dict[str, Any]:
    """Minimal document for datamodel-code-generator: the contract schemas plus the synthesized ones."""
    schemas = deepcopy((doc.get("components") or {}).get("schemas") or {})
    schemas.update(extra)
    leftovers = set(re.findall(r"#/(?!components/schemas/)[A-Za-z/]+", json.dumps(schemas)))
    if leftovers:
        raise ContractError(f"schemas reference something outside components/schemas: {sorted(leftovers)}")
    return {
        "openapi": "3.1.0",
        "info": {"title": "Infi SDK models", "version": str((doc.get("info") or {}).get("version", "0"))},
        "paths": {},
        "components": {"schemas": dict(sorted(schemas.items()))},
    }


# --------------------------------------------------------------------------- generation


def _arg_type(model: str, optional: bool = False) -> str:
    inner = model[len("Union[") : -1] if model.startswith("Union[") else model
    t = f"Union[{inner}, Mapping[str, Any]]"
    return f"Optional[{t}] = None" if optional else t


def _result_type(sig: Sig) -> str:
    types = [t for t in dict.fromkeys(sig.responses.values())]
    concrete = [t for t in types if t is not None]
    if not concrete:
        return "None"
    inner = concrete[0] if len(concrete) == 1 else f"Union[{', '.join(concrete)}]"
    # Nested Union[...] is flattened by typing; Optional only appears if some 2xx has no body.
    return f"Optional[{inner}]" if None in types else inner


def _doc(op: Op) -> str:
    summary = op.summary.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
    head = f"{op.method} {op.path} (scope {op.scope})"
    return f'        """{head}\n\n        {summary}\n        """' if summary else f'        """{head}"""'


def _method(sig: Sig) -> str:
    op = sig.op
    args: List[str] = []
    if sig.path:
        args.append(f"path: {_arg_type(sig.path.model)}")
    if sig.query:
        args.append(f"query: {_arg_type(sig.query.model, not sig.query.required)}")
    if sig.headers:
        args.append(f"headers: {_arg_type(sig.headers.model, not sig.headers.required)}")
    if sig.body:
        args.append(f"body: {_arg_type(sig.body, not sig.body_required)}")
    args += ["idempotency_key: Optional[str] = None", "if_match: Optional[str] = None", "channel: Optional[Channel] = None"]
    # Required first, just for readability: all of them are keyword-only.
    args.sort(key=lambda a: " = " in a)
    result = _result_type(sig)
    concrete = {k: v for k, v in sig.responses.items() if v is not None}
    resp_map = "{" + ", ".join(f"{k}: {v}" for k, v in concrete.items()) + "}" if concrete else "None"
    call = (
        f"self._t.request(\n"
        f'            Request(\n'
        f'                method="{op.method}",\n'
        f'                path="{op.path}",\n'
        f"                path_params={'path' if sig.path else 'None'},\n"
        f"                query={'query' if sig.query else 'None'},\n"
        f"                headers={'headers' if sig.headers else 'None'},\n"
        f"                body={'body' if sig.body else 'None'},\n"
        f"                idempotency_key=idempotency_key,\n"
        f"                if_match=if_match,\n"
        f"                channel=channel,\n"
        f"            ),\n"
        f"            responses={resp_map},\n"
        f"        )"
    )
    sig_lines = "\n".join(f"        {a}," for a in args)
    body = f"        return cast(\"{result}\", {call})" if result != "None" else f"        {call}"
    return f"    def {op.action}(\n        self,\n        *,\n{sig_lines}\n    ) -> {result}:\n{_doc(op)}\n{body}\n"


def generate(ops: List[Op], sigs: Optional[List[Sig]] = None) -> str:
    """Code of resources.py. Without `sigs` (e.g. generator tests) the signatures stay generic."""
    if sigs is None:
        sigs = [Sig(o) for o in ops]
    tags = list(dict.fromkeys(o.tag for o in ops))
    out: List[str] = [
        "# GENERATED by scripts/gen_facade.py from api/openapi.sdk.json. DO NOT EDIT.\n"
        "# To change something, change the contract (in the monorepo) and run `make sync-contract`.\n"
        '"""One resource per contract tag, one method per operation (`infi.<tag>.<action>`)."""\n'
        "\n"
        "from typing import Any, Mapping, Optional, Union, cast\n"
        "\n"
        "from .._http import Channel, Request, Transport\n"
        "from . import models as m\n"
    ]
    for tag in tags:
        methods = "\n".join(_method(s) for s in sigs if s.op.tag == tag)
        out.append(
            f"\nclass {pascal(tag)}Resource:\n"
            f"    def __init__(self, t: Transport) -> None:\n"
            f"        self._t = t\n\n{methods}"
        )
    attrs = "\n".join(f"        self.{t} = {pascal(t)}Resource(t)" for t in tags)
    out.append(f"\nclass Resources:\n    def __init__(self, t: Transport) -> None:\n{attrs}\n")
    entries = []
    for o in ops:
        entry = {
            "operation_id": o.operation_id,
            "tag": o.tag,
            "property": o.tag,
            "method": o.action,
            "http_method": o.method,
            "path": o.path,
            "scope": o.scope,
        }
        entries.append(f"    {entry!r},")
    out.append("\nOPERATIONS = [\n" + "\n".join(entries) + "\n]\n")
    return "\n".join(out)


def main() -> int:
    try:
        doc = json.loads(CONTRACT.read_text(encoding="utf-8"))
        ops = collect_ops(doc)
        sigs, _ = plan_signatures(doc, ops)
        RESOURCES_OUT.parent.mkdir(parents=True, exist_ok=True)
        RESOURCES_OUT.write_text(generate(ops, sigs), encoding="utf-8")
    except ContractError as e:
        print(f"gen_facade: {e}", file=sys.stderr)
        return 1
    print(f"resources.py: {len(ops)} operations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
