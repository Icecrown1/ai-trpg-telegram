import SceneArt from './SceneArt.jsx'

export default function DeathScreen({ run, onNewRun }) {
  const s = run.state
  return (
    <div className="screen">
      <div className="death">
        <SceneArt tag="skull" />
        <h1>ТЫ МЁРТВ</h1>
        <div className="panel" style={{ width: '100%' }}>
          <span className="panel-title">Эпитафия</span>
          <p>{run.death_cause}</p>
          <table className="stat-table" style={{ marginTop: 10 }}>
            <tbody>
              <tr><td>Герой</td><td>{s.name}</td></tr>
              <tr><td>Уровень</td><td>{s.level}</td></tr>
              <tr><td>Ярус</td><td>{s.depth}</td></tr>
              <tr><td>Золото</td><td>{s.gold}</td></tr>
              <tr><td>Ходов прожито</td><td>{run.turn_count}</td></tr>
            </tbody>
          </table>
        </div>
        <p className="muted">Пермасмерть — это навсегда. Но подземелье ждёт следующего.</p>
        <button className="primary" onClick={onNewRun}>▸ НОВЫЙ ГЕРОЙ</button>
      </div>
    </div>
  )
}


const RES_RU = {
  wood: 'Дерево', wood_hard: 'Прочное дерево', wood_enchanted: 'Зачарованное дерево',
  stone: 'Камень', iron: 'Железная руда', mithril: 'Мифриловая руда',
  leather: 'Кожа', cloth: 'Ткань', bone: 'Кость чудовища',
  ash_essence: 'Пепельная эссенция', soul_shard: 'Осколок души', living_gold: 'Живое золото',
}

export function ExtractScreen({ run, hauled, entryArt, onNewRun }) {
  const s = run.state
  const items = Object.entries(hauled || {})
  return (
    <div className="screen">
      <div className="death">
        <SceneArt tag={entryArt || 'gates'} />
        <h1 style={{ color: 'var(--amber)' }}>ТЫ ВЫБРАЛСЯ</h1>
        <div className="panel" style={{ width: '100%' }}>
          <span className="panel-title">Добыча уехала в город</span>
          {items.length === 0 && <p className="muted">Рюкзак был пуст. Зато жив.</p>}
          {items.map(([k, v]) => (
            <span key={k} className="inv-item">{RES_RU[k] || k} × {v}</span>
          ))}
          <table className="stat-table" style={{ marginTop: 10 }}>
            <tbody>
              <tr><td>Герой</td><td>{s.name} · ур.{s.level}</td></tr>
              <tr><td>Золото в казну</td><td>{s.gold}</td></tr>
              <tr><td>Глубина</td><td>ярус {s.depth}</td></tr>
            </tbody>
          </table>
        </div>
        <p className="muted">Живой искатель может вернуться в глубины.</p>
        <button className="primary" onClick={onNewRun}>▸ В ГОРОД</button>
      </div>
    </div>
  )
}