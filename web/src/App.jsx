import { useEffect, useState } from 'react'
import { api, haptic } from './api.js'
import CharacterCreate from './components/CharacterCreate.jsx'
import CityScreen from './components/CityScreen.jsx'
import PrologueScreen from './components/PrologueScreen.jsx'
import TitleScreen from './components/TitleScreen.jsx'
import GameScreen from './components/GameScreen.jsx'
import DeathScreen, { ExtractScreen } from './components/DeathScreen.jsx'

export default function App() {
  const [meta, setMeta] = useState(null)
  const [user, setUser] = useState(null)
  const [city, setCity] = useState(null)
  const [creating, setCreating] = useState(false)
  const [dungeon, setDungeon] = useState('kar_mord')
  const [entered, setEntered] = useState(false)
  const [isAdmin, setIsAdmin] = useState(false)
  const [tutorialDone, setTutorialDone] = useState(false)  // акт 1 пройден -> город
  const [run, setRun] = useState(null) // { run_id, status, state, turn_count, log }
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [booted, setBooted] = useState(false)

  useEffect(() => {
    api.adminCheck().then((r) => setIsAdmin(!!r.admin)).catch(() => {})
    Promise.all([api.meta(), api.me(), api.city()])
      .then(([m, me, c]) => {
        setMeta(m)
        setUser(me.user)
        setCity(c)
        if (me.run) setRun(me.run)
      })
      .catch((e) => setError(e.message))
      .finally(() => setBooted(true))
  }, [])

  const refreshTurnsLeft = () =>
    setUser((u) => ({ ...u, turns_left: Math.max(0, u.turns_left - 1) }))

  const mergeTurn = (payload) => {
    setRun((prev) => {
      const log = [...(prev?.log || []), { ...payload.last, justArrived: true }]
      return { ...payload, log }
    })
    if (payload.last?.rolls?.length) haptic('medium')
  }

  const refreshCity = () => api.city().then(setCity).catch(() => {})

  const handleCreate = async (body) => {
    setBusy(true)
    setError('')
    try {
      const payload = await api.newRun(body)
      refreshTurnsLeft()
      mergeTurn(payload)
      setCreating(false)
      refreshCity()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const handleSendSeeker = (seekerId, dungeonId) => handleCreate({ seeker_id: seekerId, dungeon: dungeonId })

  const handleBuild = async (building) => {
    setBusy(true); setError('')
    try { setCity(await api.build(building)); refreshCity() }
    catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }

  const handleCraft = async (itemId, seekerId) => {
    setBusy(true); setError('')
    try { setCity(await api.craft(itemId, seekerId)) }
    catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }

  const handleEnchant = async (itemId, seekerId) => {
    setBusy(true); setError('')
    try { setCity(await api.enchant(itemId, seekerId)) }
    catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }

  const handleSpendStat = async (stat) => {
    setBusy(true); setError('')
    try {
      const { state } = await api.levelup(run.run_id, stat)
      setRun((r) => ({ ...r, state }))
    } catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }

  const handlePickTalent = async (talentId) => {
    setBusy(true); setError('')
    try {
      const { state } = await api.talent(run.run_id, talentId)
      setRun((r) => ({ ...r, state }))
    } catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }

  const handleDemolish = async (ruinId) => {
    setBusy(true); setError('')
    try { setCity(await api.demolish(ruinId)) }
    catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }

  const handleAdmin = async (what) => {
    setBusy(true); setError('')
    try {
      await api.adminReset(what)
      if (what === 'reset_account' || what === 'reset_prologue') { setRun(null); setTutorialDone(false) }
      const [me, c] = await Promise.all([api.me(), api.city()])
      setUser(me.user); setCity(c); if (!me.run) setRun(null)
    } catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }

  const handlePrologueDone = async () => {
    setBusy(true); setError('')
    try {
      setCity(await api.prologueDone())
      setCreating(true) // сразу к созданию первого искателя — как велел Одо
    } catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }

  const handleDaily = async () => {
    setBusy(true); setError('')
    try { setCity(await api.dailyClaim()) }
    catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }

  const handleHire = async (name) => {
    setBusy(true); setError('')
    try { setCity(await api.hire(name)) }
    catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }

  const handleTurn = async (text) => {
    setBusy(true)
    setError('')
    setRun((r) => ({ ...r, log: [...r.log, { player_input: text, narration: '', rolls: [], pending: true }] }))
    try {
      const payload = await api.turn(run.run_id, text)
      refreshTurnsLeft()
      setRun((prev) => {
        const log = prev.log.filter((t) => !t.pending)
        log.push({ player_input: text, ...payload.last, justArrived: true })
        return { ...payload, log }
      })
      if (payload.last?.rolls?.length) haptic('medium')
      if (payload.status === 'dead') haptic('heavy')
    } catch (e) {
      setError(e.message)
      setRun((prev) => ({ ...prev, log: prev.log.filter((t) => !t.pending) }))
    } finally {
      setBusy(false)
    }
  }

  const handleAbandon = async () => {
    if (!confirm('Покинуть подземелье? Забег будет засчитан как потерянный.')) return
    try {
      await api.abandon(run.run_id)
      setRun(null)
      setUser((u) => ({ ...u, total_runs: u.total_runs + 1 }))
    } catch (e) {
      setError(e.message)
    }
  }

  if (!booted) {
    return (
      <div className="crt">
        <div className="screen" style={{ justifyContent: 'center', alignItems: 'center' }}>
          <p className="typing">Загрузка подземелья</p>
        </div>
      </div>
    )
  }

  if (!meta) {
    return (
      <div className="crt">
        <div className="screen" style={{ justifyContent: 'center' }}>
          <p className="error">{error || 'Сервер недоступен'}</p>
        </div>
      </div>
    )
  }

  const prologueActive = city && !(city.flags || {}).prologue_done
  const tavernBuilt = city && (city.buildings || {}).tavern >= 1
  const ruinsTouched = city && ((city.ruins || []).some((r) => r.cleared))
  const inTutorial = prologueActive && (tutorialDone || ruinsTouched) && !tavernBuilt

  let screen
  if (!entered) {
    screen = <TitleScreen ready={!!(meta && user && city)} onEnter={() => setEntered(true)} />
  } else if (!run && !creating && prologueActive && !tutorialDone && !ruinsTouched && !tavernBuilt) {
    screen = <PrologueScreen busy={busy} part={1} onDone={() => setTutorialDone(true)} />
  } else if (!run && !creating && inTutorial) {
    screen = (
      <CityScreen city={city} user={user} dungeons={meta?.dungeons} busy={busy} error={error}
        tutorial onDemolish={handleDemolish} onBuild={handleBuild}
        onSend={() => {}} onNewSeeker={() => {}} onHire={() => {}} onCraft={() => {}}
        onEnchant={() => {}} onDaily={() => {}} isAdmin={false} onAdmin={() => {}} />
    )
  } else if (!run && !creating && prologueActive && tavernBuilt) {
    screen = <PrologueScreen busy={busy} part={2} onDone={handlePrologueDone} />
  } else if (!run && !creating) {
    screen = city ? (
      <CityScreen city={city} user={user} dungeons={meta?.dungeons} busy={busy} error={error}
        isAdmin={isAdmin} onAdmin={handleAdmin}
        onSend={handleSendSeeker} onNewSeeker={(d) => { setDungeon(d); setCreating(true); setError('') }}
        onBuild={handleBuild} onHire={handleHire} onCraft={handleCraft}
        onEnchant={handleEnchant} onDaily={handleDaily} />
    ) : (
      <CharacterCreate meta={meta} user={user} busy={busy} error={error} onCreate={handleCreate} />
    )
  } else if (!run && creating) {
    screen = (
      <CharacterCreate meta={meta} user={user} busy={busy} error={error}
        onCreate={(body) => handleCreate({ ...body, dungeon })}
        onBack={() => setCreating(false)} />
    )
  } else if (run.status === 'dead') {
    screen = <DeathScreen run={run} onNewRun={() => { setRun(null); setError(''); refreshCity() }} />
  } else if (run.status === 'extracted') {
    screen = <ExtractScreen run={run} hauled={run.hauled}
      entryArt={meta?.dungeons?.find((d) => d.id === run.dungeon)?.entry_art}
      onNewRun={() => { setRun(null); setError(''); refreshCity() }} />
  } else {
    screen = (
      <GameScreen
        run={run}
        user={user}
        meta={meta}
        busy={busy}
        error={error}
        onTurn={handleTurn}
        onAbandon={handleAbandon}
        onSpendStat={handleSpendStat}
        onPickTalent={handlePickTalent}
      />
    )
  }

  return (
    <div className="crt">
      {screen}
      <p className="version">
        клиент {typeof __CLIENT_VERSION__ !== 'undefined' ? __CLIENT_VERSION__ : 'dev'}
        {meta?.server_version && <> · сервер {meta.server_version}</>}
      </p>
    </div>
  )
}
