"""Closed schemas and invariants for specs/013 runtime configuration."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

SENSITIVE_CONFIG_KEY_PATTERN = re.compile(
    r"^(?:(?:[a-z0-9]+[_-])?(?:api[_-]?key|token|secret|password|credential|private[_-]?key))$",
    re.IGNORECASE,
)
ROUTE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]{2,62}$")
GATEWAY_ROUTE_PATTERN = re.compile(r"^[a-z][a-z0-9-]{2,62}-r[1-9][0-9]*$")


class RuntimeConfigModel(BaseModel):
    """Base model that rejects unknown keys in every persisted configuration layer."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class LogicalRoute(RuntimeConfigModel):
    """A portable logical route resolved to a versioned Gateway alias."""

    effective_gateway_route: str = Field(min_length=4, max_length=63)
    capabilities: frozenset[Literal["text", "vision", "tool_calling", "structured_output"]]

    @field_validator("effective_gateway_route")
    @classmethod
    def validate_gateway_route(cls, value: str) -> str:
        if not GATEWAY_ROUTE_PATTERN.fullmatch(value):
            raise ValueError("effective_gateway_route must be a versioned logical Gateway alias")
        return value

    @model_validator(mode="after")
    def validate_capabilities(self) -> LogicalRoute:
        if not self.capabilities:
            raise ValueError("route capabilities must not be empty")
        return self


class RoutingConfig(RuntimeConfigModel):
    default_route: str = Field(min_length=3, max_length=63)
    routes: dict[str, LogicalRoute] = Field(min_length=1)

    @field_validator("default_route")
    @classmethod
    def validate_default_route_name(cls, value: str) -> str:
        if not ROUTE_NAME_PATTERN.fullmatch(value):
            raise ValueError("default_route must be a logical route name")
        return value

    @field_validator("routes")
    @classmethod
    def validate_route_names(cls, value: dict[str, LogicalRoute]) -> dict[str, LogicalRoute]:
        invalid = [name for name in value if not ROUTE_NAME_PATTERN.fullmatch(name)]
        if invalid:
            raise ValueError("route names must be logical route names")
        return value

    @model_validator(mode="after")
    def validate_default_route_exists(self) -> RoutingConfig:
        if self.default_route not in self.routes:
            raise ValueError("default_route must exist in routes")
        if "text" not in self.routes[self.default_route].capabilities:
            raise ValueError("default_route must support text")
        return self


class ExecutionBudgetConfig(RuntimeConfigModel):
    max_runtime_seconds: int = Field(ge=1, le=600)
    max_model_calls: int = Field(ge=1, le=50)
    max_tool_calls: int = Field(ge=1, le=20)
    max_same_tool_args_after_success: int = Field(ge=1, le=5)
    max_gateway_requests: int = Field(ge=1, le=100)
    max_gateway_attempts_per_model_call: int = Field(ge=1, le=5)
    max_output_tokens: int = Field(ge=1, le=32768)
    max_queue_wait_seconds: int = Field(ge=0, le=300)
    max_estimated_cost_usd: float | None = Field(default=None, gt=0, le=1000)

    @model_validator(mode="after")
    def validate_cross_field_limits(self) -> ExecutionBudgetConfig:
        if self.max_gateway_requests < self.max_model_calls:
            raise ValueError("max_gateway_requests must be at least max_model_calls")
        minimum_attempts = self.max_model_calls * self.max_gateway_attempts_per_model_call
        if self.max_gateway_requests > minimum_attempts:
            raise ValueError("max_gateway_requests cannot exceed the model-call attempt ceiling")
        return self


class ConcurrencyConfig(RuntimeConfigModel):
    per_chat: int = Field(ge=1, le=20)
    per_user: int = Field(ge=1, le=20)
    global_: int = Field(alias="global", ge=1, le=100)
    queued_per_chat: int = Field(ge=1, le=100)
    pending_global: int = Field(ge=1, le=1000)

    @model_validator(mode="after")
    def validate_capacity(self) -> ConcurrencyConfig:
        if self.pending_global < self.global_:
            raise ValueError("pending_global must be at least global")
        if self.queued_per_chat > self.pending_global:
            raise ValueError("queued_per_chat cannot exceed pending_global")
        return self


class AdmissionConfig(RuntimeConfigModel):
    user_burst: int = Field(ge=1, le=100)
    user_requests_per_minute: int = Field(ge=1, le=1000)
    user_requests_per_hour: int = Field(ge=1, le=10000)

    @model_validator(mode="after")
    def validate_rate_windows(self) -> AdmissionConfig:
        if self.user_burst > self.user_requests_per_minute:
            raise ValueError("user_burst cannot exceed user_requests_per_minute")
        if self.user_requests_per_minute > self.user_requests_per_hour:
            raise ValueError("user_requests_per_minute cannot exceed user_requests_per_hour")
        return self


class GatewayConfig(RuntimeConfigModel):
    request_timeout_seconds: int = Field(ge=1, le=300)
    retries: Literal[0]
    cross_model_fallbacks: Literal[0]
    cooldown_seconds: int = Field(ge=1, le=3600)
    openrouter_provider_fallback: bool


class ObservabilityConfig(RuntimeConfigModel):
    traces_enabled: bool
    metrics_enabled: bool
    content_capture: Literal[False]
    trace_sample_rate: float = Field(ge=0, le=1)


class RoutePricing(RuntimeConfigModel):
    """Optional per-route pricing snapshot for cost estimation (USD per 1M tokens)."""

    input_cost_per_1m_usd: float | None = Field(default=None, ge=0)
    output_cost_per_1m_usd: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_has_price(self) -> RoutePricing:
        if self.input_cost_per_1m_usd is None and self.output_cost_per_1m_usd is None:
            raise ValueError("route pricing must declare at least one token price")
        return self


class PricingConfig(RuntimeConfigModel):
    """Static pricing snapshot; avoids DB/disk reads on the per-call path."""

    routes: dict[str, RoutePricing] = Field(default_factory=dict)

    def route_price(self, effective_gateway_route: str) -> RoutePricing | None:
        """Return the pricing entry for a versioned Gateway alias, when known."""
        return self.routes.get(effective_gateway_route)


class RuntimeConfiguration(RuntimeConfigModel):
    """Portable, secret-free configuration held in immutable DB revisions."""

    schema_version: Literal[1]
    routing: RoutingConfig
    execution_budget: ExecutionBudgetConfig
    concurrency: ConcurrencyConfig
    admission: AdmissionConfig
    gateway: GatewayConfig
    observability: ObservabilityConfig
    pricing: PricingConfig | None = None

    @model_validator(mode="after")
    def validate_runtime_limits(self) -> RuntimeConfiguration:
        if self.gateway.request_timeout_seconds > self.execution_budget.max_runtime_seconds:
            raise ValueError("gateway timeout cannot exceed total runtime budget")
        if self.concurrency.global_ > self.concurrency.pending_global:
            raise ValueError("global concurrency cannot exceed pending_global")
        if self.pricing is not None:
            effective_routes = {
                route.effective_gateway_route for route in self.routing.routes.values()
            }
            unknown_pricing_routes = set(self.pricing.routes) - effective_routes
            if unknown_pricing_routes:
                raise ValueError("pricing routes must reference configured Gateway aliases")
        return self


class RuntimeConfigSnapshot(RuntimeConfigModel):
    """Immutable in-memory configuration captured once by every future run."""

    revision: int = Field(ge=0)
    checksum: str = Field(min_length=64, max_length=64)
    source: Literal["bootstrap", "database"]
    config: RuntimeConfiguration


class RuntimeConfigRevision(RuntimeConfigModel):
    """Immutable database revision metadata and typed configuration."""

    revision: int = Field(ge=1)
    schema_version: int = Field(ge=1)
    config: RuntimeConfiguration
    checksum: str = Field(min_length=64, max_length=64)
    validation_status: Literal["valid", "invalid"]
    validation_errors: tuple[str, ...] = ()
    created_by: str
    reason: str
    created_at: datetime


class RuntimeConfigActivation(RuntimeConfigModel):
    """Append-only audit record for a successful active-pointer transition."""

    revision: int = Field(ge=1)
    previous_revision: int | None = Field(default=None, ge=1)
    actor: str
    reason: str
    activated_at: datetime


class RuntimeConfigValidationResult(RuntimeConfigModel):
    """Safe validation result returned by the manager and admin API."""

    valid: bool
    errors: tuple[str, ...] = ()
    checksum: str | None = Field(default=None, min_length=64, max_length=64)


def bootstrap_runtime_configuration(
    default_route: str = "ancoramind-default",
) -> RuntimeConfiguration:
    """Return the approved safe bootstrap configuration for cold starts/recovery."""
    routes = {
        "ancoramind-default": {
            "effective_gateway_route": "ancoramind-default-r1",
            "capabilities": ["text", "tool_calling", "structured_output"],
        },
        "ancoramind-fast": {
            "effective_gateway_route": "ancoramind-fast-r1",
            "capabilities": ["text", "tool_calling"],
        },
        "ancoramind-vision": {
            "effective_gateway_route": "ancoramind-vision-r1",
            "capabilities": ["text", "vision", "structured_output"],
        },
    }
    return RuntimeConfiguration.model_validate(
        {
            "schema_version": 1,
            "routing": {"default_route": default_route, "routes": routes},
            "execution_budget": {
                "max_runtime_seconds": 120,
                "max_model_calls": 6,
                "max_tool_calls": 12,
                "max_same_tool_args_after_success": 1,
                "max_gateway_requests": 8,
                "max_gateway_attempts_per_model_call": 2,
                "max_output_tokens": 1024,
                "max_queue_wait_seconds": 30,
                "max_estimated_cost_usd": None,
            },
            "concurrency": {
                "per_chat": 1,
                "per_user": 1,
                "global": 2,
                "queued_per_chat": 5,
                "pending_global": 20,
            },
            "admission": {
                "user_burst": 5,
                "user_requests_per_minute": 10,
                "user_requests_per_hour": 120,
            },
            "gateway": {
                "request_timeout_seconds": 45,
                "retries": 0,
                "cross_model_fallbacks": 0,
                "cooldown_seconds": 60,
                "openrouter_provider_fallback": True,
            },
            "observability": {
                "traces_enabled": True,
                "metrics_enabled": True,
                "content_capture": False,
                "trace_sample_rate": 1.0,
            },
            "pricing": None,
        }
    )


def canonical_config_json(config: RuntimeConfiguration) -> str:
    """Serialize a config deterministically for its immutable SHA-256 checksum."""
    return json.dumps(
        config.model_dump(mode="json", by_alias=True),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def config_checksum(config: RuntimeConfiguration) -> str:
    """Return the deterministic SHA-256 checksum of a typed runtime config."""
    return hashlib.sha256(canonical_config_json(config).encode("utf-8")).hexdigest()


def validate_runtime_config(payload: object) -> RuntimeConfigValidationResult:
    """Validate unknown input without persisting it or allowing secret-like fields."""
    secret_paths = find_sensitive_config_keys(payload)
    if secret_paths:
        return RuntimeConfigValidationResult(
            valid=False,
            errors=tuple(
                f"sensitive configuration key is forbidden: {path}" for path in secret_paths
            ),
        )
    try:
        config = RuntimeConfiguration.model_validate(payload)
    except ValidationError as exc:
        return RuntimeConfigValidationResult(
            valid=False,
            errors=tuple(format_validation_error(error) for error in exc.errors()),
        )
    return RuntimeConfigValidationResult(valid=True, checksum=config_checksum(config))


def parse_runtime_config(payload: object) -> RuntimeConfiguration:
    """Return a typed config or raise a safe validation error for service callers."""
    validation = validate_runtime_config(payload)
    if not validation.valid:
        raise RuntimeConfigValidationError(validation.errors)
    return RuntimeConfiguration.model_validate(payload)


class RuntimeConfigValidationError(ValueError):
    """Configuration failed closed validation before any database mutation."""

    def __init__(self, errors: tuple[str, ...]):
        super().__init__("Runtime configuration is invalid")
        self.errors = errors


def find_sensitive_config_keys(value: object, path: str = "$") -> tuple[str, ...]:
    """Reject secret-like key names recursively before they enter persisted JSONB."""
    if isinstance(value, dict):
        found: list[str] = []
        for key, child in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            if SENSITIVE_CONFIG_KEY_PATTERN.fullmatch(key_text):
                found.append(child_path)
            found.extend(find_sensitive_config_keys(child, child_path))
        return tuple(found)
    if isinstance(value, list):
        found = []
        for index, child in enumerate(value):
            found.extend(find_sensitive_config_keys(child, f"{path}[{index}]"))
        return tuple(found)
    return ()


def format_validation_error(error: Mapping[str, Any]) -> str:
    """Convert Pydantic validation metadata to a stable non-secret error string."""
    location = ".".join(str(item) for item in error.get("loc", ())) or "$"
    return f"{location}: {error.get('msg', 'invalid value')}"
