export interface RemoteOauthLogoutDeps {
  clearNativeTokens: () => void
  clearCookies: () => Promise<void>
}

export async function clearRemoteOauthSession(deps: RemoteOauthLogoutDeps): Promise<void> {
  try {
    deps.clearNativeTokens()
  } finally {
    await deps.clearCookies()
  }
}
