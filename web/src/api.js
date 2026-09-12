const tg = window.Telegram?.WebApp

export function initTelegram() {
  if (!tg) return
  tg.ready()
  tg.expand()
  tg.setHeaderColor?.('#0a0602')
  tg.setBackgroundColor?.('#0a0602')
}

async function req(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-Telegram-Init-Data': tg?.initData || '',
      ...options.headers,
    },
  })
  if (!res.ok) {
    let detail = `Ошибка ${res.status}`
    try {
      detail = (await res.json()).detail || detail
    } catch { /* keep default */ }
    throw new Error(detail)
  }
  return res.json()
}

export const api = {
  meta: () => req('/api/meta'),
  me: () => req('/api/me'),
  newRun: (body) => req('/api/run/new', { method: 'POST', body: JSON.stringify(body) }),
  turn: (runId, text) =>
    req(`/api/run/${runId}/turn`, { method: 'POST', body: JSON.stringify({ text }) }),
  abandon: (runId) => req(`/api/run/${runId}/abandon`, { method: 'POST' }),
  city: () => req('/api/city'),
  build: (building) => req('/api/city/build', { method: 'POST', body: JSON.stringify({ building }) }),
  hire: (name) => req('/api/city/hire', { method: 'POST', body: JSON.stringify({ name }) }),
}

export function haptic(type = 'light') {
  tg?.HapticFeedback?.impactOccurred?.(type)
}
