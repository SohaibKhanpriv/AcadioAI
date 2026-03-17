<template>
  <div class="rag-container">
    <div class="rag-grid">
      <!-- Left Column: Ingestion -->
      <div class="ingest-panel card">
        <div class="panel-header">
          <h2 class="gradient-text">1. Add Knowledge</h2>
          <p>Ingest documents or websites into the knowledge base</p>
        </div>

        <form @submit.prevent="ingestDocument" class="ingest-form">
          <div class="form-group">
            <label>Tenant ID</label>
            <input v-model="config.tenantId" class="input" placeholder="e.g. demo_tenant" required />
          </div>

          <div class="form-group">
            <label>Document Title</label>
            <input v-model="ingest.title" class="input" placeholder="e.g. School Policy 2024" required />
          </div>

          <div class="form-group">
            <label>Source Type</label>
            <div class="toggle-group">
              <button 
                type="button" 
                class="btn-toggle" 
                :class="{ active: ingest.type === 'text' }"
                @click="setIngestType('text')"
              >Text</button>
              <button 
                type="button" 
                class="btn-toggle" 
                :class="{ active: ingest.type === 'url' }"
                @click="setIngestType('url')"
              >URL</button>
              <button 
                type="button" 
                class="btn-toggle" 
                :class="{ active: ingest.type === 'file' }"
                @click="setIngestType('file')"
              >File</button>
            </div>
          </div>

          <div class="form-group">
            <label>
              {{ ingest.type === 'url' ? 'Document URL' : ingest.type === 'file' ? 'Upload File' : 'Text Content' }}
            </label>
            <input 
              v-if="ingest.type === 'url'"
              v-model="ingest.value" 
              class="input" 
              placeholder="https://example.com/policy" 
              required
            />
            <input
              v-else-if="ingest.type === 'file'"
              type="file"
              class="input"
              accept=".pdf,.txt"
              @change="onFileChange"
              required
            />
            <textarea 
              v-else 
              v-model="ingest.value" 
              class="input textarea" 
              placeholder="Paste document text here..." 
              required
              rows="6"
            ></textarea>
          </div>

          <button type="submit" class="btn btn-primary full-width" :disabled="isIngesting">
            <span v-if="isIngesting" class="spinner"></span>
            <span v-else>Ingest Document</span>
          </button>
        </form>

        <!-- Ingestion Status -->
        <div v-if="ingestJobs.length > 0" class="jobs-list animate-fade-in">
          <h3>Recent Jobs</h3>
          <div v-for="job in ingestJobs" :key="job.jobId" class="job-item">
            <div class="job-info">
              <span class="job-id">Job: {{ job.jobId.substring(0,8) }}...</span>
              <span class="job-status" :class="job.status">{{ job.status }}</span>
            </div>
            <div v-if="job.errorMessage" class="job-error">{{ job.errorMessage }}</div>
          </div>
        </div>
      </div>

      <!-- Right Column: Chat -->
      <div class="chat-panel card">
        <div class="panel-header">
          <h2 class="gradient-text">2. Chat with Docs</h2>
          <p>Ask questions based on ingested knowledge</p>
        </div>

        <div class="chat-area" ref="messagesContainer">
          <div v-if="chatMessages.length === 0" class="empty-state">
            <p>No messages yet. Try asking about the documents you added.</p>
          </div>
          
          <div 
            v-for="(msg, index) in chatMessages" 
            :key="index" 
            class="message animate-fade-in"
            :class="msg.role"
          >
            <div class="message-role">
              {{ msg.role === 'user' ? 'You' : 'AI' }}
            </div>
            <div class="message-bubble">
              <div class="message-text">{{ msg.content }}</div>
              
              <!-- Citations -->
              <div v-if="msg.citations && msg.citations.length > 0" class="citations">
                <span class="citations-Label">Sources:</span>
                <div class="citation-tags">
                  <span 
                    v-for="cite in msg.citations" 
                    :key="cite.chunkId" 
                    class="citation-tag"
                    :title="cite.title"
                  >
                    📄 {{ cite.title }}
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div v-if="isChatting" class="message ai typing">
            <div class="message-role">AI</div>
            <div class="message-bubble">
              <span class="spinner-dots">...</span>
            </div>
          </div>
        </div>

        <form @submit.prevent="sendChatMessage" class="chat-input-form">
          <input 
            v-model="chatInput" 
            class="input" 
            placeholder="Ask a question..." 
            :disabled="isChatting"
          />
          <button type="submit" class="btn btn-primary" :disabled="!chatInput.trim() || isChatting">
            Send
          </button>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, nextTick, onUnmounted } from 'vue'

const runtimeConfig = useRuntimeConfig()
const apiBaseUrl = runtimeConfig.public.apiBaseUrl

// --- State ---

const config = reactive({
  tenantId: 'demo_tenant',
  userId: 'user_' + Math.floor(Math.random() * 1000),
})

// Ingestion State
const ingest = reactive({
  title: '',
  type: 'text' as 'text' | 'url' | 'file',
  value: '',
  file: null as File | null
})
const isIngesting = ref(false)
const ingestJobs = ref<Array<{jobId: string, status: string, errorMessage?: string}>>([])
let pollInterval: any = null

// Chat State
const chatInput = ref('')
const isChatting = ref(false)
const chatMessages = ref<Array<{
  role: 'user' | 'assistant',
  content: string,
  citations?: Array<{documentId: string, chunkId: string, title: string}>
}>>([])
const sessionId = ref(`sess_${Date.now()}`)
const messagesContainer = ref<HTMLElement | null>(null)

// --- Methods ---

function setIngestType(type: 'text' | 'url' | 'file') {
  ingest.type = type
  ingest.value = ''
  ingest.file = null
}

function onFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  ingest.file = target.files && target.files.length > 0 ? target.files[0] : null
}

async function ingestDocument() {
  if (!ingest.title) return
  if (ingest.type === 'file' && !ingest.file) return
  
  isIngesting.value = true
  try {
    let res: Response

    if (ingest.type === 'file' && ingest.file) {
      const form = new FormData()
      form.append('file', ingest.file)
      form.append('tenantId', config.tenantId)
      form.append('title', ingest.title)
      form.append('language', 'en-US')
      form.append('sourceType', 'demo_upload')
      form.append('visibilityRoles', 'user')
      form.append('visibilityScopes', 'public')
      form.append('tags', JSON.stringify({}))

      res = await fetch(`${apiBaseUrl}/v1/ingest/upload`, {
        method: 'POST',
        body: form
      })
    } else {
      const payload = {
        tenantId: config.tenantId,
        title: ingest.title,
        language: 'en-US',
        sourceType: 'demo_upload',
        visibility: {
          roles: ['user'],
          scopes: ['public']
        },
        content: {
          type: ingest.type,
          value: ingest.value
        }
      }

      res = await fetch(`${apiBaseUrl}/v1/ingest/document`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
    }

    if (!res.ok) {
      const err = await res.json()
      throw new Error(err.message || 'Ingestion failed')
    }

    const data = await res.json()
    // Add job to list
    ingestJobs.value.unshift({
      jobId: data.jobId,
      status: data.status
    })

    // Start polling if not already
    if (!pollInterval) {
      pollInterval = setInterval(pollJobs, 2000)
    }

    // Reset form
    ingest.title = ''
    ingest.value = ''
    ingest.file = null
  } catch (e: any) {
    alert(`Error: ${e.message}`)
  } finally {
    isIngesting.value = false
  }
}

async function pollJobs() {
  if (ingestJobs.value.length === 0) return

  let allCompleted = true

  for (const job of ingestJobs.value) {
    if (['completed', 'failed'].includes(job.status)) continue

    allCompleted = false
    try {
      const res = await fetch(`${apiBaseUrl}/v1/ingest/status?jobId=${job.jobId}`)
      if (res.ok) {
        const data = await res.json()
        job.status = data.status
        if (data.errorMessage) job.errorMessage = data.errorMessage
      }
    } catch (e) {
      console.error("Polling error", e)
    }
  }

  if (allCompleted) {
    clearInterval(pollInterval)
    pollInterval = null
  }
}

async function sendChatMessage() {
  if (!chatInput.value.trim()) return
  
  const text = chatInput.value.trim()
  chatInput.value = ''
  
  // Add user message
  chatMessages.value.push({ role: 'user', content: text })
  scrollToBottom()
  
  isChatting.value = true
  try {
    // Build history for API
    const history = chatMessages.value.slice(0, -1).map(m => ({
      role: m.role,
      content: m.content
    }))

    const payload = {
      tenantId: config.tenantId,
      userId: config.userId,
      roles: ['user'], // Ensure we have access to the documents we uploaded
      language: 'en-US',
      message: text,
      sessionId: sessionId.value,
      history: history
    }

    const res = await fetch(`${apiBaseUrl}/v1/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })

    if (!res.ok) {
      const err = await res.json()
      throw new Error(err.message || 'Chat failed')
    }

    const data = await res.json()
    
    chatMessages.value.push({
      role: 'assistant',
      content: data.answer,
      citations: data.citations
    })
    
  } catch (e: any) {
    chatMessages.value.push({
      role: 'assistant',
      content: `Error: ${e.message}`
    })
  } finally {
    isChatting.value = false
    scrollToBottom()
  }
}

async function scrollToBottom() {
  await nextTick()
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

onUnmounted(() => {
  if (pollInterval) clearInterval(pollInterval)
})
</script>

<style scoped>
.rag-container {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.rag-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-lg);
  height: 100%;
}

@media (max-width: 900px) {
  .rag-grid {
    grid-template-columns: 1fr;
    height: auto;
  }
}

/* Common Card Styles */
.card {
  background: var(--bg-card); /* Fallback */
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: var(--radius-lg);
  padding: var(--space-lg);
  display: flex;
  flex-direction: column;
}

.ingest-panel {
  background: rgba(255, 255, 255, 0.03);
}

.chat-panel {
  background: rgba(0, 0, 0, 0.2);
}

/* Header */
.panel-header {
  margin-bottom: var(--space-lg);
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  padding-bottom: var(--space-md);
}

.panel-header h2 {
  font-size: 1.5rem;
  margin-bottom: var(--space-xs);
}

.panel-header p {
  color: var(--text-secondary);
  font-size: 0.9rem;
}

/* Forms */
.form-group {
  margin-bottom: var(--space-md);
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.form-group label {
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--text-muted);
}

.input {
  /* Inherit global input styles usually, but defining basic here just in case */
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: var(--radius-md);
  padding: 0.75rem;
  color: #fff;
  width: 100%;
}

.textarea {
  resize: vertical;
}

.toggle-group {
  display: flex;
  gap: var(--space-xs);
  background: rgba(0, 0, 0, 0.3);
  padding: 4px;
  border-radius: var(--radius-md);
  align-self: flex-start;
}

.btn-toggle {
  background: transparent;
  border: none;
  color: var(--text-muted);
  padding: 4px 12px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 0.85rem;
}

.btn-toggle.active {
  background: var(--primary);
  color: #fff;
}

.full-width {
  width: 100%;
}

/* Jobs List */
.jobs-list {
  margin-top: var(--space-xl);
  border-top: 1px solid rgba(255, 255, 255, 0.1);
  padding-top: var(--space-md);
}

.jobs-list h3 {
  font-size: 1rem;
  margin-bottom: var(--space-md);
  color: var(--text-secondary);
}

.job-item {
  background: rgba(0, 0, 0, 0.2);
  padding: var(--space-sm);
  border-radius: var(--radius-sm);
  margin-bottom: var(--space-sm);
  font-size: 0.85rem;
}

.job-info {
  display: flex;
  justify-content: space-between;
}

.job-status {
  text-transform: uppercase;
  font-size: 0.75rem;
  font-weight: 600;
}
.job-status.pending { color: var(--accent-yellow); }
.job-status.processing { color: var(--accent-blue); }
.job-status.completed { color: var(--accent-green); }
.job-status.failed { color: var(--accent-red); }

.job-error {
  color: var(--accent-red);
  font-size: 0.75rem;
  margin-top: 4px;
}

/* Chat Area */
.chat-area {
  flex: 1;
  overflow-y: auto;
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: var(--radius-md);
  background: rgba(0, 0, 0, 0.3);
  padding: var(--space-md);
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  margin-bottom: var(--space-md);
  min-height: 300px;
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-muted);
  font-style: italic;
}

.message {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-width: 85%;
}

.message.user {
  align-self: flex-end;
  align-items: flex-end;
}

.message.assistant {
  align-self: flex-start;
  align-items: flex-start;
}

.message-role {
  font-size: 0.7rem;
  color: var(--text-muted);
  margin-bottom: 2px;
}

.message-bubble {
  padding: var(--space-md);
  border-radius: var(--radius-lg);
  font-size: 0.95rem;
  line-height: 1.5;
}

.message.user .message-bubble {
  background: var(--primary);
  color: white;
  border-bottom-right-radius: 4px;
}

.message.assistant .message-bubble {
  background: var(--bg-card);
  border: 1px solid rgba(255,255,255,0.1);
  border-bottom-left-radius: 4px;
}

/* Citations */
.citations {
  margin-top: var(--space-md);
  padding-top: var(--space-sm);
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.citations-Label {
  font-size: 0.75rem;
  color: var(--text-muted);
  display: block;
  margin-bottom: 4px;
}

.citation-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.citation-tag {
  background: rgba(255, 255, 255, 0.1);
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-size: 0.75rem;
  color: var(--text-secondary);
}

.chat-input-form {
  display: flex;
  gap: var(--space-sm);
}

.spinner-dots {
  animation: pulse 1.5s infinite;
}

@keyframes pulse {
  0% { opacity: 0.3; }
  50% { opacity: 1; }
  100% { opacity: 0.3; }
}
</style>
