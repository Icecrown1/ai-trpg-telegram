import { useState } from 'react'

const B_ORDER = ['tavern', 'throne', 'forge', 'mage_tower']

export default function CityScreen({ city, user, busy, error, onSend, onNewSeeker, onBuild, onHire }) {
  const [tab, setTab] = useState('city')
  const comps = city.companions || []
  const seekers = city.seekers || []

  return (
    <div className="screen">
      <div className="panel">
        <span className="panel-title">Город у врат Кар-Морда</span>
        <div className="stats">
          <span>КАЗНА <b>{city.gold}</b></span>
          <span>ИСКАТЕЛИ <b>{seekers.length}/{city.seeker_slots}</b></span>
          <span>ДРУЖИНА <b>{comps.length}/{city.companion_slots}</b></span>
          <span className="muted">ходы: {user.turns_left}</span>
        </div>
      </div>

      <div className="actions">
        <button className={tab === 'city' ? 'primary' : ''} onClick={() => setTab('city')}>Здания</button>
        <button className={tab === 'tavern' ? 'primary' : ''} onClick={() => setTab('tavern')}>Таверна</button>
        <button className={tab === 'store' ? 'primary' : ''} onClick={() => setTab('store')}>Склад</button>
      </div>

      {error && <p className="error">{error}</p>}

      {tab === 'city' && (
        <div className="log" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {B_ORDER.map((bid) => {
            const lvl = (city.buildings || {})[bid] || 0
            const up = (city.upgrades || {})[bid]
            return (
              <div className="panel" key={bid}>
                <span className="panel-title">{city.building_names[bid]} · ур.{lvl}</span>
                {up?.locked && <p className="muted">{up.text}</p>}
                {up && !up.locked && (
                  <div>
                    <p className="muted">До ур.{up.level}: {up.desc}</p>
                    <p className="muted">
                      Цена: {Object.entries(up.cost_named).map(([n, c]) => `${n} × ${c}`).join(', ')}
                      {up.gold > 0 && `${Object.keys(up.cost_named).length ? ', ' : ''}золото ${up.gold}`}
                    </p>
                    <button disabled={busy} onClick={() => onBuild(bid)}>▸ Улучшить</button>
                  </div>
                )}
                {!up && lvl > 0 && <p className="muted">Служит городу исправно.</p>}
              </div>
            )
          })}
        </div>
      )}

      {tab === 'tavern' && (
        <div className="log" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <p className="muted">
            {(city.flags || {}).barman_dead
              ? 'За стойкой — подмастерье покойного бармена. Наливает молча.'
              : 'Старый бармен протирает кружку, которая чище не станет.'}
          </p>
          <div className="panel">
            <span className="panel-title">Твоя дружина ({comps.length}/{city.companion_slots})</span>
            {comps.length === 0 && <p className="muted">Пока никого. Столы таверны ждут.</p>}
            {comps.map((c) => (
              <span key={c.name} className="inv-item">
                {c.name} · {c.cls_name} · ❤{c.hp}/{c.max_hp} · верность {c.loyalty}
              </span>
            ))}
            {comps.length > 0 && (
              <p className="muted" style={{ marginTop: 6 }}>Дружина пойдёт со следующим искателем.</p>
            )}
          </div>
          {(city.tavern_patrons || []).map((p) => (
            <div className="panel" key={p.name}>
              <span className="panel-title">{p.name}</span>
              <p className="muted">{p.bio}</p>
              <button disabled={busy} onClick={() => onHire(p.name)}>
                ▸ Нанять за {p.price} зол.
              </button>
            </div>
          ))}
        </div>
      )}

      {tab === 'store' && (
        <div className="panel log">
          <span className="panel-title">Склад города</span>
          {Object.keys(city.resources_named || {}).length === 0 && (
            <p className="muted">Пусто. Ресурсы приносят выжившие.</p>
          )}
          {Object.entries(city.resources_named || {}).map(([n, c]) => (
            <span key={n} className="inv-item">{n} × {c}</span>
          ))}
        </div>
      )}

      <div className="panel">
        <span className="panel-title">В подземелье</span>
        {seekers.filter((s) => s.status === 'idle').map((s) => (
          <button key={s.id} disabled={busy} style={{ marginRight: 8, marginBottom: 6 }}
            onClick={() => onSend(s.id)}>
            ▸ {s.name} · {s.cls_name} ур.{s.level} · выжил {s.runs_survived}
          </button>
        ))}
        {seekers.length < city.seeker_slots && (
          <button className="primary" disabled={busy} onClick={onNewSeeker}>
            ▸ НОВЫЙ ИСКАТЕЛЬ
          </button>
        )}
        {seekers.length >= city.seeker_slots && seekers.every((s) => s.status !== 'idle') && (
          <p className="muted">Свободных искателей нет.</p>
        )}
      </div>
    </div>
  )
}
