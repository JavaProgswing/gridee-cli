from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any


DEFAULT_API_CLASS = "com.gridee.parking.data.api.ApiService"
SIMPLE_HTTP = re.compile(
    r"\.annotation runtime Lretrofit2/http/"
    r"(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS);\s+"
    r'value = "([^"]+)"',
    re.DOTALL,
)
GENERIC_HTTP = re.compile(
    r"\.annotation runtime Lretrofit2/http/HTTP;(?P<body>.*?)\.end annotation",
    re.DOTALL,
)
QUERY = re.compile(
    r"\.annotation runtime Lretrofit2/http/Query;\s+"
    r'value = "([^"]+)"',
    re.DOTALL,
)
MODEL_PREFIX = "com.gridee.parking.data.model."
PRIMITIVES = {
    "V": "null",
    "Z": "boolean",
    "B": "integer",
    "S": "integer",
    "I": "integer",
    "J": "integer",
    "F": "number",
    "D": "number",
    "C": "string",
}
JAVA_TYPES = {
    "java.lang.String": "string",
    "java.lang.Boolean": "boolean",
    "java.lang.Byte": "integer",
    "java.lang.Short": "integer",
    "java.lang.Integer": "integer",
    "java.lang.Long": "integer",
    "java.lang.Float": "number",
    "java.lang.Double": "number",
    "java.lang.Void": "null",
    "java.lang.Object": "object",
    "java.util.List": "List",
    "java.util.Map": "Map",
}


def parse_descriptor(value: str, position: int = 0) -> tuple[str, int]:
    while position < len(value) and value[position] in "+-":
        position += 1
    if position >= len(value):
        return "unknown", position
    marker = value[position]
    if marker in PRIMITIVES:
        return PRIMITIVES[marker], position + 1
    if marker == "[":
        item, end = parse_descriptor(value, position + 1)
        return f"List<{item}>", end
    if marker == "T":
        end = value.find(";", position)
        return value[position + 1 : end if end >= 0 else len(value)], (
            end + 1 if end >= 0 else len(value)
        )
    if marker != "L":
        return "unknown", position + 1

    cursor = position + 1
    while cursor < len(value) and value[cursor] not in "<;":
        cursor += 1
    class_name = value[position + 1 : cursor].replace("/", ".")
    display = JAVA_TYPES.get(class_name, class_name.rsplit(".", 1)[-1])
    arguments: list[str] = []
    if cursor < len(value) and value[cursor] == "<":
        cursor += 1
        while cursor < len(value) and value[cursor] != ">":
            argument, cursor = parse_descriptor(value, cursor)
            arguments.append(argument)
        cursor += 1
    if cursor < len(value) and value[cursor] == ";":
        cursor += 1
    if arguments:
        display += "<" + ", ".join(arguments) + ">"
    return display, cursor


def descriptor_parameters(descriptor: str) -> list[str]:
    if not descriptor.startswith("("):
        return []
    position = 1
    parameters: list[str] = []
    while position < len(descriptor) and descriptor[position] != ")":
        parsed, position = parse_descriptor(descriptor, position)
        parameters.append(parsed)
    return parameters


def signature_value(block: str) -> str:
    match = re.search(
        r"\.annotation system Ldalvik/annotation/Signature;(?P<body>.*?)\.end annotation",
        block,
        re.DOTALL,
    )
    return "".join(re.findall(r'"([^"]*)"', match.group("body"))) if match else ""


def response_type(block: str) -> str:
    signature = signature_value(block)
    marker = "Lretrofit2/Response<"
    start = signature.find(marker)
    if start < 0:
        return "unknown"
    parsed, _ = parse_descriptor(signature, start + len(marker))
    return parsed


def request_type(block: str) -> str:
    if "Lretrofit2/http/Body;" not in block:
        return "none"
    header = re.search(
        r"^\.method public abstract [^\s(]+(?P<descriptor>\([^)]*\)[^\s]+)",
        block,
        re.MULTILINE,
    )
    body_param = None
    for parameter in re.finditer(
        r"(?ms)^    \.param p(?P<index>\d+).*?^    \.end param$",
        block,
    ):
        if "Lretrofit2/http/Body;" in parameter.group(0):
            body_param = parameter
            break
    if not header or body_param is None:
        return "unknown"
    parameters = descriptor_parameters(header.group("descriptor"))
    index = int(body_param.group("index")) - 1
    return parameters[index] if 0 <= index < len(parameters) else "unknown"


def referenced_models(*types: str) -> list[str]:
    names: list[str] = []
    for value in types:
        for name in re.findall(r"\b[A-Z][A-Za-z0-9_$]*(?:Response|Request|Dto|Info|Policy|Booking|User|Wallet|Ticket|Ad|Lot|Spot)\b", value):
            names.append(MODEL_PREFIX + name)
    return list(dict.fromkeys(names))


def referenced_model_classes(text: str) -> list[str]:
    return list(
        dict.fromkeys(
            MODEL_PREFIX + name
            for name in re.findall(
                r"Lcom/gridee/parking/data/model/([A-Za-z0-9_$]+);",
                text,
            )
        )
    )


def parse_model_fields(text: str) -> list[dict[str, str]]:
    section_match = re.search(
        r"(?ms)^# instance fields\s*(?P<body>.*?)^# direct methods",
        text,
    )
    if not section_match:
        return []
    section = section_match.group("body")
    fields: list[dict[str, str]] = []
    for match in re.finditer(
        r"(?ms)^\.field [^\n]* (?P<name>[^\s:]+):(?P<descriptor>[^\s]+)"
        r"(?P<body>.*?)(?=^\.field |\Z)",
        section,
    ):
        name = match.group("name")
        if name.startswith("$") or name == "Companion":
            continue
        block = match.group(0)
        serialized = re.search(
            r'Lcom/google/gson/annotations/SerializedName;\s+value = "([^"]+)"',
            block,
        )
        field_signature = signature_value(block)
        type_name, _ = parse_descriptor(field_signature or match.group("descriptor"))
        fields.append({"name": serialized.group(1) if serialized else name, "type": type_name})
    return fields


def pattern_for_type(
    type_name: str,
    models: dict[str, Any],
    seen: frozenset[str] = frozenset(),
) -> Any:
    if type_name == "none":
        return None
    if type_name == "null":
        return None
    if type_name == "string":
        return "<string>"
    if type_name == "boolean":
        return "<boolean>"
    if type_name == "integer":
        return "<integer>"
    if type_name == "number":
        return "<number>"
    if type_name == "Date":
        return "<ISO-8601 datetime>"
    if type_name in {"JsonElement", "object"}:
        return "<dynamic JSON>"
    if type_name.startswith("List<") and type_name.endswith(">"):
        return [pattern_for_type(type_name[5:-1], models, seen)]
    if type_name.startswith("Map"):
        return {"<key>": "<value>"}
    for model, schema in models.items():
        if model.rsplit(".", 1)[-1] == type_name:
            if type_name in seen:
                return f"<{type_name}>"
            nested_seen = seen | {type_name}
            return {
                field["name"]: pattern_for_type(field["type"], models, nested_seen)
                for field in schema["fields"]
            }
    return f"<{type_name}>"


def find_apkanalyzer(explicit: str | None = None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    found = shutil.which("apkanalyzer") or shutil.which("apkanalyzer.bat")
    if found:
        candidates.append(Path(found))
    for variable in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        if os.getenv(variable):
            candidates.append(
                Path(os.environ[variable]) / "cmdline-tools" / "latest" / "bin" / "apkanalyzer.bat"
            )
    if os.getenv("LOCALAPPDATA"):
        candidates.append(
            Path(os.environ["LOCALAPPDATA"])
            / "Android"
            / "Sdk"
            / "cmdline-tools"
            / "latest"
            / "bin"
            / "apkanalyzer.bat"
        )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(
        "apkanalyzer was not found. Pass --apkanalyzer or install Android SDK command-line tools."
    )


def run_analyzer(tool: Path, *arguments: str) -> str:
    result = subprocess.run(
        [str(tool), *arguments],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"apkanalyzer {' '.join(arguments[:2])} failed: {detail}")
    return result.stdout.strip()


def parse_api_service(text: str, source_class: str = DEFAULT_API_CLASS) -> list[dict[str, Any]]:
    endpoints: list[dict[str, Any]] = []
    for match in re.finditer(
        r"(?ms)^\.method public abstract (?P<name>[^\s(]+).*?^\.end method$",
        text,
    ):
        block = match.group(0)
        simple = SIMPLE_HTTP.search(block)
        method: str | None = None
        route: str | None = None
        if simple:
            method, route = simple.groups()
        else:
            generic = GENERIC_HTTP.search(block)
            if generic:
                annotation = generic.group("body")
                method_match = re.search(r'method = "([^"]+)"', annotation)
                route_match = re.search(r'path = "([^"]+)"', annotation)
                if method_match and route_match:
                    method, route = method_match.group(1), route_match.group(1)
        if not method or not route:
            continue
        request = request_type(block)
        response = response_type(block)
        endpoints.append(
            {
                "method": method.upper(),
                "route": "/" + route.lstrip("/"),
                "function": match.group("name"),
                "query": list(dict.fromkeys(QUERY.findall(block))),
                "hasBody": "Lretrofit2/http/Body;" in block
                or bool(re.search(r"hasBody\s*=\s*true", block)),
                "requestType": request,
                "responseType": response,
                "models": referenced_model_classes(block)
                or referenced_models(request, response),
                "sourceClass": source_class,
            }
        )
    return endpoints


def consolidate(declarations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for declaration in declarations:
        key = (declaration["method"], declaration["route"])
        endpoint = grouped.setdefault(
            key,
            {
                "method": declaration["method"],
                "route": declaration["route"],
                "functions": [],
                "query": [],
                "hasBody": False,
                "requestTypes": [],
                "responseTypes": [],
                "models": [],
                "sourceClasses": [],
            },
        )
        endpoint["functions"].append(declaration["function"])
        endpoint["query"].extend(declaration["query"])
        endpoint["hasBody"] = endpoint["hasBody"] or declaration["hasBody"]
        endpoint["requestTypes"].append(declaration["requestType"])
        endpoint["responseTypes"].append(declaration["responseType"])
        endpoint["models"].extend(declaration["models"])
        endpoint["sourceClasses"].append(declaration["sourceClass"])
    for endpoint in grouped.values():
        endpoint["functions"] = list(dict.fromkeys(endpoint["functions"]))
        endpoint["query"] = list(dict.fromkeys(endpoint["query"]))
        endpoint["requestTypes"] = list(dict.fromkeys(endpoint["requestTypes"]))
        endpoint["responseTypes"] = list(dict.fromkeys(endpoint["responseTypes"]))
        endpoint["models"] = list(dict.fromkeys(endpoint["models"]))
        endpoint["sourceClasses"] = list(dict.fromkeys(endpoint["sourceClasses"]))
    return sorted(grouped.values(), key=lambda item: (item["route"], item["method"]))


def audit(apk: Path, tool: Path, api_classes: list[str]) -> dict[str, Any]:
    apk = apk.resolve()
    if not apk.is_file():
        raise FileNotFoundError(f"APK not found: {apk}")
    declarations: list[dict[str, Any]] = []
    for api_class in api_classes:
        code = run_analyzer(tool, "dex", "code", "--class", api_class, str(apk))
        declarations.extend(parse_api_service(code, api_class))
    endpoints = consolidate(declarations)
    model_names = sorted(
        {
            model
            for endpoint in endpoints
            for model in endpoint["models"]
        }
    )
    models: dict[str, Any] = {}

    def load_model(model: str) -> tuple[str, list[dict[str, str]], list[str]]:
        code = run_analyzer(tool, "dex", "code", "--class", model, str(apk))
        section = re.search(
            r"(?ms)^# instance fields\s*(?P<body>.*?)^# direct methods",
            code,
        )
        references = referenced_model_classes(section.group("body")) if section else []
        return model, parse_model_fields(code), references

    pending = set(model_names)
    while pending:
        batch = sorted(pending)
        pending.clear()
        with ThreadPoolExecutor(max_workers=min(4, len(batch) or 1)) as executor:
            futures = {executor.submit(load_model, model): model for model in batch}
            for future in as_completed(futures):
                model = futures[future]
                try:
                    _, fields, references = future.result()
                    models[model] = {
                        "fields": fields,
                        "pattern": {field["name"]: f"<{field['type']}>" for field in fields},
                    }
                    pending.update(
                        reference
                        for reference in references
                        if reference != model
                        and reference not in models
                        and len(models) + len(pending) < 150
                    )
                except RuntimeError as exc:
                    models[model] = {"fields": [], "pattern": {}, "error": str(exc)}
    models = dict(sorted(models.items()))
    for endpoint in endpoints:
        endpoint["requestPatterns"] = [
            pattern_for_type(type_name, models) for type_name in endpoint["requestTypes"]
        ]
        endpoint["responsePatterns"] = [
            pattern_for_type(type_name, models) for type_name in endpoint["responseTypes"]
        ]
        for request in endpoint["requestPatterns"]:
            if isinstance(request, dict) and endpoint["route"].endswith("/create"):
                for field in ("checkInTime", "checkOutTime"):
                    if field in request:
                        request[field] = "<yyyy-MM-ddTHH:mm:ss+05:30>"
    return {
        "apk": str(apk),
        "applicationId": run_analyzer(tool, "manifest", "application-id", str(apk)),
        "versionName": run_analyzer(tool, "manifest", "version-name", str(apk)),
        "versionCode": int(run_analyzer(tool, "manifest", "version-code", str(apk))),
        "endpointCount": len(endpoints),
        "declarationCount": len(declarations),
        "endpoints": endpoints,
        "models": models,
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Gridee APK endpoint audit",
        "",
        f"- APK: `{report['apk']}`",
        f"- Application ID: `{report['applicationId']}`",
        f"- Version: `{report['versionName']}` (code `{report['versionCode']}`)",
        f"- Unique Retrofit endpoints: **{report['endpointCount']}**",
        f"- Retrofit declarations: **{report['declarationCount']}**",
        f"- Request/response models extracted: **{len(report['models'])}**",
        "",
        "",
        "Patterns below are inferred from Retrofit annotations and APK model fields.",
        "They describe JSON structure, not server-side authorization or value constraints.",
        "",
        "| Method | Route | Request pattern | Response pattern | Query |",
        "|---|---|---|---|---|",
    ]
    for item in report["endpoints"]:
        query = ", ".join(item["query"]) or "-"
        functions = ", ".join(item["functions"])
        request = " / ".join(item["requestTypes"])
        response = " / ".join(item["responseTypes"])
        lines.append(
            f"| {item['method']} | `{item['route']}` | "
            f"`{request}` | `{response}` | {query} |"
        )
    lines.extend(["", "## APK model field patterns", ""])
    for model, schema in report["models"].items():
        lines.extend(
            [
                f"### {model.rsplit('.', 1)[-1]}",
                "",
                f"APK class: `{model}`",
                "",
                "```json",
                json.dumps(schema["pattern"], indent=2),
                "```",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract version and Retrofit endpoints from a Gridee APK."
    )
    parser.add_argument("apk", type=Path)
    parser.add_argument("--apkanalyzer", help="Path to apkanalyzer or apkanalyzer.bat.")
    parser.add_argument(
        "--api-class",
        action="append",
        dest="api_classes",
        help=f"Retrofit interface to inspect (default: {DEFAULT_API_CLASS}).",
    )
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--output", type=Path)
    return parser


def main() -> int:
    args = make_parser().parse_args()
    try:
        report = audit(
            args.apk,
            find_apkanalyzer(args.apkanalyzer),
            args.api_classes or [DEFAULT_API_CLASS],
        )
        rendered = (
            json.dumps(report, indent=2) + "\n"
            if args.format == "json"
            else markdown(report)
        )
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
            print(f"Wrote {args.output} ({report['endpointCount']} endpoints)")
        else:
            print(rendered, end="")
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"[!] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
