<script setup>
import { ref, computed, nextTick, onMounted, onUnmounted } from 'vue'

const files = ref([])
const rawDocuments = ref([])
const documents = ref([])
const splitVersion = ref(Date.now())

const createEmptySelections = () => ({
  first: { instrument: null, page: null },
  second: { instrument: null, page: null },
  third: { instrument: null, page: null }
})

const selections = ref(createEmptySelections())
const ocrProfiles = ref({ first: null, second: null, third: null })
const referencePages = ref({ first: '', second: '', third: '' })
const projectTitle = ref('')
const savedProjects = ref(JSON.parse(localStorage.getItem('noten-projects') || '[]'))
const returnMode = ref('empty')
const pages = ref([])
const currentIndex = ref(0)
const mode = ref('empty')
const rules = ref([])
const rulesLoaded = ref(false)
const isBusy = ref(false)
const instrumentInput = ref(null)
const activeTarget = ref(null)
const drawing = ref(null)
const draggingSplitDocIndex = ref(null)

const referenceMeta = [
  { key: 'first', title: '1. Referenzseite (Seite 1 / Titel)' },
  { key: 'second', title: '2. Referenzseite (Gerade Seiten: 2, 4, …)' },
  { key: 'third', title: '3. Referenzseite (Ungerade Seiten: 3, 5, …)' }
]

const currentPage = computed(() => pages.value[currentIndex.value] || null)

// Dynamische Gruppierung aller Seiten nach Instrument (Notensätze)
const instrumentSets = computed(() => {
  const map = new Map()
  pages.value.forEach((page, index) => {
    const rawName = (page.instrument || '').trim()
    const name = rawName || 'Unbenannt'
    if (!map.has(name)) {
      map.set(name, {
        name,
        pages: []
      })
    }
    map.get(name).pages.push({ ...page, pageIndex: index })
  })
  return Array.from(map.values())
})

const loadRules = async () => {
  const response = await fetch('http://127.0.0.1:8000/instrument-rules/')
  if (!response.ok) throw new Error('Regeln konnten nicht geladen werden')
  const data = await response.json()
  rules.value = data.regeln.map((rule) => ({ ...rule }))
  rulesLoaded.value = true
}

const openRules = async () => {
  try {
    await loadRules()
    returnMode.value = mode.value
    mode.value = 'rules'
  } catch (error) {
    alert(error.message)
  }
}

const backFromRules = () => {
  mode.value = returnMode.value
}

const persistProjects = () => {
  localStorage.setItem('noten-projects', JSON.stringify(savedProjects.value))
}

const saveProject = () => {
  const title = projectTitle.value.trim()
  if (!title) {
    alert('Bitte einen Titel für den Notensatz eingeben.')
    return
  }
  const project = {
    title,
    referencePages: referencePages.value,
    selections: selections.value
  }
  const existingIndex = savedProjects.value.findIndex((item) => item.title === title)
  if (existingIndex >= 0) savedProjects.value[existingIndex] = project
  else savedProjects.value.push(project)
  persistProjects()
  alert('Notensatz-Projekt gespeichert.')
}

const loadProject = (project) => {
  if (!project) return
  if (!documents.value.length) {
    alert('Bitte zuerst die PDFs hochladen und den Schnitt bestätigen.')
    return
  }
  projectTitle.value = project.title
  referencePages.value = {
    first: project.referencePages?.first || '0:1',
    second: project.referencePages?.second || '0:1',
    third: project.referencePages?.third || project.referencePages?.second || '0:1'
  }
  const loadedSelections = JSON.parse(JSON.stringify(project.selections || {}))
  selections.value = {
    first: loadedSelections.first || { instrument: null, page: null },
    second: loadedSelections.second || { instrument: null, page: null },
    third: loadedSelections.third || { instrument: null, page: null }
  }
  mode.value = 'mark'
}

const deleteProject = (title) => {
  savedProjects.value = savedProjects.value.filter((project) => project.title !== title)
  persistProjects()
}

const addRule = () => rules.value.push({ erkannt: '', ziel: '' })
const removeRule = (index) => rules.value.splice(index, 1)

const saveRules = async () => {
  const response = await fetch('http://127.0.0.1:8000/instrument-rules/', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(rules.value)
  })
  if (!response.ok) throw new Error('Regeln konnten nicht gespeichert werden')
  const data = await response.json()
  rules.value = data.regeln
  alert('Instrument-Regeln gespeichert.')
}

const onFileChange = (event) => {
  files.value = Array.from(event.target.files)
}

const uploadAndPrepare = async () => {
  if (!files.value.length) return
  isBusy.value = true
  const formData = new FormData()
  files.value.forEach((file) => formData.append('files', file))

  try {
    const response = await fetch('http://127.0.0.1:8000/upload/', { method: 'POST', body: formData })
    if (!response.ok) throw new Error(`Upload fehlgeschlagen (${response.status})`)
    const data = await response.json()
    rawDocuments.value = data.dokumente.map((doc) => ({
      ...doc,
      previewPage: 1,
      target_format: doc.target_format || 'a4'
    }))
    mode.value = 'split'
  } catch (error) {
    alert(`Fehler beim Hochladen: ${error.message}`)
  } finally {
    isBusy.value = false
  }
}

const uploadPreviewUrl = (rawDoc) =>
  `http://127.0.0.1:8000/preview-upload/${encodeURIComponent(rawDoc.original_name)}/${rawDoc.previewPage}?rotation=${rawDoc.rotation}`

const rotateDoc = (rawDoc, delta) => {
  rawDoc.rotation = (rawDoc.rotation + delta + 360) % 360
}

const adjustSplit = (rawDoc, delta) => {
  rawDoc.split_ratio = Math.round(Math.max(0.1, Math.min(0.9, rawDoc.split_ratio + delta)) * 1000) / 1000
}

const applySplitToAll = (sourceDoc) => {
  rawDocuments.value.forEach((doc) => {
    doc.rotation = sourceDoc.rotation
    doc.split_ratio = sourceDoc.split_ratio
    doc.enabled = sourceDoc.enabled
    doc.target_format = sourceDoc.target_format
  })
}

const startSplitDrag = (event, docIndex) => {
  if (!rawDocuments.value[docIndex].enabled) return
  draggingSplitDocIndex.value = docIndex
  updateSplitDrag(event, docIndex)
  event.currentTarget.setPointerCapture(event.pointerId)
}

const updateSplitDrag = (event, docIndex) => {
  if (draggingSplitDocIndex.value !== docIndex) return
  const bounds = event.currentTarget.getBoundingClientRect()
  const ratio = (event.clientX - bounds.left) / bounds.width
  rawDocuments.value[docIndex].split_ratio = Math.round(Math.max(0.1, Math.min(0.9, ratio)) * 1000) / 1000
}

const finishSplitDrag = () => {
  draggingSplitDocIndex.value = null
}

const confirmSplitAndContinue = async () => {
  if (!rawDocuments.value.length) return
  isBusy.value = true
  try {
    const payload = rawDocuments.value.map((doc) => ({
      original_name: doc.original_name,
      rotation: doc.rotation,
      split_ratio: doc.split_ratio,
      enabled: doc.enabled,
      target_format: doc.target_format || 'a4'
    }))
    const response = await fetch('http://127.0.0.1:8000/split/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    if (!response.ok) throw new Error(`Schnitt fehlgeschlagen (${response.status})`)
    const data = await response.json()
    documents.value = data.dokumente
    selections.value = createEmptySelections()
    splitVersion.value = Date.now()

    const docWith2Pages = documents.value.findIndex((d) => d.page_count >= 2)
    const docWith3Pages = documents.value.findIndex((d) => d.page_count >= 3)

    referencePages.value = {
      first: '0:1',
      second: docWith2Pages >= 0 ? `${docWith2Pages}:2` : '0:1',
      third: docWith3Pages >= 0 ? `${docWith3Pages}:3` : (docWith2Pages >= 0 ? `${docWith2Pages}:2` : '0:1')
    }
    mode.value = 'mark'
  } catch (error) {
    alert(`Fehler beim Schneiden: ${error.message}`)
  } finally {
    isBusy.value = false
  }
}

const previewUrl = (document, page) => {
  if (!document || !document.filename) return ''
  return `http://127.0.0.1:8000/preview/${encodeURIComponent(document.filename)}/${page}?v=${splitVersion.value}`
}

const referenceChoice = (sample) => {
  const val = referencePages.value[sample]
  if (!val) return { document: null, page: 1 }
  const [documentIndex, page] = val.split(':').map(Number)
  return { document: documents.value[documentIndex], page }
}

const referenceOptions = computed(() =>
  documents.value.flatMap((document, documentIndex) =>
    Array.from({ length: document.page_count }, (_, index) => ({
      value: `${documentIndex}:${index + 1}`,
      label: `${document.original_name} - A4-Seite ${index + 1}`
    }))
  )
)

const regionStyle = (region) =>
  region
    ? {
        left: `${region.x * 100}%`,
        top: `${region.y * 100}%`,
        width: `${region.width * 100}%`,
        height: `${region.height * 100}%`
      }
    : {}

const pointInPreview = (event) => {
  const bounds = event.currentTarget.getBoundingClientRect()
  if (!bounds.width || !bounds.height) return { x: 0, y: 0 }
  return {
    x: Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width)),
    y: Math.max(0, Math.min(1, (event.clientY - bounds.top) / bounds.height))
  }
}

const chooseTarget = (sample, type) => {
  activeTarget.value = { sample, type }
}

const clearSelection = (sample) => {
  selections.value[sample] = { instrument: null, page: null }
}

const startMark = (event, sample) => {
  const target = activeTarget.value
  if (!target || target.sample !== sample) return
  drawing.value = { ...target, start: pointInPreview(event) }
  event.currentTarget.setPointerCapture(event.pointerId)
}

const updateMark = (event, sample) => {
  if (!drawing.value || drawing.value.sample !== sample) return
  const point = pointInPreview(event)
  const start = drawing.value.start
  selections.value[sample][drawing.value.type] = {
    x: Math.min(start.x, point.x),
    y: Math.min(start.y, point.y),
    width: Math.abs(point.x - start.x),
    height: Math.abs(point.y - start.y)
  }
}

const finishMark = () => {
  drawing.value = null
  activeTarget.value = null
}

const processDocuments = async () => {
  isBusy.value = true
  try {
    ocrProfiles.value = {
      first: { instrument: selections.value.first.instrument, page: selections.value.first.page },
      second: { instrument: selections.value.second.instrument, page: selections.value.second.page },
      third: { instrument: selections.value.third.instrument, page: selections.value.third.page }
    }
    const payload = documents.value.map((document) => ({
      filename: document.filename,
      first_instrument: selections.value.first.instrument,
      first_page_number: selections.value.first.page,
      second_instrument: selections.value.second.instrument,
      second_page_number: selections.value.second.page,
      third_instrument: selections.value.third.instrument,
      third_page_number: selections.value.third.page
    }))
    const response = await fetch('http://127.0.0.1:8000/process/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    if (!response.ok) throw new Error(`OCR fehlgeschlagen (${response.status})`)
    const data = await response.json()
    pages.value = data.seiten
    currentIndex.value = 0
    mode.value = 'review'
    await nextTick()
    instrumentInput.value?.focus()
    instrumentInput.value?.select()
  } catch (error) {
    alert(`Fehler bei der OCR: ${error.message}`)
  } finally {
    isBusy.value = false
  }
}

const applyReferenceProfile = async (targetProfile) => {
  if (!currentPage.value) return
  const profile = ocrProfiles.value[targetProfile]
  if (!profile) return

  isBusy.value = true
  try {
    const response = await fetch('http://127.0.0.1:8000/process-page/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        filename: currentPage.value.dateiname,
        page_index: currentPage.value.id,
        instrument: profile.instrument,
        page_number: profile.page
      })
    })
    if (!response.ok) throw new Error(`Seite konnte nicht neu erkannt werden (${response.status})`)
    const data = await response.json()
    currentPage.value.instrument = data.instrument
    currentPage.value.seite = data.seite
    currentPage.value.profil = targetProfile

    await nextTick()
    instrumentInput.value?.focus()
    instrumentInput.value?.select()
  } catch (error) {
    alert(`Fehler beim Wechseln der Referenz: ${error.message}`)
  } finally {
    isBusy.value = false
  }
}

// Navigation vor und zurück
const nextPage = () => {
  if (!pages.value.length) return
  pages.value[currentIndex.value].geprueft = true

  if (currentIndex.value < pages.value.length - 1) {
    currentIndex.value++
    nextTick(() => {
      instrumentInput.value?.focus()
      instrumentInput.value?.select()
    })
  } else {
    alert('Letzte Seite erreicht! Alle Seiten sind durchgesehen. Du kannst die Sätze oben einzeln exportieren.')
  }
}

const prevPage = () => {
  if (currentIndex.value > 0) {
    currentIndex.value--
    nextTick(() => {
      instrumentInput.value?.focus()
      instrumentInput.value?.select()
    })
  }
}

const jumpToPage = (index) => {
  if (index >= 0 && index < pages.value.length) {
    currentIndex.value = index
    nextTick(() => {
      instrumentInput.value?.focus()
      instrumentInput.value?.select()
    })
  }
}

// Einzelnen Notensatz manuell exportieren
const exportSingleSet = async (group) => {
  isBusy.value = true
  try {
    const response = await fetch('http://127.0.0.1:8000/export-single-set/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        instrument: group.name,
        pages: group.pages
      })
    })
    if (!response.ok) throw new Error('Export fehlgeschlagen')
    const data = await response.json()

    // Download anstoßen
    const a = document.createElement('a')
    a.href = data.download_url
    a.download = data.filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  } catch (error) {
    alert(`Fehler beim Exportieren von "${group.name}": ${error.message}`)
  } finally {
    isBusy.value = false
  }
}

// Alle Sätze auf einmal speichern
const exportAllSets = async () => {
  isBusy.value = true
  try {
    const response = await fetch('http://127.0.0.1:8000/finalize/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(pages.value)
    })
    if (!response.ok) throw new Error('Fehler beim Gesamtexport')
    alert('Alle Sätze wurden erfolgreich im Ordner "Dateien/Fertig" gespeichert!')
  } catch (error) {
    alert(`Fehler beim Speichern: ${error.message}`)
  } finally {
    isBusy.value = false
  }
}

// Tastatursteuerung: NumPad 1-3 für Referenz, Alt+Pfeile zum Blättern
const handleKeyDown = (event) => {
  if (mode.value !== 'review' || isBusy.value) return

  if (event.code === 'Numpad1') {
    event.preventDefault()
    applyReferenceProfile('first')
  } else if (event.code === 'Numpad2') {
    event.preventDefault()
    applyReferenceProfile('second')
  } else if (event.code === 'Numpad3') {
    event.preventDefault()
    applyReferenceProfile('third')
  } else if (event.altKey && event.key === 'ArrowLeft') {
    event.preventDefault()
    prevPage()
  } else if (event.altKey && event.key === 'ArrowRight') {
    event.preventDefault()
    nextPage()
  }
}

onMounted(() => window.addEventListener('keydown', handleKeyDown))
onUnmounted(() => window.removeEventListener('keydown', handleKeyDown))
</script>

<template>
  <div class="h-screen flex flex-col bg-gray-50 text-gray-900 font-sans overflow-hidden">
    <header class="relative bg-white shadow px-6 py-3 flex justify-between items-center z-10">
      <h1 class="text-xl font-bold text-gray-800">Noten OCR Kontrolle</h1>
      <div class="flex items-center gap-4">
        <button @click="openRules" class="border border-gray-300 text-gray-700 px-3 py-1.5 rounded-md text-sm hover:bg-gray-50">Instrument-Regeln</button>
        <input type="file" accept="application/pdf" multiple @change="onFileChange"
          class="file:mr-4 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:text-xs file:font-semibold file:bg-blue-50 file:text-blue-700 cursor-pointer" />
        <span v-if="files.length" class="text-xs text-gray-600">{{ files.length }} PDF{{ files.length === 1 ? '' : 's' }}</span>
        <button @click="uploadAndPrepare" :disabled="!files.length || isBusy"
          class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-1.5 rounded-md text-sm font-medium disabled:opacity-50">
          {{ isBusy ? 'Verarbeite...' : 'PDFs vorbereiten' }}
        </button>
      </div>
      <div v-if="isBusy" class="absolute bottom-0 left-0 h-1 w-full overflow-hidden bg-blue-100" role="progressbar">
        <div class="upload-progress h-full w-1/3 bg-blue-600"></div>
      </div>
    </header>

    <!-- REGELN -->
    <main v-if="mode === 'rules'" class="flex-1 overflow-y-auto bg-gray-50 p-6">
      <div class="max-w-4xl mx-auto space-y-6">
        <div>
          <h2 class="text-2xl font-bold text-gray-800">Instrument-Regeln</h2>
          <p class="text-gray-600 mt-1">Ordne einen OCR-Begriff dem Namen zu, der später verwendet werden soll.</p>
        </div>
        <section class="bg-white rounded-lg shadow p-5 space-y-4">
          <div v-for="(rule, index) in rules" :key="index" class="grid grid-cols-[1fr_1fr_auto] gap-3 items-center">
            <input v-model="rule.erkannt" placeholder="Erkannter Begriff, z. B. Eb Clarinet" class="border rounded px-3 py-2">
            <input v-model="rule.ziel" placeholder="Zielname, z. B. Klarinette in Eb" class="border rounded px-3 py-2">
            <button @click="removeRule(index)" class="text-red-600 px-3 py-2">Löschen</button>
          </div>
          <p v-if="!rules.length" class="text-gray-500">Noch keine eigenen Regeln angelegt.</p>
          <div class="flex gap-3">
            <button @click="addRule" class="border border-blue-300 text-blue-700 px-4 py-2 rounded">Regel hinzufügen</button>
            <button @click="saveRules" class="bg-blue-600 text-white px-4 py-2 rounded">Regeln speichern</button>
            <button @click="backFromRules" class="border border-gray-300 px-4 py-2 rounded">Zurück</button>
          </div>
        </section>
      </div>
    </main>

    <!-- SCHRITT 1 - A3-BOGEN & SCHNITT -->
    <main v-else-if="mode === 'split'" class="flex-1 overflow-y-auto bg-gray-50 p-6">
      <div class="max-w-6xl mx-auto space-y-6">
        <div class="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 class="text-2xl font-bold text-gray-800">1. A3-Bogen & Schnitt prüfen</h2>
            <p class="text-gray-600 mt-1">Passe die Schnittmitte per Schieberegler an. Beide Seiten werden aufrecht in DIN A4 erzeugt.</p>
          </div>
          <button @click="confirmSplitAndContinue" :disabled="isBusy"
            class="bg-green-600 hover:bg-green-700 text-white px-6 py-3 rounded-lg font-bold shadow disabled:opacity-50">
            {{ isBusy ? 'Schneide PDFs...' : 'Schnitt ist in Ordnung → Weiter zu den Referenzseiten' }}
          </button>
        </div>

        <div v-for="(rawDoc, docIndex) in rawDocuments" :key="rawDoc.original_name" class="bg-white rounded-lg shadow p-5 space-y-5">
          <div class="flex flex-wrap items-center justify-between gap-3 border-b pb-3">
            <div>
              <h3 class="font-bold text-lg text-gray-800">{{ rawDoc.original_name }}</h3>
              <p class="text-xs text-gray-500">{{ rawDoc.raw_page_count }} Original-Bogen-Seite(n) • Drehung: {{ rawDoc.rotation }}°</p>
            </div>
            <div class="flex flex-wrap items-center gap-2">
              <button @click="rotateDoc(rawDoc, -90)" class="border border-gray-300 hover:bg-gray-100 px-3 py-1.5 rounded text-sm font-medium">↺ 90° links</button>
              <button @click="rotateDoc(rawDoc, 90)" class="border border-gray-300 hover:bg-gray-100 px-3 py-1.5 rounded text-sm font-medium">↻ 90° rechts</button>
              <label class="flex items-center gap-2 ml-2 text-sm font-medium cursor-pointer select-none bg-gray-50 px-2 py-1 rounded border">
                <input type="checkbox" v-model="rawDoc.enabled" class="w-4 h-4 text-blue-600 rounded">
                Schnitt aktiv
              </label>
              <button v-if="rawDocuments.length > 1" @click="applySplitToAll(rawDoc)"
                class="ml-2 text-xs bg-blue-50 hover:bg-blue-100 text-blue-700 px-3 py-1.5 rounded font-medium">
                Auf alle übertragen
              </button>
            </div>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-4 bg-gray-50 p-4 rounded-lg border border-gray-200">
            <div v-if="rawDoc.enabled" class="space-y-2">
              <div class="flex items-center justify-between">
                <span class="text-sm font-semibold text-gray-700">
                  Schnitt: <strong class="text-red-600 font-mono">{{ (rawDoc.split_ratio * 100).toFixed(1) }}%</strong>
                </span>
                <div class="flex items-center gap-1">
                  <button @click="adjustSplit(rawDoc, -0.01)" class="text-xs border bg-white px-2 py-1 rounded hover:bg-gray-100 font-bold">◀ -1%</button>
                  <button @click="adjustSplit(rawDoc, 0.01)" class="text-xs border bg-white px-2 py-1 rounded hover:bg-gray-100 font-bold">+1% ▶</button>
                  <button @click="rawDoc.split_ratio = 0.5" class="text-xs border bg-white text-blue-700 px-2.5 py-1 rounded hover:bg-blue-50">50%</button>
                </div>
              </div>
              <input type="range" min="0.2" max="0.8" step="0.001" v-model.number="rawDoc.split_ratio" class="w-full cursor-pointer accent-red-600">
            </div>
            <div v-else class="text-sm text-amber-700 font-medium flex items-center">Kein Schnitt aktiv.</div>

            <div class="flex flex-col justify-between border-t md:border-t-0 md:border-l md:pl-4 pt-2 md:pt-0">
              <div class="flex items-center justify-between gap-2">
                <label class="text-sm font-semibold text-gray-700">Zielformat:</label>
                <select v-model="rawDoc.target_format" class="border rounded px-3 py-1.5 text-sm bg-white font-medium">
                  <option value="a4">DIN A4 Hochformat (210 × 297 mm)</option>
                  <option value="a4_landscape">DIN A4 Querformat (297 × 210 mm)</option>
                  <option value="original">Originalmaß (1:1)</option>
                </select>
              </div>
              <div v-if="rawDoc.raw_page_count > 1" class="flex items-center justify-between gap-2 text-sm mt-2">
                <span class="text-gray-600">Vorschau-Bogen:</span>
                <select v-model.number="rawDoc.previewPage" class="border rounded px-2.5 py-1 bg-white">
                  <option v-for="p in rawDoc.raw_page_count" :key="p" :value="p">Bogen {{ p }} von {{ rawDoc.raw_page_count }}</option>
                </select>
              </div>
            </div>
          </div>

          <div class="relative select-none border-2 border-slate-300 rounded-lg bg-gray-100 max-w-4xl mx-auto overflow-hidden shadow-inner"
            :class="rawDoc.enabled ? 'cursor-ew-resize' : ''"
            @pointerdown.prevent="startSplitDrag($event, docIndex)"
            @pointermove="updateSplitDrag($event, docIndex)"
            @pointerup="finishSplitDrag"
            @pointercancel="finishSplitDrag">
            <img :src="uploadPreviewUrl(rawDoc)" class="block w-full pointer-events-none" draggable="false">
            <template v-if="rawDoc.enabled">
              <div class="absolute top-0 bottom-0 left-0 bg-blue-500/15 border-r border-blue-400/40 pointer-events-none p-3"
                :style="{ width: `${rawDoc.split_ratio * 100}%` }">
                <span class="inline-flex bg-blue-700 text-white text-xs font-bold px-2 py-1 rounded shadow">A4 Links (S. 1)</span>
              </div>
              <div class="absolute top-0 bottom-0 right-0 bg-emerald-500/15 border-l border-emerald-400/40 pointer-events-none p-3 flex justify-end"
                :style="{ width: `${(1 - rawDoc.split_ratio) * 100}%` }">
                <span class="inline-flex bg-emerald-700 text-white text-xs font-bold px-2 py-1 rounded shadow">A4 Rechts (S. 2)</span>
              </div>
              <div class="absolute top-0 bottom-0 w-0.5 bg-red-600 pointer-events-none shadow-[0_0_10px_rgba(220,38,38,1)] z-10"
                :style="{ left: `${rawDoc.split_ratio * 100}%` }">
                <div class="absolute top-2 -translate-x-1/2 bg-red-600 text-white text-xs font-bold px-2.5 py-1 rounded-full shadow">
                  ✂ {{ (rawDoc.split_ratio * 100).toFixed(1) }}%
                </div>
              </div>
            </template>
          </div>
        </div>
      </div>
    </main>

    <!-- SCHRITT 2 - REFERENZEN -->
    <main v-else-if="mode === 'mark'" class="flex-1 overflow-y-auto bg-gray-50 p-6">
      <div class="max-w-[1600px] mx-auto space-y-6">
        <div class="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 class="text-2xl font-bold text-gray-800">2. OCR-Bereiche auf 3 Referenzseiten festlegen</h2>
            <p class="text-gray-600 mt-1">1. Referenz = Seite 1 • 2. Referenz = Gerade Seiten • 3. Referenz = Ungerade Folgeseiten</p>
          </div>
          <div class="flex gap-3">
            <button @click="mode = 'split'" class="border border-gray-300 bg-white hover:bg-gray-50 px-4 py-2 rounded-lg font-medium">← Zurück zum Schnitt</button>
            <button @click="processDocuments" :disabled="isBusy" class="bg-green-600 hover:bg-green-700 text-white px-6 py-3 rounded-lg font-bold disabled:opacity-50">
              {{ isBusy ? 'OCR läuft...' : 'OCR starten' }}
            </button>
          </div>
        </div>

        <section class="bg-white rounded-lg shadow p-5">
          <label class="block text-sm font-semibold text-gray-700">Titel des Notensatzes
            <input v-model="projectTitle" placeholder="z. B. Marsch / Konzertstück" class="mt-2 w-full max-w-xl border rounded px-3 py-2">
          </label>
          <div class="flex gap-3 mt-4">
            <button @click="saveProject" class="bg-blue-600 text-white px-4 py-2 rounded text-sm">Projekt speichern</button>
            <select @change="loadProject(savedProjects.find((p) => p.title === $event.target.value))" class="border rounded px-3 py-2 text-sm">
              <option value="">Gespeichertes Projekt laden</option>
              <option v-for="project in savedProjects" :key="project.title" :value="project.title">{{ project.title }}</option>
            </select>
          </div>
        </section>

        <section class="bg-white rounded-lg shadow p-5">
          <div class="grid grid-cols-1 xl:grid-cols-3 gap-6">
            <div v-for="refItem in referenceMeta" :key="refItem.key" class="flex flex-col">
              <div class="flex items-center justify-between gap-2 mb-3">
                <h4 class="font-semibold text-gray-700 text-sm">{{ refItem.title }}</h4>
                <select v-model="referencePages[refItem.key]" class="max-w-[55%] border rounded px-2 py-1 text-xs">
                  <option v-for="option in referenceOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
                </select>
              </div>

              <div v-if="referenceChoice(refItem.key).document"
                class="relative select-none border border-gray-300 bg-gray-100"
                @pointerdown.prevent="startMark($event, refItem.key)"
                @pointermove="updateMark($event, refItem.key)"
                @pointerup="finishMark"
                @pointercancel="finishMark">
                <img :src="previewUrl(referenceChoice(refItem.key).document, referenceChoice(refItem.key).page)" class="block w-full pointer-events-none" draggable="false">
                <template v-for="type in ['instrument', 'page']" :key="type">
                  <div v-if="selections[refItem.key][type]" class="absolute border-2 pointer-events-none"
                    :class="type === 'instrument' ? 'border-blue-500 bg-blue-200/20' : 'border-emerald-500 bg-emerald-200/20'"
                    :style="regionStyle(selections[refItem.key][type])"></div>
                </template>
              </div>

              <div class="flex flex-wrap gap-2 mt-3">
                <button @click="chooseTarget(refItem.key, 'instrument')"
                  :class="activeTarget?.sample === refItem.key && activeTarget?.type === 'instrument' ? 'ring-2 ring-blue-600' : ''"
                  class="px-3 py-1.5 rounded bg-blue-100 text-blue-800 text-xs font-medium">Instrument</button>
                <button @click="chooseTarget(refItem.key, 'page')"
                  :class="activeTarget?.sample === refItem.key && activeTarget?.type === 'page' ? 'ring-2 ring-emerald-600' : ''"
                  class="px-3 py-1.5 rounded bg-emerald-100 text-emerald-800 text-xs font-medium">Seitenzahl</button>
                <button v-if="selections[refItem.key].instrument || selections[refItem.key].page"
                  @click="clearSelection(refItem.key)" class="px-2 py-1.5 rounded border text-gray-600 text-xs hover:bg-gray-100">Zurücksetzen</button>
              </div>
            </div>
          </div>
        </section>
      </div>
    </main>

    <!-- SCHRITT 3 - EINZELPRÜFUNG MIT OBERER SATZ-GALERIE -->
    <main v-else-if="mode === 'review'" class="flex-1 flex flex-col overflow-hidden">
      <!-- OBERE GALERIE ALLER NOTENSÄTZE -->
      <section class="bg-white border-b border-gray-200 px-4 py-2 flex items-center gap-3 overflow-x-auto shadow-sm shrink-0">
        <div class="flex items-center gap-2 pr-3 border-r border-gray-200 shrink-0">
          <span class="text-xs font-bold text-gray-500 uppercase tracking-wider">Erkannte Sätze:</span>
          <button @click="exportAllSets" :disabled="isBusy"
            class="bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold px-3 py-1.5 rounded flex items-center gap-1 shadow-sm disabled:opacity-50">
            💾 Alle Sätze exportieren
          </button>
        </div>

        <div class="flex items-center gap-2.5 overflow-x-auto py-1">
          <div v-for="set in instrumentSets" :key="set.name"
            :class="currentPage?.instrument?.trim() === set.name ? 'ring-2 ring-blue-500 bg-blue-50/80 border-blue-400' : 'bg-gray-50 border-gray-200 hover:bg-gray-100'"
            class="flex items-center gap-2 border rounded-lg px-3 py-1.5 text-xs transition-all shrink-0">
            <!-- Klick auf Namen springt zur ersten Seite des Satzes -->
            <button @click="jumpToPage(set.pages[0].pageIndex)" class="font-bold text-gray-800 hover:text-blue-600 text-left">
              {{ set.name }}
              <span class="ml-1 text-[11px] font-normal text-gray-500">({{ set.pages.length }} S.)</span>
            </button>

            <!-- Einzel-Export-Button für genau diesen Satz -->
            <button @click.stop="exportSingleSet(set)" :disabled="isBusy" title="Diesen Satz sofort exportieren & herunterladen"
              class="border border-emerald-500 text-emerald-700 hover:bg-emerald-600 hover:text-white px-2 py-0.5 rounded font-semibold transition-colors disabled:opacity-50 flex items-center gap-0.5">
              <span>💾</span>
              <span>Export</span>
            </button>
          </div>
        </div>
      </section>

      <!-- HAUPTBEREICH: PDF + KONTROLLLEISTE -->
      <div class="flex-1 flex overflow-hidden">
        <div class="w-2/3 h-full bg-slate-200 border-r border-slate-300">
          <iframe v-if="currentPage" :key="`${currentPage.pdf_url}&zoom=80`" :src="`${currentPage.pdf_url}&zoom=80`" class="w-full h-full"></iframe>
        </div>

        <div class="w-1/3 h-full bg-white p-5 overflow-y-auto flex flex-col justify-between">
          <div>
            <div class="mb-4 pb-3 border-b border-gray-200 flex justify-between items-center">
              <div>
                <h2 class="text-lg font-bold">Seite {{ currentIndex + 1 }} von {{ pages.length }}</h2>
                <span class="text-xs text-gray-500">
                  Status: {{ pages.filter(p => p.geprueft).length }} von {{ pages.length }} geprüft
                </span>
              </div>
              <span class="text-xs font-semibold px-2 py-1 rounded bg-gray-100 text-gray-600">
                Aktive Ref: {{ currentPage?.profil === 'first' ? '1' : currentPage?.profil === 'second' ? '2' : '3' }}
              </span>
            </div>

            <p v-if="currentPage" class="mb-4 text-xs text-gray-500 truncate" :title="currentPage.dateiname">
              Datei: {{ currentPage.dateiname }}
            </p>

            <div v-if="currentPage" class="space-y-4">
              <label class="block text-sm font-semibold">Instrument
                <input ref="instrumentInput" v-model="currentPage.instrument"
                  class="mt-1 w-full border rounded-lg px-3 py-2 text-base font-medium focus:ring-2 focus:ring-blue-500 outline-none"
                  @keydown.enter.exact.prevent="nextPage"
                  @keydown.shift.enter.exact.prevent="prevPage">
              </label>

              <label class="block text-sm font-semibold">Seitenzahl
                <input v-model="currentPage.seite"
                  class="mt-1 w-full border rounded-lg px-3 py-2 text-base font-medium focus:ring-2 focus:ring-blue-500 outline-none"
                  @keydown.enter.exact.prevent="nextPage"
                  @keydown.shift.enter.exact.prevent="prevPage">
              </label>
            </div>

            <!-- Referenz-Auswahl mit Hotkeys NumPad 1, 2, 3 -->
            <div class="mt-5">
              <p class="text-xs font-semibold text-gray-500 mb-2">Mit anderer Referenzseite neu erkennen:</p>
              <div class="grid grid-cols-3 gap-2">
                <button @click="applyReferenceProfile('first')" :disabled="isBusy"
                  :class="currentPage?.profil === 'first' ? 'bg-blue-600 text-white ring-2 ring-blue-400' : 'border border-blue-300 text-blue-700 hover:bg-blue-50'"
                  class="py-2 px-1 rounded-lg text-xs font-semibold disabled:opacity-50 flex flex-col items-center gap-0.5">
                  <span>1. Referenz</span>
                  <span class="text-[10px] font-mono opacity-80 bg-black/10 px-1 py-0.5 rounded">Num 1</span>
                </button>
                <button @click="applyReferenceProfile('second')" :disabled="isBusy"
                  :class="currentPage?.profil === 'second' ? 'bg-blue-600 text-white ring-2 ring-blue-400' : 'border border-blue-300 text-blue-700 hover:bg-blue-50'"
                  class="py-2 px-1 rounded-lg text-xs font-semibold disabled:opacity-50 flex flex-col items-center gap-0.5">
                  <span>2. Referenz</span>
                  <span class="text-[10px] font-mono opacity-80 bg-black/10 px-1 py-0.5 rounded">Num 2</span>
                </button>
                <button @click="applyReferenceProfile('third')" :disabled="isBusy"
                  :class="currentPage?.profil === 'third' ? 'bg-blue-600 text-white ring-2 ring-blue-400' : 'border border-blue-300 text-blue-700 hover:bg-blue-50'"
                  class="py-2 px-1 rounded-lg text-xs font-semibold disabled:opacity-50 flex flex-col items-center gap-0.5">
                  <span>3. Referenz</span>
                  <span class="text-[10px] font-mono opacity-80 bg-black/10 px-1 py-0.5 rounded">Num 3</span>
                </button>
              </div>
            </div>
          </div>

          <!-- NAVIGATION & MANUELLER SCHRITT ZURÜCK -->
          <div class="pt-4 border-t border-gray-200 space-y-2 mt-4">
            <div class="grid grid-cols-2 gap-3">
              <button @click="prevPage" :disabled="currentIndex === 0"
                class="border border-gray-300 hover:bg-gray-100 text-gray-700 py-2.5 rounded-lg font-bold text-sm disabled:opacity-40 flex items-center justify-center gap-1">
                <span>← Zurück</span>
                <span class="text-[10px] text-gray-500 font-normal">(Shift+Enter)</span>
              </button>
              <button @click="nextPage"
                class="bg-blue-600 hover:bg-blue-700 text-white py-2.5 rounded-lg font-bold text-sm flex items-center justify-center gap-1 shadow">
                <span>Weiter →</span>
                <span class="text-[10px] text-blue-200 font-normal">(Enter)</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </main>

    <!-- STARTANSICHT -->
    <main v-else class="flex-1 flex flex-col items-center justify-center text-gray-400 bg-gray-50 p-6">
      <p class="text-lg">Lade ein Noten-PDF hoch, um Schnitt und Erkennung zu starten.</p>
      <div v-if="savedProjects.length" class="mt-8 w-full max-w-xl bg-white rounded-lg shadow p-5">
        <h2 class="text-base font-bold text-gray-700 mb-3">Gespeicherte Notensatz-Projekte</h2>
        <div v-for="project in savedProjects" :key="project.title" class="flex items-center justify-between border-b last:border-b-0 py-2.5">
          <span class="text-gray-800 text-sm font-medium">{{ project.title }}</span>
          <button @click="loadProject(project)" class="bg-blue-600 text-white text-xs px-3 py-1.5 rounded">Laden</button>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
.upload-progress { animation: upload-progress 1.2s ease-in-out infinite; }
@keyframes upload-progress {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(400%); }
}
</style>