<script setup>
import { ref, computed, nextTick } from 'vue'

const files = ref([])
const documents = ref([])
const selections = ref({
  first: { instrument: null, page: null },
  second: { instrument: null, page: null }
})
const ocrProfiles = ref({ first: null, second: null })
const referencePages = ref({ first: '', second: '' })
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

const currentPage = computed(() => pages.value[currentIndex.value] || null)

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
    alert('Bitte zuerst die vorbereiteten PDFs laden. Das Projekt enthält nur die Referenzfelder.')
    return
  }
  projectTitle.value = project.title
  referencePages.value = { ...project.referencePages }
  selections.value = JSON.parse(JSON.stringify(project.selections))
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
    documents.value = data.dokumente
    selections.value = {
      first: { instrument: null, page: null },
      second: { instrument: null, page: null }
    }
    const secondDocumentIndex = documents.value.findIndex((document) => document.page_count > 1)
    referencePages.value = {
      first: '0:1',
      second: `${secondDocumentIndex >= 0 ? secondDocumentIndex : 0}:${secondDocumentIndex >= 0 ? 2 : 1}`
    }
    mode.value = 'mark'
  } catch (error) {
    alert(`Fehler beim Vorbereiten: ${error.message}`)
  } finally {
    isBusy.value = false
  }
}

const previewUrl = (document, page) =>
  `http://127.0.0.1:8000/preview/${encodeURIComponent(document.filename)}/${page}`

const referenceChoice = (sample) => {
  const [documentIndex, page] = referencePages.value[sample].split(':').map(Number)
  return { document: documents.value[documentIndex], page }
}

const referenceOptions = computed(() => documents.value.flatMap((document, documentIndex) =>
  Array.from({ length: document.page_count }, (_, index) => ({
    value: `${documentIndex}:${index + 1}`,
    label: `${document.original_name} - A4-Seite ${index + 1}`
  }))
))

const regionStyle = (region) => region ? {
  left: `${region.x * 100}%`, top: `${region.y * 100}%`,
  width: `${region.width * 100}%`, height: `${region.height * 100}%`
} : {}

const pointInPreview = (event) => {
  const bounds = event.currentTarget.getBoundingClientRect()
  return {
    x: Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width)),
    y: Math.max(0, Math.min(1, (event.clientY - bounds.top) / bounds.height))
  }
}

const chooseTarget = (sample, type) => {
  activeTarget.value = { sample, type }
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
    x: Math.min(start.x, point.x), y: Math.min(start.y, point.y),
    width: Math.abs(point.x - start.x), height: Math.abs(point.y - start.y)
  }
}

const finishMark = () => {
  drawing.value = null
  activeTarget.value = null
}

const allRegionsMarked = computed(() =>
  referencePages.value.first !== referencePages.value.second
)

const processDocuments = async () => {
  if (!allRegionsMarked.value) {
    alert('Bitte wähle zwei unterschiedliche Referenzseiten aus.')
    return
  }
  isBusy.value = true
  try {
    ocrProfiles.value = {
      first: { instrument: selections.value.first.instrument, page: selections.value.first.page },
      second: { instrument: selections.value.second.instrument, page: selections.value.second.page }
    }
    const payload = documents.value.map((document) => ({
      filename: document.filename,
      first_instrument: selections.value.first.instrument,
      first_page_number: selections.value.first.page,
      second_instrument: selections.value.second.instrument,
      second_page_number: selections.value.second.page
    }))
    const response = await fetch('http://127.0.0.1:8000/process/', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
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

const switchReference = async () => {
  if (!currentPage.value) return
  const nextProfile = currentPage.value.profil === 'first' ? 'second' : 'first'
  const profile = ocrProfiles.value[nextProfile]
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
    currentPage.value.profil = nextProfile
  } catch (error) {
    alert(`Fehler beim Wechseln der Referenz: ${error.message}`)
  } finally {
    isBusy.value = false
  }
}

const finalize = async () => {
  try {
    const response = await fetch('http://127.0.0.1:8000/finalize/', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(pages.value)
    })
    if (!response.ok) throw new Error('Fehler beim Speichern')
    alert('Erfolgreich gespeichert.')
    files.value = []
    projectTitle.value = ''
    documents.value = []
    selections.value = { first: { instrument: null, page: null }, second: { instrument: null, page: null } }
    ocrProfiles.value = { first: null, second: null }
    referencePages.value = { first: '', second: '' }
    pages.value = []
    mode.value = 'empty'
  } catch (error) {
    alert(`Fehler beim finalen Speichern: ${error.message}`)
  }
}

const nextPage = () => {
  if (currentIndex.value < pages.value.length - 1) {
    pages.value[currentIndex.value].geprueft = true
    currentIndex.value++
    nextTick(() => {
      instrumentInput.value?.focus()
      instrumentInput.value?.select()
    })
  } else {
    pages.value[currentIndex.value].geprueft = true
    finalize()
  }
}
</script>

<template>
  <div class="h-screen flex flex-col bg-gray-50 text-gray-900 font-sans overflow-hidden">
    <header class="relative bg-white shadow px-6 py-4 flex justify-between items-center z-10">
      <h1 class="text-2xl font-bold text-gray-800">Noten OCR Kontrolle</h1>
      <div class="flex items-center gap-4">
        <button @click="openRules" class="border border-gray-300 text-gray-700 px-3 py-2 rounded-md text-sm hover:bg-gray-50">Instrument-Regeln</button>
        <input type="file" accept="application/pdf" multiple @change="onFileChange"
          class="file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 cursor-pointer" />
        <span v-if="files.length" class="text-sm text-gray-600">{{ files.length }} PDF{{ files.length === 1 ? '' : 's' }} ausgewählt</span>
        <button @click="uploadAndPrepare" :disabled="!files.length || isBusy"
          class="bg-blue-600 hover:bg-blue-700 text-white px-5 py-2 rounded-md font-medium disabled:opacity-50">
          {{ isBusy ? 'Verarbeite...' : 'PDFs vorbereiten' }}
        </button>
      </div>
      <div v-if="isBusy" class="absolute bottom-0 left-0 h-1 w-full overflow-hidden bg-blue-100" role="progressbar">
        <div class="upload-progress h-full w-1/3 bg-blue-600"></div>
      </div>
    </header>

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
        <p class="text-sm text-gray-500">Beispiel: OCR-Begriff <strong>Eb Clarinet</strong>, Zielname <strong>Klarinette in Eb</strong>.</p>
      </div>
    </main>

    <main v-else-if="mode === 'mark'" class="flex-1 overflow-y-auto bg-gray-50 p-6">
      <div class="max-w-7xl mx-auto space-y-8">
        <div>
          <h2 class="text-2xl font-bold text-gray-800">OCR-Bereiche festlegen</h2>
          <p class="text-gray-600 mt-1">Markiere pro Notensatz auf beiden Beispielseiten Instrument und Seitenzahl.</p>
        </div>
        <section class="bg-white rounded-lg shadow p-5">
          <label class="block text-sm font-semibold text-gray-700">Titel des Notensatzes
            <input v-model="projectTitle" placeholder="z. B. Konzertprogramm Frühjahr" class="mt-2 w-full max-w-xl border rounded px-3 py-2">
          </label>
          <div class="flex gap-3 mt-4">
            <button @click="saveProject" class="bg-blue-600 text-white px-4 py-2 rounded">Projekt speichern</button>
            <select @change="loadProject(savedProjects.find((project) => project.title === $event.target.value))" class="border rounded px-3 py-2">
              <option value="">Gespeichertes Projekt laden</option>
              <option v-for="project in savedProjects" :key="project.title" :value="project.title">{{ project.title }}</option>
            </select>
            <button v-if="savedProjects.some((project) => project.title === projectTitle)" @click="deleteProject(projectTitle)" class="text-red-600 px-3 py-2">Projekt löschen</button>
          </div>
        </section>
        <section class="bg-white rounded-lg shadow p-5">
          <h3 class="text-lg font-bold text-gray-800 mb-4">Zwei Referenzseiten auswählen</h3>
          <div class="grid grid-cols-1 xl:grid-cols-2 gap-6">
            <div v-for="sample in ['first', 'second']" :key="sample">
              <div class="flex items-center justify-between mb-3">
                <h4 class="font-semibold text-gray-700">{{ sample === 'first' ? '1. Referenzseite' : '2. Referenzseite' }}</h4>
                <select v-model="referencePages[sample]" class="max-w-[60%] border rounded px-2 py-1 text-sm">
                  <option v-for="option in referenceOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
                </select>
              </div>
              <div v-if="referenceChoice(sample).document" class="relative select-none border border-gray-300 bg-gray-100"
                @pointerdown.prevent="startMark($event, sample)" @pointermove="updateMark($event, sample)" @pointerup="finishMark" @pointercancel="finishMark">
                <img :src="previewUrl(referenceChoice(sample).document, referenceChoice(sample).page)" class="block w-full pointer-events-none" draggable="false">
                <template v-for="type in ['instrument', 'page']" :key="type">
                  <div v-if="selections[sample][type]" class="absolute border-2 pointer-events-none"
                    :class="type === 'instrument' ? 'border-blue-500 bg-blue-200/20' : 'border-emerald-500 bg-emerald-200/20'"
                    :style="regionStyle(selections[sample][type])"></div>
                </template>
              </div>
              <div class="flex gap-2 mt-3">
                <button @click="chooseTarget(sample, 'instrument')" class="px-3 py-2 rounded bg-blue-100 text-blue-800 text-sm">Instrument markieren</button>
                <button @click="chooseTarget(sample, 'page')" class="px-3 py-2 rounded bg-emerald-100 text-emerald-800 text-sm">Seitenzahl markieren</button>
              </div>
              <p class="text-xs text-gray-500 mt-2">{{ activeTarget?.sample === sample ? 'Jetzt Bereich aufziehen.' : 'Zuerst einen Bereich auswählen.' }}</p>
            </div>
          </div>
        </section>
        <button @click="processDocuments" :disabled="isBusy" class="bg-green-600 hover:bg-green-700 text-white px-6 py-3 rounded-lg font-bold disabled:opacity-50">
          {{ isBusy ? 'OCR läuft...' : 'Markierungen übernehmen und OCR starten' }}
        </button>
      </div>
    </main>

    <main v-else-if="mode === 'review'" class="flex-1 flex overflow-hidden">
      <div class="w-2/3 h-full bg-slate-200 border-r border-slate-300">
        <iframe v-if="currentPage" :key="`${currentPage.pdf_url}&zoom=80`" :src="`${currentPage.pdf_url}&zoom=80`" class="w-full h-full"></iframe>
      </div>
      <div class="w-1/3 h-full bg-white p-5 overflow-y-auto flex flex-col">
        <div class="mb-6 pb-4 border-b border-gray-200 flex justify-between"><h2 class="text-lg font-bold">Seite {{ currentIndex + 1 }} von {{ pages.length }}</h2><span>Zu prüfen</span></div>
        <p v-if="currentPage" class="mb-5 text-sm text-gray-500 truncate">Datei: {{ currentPage.dateiname }}</p>
        <div v-if="currentPage" class="space-y-5 flex-1">
          <label class="block text-sm font-semibold">Erkanntes Instrument<input ref="instrumentInput" v-model="currentPage.instrument" class="mt-2 w-full border rounded-lg px-4 py-3 text-lg" @keyup.enter="nextPage"></label>
          <label class="block text-sm font-semibold">Erkannte Seitenzahl<input v-model="currentPage.seite" class="mt-2 w-full border rounded-lg px-4 py-3 text-lg" @keyup.enter="nextPage"></label>
        </div>
        <button @click="switchReference" :disabled="isBusy" class="mt-4 w-full border border-blue-300 text-blue-700 hover:bg-blue-50 py-2 rounded-lg disabled:opacity-50">
          Andere Referenz verwenden ({{ currentPage?.profil === 'first' ? '2' : '1' }})
        </button>
        <button @click="nextPage" class="sticky bottom-0 mt-6 w-full bg-green-600 hover:bg-green-700 text-white py-3 rounded-lg font-bold">Bestätigen & Weiter</button>
      </div>
    </main>

    <main v-else class="flex-1 flex flex-col items-center justify-center text-gray-400 bg-gray-50 p-6">
      <p class="text-xl">Lade ein Noten-PDF hoch, um die Bereiche zu markieren.</p>
      <div v-if="savedProjects.length" class="mt-8 w-full max-w-xl bg-white rounded-lg shadow p-5">
        <h2 class="text-lg font-bold text-gray-700 mb-3">Gespeicherte Notensatz-Projekte</h2>
        <div v-for="project in savedProjects" :key="project.title" class="flex items-center justify-between border-b last:border-b-0 py-3">
          <span class="text-gray-800">{{ project.title }}</span>
          <button @click="loadProject(project)" class="bg-blue-600 text-white px-3 py-2 rounded">Laden</button>
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
