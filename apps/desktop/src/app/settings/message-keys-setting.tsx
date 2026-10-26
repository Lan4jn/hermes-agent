import { useStore } from '@nanostores/react'
import { useCallback, useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { useI18n } from '@/i18n'
import { triggerHaptic } from '@/lib/haptics'
import { AlertTriangle, Check, Copy, KeyRound, Plus, ShieldLock, Trash2 } from '@/lib/icons'
import { $activeConnectionId } from '@/store/connections'
import { requestGatewayForAgent } from '@/store/gateway'
import { notify, notifyError } from '@/store/notifications'
import { $gatewayState } from '@/store/session'
import { $settingsScopeProfile } from '@/store/settings-scope'

import { ListRow, SectionHeading, SettingsContent, SettingsSkeleton } from './primitives'

export interface MessageKeyItem {
  id: string
  name: string
  created_at: number
}

const DEFAULT_STRINGS = {
  enforcementPolicyTitle: 'Enforcement Policy',
  requireChatKeyTitle: 'Require Chat API Key',
  requireChatKeyDesc: 'When enabled, incoming /message requests must provide a valid API key in headers or JSON body.',
  newKeyBannerTitle: 'Copy Your New Message Key',
  newKeyBannerDesc: 'This key will never be shown again. Please copy and store it safely.',
  activeKeysTitle: (count: number) => `Active Keys (${count})`,
  createKeyBtn: 'Create Key',
  emptyKeys: 'No message keys created for this profile.',
  createDialogTitle: 'Create Message API Key',
  createDialogDesc: 'Assign a descriptive label or client name to identify this key (1–80 characters).',
  keyNamePlaceholder: 'e.g. openclaw-gateway, router-node',
  cancelBtn: 'Cancel',
  createBtn: 'Create',
  creatingBtn: 'Creating...',
  revokeDialogTitle: 'Revoke Message Key',
  revokeDialogDesc: (name: string) => `Are you sure you want to revoke key "${name}"? Applications using this key will immediately lose access.`,
  revokeBtn: 'Revoke',
  revokingBtn: 'Revoking...',
  copied: 'Copied',
  copy: 'Copy',
  done: 'Done',
  keyCreatedToast: 'Message API key created',
  keyRevokedToast: (name: string) => `Key "${name}" revoked`,
  keyCopiedToast: 'Key copied to clipboard',
  policyRequiredToast: 'Message API key required',
  policyOptionalToast: 'Message API key optional',
}

export function MessageKeysSetting() {
  const { t } = useI18n()
  const copy = t.settings.messageKeys ?? DEFAULT_STRINGS

  const gatewayState = useStore($gatewayState)
  const connectionId = useStore($activeConnectionId)
  const scopeProfile = useStore($settingsScopeProfile)

  const currentIdentity = `${connectionId}:${scopeProfile ?? 'default'}`
  const identityRef = useRef(currentIdentity)
  identityRef.current = currentIdentity

  const [loading, setLoading] = useState(true)
  const [keys, setKeys] = useState<MessageKeyItem[]>([])
  const [requireChatKey, setRequireChatKey] = useState(false)
  const [policyUpdating, setPolicyUpdating] = useState(false)

  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const [newKeyName, setNewKeyName] = useState('')
  const [creating, setCreating] = useState(false)

  const [oneTimeKey, setOneTimeKey] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  const [pendingRevoke, setPendingRevoke] = useState<null | MessageKeyItem>(null)
  const [revoking, setRevoking] = useState(false)

  useEffect(() => {
    // Identity changed: immediately discard sensitive transient states
    setOneTimeKey(null)
    setPendingRevoke(null)
    setCreateDialogOpen(false)
    setNewKeyName('')
    setKeys([])
  }, [currentIdentity])

  const requestGateway = useCallback(
    <T,>(method: string, params: Record<string, unknown> = {}) =>
      requestGatewayForAgent<T>(connectionId, scopeProfile, method, params, undefined, undefined, {
        spawnPriority: 'foreground'
      }),
    [connectionId, scopeProfile]
  )

  const loadData = useCallback(async () => {
    if (gatewayState !== 'open') {return}
    const requestIdentity = currentIdentity

    try {
      setLoading(true)

      const [listRes, policyRes] = await Promise.all([
        requestGateway<{ items: MessageKeyItem[] }>('message_keys.list'),
        requestGateway<{ require_chat_key: boolean }>('message_keys.get_policy')
      ])

      if (identityRef.current !== requestIdentity) {return}
      setKeys(listRes.items || [])
      setRequireChatKey(Boolean(policyRes.require_chat_key))
    } catch (err) {
      if (identityRef.current !== requestIdentity) {return}
      notifyError(err, 'Failed to load message keys')
    } finally {
      if (identityRef.current === requestIdentity) {
        setLoading(false)
      }
    }
  }, [gatewayState, requestGateway, currentIdentity])

  useEffect(() => {
    void loadData()
  }, [loadData])

  const handleTogglePolicy = async (checked: boolean) => {
    const requestIdentity = currentIdentity

    try {
      setPolicyUpdating(true)

      const res = await requestGateway<{ require_chat_key: boolean }>('message_keys.set_policy', {
        require_chat_key: checked
      })

      if (identityRef.current !== requestIdentity) {return}
      setRequireChatKey(res.require_chat_key)
      notify({
        message: res.require_chat_key ? copy.policyRequiredToast : copy.policyOptionalToast
      })
      triggerHaptic('selection')
    } catch (err) {
      if (identityRef.current !== requestIdentity) {return}
      notifyError(err, 'Failed to update message policy')
    } finally {
      if (identityRef.current === requestIdentity) {
        setPolicyUpdating(false)
      }
    }
  }

  const handleCreate = async () => {
    const name = newKeyName.trim()

    if (!name) {return}
    const requestIdentity = currentIdentity

    try {
      setCreating(true)

      const res = await requestGateway<MessageKeyItem & { key: string }>('message_keys.create', {
        name
      })

      if (identityRef.current !== requestIdentity) {return}
      setOneTimeKey(res.key)
      setCreateDialogOpen(false)
      setNewKeyName('')
      setKeys(prev => [...prev, { id: res.id, name: res.name, created_at: res.created_at }])
      notify({ message: copy.keyCreatedToast })
      triggerHaptic('success')
    } catch (err) {
      if (identityRef.current !== requestIdentity) {return}
      notifyError(err, 'Failed to create message key')
    } finally {
      if (identityRef.current === requestIdentity) {
        setCreating(false)
      }
    }
  }

  const handleCopyKey = async () => {
    if (!oneTimeKey) {return}

    try {
      await navigator.clipboard.writeText(oneTimeKey)
      setCopied(true)
      notify({ message: copy.keyCopiedToast })
      triggerHaptic('selection')
      setTimeout(() => setCopied(false), 2000)
    } catch (err) {
      notifyError(err, 'Failed to copy to clipboard')
    }
  }

  const handleRevoke = async () => {
    if (!pendingRevoke) {return}
    const requestIdentity = currentIdentity

    try {
      setRevoking(true)
      await requestGateway<{ ok: boolean; removed: boolean }>('message_keys.revoke', {
        id: pendingRevoke.id
      })

      if (identityRef.current !== requestIdentity) {return}
      setKeys(prev => prev.filter(k => k.id !== pendingRevoke.id))
      notify({ message: copy.keyRevokedToast(pendingRevoke.name) })
      setPendingRevoke(null)
      triggerHaptic('selection')
    } catch (err) {
      if (identityRef.current !== requestIdentity) {return}
      notifyError(err, 'Failed to revoke message key')
    } finally {
      if (identityRef.current === requestIdentity) {
        setRevoking(false)
      }
    }
  }

  if (loading && keys.length === 0) {
    return <SettingsSkeleton sections={[{ rows: 3 }]} />
  }

  return (
    <SettingsContent>
      {/* Enforcement Policy */}
      <div className="mb-6 space-y-2">
        <SectionHeading icon={ShieldLock} title={copy.enforcementPolicyTitle} />
        <div className="rounded-[6px] border border-border bg-card p-4">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <div className="flex items-center gap-2 font-medium text-sm text-foreground">
                <ShieldLock className="h-4 w-4 text-primary" />
                <span>{copy.requireChatKeyTitle}</span>
              </div>
              <p className="text-xs text-muted-foreground">
                {copy.requireChatKeyDesc}
              </p>
            </div>
            <Switch
              checked={requireChatKey}
              disabled={policyUpdating}
              onCheckedChange={handleTogglePolicy}
            />
          </div>
        </div>
      </div>

      {/* One-time plaintext display modal */}
      {oneTimeKey && (
        <div className="mb-6 rounded-[6px] border border-amber-500/50 bg-amber-500/10 p-4">
          <div className="flex items-center gap-2 font-medium text-amber-500 text-sm mb-1">
            <AlertTriangle className="h-4 w-4" />
            <span>{copy.newKeyBannerTitle}</span>
          </div>
          <p className="text-xs text-muted-foreground mb-3">
            {copy.newKeyBannerDesc}
          </p>
          <div className="flex items-center gap-2">
            <Input className="font-mono text-xs bg-background/80" readOnly value={oneTimeKey} />
            <Button onClick={handleCopyKey} size="sm">
              {copied ? <Check className="h-3.5 w-3.5 mr-1" /> : <Copy className="h-3.5 w-3.5 mr-1" />}
              {copied ? copy.copied : copy.copy}
            </Button>
            <Button onClick={() => setOneTimeKey(null)} size="sm" variant="ghost">
              {copy.done}
            </Button>
          </div>
        </div>
      )}

      {/* Keys List */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <SectionHeading icon={KeyRound} title={copy.activeKeysTitle(keys.length)} />
          <Button onClick={() => setCreateDialogOpen(true)} size="sm">
            <Plus className="h-3.5 w-3.5 mr-1" />
            {copy.createKeyBtn}
          </Button>
        </div>

        {keys.length === 0 ? (
          <div className="rounded-[6px] border border-border bg-card p-6 text-center text-xs text-muted-foreground">
            {copy.emptyKeys}
          </div>
        ) : (
          <div className="divide-y divide-border rounded-[6px] border border-border bg-card">
            {keys.map(k => (
              <ListRow
                action={
                  <Button
                    className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                    onClick={() => setPendingRevoke(k)}
                    size="sm"
                    variant="ghost"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                }
                description={`ID: ${k.id.slice(0, 8)}... • Created: ${new Date(k.created_at).toLocaleString()}`}
                key={k.id}
                title={k.name}
              />
            ))}
          </div>
        )}
      </div>

      {/* Create Dialog */}
      <Dialog onOpenChange={setCreateDialogOpen} open={createDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{copy.createDialogTitle}</DialogTitle>
            <DialogDescription>
              {copy.createDialogDesc}
            </DialogDescription>
          </DialogHeader>
          <div className="py-2">
            <Input
              autoFocus
              maxLength={80}
              onChange={e => setNewKeyName(e.target.value)}
              placeholder={copy.keyNamePlaceholder}
              value={newKeyName}
            />
          </div>
          <DialogFooter>
            <Button onClick={() => setCreateDialogOpen(false)} variant="ghost">
              {copy.cancelBtn}
            </Button>
            <Button disabled={creating || !newKeyName.trim()} onClick={handleCreate}>
              {creating ? copy.creatingBtn : copy.createBtn}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Revoke Confirm Dialog */}
      {pendingRevoke && (
        <ConfirmDialog
          confirmLabel={revoking ? copy.revokingBtn : copy.revokeBtn}
          description={copy.revokeDialogDesc(pendingRevoke.name)}
          destructive
          onClose={() => setPendingRevoke(null)}
          onConfirm={handleRevoke}
          open={Boolean(pendingRevoke)}
          title={copy.revokeDialogTitle}
        />
      )}
    </SettingsContent>
  )
}
