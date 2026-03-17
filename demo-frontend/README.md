# Acadlo AI Tutor - Demo Frontend

A polished Nuxt 3 demo application showcasing the Acadlo AI Tutor Runtime Engine.

## Features

- 🎨 **Modern Dark Theme** - Beautiful glassmorphism design with animations
- 💬 **Interactive Chat Interface** - Real-time tutoring conversation
- 🧠 **Thinking Trace Visualization** - See how the AI makes decisions
- 🌐 **Multi-language Support** - English, Arabic, French, Spanish
- 📊 **Session Debug Panel** - Monitor session state in real-time

## Prerequisites

- Node.js 18+ 
- The Acadlo AI Core backend running on `http://localhost:8000`

## Quick Start

```bash
# Install dependencies
npm install

# Start development server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

## Configuration

### API URL

By default, the frontend connects to `http://localhost:8000`. To change this:

```bash
# Set environment variable
API_BASE_URL=http://your-api-url npm run dev
```

Or create a `.env` file:

```env
API_BASE_URL=http://localhost:8000
```

## Demo Flow

1. **Start a Session**
   - Enter tenant ID (demo_tenant)
   - Enter student ID (auto-generated)
   - Enter lesson ID (e.g., lesson_fractions_101)
   - Add objective IDs (comma-separated)
   - Select language
   - Enable "Show AI Thinking Trace" for debug view
   - Click "Start Session"

2. **Chat with the Tutor**
   - The AI tutor will greet you with a diagnostic question
   - Type your answers to interact
   - Watch the thinking trace to see how the AI reasons

3. **Observe the AI**
   - **Analysis**: How the AI classifies your response
   - **Performance Update**: How it tracks your progress
   - **Planning**: What action it decides to take
   - **Response Generation**: How it formulates its reply

## Screenshots

The interface features:
- Session setup form with configuration options
- Real-time chat with tutor and student messages
- Expandable thinking trace for each tutor response
- Session debug panel (sidebar)
- Connection status indicator

## Tech Stack

- **Nuxt 3** - Vue.js framework
- **TypeScript** - Type safety
- **CSS Variables** - Design token system
- **Google Fonts (Inter)** - Typography

## License

MIT
