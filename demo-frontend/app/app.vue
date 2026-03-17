<template>
  <div class="app-container">
    <!-- Header -->
    <header class="header glass">
      <div class="header-content">
        <div class="logo">
          <div class="logo-icon">
            <svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
              <circle cx="16" cy="16" r="14" stroke="url(#gradient)" stroke-width="2"/>
              <path d="M10 16L14 20L22 12" stroke="url(#gradient)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              <defs>
                <linearGradient id="gradient" x1="0" y1="0" x2="32" y2="32">
                  <stop stop-color="#6366f1"/>
                  <stop offset="1" stop-color="#a855f7"/>
                </linearGradient>
              </defs>
            </svg>
          </div>
          <div class="logo-text">
            <h1>Acadlo AI</h1>
            <span class="badge badge-primary">{{ activeTab === 'tutor' ? 'Tutor Demo' : 'RAG Knowledge' }}</span>
          </div>
        </div>

        <!-- Navigation Tabs -->
        <nav class="nav-tabs">
          <button 
            class="nav-tab" 
            :class="{ active: activeTab === 'tutor' }"
            @click="activeTab = 'tutor'"
          >
            🎓 AI Tutor
          </button>
          <button 
            class="nav-tab" 
            :class="{ active: activeTab === 'rag' }"
            @click="activeTab = 'rag'"
          >
            📚 Knowledge & RAG
          </button>
        </nav>

        <div class="header-actions">
          <span class="status-indicator" :class="{ connected: isConnected }">
            <span class="status-dot"></span>
            {{ isConnected ? 'Connected' : 'Disconnected' }}
          </span>
        </div>
      </div>
    </header>

    <!-- Main Content -->
    <main class="main-content">
      <TutorDemo v-if="activeTab === 'tutor'" />
      <RagDemo v-if="activeTab === 'rag'" />
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import TutorDemo from './components/TutorDemo.vue'
import RagDemo from './components/RagDemo.vue'
import './assets/css/main.css'

const activeTab = ref<'tutor' | 'rag'>('tutor')
const isConnected = ref(true)

const runtimeConfig = useRuntimeConfig()
const apiBaseUrl = runtimeConfig.public.apiBaseUrl

// Check API connection on mount
onMounted(async () => {
  try {
    const response = await fetch(`${apiBaseUrl}/health`)
    isConnected.value = response.ok
  } catch {
    isConnected.value = false
  }
})
</script>

<style scoped>
.app-container {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

/* Header */
.header {
  position: sticky;
  top: 0;
  z-index: 100;
  padding: var(--space-md) var(--space-xl);
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(15, 23, 42, 0.8);
  backdrop-filter: blur(12px);
}

.header-content {
  max-width: 1400px;
  margin: 0 auto;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.logo {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  min-width: 200px;
}

.logo-icon {
  display: flex;
  align-items: center;
  justify-content: center;
}

.logo-text h1 {
  font-size: 1.25rem;
  font-weight: 700;
  margin-bottom: 2px;
}

.logo-text .badge {
  font-size: 0.65rem;
}

/* Navigation Tabs */
.nav-tabs {
  display: flex;
  background: rgba(255, 255, 255, 0.05);
  padding: 4px;
  border-radius: var(--radius-lg);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.nav-tab {
  padding: 8px 24px;
  border-radius: var(--radius-md);
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.nav-tab:hover {
  color: var(--text-primary);
}

.nav-tab.active {
  background: var(--primary);
  color: white;
  box-shadow: 0 2px 10px rgba(99, 102, 241, 0.3);
}

/* Status */
.header-actions {
  min-width: 200px;
  display: flex;
  justify-content: flex-end;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  font-size: 0.875rem;
  color: var(--text-secondary);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--accent-red);
}

.status-indicator.connected .status-dot {
  background: var(--accent-green);
  box-shadow: 0 0 8px var(--accent-green);
}

/* Main Content */
.main-content {
  flex: 1;
  width: 100%;
  max-width: 1400px;
  margin: 0 auto;
  padding: var(--space-lg) var(--space-xl);
  display: flex;
  flex-direction: column;
}

/* Transitions */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
