import { useEffect, useRef, useState } from 'react'
import DiceOverlay from './DiceOverlay.jsx'

function Roll({ r }) {
  const isD20 = r.sides === 20 && r.count === 1
  const nat = r.rolls[0]
  const hasDc = typeof r.dc === 'number'
  let cls = ''
  if (isD20 && nat === 20) cls = 'crit'
  else if (isD20 && nat === 1) cls = 'fail'
  else if (hasDc) cls = r.success ? 'crit' : 'fail'
  const modStr = r.modifier ? (r.modifier > 0 ? `+${r.modifier}` : `${r.modifier}`) : ''
  return (
    <span className={`roll ${cls}`}>
      {r.reason && <>{r.reason}: </>}
      {r.count}d{r.sides}
      {modStr} → [{r.rolls.join(', ')}]{modStr} = <b>{r.total}</b>
      {hasDc && <> против СЛ {r.dc} — <b>{r.success ? 'УСПЕХ' : 'ПРОВАЛ'}</b></>}
    </span>
  )
}

export default function GameScreen({ run, user, busy, error, onTurn, onAbandon }) {
  const [text, setText] = useState('')
  const [showInv, setShowInv] = useState(false)
  const [pendingRolls, setPendingRolls] = useState(null)
  const logRef = useRef(null)
  const s = run.state
  const log = run.log || []
  const lastActions = log.length ? log[log.length - 1].suggested_actions || [] : []
  const hpPct = Math.round((s.hp / s.max_hp) * 100)

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: 'smooth' })
  }, [log.length, busy])

  // show the dice overlay when a new turn arrives with rolls
  useEffect(() => {
    const last = log[log.length - 1]
    if (last?.justArrived && last.rolls?.length) {
      setPendingRolls(last.rolls)
    }
  }, [log])

  const submit = (t) => {
    const value = (t ?? text).trim()
    if (!value || busy) return
    setText('')
    onTurn(value)
  }

  return (
    <div className="screen">
      <div className="panel">
        <span className="panel-title">
          {s.name} · {run.stateRaceName || s.race} {run.stateClassName || s.class} · ур.{s.level}
        </span>
        <div className="stats">
          <span className={hpPct <= 25 ? 'low' : ''}>HP <b>{s.hp}/{s.max_hp}</b></span>
          <span>ЗОЛ <b>{s.gold}</b></span>
          <span>XP <b>{s.xp}</b></span>
          <span>ЯРУС <b>{s.depth}</b></span>
          <span className="muted">ходы: {user.turns_left}</span>
        </div>
        <div className="hp-bar"><i style={{ width: `${hpPct}%` }} /></div>
        <button
          className="inv-toggle"
          onClick={() => setShowInv((v) => !v)}
        >
          {showInv ? '▾' : '▸'} снаряжение ({s.inventory.length})
        </button>
        {showInv && (
          <div className="inv">
            {s.inventory.map((it, i) => <span key={i} className="inv-item">{it}</span>)}
            {s.spells?.length > 0 && (
              <div style={{ marginTop: 4 }}>
                {s.spells.map((sp, i) => <span key={i} className="inv-item spell">✦ {sp}</span>)}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="log panel" ref={logRef}>
        <span className="panel-title">{s.location}</span>
        {log.map((t, i) => (
          <div className="log-entry" key={i}>
            {t.player_input !== '[начало забега]' && (
              <div className="log-player">{t.player_input}</div>
            )}
            {t.rolls?.length > 0 && (
              <div>{t.rolls.map((r, j) => <Roll r={r} key={j} />)}</div>
            )}
            <div className="log-narration">{t.narration}</div>
          </div>
        ))}
        {busy && <div className="typing">Мастер подземелья думает</div>}
        {error && <p className="error">{error}</p>}
      </div>

      <div className="actions">
        {lastActions.map((a, i) => (
          <button key={i} disabled={busy} onClick={() => submit(a)}>{a}</button>
        ))}
      </div>

      <div className="input-row">
        <input
          type="text"
          placeholder="Что ты делаешь?"
          value={text}
          maxLength={500}
          disabled={busy}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && submit()}
        />
        <button className="primary" disabled={busy || !text.trim()} onClick={() => submit()}>
          ▸
        </button>
      </div>

      <button className="muted" style={{ border: 'none', alignSelf: 'center', fontSize: 12 }}
        onClick={onAbandon} disabled={busy}>
        покинуть подземелье (забег будет потерян)
      </button>

      {pendingRolls && (
        <DiceOverlay rolls={pendingRolls} onDone={() => setPendingRolls(null)} />
      )}
    </div>
  )
}
