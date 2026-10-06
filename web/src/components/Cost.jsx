/* Цена «есть / нужно»: ✓ хватает — янтарь, ✗ не хватает — красным с тем, сколько есть. */
export default function Cost({ list }) {
  if (!list || !list.length) return null
  return (
    <div className="cost">
      {list.map((c) => (
        <span key={c.id} className={`cost-item ${c.ok ? 'ok' : 'miss'}`}>
          {c.ok ? '✓' : '✗'} {c.name} <b>{c.have}/{c.need}</b>
        </span>
      ))}
    </div>
  )
}

/* Строка характеристик вещи снаряжения */
export function gearStats(it) {
  if (!it) return ''
  const p = []
  if (it.dmg) p.push(`урон ${it.dmg}${it.atk ? `, попад. +${it.atk}` : ''}`)
  if (it.def) p.push(`защита +${it.def}`)
  if (it.capacity) p.push(`рюкзак +${it.capacity}`)
  if (it.two_handed) p.push('двуручное')
  if (it.props) p.push(it.props)
  if (it.value) p.push(`${it.value} зол.`)
  return p.join(' · ')
}

export const SLOT_RU = { weapon: '⚔ Оружие', offhand: '🛡 Левая рука', head: '⛑ Голова', armor: '◼ Тело', pack: '🎒 Рюкзак' }
export const WEAR = ['weapon', 'offhand', 'head', 'armor']
