import { useState } from 'react'

const TITLE = String.raw`
 ██╗  ██╗ █████╗ ██████╗       ███╗   ███╗ ██████╗ ██████╗ ██████╗
 ██║ ██╔╝██╔══██╗██╔══██╗      ████╗ ████║██╔═══██╗██╔══██╗██╔══██╗
 █████╔╝ ███████║██████╔╝█████╗██╔████╔██║██║   ██║██████╔╝██║  ██║
 ██╔═██╗ ██╔══██║██╔══██╗╚════╝██║╚██╔╝██║██║   ██║██╔══██╗██║  ██║
 ██║  ██╗██║  ██║██║  ██║      ██║ ╚═╝ ██║╚██████╔╝██║  ██║██████╔╝
 ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝      ╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝`

export default function CharacterCreate({ meta, user, busy, error, onCreate }) {
  const [name, setName] = useState('')
  const [race, setRace] = useState('human')
  const [cls, setCls] = useState('fighter')

  const canGo = name.trim().length > 0 && !busy

  return (
    <div className="screen">
      <pre className="title-art">{TITLE}</pre>
      <p className="muted" style={{ textAlign: 'center' }}>
        текстовое подземелье · пермасмерть · честный d20
      </p>

      {user?.total_runs > 0 && (
        <div className="panel">
          <span className="panel-title">Летопись</span>
          <div className="stats">
            <span>Забегов: <b>{user.total_runs}</b></span>
            <span>Глубина: <b>ярус {user.deepest_level}</b></span>
            <span>Рекорд золота: <b>{user.best_gold}</b></span>
          </div>
        </div>
      )}

      <div className="panel">
        <span className="panel-title">Имя героя</span>
        <input
          type="text"
          maxLength={24}
          placeholder="Как тебя запомнит подземелье?"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </div>

      <div className="panel">
        <span className="panel-title">Раса</span>
        <div className="choice-grid">
          {Object.entries(meta.races).map(([key, label]) => (
            <button
              key={key}
              className={`choice ${race === key ? 'selected' : ''}`}
              onClick={() => setRace(key)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="panel">
        <span className="panel-title">Класс</span>
        <div className="choice-grid">
          {Object.entries(meta.classes).map(([key, c]) => (
            <button
              key={key}
              className={`choice ${cls === key ? 'selected' : ''}`}
              onClick={() => setCls(key)}
            >
              {c.name}
              <small>{c.desc}</small>
            </button>
          ))}
        </div>
      </div>

      {error && <p className="error">{error}</p>}

      <button
        className="primary"
        disabled={!canGo}
        onClick={() => onCreate({ name: name.trim(), race, class: cls })}
      >
        {busy ? 'Кости брошены…' : '▸ ВОЙТИ В ПОДЗЕМЕЛЬЕ'}
      </button>
      <p className="muted" style={{ textAlign: 'center' }}>
        Характеристики бросаются честными 3d6. Смерть окончательна.
      </p>
    </div>
  )
}
