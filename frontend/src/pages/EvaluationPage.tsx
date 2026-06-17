import { useReducer } from 'react'
import type { FormEvent } from 'react'
import { m } from 'framer-motion'
import { Send, FlaskConical, Cpu, AlertTriangle } from 'lucide-react'
import { api } from '../services/api'
import type { RiskLevel, MessageIntent } from '../types'

interface SimResult {
  conversation_id?: string
  intent?: MessageIntent
  risk_level?: RiskLevel
  message?: string
}

const EXAMPLE_MESSAGES = [
  "Hi, we need to cancel the event. The venue fell through and we can't reschedule.",
  "Quick update — our guest count has changed from 120 to 165. Will that affect catering?",
  "I haven't received the invoice yet and the payment deadline is tomorrow. Can you resend?",
  "Everything looks great! We're confirmed for June 14th at the Grand Ballroom.",
  "We've had multiple complaints about the decoration choices. The client is very unhappy.",
]

const RISK_COLORS: Record<string, string> = {
  low: 'bg-success-soft text-success',
  medium: 'bg-warning-soft text-warning',
  high: 'bg-danger-soft text-danger',
  critical: 'bg-danger-soft text-danger',
}

const DETECTED_SIGNALS = [
  { label: 'Cancellation risk', color: 'text-danger' },
  { label: 'Complaint', color: 'text-danger' },
  { label: 'Payment issue', color: 'text-warning' },
  { label: 'Guest count change', color: 'text-warning' },
  { label: 'General inquiry', color: 'text-info' },
  { label: 'Confirmation', color: 'text-success' },
]

type EvaluationState = {
  message: string
  clientName: string
  loading: boolean
  result: SimResult | null
  error: string
}

type EvaluationAction =
  | { type: 'SET_MESSAGE'; payload: string }
  | { type: 'SET_CLIENT_NAME'; payload: string }
  | { type: 'SUBMIT_STARTED' }
  | { type: 'SUBMIT_SUCCEEDED'; payload: SimResult }
  | { type: 'SUBMIT_FAILED'; payload: string }

const initialEvaluationState: EvaluationState = {
  message: '',
  clientName: '',
  loading: false,
  result: null,
  error: '',
}

function evaluationReducer(state: EvaluationState, action: EvaluationAction): EvaluationState {
  switch (action.type) {
    case 'SET_MESSAGE':
      return { ...state, message: action.payload }
    case 'SET_CLIENT_NAME':
      return { ...state, clientName: action.payload }
    case 'SUBMIT_STARTED':
      return { ...state, loading: true, error: '', result: null }
    case 'SUBMIT_SUCCEEDED':
      return { ...state, loading: false, result: action.payload }
    case 'SUBMIT_FAILED':
      return { ...state, loading: false, error: action.payload }
    default:
      return state
  }
}

export function EvaluationPage() {
  const [state, dispatch] = useReducer(evaluationReducer, initialEvaluationState)
  const { message, clientName, loading, result, error } = state

  const handleSimulate = async (e: FormEvent) => {
    e.preventDefault()
    if (!message.trim()) return
    dispatch({ type: 'SUBMIT_STARTED' })
    try {
      const res = await api.post('/api/v1/simulator/messages', {
        content: message,
        client_name: clientName || 'Demo Client',
      })
      dispatch({ type: 'SUBMIT_SUCCEEDED', payload: res.data as SimResult })
    } catch {
      dispatch({ type: 'SUBMIT_FAILED', payload: 'Failed to simulate message. Ensure the backend is running.' })
    }
  }

  return (
    <div>
      <div className="mb-8">
        <div className="flex items-center gap-2.5 mb-2">
          <div className="w-9 h-9 rounded-lg bg-info-soft border border-info/20 flex items-center justify-center">
            <FlaskConical className="w-5 h-5 text-info" strokeWidth={1.75} />
          </div>
          <div>
            <h1 className="font-display text-3xl font-medium text-text-primary">AI Sandbox</h1>
          </div>
        </div>
        <p className="text-sm text-text-muted">
          Test how EventSense classifies and responds to client messages. Simulate any scenario to see real-time intent detection and risk assessment.
        </p>
      </div>

      <div className="grid lg:grid-cols-5 gap-6">
        {/* Simulator form */}
        <div className="lg:col-span-3">
          <div className="card p-6">
            <h2 className="text-sm font-semibold text-text-primary mb-4 flex items-center gap-2">
              <Cpu className="w-4 h-4 text-accent" strokeWidth={1.75} />
              Message simulator
            </h2>

            <form onSubmit={handleSimulate} className="space-y-4">
              <div>
                <label htmlFor="sim-client-name" className="block text-xs font-medium text-text-primary mb-1.5">Client name (optional)</label>
                <input
                  id="sim-client-name"
                  type="text"
                  value={clientName}
                  onChange={(e) => dispatch({ type: 'SET_CLIENT_NAME', payload: e.target.value })}
                  placeholder="Demo Client"
                  className="input-base"
                />
              </div>
              <div>
                <label htmlFor="sim-message" className="block text-xs font-medium text-text-primary mb-1.5">Client message</label>
                <textarea
                  id="sim-message"
                  value={message}
                  onChange={(e) => dispatch({ type: 'SET_MESSAGE', payload: e.target.value })}
                  placeholder="Type a simulated client message…"
                  rows={4}
                  className="input-base resize-none"
                />
              </div>
              <button
                type="submit"
                disabled={!message.trim() || loading}
                className="btn-primary w-full gap-2 disabled:opacity-60"
              >
                <Send className="w-4 h-4" />
                {loading ? 'Analyzing…' : 'Simulate message'}
              </button>
            </form>

            {/* Result */}
            {error && (
              <div className="mt-4 p-3 bg-danger-soft border border-danger/20 rounded-lg">
                <p className="text-xs text-danger">{error}</p>
              </div>
            )}

            {result && (
              <m.div
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                className="mt-5 p-4 bg-surface-warm border border-border rounded-lg space-y-3"
              >
                <p className="text-xs font-semibold text-text-primary">Analysis result</p>
                <div className="grid grid-cols-2 gap-3">
                  {result.intent && (
                    <div className="p-3 bg-surface rounded-lg border border-border">
                      <p className="text-[10px] text-text-muted mb-1">Intent</p>
                      <p className="text-sm font-medium text-text-primary capitalize">
                        {result.intent.replace(/_/g, ' ')}
                      </p>
                    </div>
                  )}
                  {result.risk_level && (
                    <div className="p-3 bg-surface rounded-lg border border-border">
                      <p className="text-[10px] text-text-muted mb-1">Risk level</p>
                      <span className={`text-sm font-medium px-2 py-0.5 rounded-full capitalize ${RISK_COLORS[result.risk_level] ?? ''}`}>
                        {result.risk_level}
                      </span>
                    </div>
                  )}
                </div>
                {result.conversation_id && (
                  <p className="text-xs text-text-muted">
                    Conversation created:{' '}
                    <span className="font-mono text-info">{result.conversation_id.slice(0, 8)}…</span>
                  </p>
                )}
              </m.div>
            )}
          </div>
        </div>

        {/* Example messages */}
        <div className="lg:col-span-2">
          <div className="card p-5">
            <h2 className="text-sm font-semibold text-text-primary mb-4 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-warning" strokeWidth={1.75} />
              Example scenarios
            </h2>
            <div className="space-y-2">
              {EXAMPLE_MESSAGES.map((ex) => (
                <button
                  key={ex}
                  type="button"
                  onClick={() => dispatch({ type: 'SET_MESSAGE', payload: ex })}
                  className="w-full text-left p-3 text-xs text-text-body bg-surface-warm hover:bg-accent-soft/40 border border-border hover:border-accent/30 rounded-lg transition-colors leading-relaxed"
                >
                  &ldquo;{ex}&rdquo;
                </button>
              ))}
            </div>
          </div>

          <div className="card p-5 mt-4">
            <h3 className="text-xs font-semibold text-text-primary mb-3">What EventSense detects</h3>
            <div className="space-y-2">
              {DETECTED_SIGNALS.map((item) => (
                <div key={item.label} className="flex items-center gap-2">
                  <div className="w-1.5 h-1.5 rounded-full bg-current opacity-60" />
                  <span className={`text-xs ${item.color}`}>{item.label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
