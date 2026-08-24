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
