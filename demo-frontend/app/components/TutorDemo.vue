<template>
  <div class="chat-container">
    <!-- Session Setup Panel -->
    <div v-if="!session.id" class="setup-panel card animate-fade-in">
      <div class="setup-header">
        <h2 class="gradient-text">Start a Tutoring Session</h2>
        <p>Configure the session parameters and begin learning</p>
      </div>
      
      <form @submit.prevent="startSession" class="setup-form">
        <div class="form-grid">
          <div class="form-group">
            <label for="tenantId">Tenant ID</label>
            <input 
              id="tenantId" 
              v-model="config.tenantId" 
              class="input" 
              placeholder="e.g., demo_tenant"
              required
            />
          </div>
          
          <div class="form-group">
            <label for="studentId">Student ID</label>
            <input 
              id="studentId" 
              v-model="config.studentId" 
              class="input" 
              placeholder="e.g., student_123"
              required
            />
          </div>
          
          <div class="form-group">
            <label for="locale">Language</label>
            <select id="locale" v-model="config.locale" class="input">
              <option value="en-US">English (US)</option>
              <option value="ar-JO">Arabic (Jordan)</option>
              <option value="fr-FR">French</option>
              <option value="es-ES">Spanish</option>
            </select>
          </div>
        </div>

        <div class="form-group full-width">
          <label for="ingestedTopic">Available Topics (from ingested documents)</label>
          <select
            id="ingestedTopic"
            v-model="selectedTopicId"
            class="input"
            :disabled="topicsLoading"
          >
            <option value="">{{ topicsLoading ? 'Loading topics...' : 'Enter custom topic (skip)' }}</option>
            <option
              v-for="topic in availableTopics"
              :key="topic.id"
              :value="topic.id"
            >
              {{ topic.topic_name }} ({{ topic.subject }})
            </option>
          </select>
          <small class="input-help">
            Select an ingested topic to skip the "what topic?" question, or leave blank for a custom topic.
          </small>
        </div>

        <div v-if="!selectedTopicId" class="form-group full-width">
          <label class="checkbox-label">
            <input type="checkbox" v-model="config.includeLessonObjectives" />
            <span>Include Lesson &amp; Objectives</span>
          </label>
        </div>

        <template v-if="!selectedTopicId && config.includeLessonObjectives">
          <div class="form-grid">
            <div class="form-group">
              <label for="lessonId">Lesson ID (optional)</label>
              <input 
                id="lessonId" 
                v-model="config.lessonId" 
                class="input" 
                placeholder="e.g., lesson_fractions_101"
              />
            </div>
          </div>

          <div class="form-group full-width">
            <label for="objectiveIds">Objective IDs (optional, comma-separated)</label>
            <input
              id="objectiveIds"
              v-model="config.objectiveIds"
              class="input"
              placeholder="e.g., obj_understand_fractions, obj_add_fractions"
            />
            <small class="input-help">If left blank, plain-English objectives below will be used.</small>
          </div>

          <div class="form-group full-width">
            <label>Objectives (plain English)</label>
            <div class="objective-items">
              <div
                v-for="(_, index) in config.objectives"
                :key="index"
                class="objective-item-row"
              >
                <input
                  v-model="config.objectives[index]"
                  class="input"
                  :placeholder="`Objective ${index + 1} (e.g., Understand equivalent fractions)`"
                />
                <button
                  type="button"
                  class="btn btn-ghost objective-remove-btn"
                  @click="removeObjective(index)"
                >
                  Remove
                </button>
              </div>
            </div>
            <button type="button" class="btn btn-ghost objective-add-btn" @click="addObjective">
              + Add objective
            </button>
          </div>
        </template>
        
        <div class="form-actions">
          <label class="checkbox-label">
            <input type="checkbox" v-model="config.showThinkingTrace" />
            <span>Show AI Thinking Trace (Debug)</span>
          </label>
          <button type="submit" class="btn btn-primary" :disabled="isLoading">
            <span v-if="isLoading" class="spinner"></span>
            <span v-else>Start Session</span>
          </button>
        </div>
      </form>
    </div>

    <!-- Chat Interface -->
    <div v-else class="chat-interface">
      <!-- Session Info Bar -->
      <div class="session-bar glass">
        <div class="session-info">
          <span class="badge badge-success">Session Active</span>
          <span class="session-id">{{ session.id.substring(0, 8) }}...</span>
          <span class="session-lesson">📚 {{ session.lessonId }}</span>
          <span class="session-objective">🎯 {{ session.currentObjectiveId }}</span>
        </div>
        <button @click="resetSession" class="btn btn-ghost">
          End Session
        </button>
      </div>

      <!-- Messages Area -->
      <div class="messages-container" ref="messagesContainer">
        <div 
          v-for="(message, index) in messages" 
          :key="index"
          class="message animate-fade-in"
          :class="message.type"
        >
          <div class="message-avatar">
            <span v-if="message.type === 'tutor'">🤖</span>
            <span v-else>👤</span>
          </div>
          <div class="message-content">
            <div class="message-header">
              <span class="message-sender">{{ message.type === 'tutor' ? 'AI Tutor' : 'You' }}</span>
              <span class="message-time">{{ formatTime(message.timestamp) }}</span>
            </div>
            <div class="message-text">{{ message.text }}</div>
            
            <!-- Thinking Trace (if available) -->
            <div v-if="message.thinkingTrace && showThinkingTrace" class="thinking-trace">
              <button @click="message.showTrace = !message.showTrace" class="trace-toggle">
                <span>{{ message.showTrace ? '▼' : '▶' }} AI Thinking Process</span>
              </button>
              <div v-if="message.showTrace" class="trace-content">
                <div 
                  v-for="(step, i) in message.thinkingTrace" 
                  :key="i" 
                  class="trace-step"
                  :class="step.stage"
                >
                  <div class="trace-stage">
                    <span class="stage-icon">{{ getStageIcon(step.stage) }}</span>
                    <span class="stage-name">{{ formatStageName(step.stage) }}</span>
                  </div>
                  <div class="trace-summary">{{ step.summary }}</div>
                  <div v-if="step.data" class="trace-data">
                    <pre>{{ JSON.stringify(step.data, null, 2) }}</pre>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Typing Indicator -->
        <div v-if="isLoading" class="message tutor typing animate-fade-in">
          <div class="message-avatar">🤖</div>
          <div class="message-content">
            <div class="typing-dots">
              <span></span>
              <span></span>
              <span></span>
            </div>
          </div>
        </div>
      </div>

      <!-- Input Area -->
      <div class="input-area glass">
        <form @submit.prevent="sendMessage" class="input-form">
          <input 
            v-model="userMessage" 
            class="input message-input" 
            placeholder="Type your answer or question..."
            :disabled="isLoading || session.lessonComplete"
          />
          <button 
            type="submit" 
            class="btn btn-primary send-btn" 
            :disabled="!userMessage.trim() || isLoading || session.lessonComplete"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M22 2L11 13M22 2L15 22L11 13L2 9L22 2Z" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </button>
        </form>
        <div v-if="session.lessonComplete" class="lesson-complete-banner">
          🎉 Lesson Complete! Great job!
        </div>
      </div>
    </div>
  </div>

  <!-- Debug Panel (Floating or Separate) -->
  <div v-if="showThinkingTrace && session.id" class="debug-panel card">
    <h3>Session Debug Info</h3>
    <div class="debug-content">
      <div class="debug-row">
        <span class="debug-label">Session ID:</span>
        <span class="debug-value">{{ session.id }}</span>
      </div>
      <div class="debug-row">
        <span class="debug-label">Tenant:</span>
        <span class="debug-value">{{ config.tenantId }}</span>
      </div>
      <div class="debug-row">
        <span class="debug-label">Lesson:</span>
        <span class="debug-value">{{ session.lessonId }}</span>
      </div>
      <div class="debug-row">
        <span class="debug-label">Current Objective:</span>
        <span class="debug-value">{{ session.currentObjectiveId || 'N/A' }}</span>
      </div>
      <div class="debug-row">
        <span class="debug-label">Lesson Complete:</span>
        <span class="debug-value">{{ session.lessonComplete ? 'Yes' : 'No' }}</span>
      </div>
      <div class="debug-row">
        <span class="debug-label">Messages:</span>
        <span class="debug-value">{{ messages.length }}</span>
      </div>
    </div>
  </div>
  
  <div v-if="error" class="error-toast animate-slide-in">
    <span>❌ {{ error }}</span>
    <button @click="error = ''" class="btn btn-ghost">×</button>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, nextTick, computed, watch } from 'vue'

// Interfaces
interface Message {
  type: 'tutor' | 'student'
  text: string
  timestamp: Date
  thinkingTrace?: ThinkingStep[]
  showTrace?: boolean
}

interface ThinkingStep {
  stage: string
  summary: string
  data?: Record<string, any>
}

interface AvailableTopic {
  id: string
  topic_name: string
  subject: string
  description: string
  grade_level: string | null
}

interface Session {
  id: string
  lessonId: string
  currentObjectiveId: string | null
  lessonComplete: boolean
}

// Runtime config
const runtimeConfig = useRuntimeConfig()
const apiBaseUrl = runtimeConfig.public.apiBaseUrl

// State
const isLoading = ref(false)
const error = ref('')
const userMessage = ref('')
const messagesContainer = ref<HTMLElement | null>(null)
const showThinkingTrace = computed(() => config.showThinkingTrace)

const config = reactive({
  tenantId: 'demo_tenant',
  studentId: 'student_' + Math.random().toString(36).substring(7),
  lessonId: '',
  objectiveIds: '',
  objectives: [] as string[],
  locale: 'en-US',
  showThinkingTrace: true,
  includeLessonObjectives: false
})

const session = reactive<Session>({
  id: '',
  lessonId: '',
  currentObjectiveId: null,
  lessonComplete: false
})

const messages = ref<Message[]>([])

// Available ingested topics for the selected tenant
const availableTopics = ref<AvailableTopic[]>([])
const selectedTopicId = ref('')
const topicsLoading = ref(false)

async function fetchTopics(tenantId: string) {
  if (!tenantId.trim()) {
    availableTopics.value = []
    return
  }
  topicsLoading.value = true
  try {
    const resp = await fetch(`${apiBaseUrl}/v1/topics?tenant_id=${encodeURIComponent(tenantId)}`)
    if (resp.ok) {
      const data = await resp.json()
      availableTopics.value = data.topics || []
    } else {
      availableTopics.value = []
    }
  } catch {
    availableTopics.value = []
  } finally {
    topicsLoading.value = false
  }
}

watch(() => config.tenantId, (val) => {
  selectedTopicId.value = ''
  fetchTopics(val)
}, { immediate: true })

// Methods
async function startSession() {
  isLoading.value = true
  error.value = ''
  
  try {
    const useLessonFields = !selectedTopicId.value && config.includeLessonObjectives
    const objectiveIds = useLessonFields
      ? config.objectiveIds.split(',').map(s => s.trim()).filter(Boolean)
      : []
    const objectives = useLessonFields
      ? config.objectives.map(s => s.trim()).filter(Boolean)
      : []
    const lessonId = useLessonFields ? (config.lessonId?.trim() || null) : null

    const payload: Record<string, any> = {
      tenant_id: config.tenantId,
      student_id: config.studentId,
      lesson_id: lessonId,
      objectives: objectives.length > 0 ? objectives : null,
      locale: config.locale,
      include_thinking_trace: config.showThinkingTrace
    }

    if (objectiveIds.length > 0) {
      payload.objective_ids = objectiveIds
    }

    if (selectedTopicId.value) {
      payload.ingested_topic_id = selectedTopicId.value
    }
    
    const response = await fetch(`${apiBaseUrl}/v1/tutor/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    
    if (!response.ok) {
      const err = await response.json()
      throw new Error(err.message || 'Failed to start session')
    }
    
    const data = await response.json()
    
    session.id = data.session_id
    session.lessonId = data.lesson_id
    session.currentObjectiveId = data.current_objective_id
    session.lessonComplete = data.lesson_complete
    
    messages.value.push({
      type: 'tutor',
      text: data.tutor_reply,
      timestamp: new Date(),
      thinkingTrace: data.debug?.thinking_trace,
      showTrace: false
    })
    
    await scrollToBottom()
  } catch (e: any) {
    error.value = e.message
  } finally {
    isLoading.value = false
  }
}

function addObjective() {
  config.objectives.push('')
}

function removeObjective(index: number) {
  config.objectives.splice(index, 1)
}

async function sendMessage() {
  if (!userMessage.value.trim() || isLoading.value) return
  
  const text = userMessage.value.trim()
  userMessage.value = ''
  
  messages.value.push({
    type: 'student',
    text,
    timestamp: new Date()
  })
  
  await scrollToBottom()
  isLoading.value = true
  error.value = ''
  
  try {
    const response = await fetch(`${apiBaseUrl}/v1/tutor/turn`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tenant_id: config.tenantId,
        session_id: session.id,
        student_message: text,
        include_thinking_trace: config.showThinkingTrace
      })
    })
    
    if (!response.ok) {
      const err = await response.json()
      throw new Error(err.message || 'Failed to send message')
    }
    
    const data = await response.json()
    
    session.currentObjectiveId = data.current_objective_id
    session.lessonComplete = data.lesson_complete
    
    messages.value.push({
      type: 'tutor',
      text: data.tutor_reply,
      timestamp: new Date(),
      thinkingTrace: data.debug?.thinking_trace,
      showTrace: false
    })
    
    await scrollToBottom()
  } catch (e: any) {
    error.value = e.message
  } finally {
    isLoading.value = false
  }
}

function resetSession() {
  session.id = ''
  session.lessonId = ''
  session.currentObjectiveId = null
  session.lessonComplete = false
  messages.value = []
  config.studentId = 'student_' + Math.random().toString(36).substring(7)
}

async function scrollToBottom() {
  await nextTick()
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
}

function getStageIcon(stage: string): string {
  const icons: Record<string, string> = {
    analysis: '🔍',
    performance_update: '📊',
    planning: '🧠',
    response_generation: '💬'
  }
  return icons[stage] || '📌'
}

function formatStageName(stage: string): string {
  return stage.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}
</script>

<style scoped>
/* Copied styles relevant to TutorDemo */
.chat-container {
  display: flex;
  flex-direction: column;
  flex: 1;
}

.setup-panel {
  padding: var(--space-2xl);
  max-width: 800px;
  margin: 0 auto;
  width: 100%;
}

.setup-header {
  text-align: center;
  margin-bottom: var(--space-xl);
}

.setup-header h2 {
  font-size: 1.75rem;
  margin-bottom: var(--space-sm);
}

.setup-header p {
  color: var(--text-secondary);
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-md);
  margin-bottom: var(--space-md);
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.form-group.full-width {
  grid-column: 1 / -1;
}

.form-group label {
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text-secondary);
}

.input-help {
  font-size: 0.75rem;
  color: var(--text-muted);
}

.objective-items {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.objective-item-row {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.objective-item-row .input {
  flex: 1;
}

.objective-add-btn,
.objective-remove-btn {
  white-space: nowrap;
}

.form-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: var(--space-lg);
  padding-top: var(--space-lg);
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  cursor: pointer;
  font-size: 0.875rem;
  color: var(--text-secondary);
}

.checkbox-label input[type="checkbox"] {
  width: 18px;
  height: 18px;
  accent-color: var(--primary);
}

/* Chat Interface */
.chat-interface {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 200px); /* Adjusted for tabs */
  min-height: 500px;
}

.session-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-md) var(--space-lg);
  margin-bottom: var(--space-md);
  border-radius: var(--radius-md);
}

.session-info {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  font-size: 0.875rem;
}

.session-id {
  color: var(--text-muted);
  font-family: monospace;
}

.session-lesson,
.session-objective {
  color: var(--text-secondary);
}

/* Messages */
.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-md);
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.message {
  display: flex;
  gap: var(--space-md);
  max-width: 85%;
}

.message.student {
  align-self: flex-end;
  flex-direction: row-reverse;
}

.message-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: var(--bg-card);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.25rem;
  flex-shrink: 0;
}

.message-content {
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  padding: var(--space-md);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.message.student .message-content {
  background: var(--primary);
  border-color: var(--primary-dark);
}

.message-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-md);
  margin-bottom: var(--space-xs);
}

.message-sender {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-secondary);
}

.message.student .message-sender {
  color: rgba(255, 255, 255, 0.8);
}

.message-time {
  font-size: 0.7rem;
  color: var(--text-muted);
}

.message.student .message-time {
  color: rgba(255, 255, 255, 0.6);
}

.message-text {
  line-height: 1.5;
}

/* Thinking Trace */
.thinking-trace {
  margin-top: var(--space-md);
  border-top: 1px solid rgba(255, 255, 255, 0.1);
  padding-top: var(--space-sm);
}

.trace-toggle {
  background: none;
  border: none;
  color: var(--primary-light);
  font-size: 0.8rem;
  cursor: pointer;
  padding: var(--space-xs) 0;
}

.trace-toggle:hover {
  color: var(--primary);
}

.trace-content {
  margin-top: var(--space-sm);
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.trace-step {
  background: rgba(0, 0, 0, 0.2);
  border-radius: var(--radius-sm);
  padding: var(--space-sm);
  border-left: 3px solid var(--primary);
}

.trace-step.analysis { border-left-color: var(--accent-blue); }
.trace-step.performance_update { border-left-color: var(--accent-yellow); }
.trace-step.planning { border-left-color: var(--accent-purple); }
.trace-step.response_generation { border-left-color: var(--accent-green); }

.trace-stage {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  font-size: 0.75rem;
  font-weight: 600;
  margin-bottom: var(--space-xs);
}

.trace-summary {
  font-size: 0.8rem;
  color: var(--text-secondary);
}

.trace-data {
  margin-top: var(--space-xs);
}

.trace-data pre {
  font-size: 0.7rem;
  color: var(--text-muted);
  background: rgba(0, 0, 0, 0.3);
  padding: var(--space-xs);
  border-radius: var(--radius-sm);
  overflow-x: auto;
}

/* Input Area */
.input-area {
  padding: var(--space-md);
  border-radius: var(--radius-md);
  margin-top: var(--space-md);
}

.input-form {
  display: flex;
  gap: var(--space-sm);
}

.message-input {
  flex: 1;
}

.send-btn {
  width: 48px;
  padding: 0;
}

/* Debug panel */
.debug-panel {
  position: fixed;
  bottom: 20px;
  right: 20px;
  width: 300px;
  background: rgba(15, 23, 42, 0.95);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: var(--radius-md);
  padding: var(--space-md);
  z-index: 1000;
  font-size: 0.8rem;
}

.debug-panel h3 {
  margin-bottom: var(--space-sm);
  padding-bottom: var(--space-sm);
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.debug-row {
  display: flex;
  justify-content: space-between;
  margin-bottom: 4px;
}

.debug-label {
  color: var(--text-muted);
}

/* Error toast */
.error-toast {
  position: fixed;
  bottom: 20px;
  left: 50%;
  transform: translateX(-50%);
  background: var(--accent-red);
  color: white;
  padding: var(--space-sm) var(--space-lg);
  border-radius: var(--radius-full);
  display: flex;
  align-items: center;
  gap: var(--space-md);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  z-index: 2000;
}
</style>
