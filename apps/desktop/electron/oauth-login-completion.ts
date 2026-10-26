export interface OauthLoginCompletionDeps {
  hasSession: () => Promise<boolean>
  flushCookies: () => Promise<void>
  onSuccess: () => void
  onFailure: (error: Error) => void
}

export function createOauthLoginCompletion(deps: OauthLoginCompletionDeps): () => Promise<void> {
  let completed = false
  let pending: Promise<void> | null = null

  return () => {
    if (completed) {
      return Promise.resolve()
    }

    if (pending) {
      return pending
    }

    // Navigation events and the poll timer can observe the same cookie.
    // Only one check may flush and settle the login promise.
    pending = (async () => {
      try {
        if (!(await deps.hasSession())) {
          return
        }

        await deps.flushCookies()
      } catch {
        completed = true
        deps.onFailure(
          new Error('Remote login session could not be saved. Check Desktop storage permissions and try again.')
        )

        return
      }

      completed = true
      deps.onSuccess()
    })().finally(() => {
      pending = null
    })

    return pending
  }
}
