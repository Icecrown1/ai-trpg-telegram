import { useEffect, useState } from 'react'

/* Rolls the first die on screen: spinning numbers settle on the real result. */
export default function DiceOverlay({ rolls, onDone }) {
  const r = rolls[0]
  const [face, setFace] = useState('?')
  const [settled, setSettled] = useState(false)

  useEffect(() => {
    let ticks = 0
    const spin = setInterval(() => {
      ticks += 1
      setFace(1 + Math.floor(Math.random() * r.sides))
      if (ticks >= 12) {
        clearInterval(spin)
        setFace(r.rolls[0])
        setSettled(true)
        setTimeout(onDone, 900)
      }
    }, 70)
    return () => clearInterval(spin)
  }, [])

  return (
    <div className="dice-overlay" onClick={settled ? onDone : undefined}>
      <div style={{ textAlign: 'center' }}>
        <div className="d20"><span>{face}</span></div>
        <p className="muted" style={{ marginTop: 18 }}>
          {r.reason || 'Бросок'} · d{r.sides}
        </p>
      </div>
    </div>
  )
}
