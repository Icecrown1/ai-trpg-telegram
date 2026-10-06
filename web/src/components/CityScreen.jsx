import { useState } from 'react'
import SceneArt from './SceneArt.jsx'
import Cost, { gearStats } from './Cost.jsx'
import Expedition from './Expedition.jsx'

const B_ORDER = ['tavern', 'throne', 'forge', 'mage_tower']

export default function CityScreen({ city, user, dungeons, busy, error, onSend, onNewSeeker, onBuild, onHire, onCraft, onEnchant, onDaily, isAdmin, onAdmin, tutorial, onDemolish, onChest, onRefine }) {
  const [packing, setPacking] = useState(false)
  const [tab, setTab] = useState('city')
  const ruins = city.ruins || []
  const ruinsLeft = ruins.filter((r) => !r.cleared).length
  const tavernReady = (city.upgrades || {}).tavern && !(city.upgrades || {}).tavern.locked &&
    Object.entries((city.upgrades || {}).tavern?.cost || {}).every(([rid, c]) => (city.resources || {})[rid] >= c)
  const hint = !tutorial ? null
    : ruinsLeft === 2 ? '«Видишь дома через дорогу? Разбирай», — Одо кивает на руины.'
    : ruinsLeft === 1 ? 'Материалы легли на склад. Одо: «Второй дом сам себя не разберёт».'
    : tavernReady ? 'Всё нужное — на складе. Одо: «Теперь строй. Кнопка у таверны, наследник».'
    : 'Одо оглядывает штабеля: «Хорошая работа».' 
  const [craftFor, setCraftFor] = useState(null)
  const [dungeon, setDungeon] = useState((dungeons && dungeons[0]?.id) || 'kar_mord')
  const [enchantFor, setEnchantFor] = useState(null)
  const comps = city.companions || []
  const seekers = city.seekers || []

  return (
    <div className="screen scrollable">
      <SceneArt tag="city" />
      <div className="panel">
        <span className="panel-title">Город у врат Кар-Морда</span>
        <div className="stats">
          <span>КАЗНА <b>{city.gold}</b></span>
          <span>ИСКАТЕЛИ <b>{seekers.length}/{city.seeker_slots}</b></span>
          <span>ДРУЖИНА <b>{comps.length}/{city.companion_slots}</b></span>
          <span>ПОПЫТКИ <b>{city.runs_left}/{city.runs_per_window}</b></span>
          {user.turns_left <= 50 && <span className="muted">ходов на сегодня: {user.turns_left}</span>}
        </div>
      </div>

      {tutorial && (
        <div className="panel" style={{ borderStyle: 'dotted' }}>
          <span className="panel-title">Одо</span>
          <p className="muted" style={{ margin: 0 }}>{hint}</p>
        </div>
      )}

      <div className="actions">
        <button className={tab === 'city' ? 'primary' : ''} onClick={() => setTab('city')}>Здания</button>
        {!tutorial && (
          <button className={tab === 'tavern' ? 'primary' : ''} onClick={() => setTab('tavern')}>Таверна</button>
        )}
        {(city.buildings || {}).forge > 0 && (
          <button className={tab === 'forge' ? 'primary' : ''} onClick={() => setTab('forge')}>Кузница</button>
        )}
        {(city.buildings || {}).mage_tower > 0 && (
          <button className={tab === 'tower' ? 'primary' : ''} onClick={() => setTab('tower')}>Башня</button>
        )}
        {(city.recipes || []).length > 0 && (
          <button className={tab === 'craft' ? 'primary' : ''} onClick={() => setTab('craft')}>Мастерская</button>
        )}
        <button className={tab === 'store' ? 'primary' : ''} onClick={() => setTab('store')}>Склад</button>
      </div>

      {error && <p className="error">{error}</p>}

      {tab === 'city' && (
        <div className="log" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {ruins.map((r) => (
            <div className="panel" key={r.id} style={{ opacity: r.cleared ? 0.45 : 1 }}>
              <span className="panel-title">{r.name}</span>
              <p className="muted">{r.cleared ? 'Разобран до основания.' : r.desc}</p>
              {!r.cleared && (
                <div>
                  <p className="muted">Материалы: {Object.entries(r.loot_named).map(([n, c]) => `${n} × ${c}`).join(', ')}</p>
                  <button className="primary" disabled={busy} onClick={() => onDemolish(r.id)}>▸ Разобрать</button>
                </div>
              )}
            </div>
          ))}
          {(tutorial ? ['tavern'] : B_ORDER).map((bid) => {
            const lvl = (city.buildings || {})[bid] || 0
            const up = (city.upgrades || {})[bid]
            return (
              <div className="panel" key={bid}>
                <span className="panel-title">{city.building_names[bid]} · ур.{lvl}</span>
                {up?.locked && <p className="muted">{up.text}</p>}
                {up && !up.locked && (
                  <div>
                    <p className="muted">До ур.{up.level}: {up.desc}</p>
                    <Cost list={up.cost_list} />
                    <button disabled={busy || up.affordable === false} onClick={() => onBuild(bid)}>
                      {up.affordable === false ? 'Не хватает материалов' : '▸ Улучшить'}
                    </button>
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

      {tab === 'forge' && (
        <div className="log" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <p className="muted">Торин Углебород оглядывает тебя поверх горна: «Ну, кому куём?»</p>
          {(city.craftable || []).map((it) => (
            <div className="panel" key={it.id}>
              <span className="panel-title">{it.name}{!it.available && ` · кузница ур.${it.forge}`}</span>
              <p className="muted">{gearStats(it)}{it.dur ? ` · прочность ${it.dur}` : ''}</p>
              <Cost list={it.cost_list} />
              {it.available && craftFor !== it.id && (
                <button disabled={busy} onClick={() => setCraftFor(it.id)}>▸ Ковать</button>
              )}
              {craftFor === it.id && (
                <div className="actions">
                  {(city.seekers || []).filter((s) => s.status === 'idle').map((s) => (
                    <button key={s.id} disabled={busy}
                      onClick={() => { onCraft(it.id, s.id); setCraftFor(null) }}>
                      для {s.name}
                    </button>
                  ))}
                  <button onClick={() => setCraftFor(null)}>отмена</button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {tab === 'tower' && (
        <div className="log" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <p className="muted">Финеус, не отрываясь от колбы: «А, заказчик! Не трогайте ничего. Особенно вон то».</p>
          {(city.enchantable || []).map((it) => (
            <div className="panel" key={it.id}>
              <span className="panel-title">{it.name}{!it.available && ` · башня ур.${it.tower}`}</span>
              <p className="muted">{it.effect}</p>
              <Cost list={it.cost_list} />
              {it.available && enchantFor !== it.id && (
                <button disabled={busy} onClick={() => setEnchantFor(it.id)}>▸ Заказать</button>
              )}
              {enchantFor === it.id && (
                <div className="actions">
                  {(city.seekers || []).filter((s) => s.status === 'idle').map((s) => (
                    <button key={s.id} disabled={busy}
                      onClick={() => { onEnchant(it.id, s.id); setEnchantFor(null) }}>
                      для {s.name}
                    </button>
                  ))}
                  <button onClick={() => setEnchantFor(null)}>отмена</button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {tab === 'craft' && (
        <div className="log" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <p className="muted">Здания перерабатывают сырьё в материалы для высоких уровней построек.</p>
          {(city.recipes || []).map((r) => (
            <div className="panel" key={r.id}>
              <span className="panel-title">{r.out_name}{!r.available && ` · ${r.building_name} ур.${r.level}`}</span>
              <p className="muted">{r.who}</p>
              <Cost list={r.cost_list} />
              {r.available && (
                <button disabled={busy || !r.cost_list.every((c) => c.ok)} onClick={() => onRefine(r.id)}>
                  ▸ Сделать 1
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {tab === 'store' && (
        <div className="log">
          <div className="panel">
          <span className="panel-title">Склад города</span>
          {Object.keys(city.resources_named || {}).length === 0 && (
            <p className="muted">Пусто. Ресурсы приносят выжившие.</p>
          )}
          {Object.entries(city.resources_named || {}).map(([n, c]) => (
            <span key={n} className="inv-item">{n} × {c}</span>
          ))}
          </div>
          <div className="panel" style={{ marginTop: 10 }}>
            <span className="panel-title">Королевский сундук ({(city.chest || []).length})</span>
            {(city.chest || []).length === 0 && (
              <p className="muted">Пуст. Снятое с искателей кладётся сюда при сборах в поход.</p>
            )}
            {(city.chest || []).map((c, i) => (
              <div key={c.uid || i} className="pack-row">
                <span>{c.name}</span>
                {c.kind === 'gear' && <i className="muted">{gearStats(c)}</i>}
              </div>
            ))}
          </div>
        </div>
      )}

      {city.daily && (
        <div className="panel">
          <span className="panel-title">Поручение трона</span>
          <p className="muted">
            Принести: {city.daily.res_name} × {city.daily.count} · награда {city.daily.reward_gold} зол.
          </p>
          {city.daily.done
            ? <p className="muted">Сдано. Корона довольна. Завтра будет новое.</p>
            : <button disabled={busy || !city.daily.can_claim} onClick={onDaily}>
                {city.daily.can_claim ? '▸ Сдать со склада' : 'На складе не хватает'}
              </button>}
        </div>
      )}

      {isAdmin && !tutorial && (
        <div className="panel" style={{ borderStyle: 'dotted' }}>
          <span className="panel-title">⚙ Админка (тест)</span>
          <div className="actions">
            <button disabled={busy} onClick={() => onAdmin('reset_cooldown')}>Сбросить КД попыток</button>
            <button disabled={busy} onClick={() => onAdmin('reset_prologue')}>Пролог заново</button>
            <button disabled={busy} onClick={() => onAdmin('grant_artifact')}>◈ Артефакт искателям</button>
            <button disabled={busy} style={{ borderColor: 'var(--red, #f66)' }}
              onClick={() => window.confirm('Снести город, искателей и все забеги?') && onAdmin('reset_account')}>
              Полный сброс
            </button>
          </div>
        </div>
      )}

      {!tutorial && (
      <div className="panel">
        <span className="panel-title">В подземелье</span>
        <div className="actions" style={{ marginBottom: 8 }}>
          {(dungeons || []).map((d) => (
            <button key={d.id} className={dungeon === d.id ? 'primary' : ''}
              title={`${d.desc} · ${d.danger}`}
              onClick={() => setDungeon(d.id)}>
              {d.name}
            </button>
          ))}
        </div>
        <p className="muted">{(dungeons || []).find((d) => d.id === dungeon)?.desc}</p>
        {city.runs_left === 0 && (
          <p className="error">Попытки исчерпаны. Следующая через {city.next_run_in}.</p>
        )}
        {!packing && (
          <button className="primary" disabled={busy || city.runs_left === 0} onClick={() => setPacking(true)}>
            ▸ ВОЙТИ В ПОДЗЕМЕЛЬЕ
          </button>
        )}
        {packing && (
          <Expedition city={city} busy={busy}
            dungeon={(dungeons || []).find((d) => d.id === dungeon)}
            onChest={onChest}
            onClose={() => setPacking(false)}
            onEnter={(sid, party) => { setPacking(false); onSend(sid, dungeon, party) }}
            onNewSeeker={(party) => { setPacking(false); onNewSeeker(dungeon, party) }} />
        )}
      </div>
      )}
    </div>
  )
}
