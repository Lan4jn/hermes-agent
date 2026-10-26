"""Wire contracts for message_keys.* methods (message API keys management)."""

from __future__ import annotations

from pydantic import Field

from .base import Params, Result
from .common import ProfileParams
from .registry import method


class MessageKeyItem(Result):
    id: str
    name: str
    created_at: str


class MessageKeysListParams(ProfileParams):
    pass


class MessageKeysListResult(Result):
    items: list[MessageKeyItem] = Field(default_factory=list)


class MessageKeyCreateParams(ProfileParams):
    name: str


class MessageKeyCreateResult(Result):
    id: str
    name: str
    created_at: str
    key: str


class MessageKeyRevokeParams(ProfileParams):
    id: str


class MessageKeyRevokeResult(Result):
    ok: bool = True
    removed: bool = False


class MessageKeysGetPolicyParams(ProfileParams):
    pass


class MessageKeysPolicyResult(Result):
    require_chat_key: bool


class MessageKeysSetPolicyParams(ProfileParams):
    require_chat_key: bool


method("message_keys.list", params=MessageKeysListParams, result=MessageKeysListResult,
       doc="List all message API keys for the current profile (metadata only, no plaintext key).")

method("message_keys.create", params=MessageKeyCreateParams, result=MessageKeyCreateResult,
       doc="Create a new message API key (returns plaintext key once).")

method("message_keys.revoke", params=MessageKeyRevokeParams, result=MessageKeyRevokeResult,
       doc="Revoke a message API key by ID.")

method("message_keys.get_policy", params=MessageKeysGetPolicyParams, result=MessageKeysPolicyResult,
       doc="Get the require_chat_key enforcement policy for message API.")

method("message_keys.set_policy", params=MessageKeysSetPolicyParams, result=MessageKeysPolicyResult,
       doc="Set the require_chat_key enforcement policy for message API.")
