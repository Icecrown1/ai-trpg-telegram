import { useState } from 'react'
import { gearStats, SLOT_RU, WEAR } from './Cost.jsx'

/* Сборы в поход: 1) кто идёт  2) что надеть и взять из сундука  3) кто из дружины  4) войти. */
export default function Expedition({ city, dungeon, busy, onChest, onEnter, onNewSeeker, onClose }) {
  const idle = (city.seekers || []).filter((s) => s.status === 'idle')
  const canNew = (city.seekers || []).length < city.seeker_slots
  const [step, setStep] = useState('seeker')
  const [sid, setSid] = useState(null)
  const comps = city.companions || []
  const [party, setParty] = useState(comps.map((c) => c.name))
  const seeker = idle.find((s) => s.id === sid)
  const chest = city.chest || []
  const isNew = sid === 'new'

  const toggle = (name) => setParty((p) => (p.includes(name) ? p.filter((n) => n !== name) : [...p, name]))
  const steps = isNew ? ['seeker', 'party'] : ['seeker', 'loadout', 'party']
  const idx = steps.indexOf(step)

  return (
    <div className="panel expedition">
      <span className="panel-title">
        Сборы · {dungeon?.name} · шаг {idx + 1}/{steps.length}
      </span>

      {step === 'seeker' && (
        <div>
          <p className="muted">Кто спустится?</p>
          {idle.map((s) => (
            <button key={s.id} disabled={busy} className={sid === s.id ? 'primary' : ''}
              style={{ display: 'block', width: '100%', textAlign: 'left', marginBottom: 6 }}
              onClick={() => { setSid(s.id); setStep('loadout') }}>
              ▸ {s.name} · {s.cls_name} ур.{s.level} · ❤{s.max_hp} · защита {s.defense}
              {s.equipment?.weapon && ` · ${s.equipment.weapon.name}`}
            </button>
          ))}
          {canNew && (
            <button className="primary" disabled={busy} style={{ display: 'block', width: '100%' }}
              onClick={() => { setSid('new'); setStep('party') }}>▸ НОВЫЙ ИСКАТЕЛЬ</button>
          )}
          {!idle.length && !canNew && <p className="muted">Свободных искателей нет.</p>}
        </div>
      )}

      {step === 'loadout' && seeker && (
        <div>
          <p className="muted">{seeker.name}: надетое уходит вниз с ним. Погибнет — сгинет всё, что на нём и в сумке.</p>
          {WEAR.map((sl) => {
            const it = seeker.equipment?.[sl]
            return (
              <div className="pack-row" key={sl}>
                <span>{SLOT_RU[sl]}: {it ? <><b>{it.name}</b> <i className="muted">{gearStats(it)}</i></> : <i className="muted">пусто</i>}</span>
                {it && (
                  <span className="row-btns">
                    <button disabled={busy} onClick={() => onChest({ seeker_id: seeker.id, action: 'unequip', slot: sl })}>в сумку</button>
                    <button disabled={busy} onClick={() => onChest({ seeker_id: seeker.id, action: 'put', slot: sl })}>в сундук</button>
                  </span>
                )}
              </div>
            )
          })}
          <p className="muted" style={{ margin: '8px 0 2px' }}>Сумка ({(seeker.bag || []).length}/6):</p>
          {(seeker.bag || []).length === 0 && <p className="muted">пусто</p>}
          {(seeker.bag || []).map((it) => (
            <div className="pack-row" key={it.uid}>
              <span>{it.name} <i className="muted">{gearStats(it)}</i></span>
              <span className="row-btns">
                <button disabled={busy} onClick={() => onChest({ seeker_id: seeker.id, action: 'equip', uid: it.uid })}>надеть</button>
                <button disabled={busy} onClick={() => onChest({ seeker_id: seeker.id, action: 'put', uid: it.uid })}>в сундук</button>
              </span>
            </div>
          ))}
          {(seeker.inventory || []).length > 0 && (
            <>
              <p className="muted" style={{ margin: '8px 0 2px' }}>Мелочь при себе:</p>
              {seeker.inventory.map((n) => (
                <div className="pack-row" key={n}>
                  <span>{n}</span>
                  <button disabled={busy} onClick={() => onChest({ seeker_id: seeker.id, action: 'put', item: n })}>в сундук</button>
                </div>
              ))}
            </>
          )}
          <p className="muted" style={{ margin: '8px 0 2px' }}>Королевский сундук ({chest.length}):</p>
          {chest.length === 0 && <p className="muted">пуст</p>}
          {chest.map((c, i) => (
            <div className="pack-row" key={c.uid || `i${i}`}>
              <span>{c.kind === 'gear' ? <>{c.name} <i className="muted">{gearStats(c)}</i></> : c.name}</span>
              <span className="row-btns">
                {c.kind === 'gear' && (
                  <button disabled={busy} onClick={() => onChest({ seeker_id: seeker.id, action: 'equip', uid: c.uid })}>надеть</button>
                )}
                <button disabled={busy} onClick={() => onChest(c.kind === 'gear'
                  ? { seeker_id: seeker.id, action: 'take', uid: c.uid }
                  : { seeker_id: seeker.id, action: 'take', index: i })}>взять</button>
              </span>
            </div>
          ))}
        </div>
      )}

      {step === 'party' && (
        <div>
          <p className="muted">Кто из дружины идёт? Остальные ждут в таверне.</p>
          {comps.length === 0 && <p className="muted">Дружины нет — пойдёшь один. Нанять можно в таверне.</p>}
          {comps.map((c) => (
            <label key={c.name} className="pack-row" style={{ cursor: 'pointer' }}>
              <span>{party.includes(c.name) ? '☑' : '☐'} {c.name} · {c.cls_name} · ❤{c.hp}/{c.max_hp} · верность {c.loyalty}</span>
              <input type="checkbox" checked={party.includes(c.name)} onChange={() => toggle(c.name)}
                style={{ display: 'none' }} />
            </label>
          ))}
        </div>
      )}

      <div className="actions" style={{ marginTop: 10 }}>
        <button disabled={busy} onClick={() => (idx > 0 ? setStep(steps[idx - 1]) : onClose())}>
          ◂ {idx > 0 ? 'назад' : 'отмена'}
        </button>
        {step === 'loadout' && (
          <button className="primary" disabled={busy} onClick={() => setStep('party')}>дальше ▸</button>
        )}
        {step === 'party' && (
          <button className="primary" disabled={busy || city.runs_left === 0}
            onClick={() => (isNew ? onNewSeeker(party) : onEnter(seeker.id, party))}>
            {isNew ? '▸ СОЗДАТЬ И ВОЙТИ' : '▸ ВОЙТИ В ПОДЗЕМЕЛЬЕ'}
          </button>
        )}
      </div>
    </div>
  )
}
