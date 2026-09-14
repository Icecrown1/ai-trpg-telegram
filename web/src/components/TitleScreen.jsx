import { useEffect } from 'react'
import SceneArt from './SceneArt.jsx'
import { ALL_ART } from '../artList.js'

const GAME_TITLE = 'THE LAST KING'
const TAGLINE = 'последний город · последний король'

export default function TitleScreen({ ready, onEnter }) {
  useEffect(() => {
    // прогрев кэша: по три картинки одновременно, не мешая интерфейсу
    let i = 0
    const next = () => {
      if (i >= ALL_ART.length) return
      const img = new Image()
      img.onload = img.onerror = next
      img.src = `/art/${ALL_ART[i++]}.webp`
    }
    next(); next(); next()
  }, [])

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
