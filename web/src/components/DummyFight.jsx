import { useEffect, useRef, useState } from 'react'

/* Скриптованный бой с манекеном во дворе таверны: инициатива, засада, атака против КД,
   урон, ответный удар по защите, крит. Ноль LLM — только честные кубики на клиенте. */

const d = (n) => Math.floor(Math.random() * n) + 1
const DUMMY_AC = 10
const DUMMY_HP = 10
const YOUR_DEF = 12
const STR = 2
const DEX = 1

export default function DummyFight({ onDone }) {
  const [phase, setPhase] = useState('intro') // intro | fight | done
  const [log, setLog] = useState([])
  const [dummyHp, setDummyHp] = useState(DUMMY_HP)
  const [hp, setHp] = useState(12)
  const [ambush, setAmbush] = useState(false)
  const [triedAmbush, setTriedAmbush] = useState(false)
  const [round, setRound] = useState(1)

  const push = (...lines) => setLog((l) => [...l, ...lines])
  const endRef = useRef(null)
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [log.length, phase])

  const rollInit = () => {
    const you = d(20), dummy = d(20)
    const youT = you + DEX, dummyT = dummy + 0
    push(
      { roll: `Инициатива: ты d20+${DEX} → [${you}] = ${youT} · манекен d20 → [${dummy}] = ${dummyT}` },
      { odo: youT >= dummyT
        ? '«Первый ход твой. Инициатива решает, кто бьёт раньше: в бою её бросают все — ты, твои люди, враги — и ходят по очереди сверху вниз».'
        : '«Пип оказался шустрее — манекен ударит первым. Так бывает: инициатива бросается всем, и очередь в бою мешается как попало».' },
    )
    if (youT < dummyT) dummySwing()
    setPhase('fight')
  }

  const dummySwing = () => {
    const r = d(20), total = r + 2
    if (total >= YOUR_DEF) {
      const dmg = d(4)
      setHp((h) => Math.max(1, h - dmg))
      push({ roll: `Манекен машет бревном: d20+2 → [${r}] = ${total} против твоей защиты ${YOUR_DEF} — ПОПАЛ, урон 1d4 → ${dmg}` },
        { odo: '«Защита — это сколько врагу надо выбросить, чтобы попасть: 10 + ловкость + броня, шлем и щит. Чем больше железа на тебе — тем реже достают».' })
    } else {
      push({ roll: `Манекен машет бревном: d20+2 → [${r}] = ${total} против твоей защиты ${YOUR_DEF} — МИМО` })
    }
  }

  const sneak = () => {
    setTriedAmbush(true)
    const r = d(20), total = r + DEX
    if (total >= 8) {
      setAmbush(true)
      push({ roll: `Засада: ЛОВ d20+${DEX} → [${r}] = ${total} против СЛ 8 — УСПЕХ` },
        { odo: '«Зашёл со спины. Засада — это проверка ловкости: на первом ярусе СЛ 8, глубже строже. Удалась — первый удар сильнее, и враг не отвечает на него».' })
    } else {
      push({ roll: `Засада: ЛОВ d20+${DEX} → [${r}] = ${total} против СЛ 8 — ПРОВАЛ` },
        { odo: '«Скрипнул гравием — Пип тебя услышал. Провал засады — бьёмся на равных».' })
      dummySwing()
    }
  }

  const strike = () => {
    const r = d(20)
    const adv = ambush ? d(6) : 0
    const total = r + STR + adv
    const hit = total >= DUMMY_AC
    const crit = hit && r >= 16
    let line = `Удар мечом: d20+${STR}${adv ? ` +преимущество d6 [${adv}]` : ''} → [${r}] = ${total} против КД манекена ${DUMMY_AC} — ${hit ? 'ПОПАЛ' : 'МИМО'}`
    const lines = []
    let left = dummyHp
    if (hit) {
      const dmg = d(8) + (crit ? d(8) : 0)
      left = Math.max(0, dummyHp - dmg)
      line += ` · урон ${crit ? '2d8 (КРИТ!)' : '1d8'} → ${dmg}`
      lines.push({ roll: line })
      if (crit) lines.push({ odo: '«Чистые 16-20 при попадании — крит: лишний кубик урона, и враг не успевает ответить».' })
      else if (round === 1) lines.push({ odo: '«КД — это броня врага: сколько выбросить, чтобы попасть. Попал — бросаешь урон своим оружием».' })
    } else {
      lines.push({ roll: line }, { odo: '«Не беда. Промах — тоже ход. Следующий раз».' })
    }
    setAmbush(false)
    setDummyHp(left)
    push(...lines)
    if (left <= 0) {
      push({ odo: '«Хватит, хватит, а то кормить его опилками нечем! — Одо смеётся. — Внизу всё так же, только манекены бьют больнее и думают. Бой там ведёт мастер, а кубики бросает сама судьба — честно, у всех на виду».' })
      setPhase('done')
      return
    }
    if (!(hit && crit) && !(adv)) dummySwing()
    setRound((n) => n + 1)
  }

  return (
    <div>
      <div className="combat" style={{ marginBottom: 8 }}>
        <div className="combat-row ally you">
          <span className="init">★</span><span className="who">Ты</span>
          <span className="hpbar"><i style={{ width: `${Math.round((100 * hp) / 12)}%` }} /></span>
          <span className="hpnum">{hp}/12</span>
        </div>
        <div className="combat-row enemy">
          <span className="init">☠</span><span className="who">Соломенный манекен · КД {DUMMY_AC}</span>
          <span className="hpbar"><i style={{ width: `${Math.round((100 * dummyHp) / DUMMY_HP)}%` }} /></span>
          <span className="hpnum">{dummyHp}/{DUMMY_HP}</span>
        </div>
      </div>

      {log.map((l, i) => (l.roll
        ? <div key={i}><span className="roll">{l.roll}</span></div>
        : <p key={i} className="log-narration" style={{ margin: '6px 0' }}>{l.odo}</p>))}

      <div className="actions" style={{ marginTop: 8 }}>
        {phase === 'intro' && (
          <button className="primary" onClick={rollInit}>🎲 Бросить инициативу</button>
        )}
        {phase === 'fight' && (
          <>
            {!triedAmbush && round === 1 && (
              <button onClick={sneak}>Подкрасться со спины (засада, ЛОВ СЛ 8)</button>
            )}
            <button className="primary" onClick={strike}>Ударить мечом (СИЛ +{STR} против КД {DUMMY_AC})</button>
          </>
        )}
        {phase === 'done' && (
          <button className="primary" onClick={onDone}>▸ Дальше</button>
        )}
      </div>
      <div ref={endRef} />
    </div>
  )
}
