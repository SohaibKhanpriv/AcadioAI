// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2025-05-15',
  devtools: { enabled: true },

  // Global CSS
  css: ['~/assets/css/main.css'],

  // Runtime config for API URL
  runtimeConfig: {
    public: {
      apiBaseUrl: 'http://localhost:8000'
    }
  },

  // App configuration
  app: {
    head: {
      title: 'Acadlo AI Tutor - Demo',
      meta: [
        { name: 'description', content: 'Demo of the Acadlo AI Tutor Runtime Engine' }
      ],
      link: [
        { rel: 'preconnect', href: 'https://fonts.googleapis.com' },
        { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: '' },
        { rel: 'stylesheet', href: 'https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap' }
      ]
    }
  }
})
