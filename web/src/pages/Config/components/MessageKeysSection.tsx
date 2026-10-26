import { useCallback, useEffect, useState } from "react";
import { KeyRound, Plus, Trash2, Copy, Check, ShieldAlert, ShieldCheck } from "lucide-react";
import { Button } from "@nous-research/ui/ui/components/button";
import { Input } from "@nous-research/ui/ui/components/input";
import { Card, CardContent, CardHeader, CardTitle } from "@nous-research/ui/ui/components/card";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import { ConfirmDialog } from "@nous-research/ui/ui/components/confirm-dialog";
import { useToast } from "@nous-research/ui/hooks/use-toast";
import { api, type MessageKeyItem } from "@/lib/api";
import { copyTextToClipboard } from "@/lib/clipboard";
import { errorMessage } from "@/lib/api-error";
import { useI18n } from "@/i18n";

export function MessageKeysSection() {
  const { t } = useI18n();
  const m = t.messageKeys ?? {
    title: "Message API Keys",
    description: "Manage API keys for sending messages through the /message HTTP endpoint.",
    policyTitle: "Authentication Policy (require_chat_key)",
    policyDesc: "When required, incoming requests to /message must provide an api_key matching an active Message Key.",
    policyRequired: "Required (Protected)",
    policyOptional: "Optional (Unprotected)",
    policyUpdating: "Updating...",
    policyEnabledToast: "Message API authentication enabled",
    policyDisabledToast: "Message API authentication disabled",
    newKeyBannerTitle: "New Key Created — Copy Now",
    newKeyBannerDesc: "This key will never be shown again. Please copy and store it in a safe place.",
    copiedToast: "Copied key to clipboard",
    copyBtn: "Copy",
    copiedBtn: "Copied",
    doneBtn: "Done",
    createCardTitle: "Create Message Key",
    createPlaceholder: "Key label or client name (e.g. node-alpha)",
    createBtn: "Create",
    creatingBtn: "Creating...",
    createSuccessToast: "Message key created successfully",
    activeKeysTitle: "Active Message Keys",
    noKeysDesc: "No message keys created yet.",
    createdPrefix: "Created: ",
    revokeDialogTitle: "Revoke Message Key",
    revokeDialogDesc: "Are you sure you want to revoke key \"{name}\"? Any client using this key will immediately lose access.",
    revokeBtn: "Revoke",
    revokingBtn: "Revoking...",
    revokeSuccessToast: "Key revoked",
  };

  const { showToast } = useToast();
  const [keys, setKeys] = useState<MessageKeyItem[]>([]);
  const [requireChatKey, setRequireChatKey] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(true);
  const [savingPolicy, setSavingPolicy] = useState<boolean>(false);
  const [newKeyName, setNewKeyName] = useState<string>("");
  const [creating, setCreating] = useState<boolean>(false);
  const [justCreatedKey, setJustCreatedKey] = useState<string | null>(null);
  const [copied, setCopied] = useState<boolean>(false);
  const [keyToDelete, setKeyToDelete] = useState<MessageKeyItem | null>(null);
  const [deleting, setDeleting] = useState<boolean>(false);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [keysRes, policyRes] = await Promise.all([
        api.getMessageKeys(),
        api.getMessagePolicy(),
      ]);
      setKeys(keysRes);
      setRequireChatKey(policyRes.require_chat_key);
    } catch (e) {
      showToast(errorMessage(e), "error");
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const handleTogglePolicy = async () => {
    try {
      setSavingPolicy(true);
      const next = !requireChatKey;
      const res = await api.updateMessagePolicy(next);
      setRequireChatKey(res.require_chat_key);
      showToast(
        res.require_chat_key ? m.policyEnabledToast : m.policyDisabledToast,
        "success",
      );
    } catch (e) {
      showToast(errorMessage(e), "error");
    } finally {
      setSavingPolicy(false);
    }
  };

  const handleCreateKey = async (e: React.FormEvent) => {
    e.preventDefault();
    const name = newKeyName.trim();
    if (!name) return;
    try {
      setCreating(true);
      const created = await api.createMessageKey(name);
      setJustCreatedKey(created.key);
      setNewKeyName("");
      setKeys((prev) => [...prev, created]);
      showToast(m.createSuccessToast, "success");
    } catch (e) {
      showToast(errorMessage(e), "error");
    } finally {
      setCreating(false);
    }
  };

  const handleCopy = async () => {
    if (!justCreatedKey) return;
    const ok = await copyTextToClipboard(justCreatedKey);
    if (ok) {
      setCopied(true);
      showToast(m.copiedToast, "success");
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleConfirmDelete = async () => {
    if (!keyToDelete) return;
    try {
      setDeleting(true);
      await api.revokeMessageKey(keyToDelete.id);
      setKeys((prev) => prev.filter((k) => k.id !== keyToDelete.id));
      showToast(m.revokeSuccessToast, "success");
      setKeyToDelete(null);
    } catch (e) {
      showToast(errorMessage(e), "error");
    } finally {
      setDeleting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Spinner className="text-xl text-primary" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Policy Card */}
      <Card>
        <CardHeader className="py-3 px-4">
          <CardTitle className="text-sm flex items-center justify-between">
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-primary" />
              <span>{m.policyTitle}</span>
            </div>
            <Button
              size="sm"
              outlined={!requireChatKey}
              onClick={handleTogglePolicy}
              disabled={savingPolicy}
            >
              {savingPolicy
                ? m.policyUpdating
                : requireChatKey
                  ? m.policyRequired
                  : m.policyOptional}
            </Button>
          </CardTitle>
        </CardHeader>
        <CardContent className="px-4 py-3 text-xs text-muted-foreground border-t border-border">
          {m.policyDesc}
        </CardContent>
      </Card>

      {/* One-time Key Creation Notification Banner */}
      {justCreatedKey && (
        <Card className="border-amber-500/50 bg-amber-500/10">
          <CardHeader className="py-3 px-4">
            <CardTitle className="text-sm flex items-center gap-2 text-amber-500 font-medium">
              <ShieldAlert className="h-4 w-4" />
              <span>{m.newKeyBannerTitle}</span>
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4 pt-1 space-y-3">
            <p className="text-xs text-muted-foreground">
              {m.newKeyBannerDesc}
            </p>
            <div className="flex items-center gap-2">
              <Input
                readOnly
                value={justCreatedKey}
                className="font-mono text-xs bg-background/80"
              />
              <Button size="sm" onClick={handleCopy} prefix={copied ? <Check /> : <Copy />}>
                {copied ? m.copiedBtn : m.copyBtn}
              </Button>
              <Button size="sm" ghost onClick={() => setJustCreatedKey(null)}>
                {m.doneBtn}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Create New Key Form */}
      <Card>
        <CardHeader className="py-3 px-4">
          <CardTitle className="text-sm flex items-center gap-2">
            <Plus className="h-4 w-4" />
            <span>{m.createCardTitle}</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="px-4 py-3 border-t border-border">
          <form onSubmit={handleCreateKey} className="flex gap-2">
            <Input
              placeholder={m.createPlaceholder}
              value={newKeyName}
              onChange={(e) => setNewKeyName(e.target.value)}
              maxLength={80}
              className="text-xs h-8"
              disabled={creating}
            />
            <Button
              size="sm"
              type="submit"
              disabled={creating || !newKeyName.trim()}
              prefix={<Plus className="h-3.5 w-3.5" />}
            >
              {creating ? m.creatingBtn : m.createBtn}
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Keys List Card */}
      <Card>
        <CardHeader className="py-3 px-4">
          <CardTitle className="text-sm flex items-center justify-between">
            <div className="flex items-center gap-2">
              <KeyRound className="h-4 w-4" />
              <span>{m.activeKeysTitle} ({keys.length})</span>
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0 border-t border-border">
          {keys.length === 0 ? (
            <div className="p-6 text-center text-xs text-muted-foreground">
              {m.noKeysDesc}
            </div>
          ) : (
            <div className="divide-y divide-border">
              {keys.map((k) => (
                <div
                  key={k.id}
                  className="flex items-center justify-between p-3 px-4 text-xs hover:bg-muted/10"
                >
                  <div className="space-y-1 min-w-0">
                    <div className="font-medium text-foreground flex items-center gap-2">
                      <span>{k.name}</span>
                      <span className="font-mono text-[10px] text-muted-foreground">
                        {k.id.slice(0, 8)}...
                      </span>
                    </div>
                    <div className="text-[11px] text-muted-foreground">
                      {m.createdPrefix}{new Date(k.created_at).toLocaleString()}
                    </div>
                  </div>
                  <Button
                    size="xs"
                    ghost
                    destructive
                    onClick={() => setKeyToDelete(k)}
                    aria-label={`Revoke ${k.name}`}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Revoke confirmation */}
      {keyToDelete && (
        <ConfirmDialog
          open={Boolean(keyToDelete)}
          title={m.revokeDialogTitle}
          description={m.revokeDialogDesc.replace("{name}", keyToDelete.name)}
          confirmLabel={deleting ? m.revokingBtn : m.revokeBtn}
          destructive
          onConfirm={handleConfirmDelete}
          onCancel={() => setKeyToDelete(null)}
        />
      )}
    </div>
  );
}
