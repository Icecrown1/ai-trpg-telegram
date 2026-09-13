import SceneArt from './SceneArt.jsx'

const GAME_TITLE = 'КАР-МОРД'
const TAGLINE = 'город наверху · тьма внизу'

export default function TitleScreen({ ready, onEnter }) {
  return (
    <div className="screen title-screen" onClick={() => ready && onEnter()}>
      <div className="title-art">
        <SceneArt tag="title" />
      </div>
      <h1 className="game-title">{GAME_TITLE}</h1>
      <p className="tagline">{TAGLINE}</p>
      <p className={`press-key ${ready ? 'blink' : ''}`}>
        {ready ? '▸ КОСНИСЬ, ЧТОБЫ ВОЙТИ' : 'подземелье просыпается…'}
      </p>
    </div>
  )
}
