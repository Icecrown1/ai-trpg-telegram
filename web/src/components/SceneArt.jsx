import { useState } from 'react'
import { ART } from '../art.js'

/* Сначала пробуем растровую иллюстрацию /art/<tag>.png (кладутся в web/public/art/),
   если файла нет — символьный арт из библиотеки. */
export default function SceneArt({ tag }) {
  const [imgFailed, setImgFailed] = useState(false)
  if (!tag) return null
  if (!imgFailed) {
    return (
      <img
        className="scene-img"
        src={`/art/${tag}.png`}
        alt=""
        onError={() => setImgFailed(true)}
      />
    )
  }
  if (ART[tag]) return <pre className="scene-art">{ART[tag]}</pre>
  return null
}
