from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, unquote, urlsplit

from pydantic import Field, field_validator

from .contracts import (
    APPLICATION_EVIDENCE_VERSION,
    SANITIZED_PAYLOAD_VERSION,
    EvidenceDomain,
    EvidenceEnvelope,
    EvidenceTrustV1,
    FrozenModel,
    content_digest,
)


_IPV4 = re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")
_IPV6 = re.compile(r"(?i)(?<![0-9a-f:])(?:[0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}(?![0-9a-f:])")
_UUID = re.compile(r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b")
_LONG_TOKEN = re.compile(r"(?i)\b(?:[0-9a-f]{24,}|[a-z0-9_-]{36,})\b")
_ABSOLUTE_TIME = re.compile(
    r"(?i)\b(?:\d{4}-\d{2}-\d{2}[T ][0-9:.+-]+|(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s+\d{1,2}\s+[A-Z][a-z]{2}\s+\d{4}\s+[0-9:]+\s+GMT)\b"
)
_HOST_HEADER = re.compile(r"(?im)^(host|origin|referer):\s*[^\r\n]+")
_SECRET_HEADER = re.compile(r"(?im)^(authorization|cookie|set-cookie):\s*[^\r\n]+")
_USER_AGENT = re.compile(r"(?im)^user-agent:\s*[^\r\n]+")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_FIXED_LAB_PATH = re.compile(
    r"(?i)/(?:dvwa|vulnerabilities|mutillidae|testbed|home/pi|var/www)(?:/[^?\s]*)?"
)
_TOOL_MARKER = re.compile(r"(?i)\b(?:sqlmap|nikto|hydra|nmap|metasploit|msfconsole)(?:[/ _-][\w.-]+)?\b")
_ENVIRONMENT_MARKER = re.compile(
    r"(?i)\b(?:digininja|randomstorm(?:\.png)?|github\.com|microsoft\s+odbc\s+sql\s+server\s+driver)\b"
)
_DATABASE_ERROR = re.compile(
    r"(?i)(?:incorrect[_ ]syntax[_ ]near[_ ][^\s<]+|odbc[_ ]sql[_ ]server[_ ]driver|sql[_ ]server)"
)
_HTTP_REQUEST_LINE = re.compile(
    r"^(GET|POST|PUT|DELETE|HEAD|OPTIONS|PATCH)\s+(\S+)\s+(HTTP/\d(?:\.\d)?)$",
    flags=re.IGNORECASE,
)
_HTTP_RESPONSE_LINE = re.compile(r"^HTTP/\d(?:\.\d)?\s+\d{3}\b", flags=re.IGNORECASE)


TSHARK_FIELDS_V1 = (
    "frame.number",
    "frame.time_epoch",
    "frame.protocols",
    "eth.src",
    "eth.dst",
    "ip.src",
    "ip.dst",
    "ipv6.src",
    "ipv6.dst",
    "tcp.srcport",
    "tcp.dstport",
    "udp.srcport",
    "udp.dstport",
    "http.request.method",
    "http.request.uri",
    "http.response.code",
    "http.content_type",
    "http.content_length",
    "dns.qry.name",
    "dns.qry.type",
    "dns.flags.rcode",
    "tls.record.version",
    "tls.handshake.type",
    "tls.handshake.version",
    "tls.handshake.extensions_server_name",
    "modbus.func_code",
    "tcp.payload",
    "udp.payload",
    "data.data",
)


class ApplicationEvidenceV1(FrozenModel):
    protocol: str = Field(min_length=1, max_length=40)
    observations: tuple[dict[str, Any], ...] = ()
    frame_count: int = Field(ge=1)
    truncated: bool = False

    @field_validator("observations")
    @classmethod
    def bound_observations(cls, value: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
        if len(value) > 24:
            raise ValueError("Application Evidence is bounded to 24 observations")
        return value


class SanitizedPayloadV1(FrozenModel):
    protocol: str = Field(min_length=1, max_length=40)
    fragments: tuple[str, ...]
    raw_fragment_count: int = Field(ge=1)
    max_fragment_chars: int = Field(ge=64, le=2048)
    truncated: bool
    sanitizer_version: str = SANITIZED_PAYLOAD_VERSION

    @field_validator("fragments")
    @classmethod
    def validate_fragments(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or len(value) > 3:
            raise ValueError("Payload Evidence requires one to three bounded fragments")
        for fragment in value:
            if _IPV4.search(fragment) or _UUID.search(fragment) or _TOOL_MARKER.search(fragment):
                raise ValueError("payload sanitizer left a direct identity/tool shortcut")
        return value


def decode_hex_payload(value: str) -> str | None:
    compact = re.sub(r"[^0-9a-fA-F]", "", value or "")
    if not compact or len(compact) % 2 or len(compact) > 131072:
        return None
    try:
        raw = bytes.fromhex(compact)
    except ValueError:
        return None
    if not raw:
        return None
    decoded = raw.decode("utf-8", errors="replace")
    if decoded.count("\ufffd") / max(1, len(decoded)) > 0.01:
        return None
    printable = sum(character.isprintable() or character in "\r\n\t" for character in decoded)
    if printable / max(1, len(decoded)) < 0.65:
        return None
    return decoded


def _bounded_unquote(value: str) -> str:
    decoded = value
    for _ in range(3):
        expanded = unquote(decoded)
        if expanded == decoded:
            break
        decoded = expanded
    return _CONTROL.sub(" ", decoded).strip()


def _value_shape(value: str) -> str:
    decoded = _bounded_unquote(value)
    # normalize_uri_shape emits these closed placeholders. Preserve them when
    # a sanitized HTTP request is validated again; otherwise e.g. <NUM> would
    # degrade to <TEXT> and make the sanitizer non-idempotent.
    if decoded.upper() in {
        "<NUM>",
        "<SQL_EXPR>",
        "<SCRIPT_EXPR>",
        "<PATH_TRAVERSAL>",
        "<EMPTY>",
        "<TEXT>",
    }:
        return decoded.upper()
    lowered = decoded.casefold()
    if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", decoded):
        return "<NUM>"
    if any(token in lowered for token in (" union ", " select ", " or ", " and ", "--", "'", '"')):
        return "<SQL_EXPR>"
    if any(token in lowered for token in ("<script", "javascript:", "onerror=", "onload=")):
        return "<SCRIPT_EXPR>"
    if re.search(r"(?:\.\./|%2e%2e)", lowered):
        return "<PATH_TRAVERSAL>"
    if not decoded:
        return "<EMPTY>"
    return "<TEXT>"


def _parameter_key_shape(value: str) -> str:
    decoded = _bounded_unquote(value).casefold()
    existing = {
        "<command_param>": "<COMMAND_PARAM>",
        "<file_param>": "<FILE_PARAM>",
        "<credential_param>": "<CREDENTIAL_PARAM>",
        "<query_param>": "<QUERY_PARAM>",
        "<param>": "<PARAM>",
    }
    if decoded in existing:
        return existing[decoded]
    if decoded in {"cmd", "command", "exec", "execute"}:
        return "<COMMAND_PARAM>"
    if decoded in {"file", "filename", "upload"}:
        return "<FILE_PARAM>"
    if decoded in {"user", "username", "pass", "password"}:
        return "<CREDENTIAL_PARAM>"
    if decoded in {"id", "query", "search"}:
        return "<QUERY_PARAM>"
    return "<PARAM>"


def normalize_uri_shape(value: str) -> str:
    try:
        parts = urlsplit(value)
    except ValueError:
        return "<INVALID_URI>"
    segments = []
    for segment in parts.path.split("/"):
        if not segment:
            continue
        decoded = _bounded_unquote(segment)
        if decoded.upper() in {"<SEG>", "<NUM>", "<ID>", "<APP>", "<ROUTE>"}:
            segments.append(decoded.upper())
        elif re.fullmatch(r"(?i)<FILE>\.[a-z0-9]{1,8}", decoded):
            segments.append("<FILE>." + decoded.rsplit(".", 1)[-1].lower())
        elif decoded in {"..", "."}:
            segments.append(decoded)
        elif re.fullmatch(r"\d+", decoded):
            segments.append("<NUM>")
        elif re.fullmatch(r"(?i)[0-9a-f-]{16,}", decoded):
            segments.append("<ID>")
        elif "." in decoded and len(decoded.rsplit(".", 1)[-1]) <= 8:
            segments.append("<FILE>." + decoded.rsplit(".", 1)[-1].lower())
        else:
            segments.append("<SEG>")
    path = "/" + "/".join(segments)
    params = [
        f"{_parameter_key_shape(key)}={_value_shape(val)}"
        for key, val in parse_qsl(parts.query, keep_blank_values=True)
    ]
    return path + (("?" + "&".join(params)) if params else "")


def normalize_dns_name(value: str) -> str:
    labels = [item for item in value.rstrip(".").split(".") if item]
    if not labels:
        return "<HOST>"
    suffix = labels[-1].casefold()
    if suffix in {"local", "arpa", "com", "org", "net", "edu", "io"}:
        return f"<HOST>.{suffix}"
    return "<HOST>"


def sanitize_payload_text(value: str, *, max_chars: int = 768) -> str | None:
    if max_chars < 64 or max_chars > 2048:
        raise ValueError("payload bound must be within 64..2048 characters")
    text = html.unescape(value).replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL.sub(" ", text)
    header, separator, body = text.partition("\n\n")
    header_lines = header.splitlines()
    if header_lines and _HTTP_RESPONSE_LINE.match(header_lines[0].strip()):
        return None
    if header_lines:
        request = _HTTP_REQUEST_LINE.match(header_lines[0].strip())
        if request:
            normalized_header = [
                f"{request.group(1).upper()} {normalize_uri_shape(request.group(2))} {request.group(3).upper()}"
            ]
            for line in header_lines[1:]:
                name, colon, field_value = line.partition(":")
                if not colon:
                    continue
                normalized_name = name.strip().casefold()
                if normalized_name in {"content-type", "content-length"}:
                    normalized_header.append(
                        f"{name.strip()[:40]}: {field_value.strip()[:120]}"
                    )
                elif normalized_name in {"host", "origin", "referer"}:
                    normalized_header.append(f"{name.strip()[:40]}: <HOST>")
                elif normalized_name in {"authorization", "cookie", "set-cookie"}:
                    normalized_header.append(f"{name.strip()[:40]}: <SECRET>")
                elif normalized_name == "user-agent":
                    normalized_header.append("User-Agent: <CLIENT>")
            text = "\n".join(normalized_header)
            if separator and body.strip():
                text += "\n\n" + _CONTROL.sub(" ", unquote(body))
    text = _SECRET_HEADER.sub(lambda m: f"{m.group(1)}: <SECRET>", text)
    text = _HOST_HEADER.sub(lambda m: f"{m.group(1)}: <HOST>", text)
    text = _USER_AGENT.sub("User-Agent: <CLIENT>", text)
    text = _TOOL_MARKER.sub("<AUTOMATION_TOOL>", text)
    text = _ENVIRONMENT_MARKER.sub("<ENVIRONMENT>", text)
    text = _DATABASE_ERROR.sub("<DATABASE_ERROR>", text)
    text = _IPV4.sub("<IP>", text)
    text = _IPV6.sub("<IPV6>", text)
    text = _UUID.sub("<UUID>", text)
    text = _ABSOLUTE_TIME.sub("<TIME>", text)
    text = _LONG_TOKEN.sub("<TOKEN>", text)
    text = _FIXED_LAB_PATH.sub("/<APP>/<ROUTE>", text)
    text = re.sub(
        r"(?i)\b[a-z0-9_-]+\.(jsp|php|asp|aspx|html?)\b",
        lambda match: f"<FILE>.{match.group(1).lower()}",
        text,
    )
    text = re.sub(r"(?i)(?<![a-z0-9])E\d{3,6}(?![a-z0-9])", "<ERROR_CODE>", text)
    text = re.sub(r"(?i)(?<![a-z0-9])fname(?![a-z0-9])", "<PARAMETER>", text)
    text = re.sub(r"(?i)boundary=([-_a-z0-9.]{8,})", "boundary=<BOUNDARY>", text)
    text = re.sub(
        r'(?i)filename="?[^";\r\n]+(?:\.([a-z0-9]{1,8}))"?',
        lambda match: f'filename="<FILE>{("." + match.group(1).lower()) if match.group(1) else ""}"',
        text,
    )
    text = re.sub(
        r"(?i)\b(device|client|session|token|userid|username)=([^&\s]+)",
        lambda match: f"{match.group(1)}=<ID>",
        text,
    )
    text = re.sub(
        r"(?i)(^|[&\s])([a-z][a-z0-9_-]{0,40})=",
        lambda match: (
            f"{match.group(1)}<COMMAND_PARAM>="
            if match.group(2).casefold() in {"cmd", "command", "exec", "execute"}
            else f"{match.group(1)}<FILE_PARAM>="
            if match.group(2).casefold() in {"file", "filename", "upload"}
            else f"{match.group(1)}<CREDENTIAL_PARAM>="
            if match.group(2).casefold() in {"user", "username", "pass", "password"}
            else f"{match.group(1)}<QUERY_PARAM>="
            if match.group(2).casefold() in {"id", "query", "search"}
            else f"{match.group(1)}<PARAM>="
        ),
        text,
    )
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        return None
    return text[:max_chars]


def application_observation_from_frame(frame: dict[str, str]) -> dict[str, Any] | None:
    protocols = frame.get("frame.protocols", "").casefold()
    if frame.get("http.request.method") or frame.get("http.response.code") or "http" in protocols:
        output: dict[str, Any] = {"kind": "http"}
        if frame.get("http.request.method"):
            output["method"] = frame["http.request.method"].upper()[:16]
        if frame.get("http.request.uri"):
            output["uri_shape"] = normalize_uri_shape(frame["http.request.uri"])
            output["parameter_count"] = len(
                parse_qsl(urlsplit(frame["http.request.uri"]).query, keep_blank_values=True)
            )
        if frame.get("http.response.code"):
            status = frame["http.response.code"][:3]
            if status.isdigit():
                output["status"] = int(status)
        if frame.get("http.content_type"):
            output["content_type"] = frame["http.content_type"].split(";", 1)[0].casefold()[:80]
        if frame.get("http.content_length", "").isdigit():
            output["content_length"] = int(frame["http.content_length"])
        return output
    if frame.get("dns.qry.name") or "dns" in protocols:
        output = {"kind": "dns"}
        if frame.get("dns.qry.name"):
            output["name_shape"] = normalize_dns_name(frame["dns.qry.name"])
        if frame.get("dns.qry.type", "").isdigit():
            output["query_type"] = int(frame["dns.qry.type"])
        if frame.get("dns.flags.rcode", "").isdigit():
            output["response_code"] = int(frame["dns.flags.rcode"])
        return output
    if "tls" in protocols or frame.get("tls.handshake.type"):
        output = {"kind": "tls"}
        if frame.get("tls.record.version"):
            output["record_version"] = frame["tls.record.version"][:24]
        if frame.get("tls.handshake.version"):
            output["handshake_version"] = frame["tls.handshake.version"][:24]
        if frame.get("tls.handshake.type"):
            output["handshake_type"] = frame["tls.handshake.type"][:24]
        if frame.get("tls.handshake.extensions_server_name"):
            output["server_name"] = "<HOST>"
        return output
    if frame.get("modbus.func_code") or "modbus" in protocols:
        output = {"kind": "modbus"}
        if frame.get("modbus.func_code"):
            output["function_code"] = frame["modbus.func_code"][:24]
        return output
    return None


def payload_fragment_from_frame(frame: dict[str, str], *, max_chars: int = 768) -> str | None:
    for field in ("tcp.payload", "udp.payload", "data.data"):
        decoded = decode_hex_payload(frame.get(field, ""))
        if decoded:
            sanitized = sanitize_payload_text(decoded, max_chars=max_chars)
            if sanitized:
                return sanitized
    return None


def _safe_evidence_id(sample_id: str, kind: str) -> str:
    return f"ev_{kind}_{content_digest([sample_id, kind])[:24]}"


def application_envelope(sample_id: str, value: ApplicationEvidenceV1) -> EvidenceEnvelope:
    return EvidenceEnvelope(
        evidence_id=_safe_evidence_id(sample_id, "application"),
        evidence_type="application",
        domain=EvidenceDomain.OBSERVATION,
        trust=EvidenceTrustV1.TRUSTED_OBSERVATION,
        content={"version": APPLICATION_EVIDENCE_VERSION, **value.model_dump(mode="json")},
        provenance="application_sidecar_v1",
        metadata={"bounded": True, "observation_count": len(value.observations)},
    )


def payload_envelope(sample_id: str, value: SanitizedPayloadV1) -> EvidenceEnvelope:
    return EvidenceEnvelope(
        evidence_id=_safe_evidence_id(sample_id, "payload"),
        evidence_type="sanitized_payload",
        domain=EvidenceDomain.OBSERVATION,
        trust=EvidenceTrustV1.UNTRUSTED_PAYLOAD,
        content=value.model_dump(mode="json"),
        provenance="sanitized_payload_sidecar_v1",
        metadata={"bounded": True, "default_visible": False},
    )


@dataclass(frozen=True, slots=True)
class ShortcutFinding:
    token: str
    fine_label: str
    support: int
    class_fraction: float


def audit_shortcut_tokens(
    rows: list[tuple[str, tuple[str, ...]]],
    *,
    minimum_support: int = 10,
    minimum_class_fraction: float = 0.20,
) -> list[ShortcutFinding]:
    from collections import Counter, defaultdict

    semantic_allow = {
        "select",
        "union",
        "script",
        "http",
        "content",
        "connection",
        "request",
        "response",
        "error",
        "login",
    }
    class_sizes = Counter(label for label, _ in rows)
    token_classes: dict[str, Counter[str]] = defaultdict(Counter)
    for label, fragments in rows:
        tokens = {
            token.casefold()
            for fragment in fragments
            for token in re.findall(r"[A-Za-z][A-Za-z0-9_.-]{3,}", fragment)
            if token.casefold() not in semantic_allow and not token.startswith("<")
        }
        for token in tokens:
            token_classes[token][label] += 1
    findings: list[ShortcutFinding] = []
    for token, counts in token_classes.items():
        if len(counts) != 1:
            continue
        label, support = next(iter(counts.items()))
        fraction = support / class_sizes[label]
        if support >= minimum_support and fraction >= minimum_class_fraction:
            findings.append(ShortcutFinding(token, label, support, fraction))
    return sorted(findings, key=lambda item: (-item.class_fraction, -item.support, item.token))
