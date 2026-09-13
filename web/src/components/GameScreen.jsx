import { useEffect, useRef, useState } from 'react'
import DiceOverlay from './DiceOverlay.jsx'
import SceneArt from './SceneArt.jsx'

const STAT_RU = { STR: 'СИЛ', DEX: 'ЛОВ', CON: 'ВЫН', INT: 'ИНТ', WIS: 'МДР', CHA: 'ХАР' }
const mod = (v) => { const m = Math.floor((v - 10) / 2); return m >= 0 ? `+${m}` : `${m}` }

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

export default function GameScreen({ run, user, meta, busy, error, onTurn, onAbandon, onSpendStat, onPickTalent }) {
  const depthLabel = meta?.dungeons?.find((d) => d.id === run.dungeon)?.depth_label || 'ЯРУС' 
  const [text, setText] = useState('')
  const [showInv, setShowInv] = useState(false)
  const [pendingRolls, setPendingRolls] = useState(null)
  const [showActions, setShowActions] = useState(false)
  const logRef = useRef(null)
  const s = run.state
  const log = run.log || []
  const lastActions = log.length ? log[log.length - 1].suggested_actions || [] : []
  const hpPct = Math.round((s.hp / s.max_hp) * 100)

  useEffect(() => { setShowActions(false) }, [log.length])

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
          <span>{depthLabel} <b>{s.depth}</b></span>
          {s.fate > 0 && <span title="Очко судьбы: спасёт от смерти один раз">СУДЬБА <b>◆</b></span>}
          {s.backpack && <span>РЮКЗАК <b>{Object.values(s.backpack.res || {}).reduce((a, b) => a + b, 0)}/{s.backpack.capacity}</b></span>}
          <span className="muted">ходы: {user.turns_left}</span>
        </div>
        <div className="hp-bar"><i style={{ width: `${hpPct}%` }} /></div>
        <button
          className="inv-toggle"
          onClick={() => setShowInv((v) => !v)}
        >
          {showInv ? '▾' : '▸'} персонаж и снаряжение ({s.inventory.length})
          {(s.stat_points > 0 || s.talent_points > 0) && <b> · ⬆ прокачка!</b>}
        </button>
        {(s.party || []).length > 0 && (
          <div className="inv" style={{ marginTop: 4 }}>
            {s.party.map((m) => (
              <span key={m.name} className="inv-item">
                ⚔ {m.name} · {m.cls_name || m.cls} · ❤{m.hp}/{m.max_hp}
              </span>
            ))}
          </div>
        )}
        {showInv && (
          <div className="inv">
            {(s.equipment?.weapon || s.equipment?.armor) && (
              <div style={{ marginBottom: 6 }}>
                {s.equipment.weapon && <span className="inv-item spell">⚔ {s.equipment.weapon.name} (+{s.equipment.weapon.atk}, {s.equipment.weapon.dmg})</span>}
                {s.equipment.armor && <span className="inv-item spell">🛡 {s.equipment.armor.name} (защита +{s.equipment.armor.def}, прочн. {s.equipment.armor.dur})</span>}
              </div>
            )}
            {s.stat_points > 0 && (
              <p className="muted" style={{ marginBottom: 4 }}>Свободных очков характеристик: <b>{s.stat_points}</b> — жми ⊕</p>
            )}
            <div className="char-stats">
              {Object.entries(s.stats || {}).map(([k, v]) => (
                <span key={k}>
                  {STAT_RU[k] || k} <b>{v}</b> <i>({mod(v)})</i>
                  {s.stat_points > 0 && (
                    <button className="plus-btn" disabled={busy} onClick={() => onSpendStat(k)}>⊕</button>
                  )}
                </span>
              ))}
            </div>
            {(s.talents || []).length > 0 && (
              <div style={{ marginBottom: 6 }}>
                {s.talents.map((t) => (
                  <span key={t} className="inv-item spell" title={meta?.talents?.[t]?.desc}>
                    ✦ {meta?.talents?.[t]?.name || t}
                  </span>
                ))}
              </div>
            )}
            {s.talent_points > 0 && (
              <div className="panel" style={{ marginBottom: 8 }}>
                <span className="panel-title">Выбор таланта ({s.talent_points})</span>
                {Object.entries(meta?.talents || {})
                  .filter(([id]) => !(s.talents || []).includes(id))
                  .map(([id, t]) => (
                    <div key={id} style={{ marginBottom: 6 }}>
                      <button disabled={busy} onClick={() => onPickTalent(id)}>{t.name}</button>
                      <span className="muted" style={{ marginLeft: 8, fontSize: 12 }}>{t.desc}</span>
                    </div>
                  ))}
              </div>
            )}
            {s.inventory.map((it, i) => <span key={i} className="inv-item">{it}</span>)}
            {s.spells?.length > 0 && (
              <div style={{ marginTop: 4 }}>
                {s.spells.map((sp, i) => <span key={i} className="inv-item spell">✦ {sp}</span>)}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="panel log-outer">
        <span className="panel-title">{s.location}</span>
        <div className="log-scroll" ref={logRef}>
        {log.map((t, i) => (
          <div className="log-entry" key={i}>
            {t.player_input !== '[начало забега]' && (
              <div className="log-player">{t.player_input}</div>
            )}
            {t.rolls?.length > 0 && (
              <div>{t.rolls.map((r, j) => <Roll r={r} key={j} />)}</div>
            )}
            {t.scene_art && <SceneArt tag={t.scene_art} />}
            <div className="log-narration">{t.narration}</div>
          </div>
        ))}
        {busy && <div className="typing">Мастер подземелья думает</div>}
        {error && <p className="error">{error}</p>}
        </div>
      </div>

      {lastActions.length > 0 && (
        <button className="actions-toggle" onClick={() => setShowActions((v) => !v)}>
          {showActions ? '▾' : '▸'} варианты действий ({lastActions.length})
        </button>
      )}
      {showActions && (
        <div className="actions">
          {lastActions.map((a, i) => (
            <button key={i} disabled={busy}
              onClick={() => { setShowActions(false); submit(a) }}>{a}</button>
          ))}
        </div>
      )}

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
