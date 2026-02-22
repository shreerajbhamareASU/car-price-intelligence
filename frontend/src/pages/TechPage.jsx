import { useState, useEffect } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Cell, ResponsiveContainer,
} from 'recharts'
import {
  Database, TrendingUp, Cpu, BarChart2, Scale,
  CheckCircle2, Layers, Zap, AlertTriangle,
  BookOpen, Shield, MessageSquare, Eye, Bot, Activity,
  ArrowRight,
} from 'lucide-react'
import { getShapImportance } from '../api'

// ── Agent hub-spoke layout data ───────────────────────────────────────────────
// Agents arranged in a circle around the OrchestratorAgent center
// Angles: 7 agents evenly spaced, starting from top (270°)
const AGENT_ANGLE_START = 270
const NUM_AGENTS = 7
const AGENTS = [
  { name: 'DataAgent',           shortName: 'Data',        Icon: Database,      color: '#3b82f6', desc: 'Price history + market context from MongoDB' },
  { name: 'TrendAnalysisAgent',  shortName: 'Trend',       Icon: TrendingUp,    color: '#8b5cf6', desc: 'Prophet 30/90-day forecast + momentum score' },
  { name: 'ForecastAgent',       shortName: 'Forecast',    Icon: Cpu,           color: '#10b981', desc: 'XGBoost inference + GPT-4o-mini LLM blend' },
  { name: 'RiskAssessmentAgent', shortName: 'Risk',        Icon: Activity,      color: '#f97316', desc: 'Volatility index + risk score + uncertainty range' },
  { name: 'DecisionAgent',       shortName: 'Decision',    Icon: Scale,         color: '#ec4899', desc: 'Three-rule deterministic BUY NOW / WAIT / MONITOR' },
  { name: 'ExplanationAgent',    shortName: 'Explain',     Icon: MessageSquare, color: '#a78bfa', desc: '3-sentence AI reasoning via GPT-4o-mini' },
  { name: 'EthicsAgent',         shortName: 'Ethics',      Icon: Shield,        color: '#22c55e', desc: 'Transparency note + bias statement + disclaimer' },
]

// Decision rules
const DECISION_RULES = [
  { cond: 'change ≤ −3% AND confidence ≥ 75', result: 'WAIT',    badge: 'bg-red-500/15 text-red-400 border-red-500/25',     desc: 'Price declining with high confidence.' },
  { cond: 'change ≥ +2% AND volatility = Low', result: 'BUY NOW', badge: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/25', desc: 'Rising prices with stable market.' },
  { cond: 'price ≤ −10% vs median AND conf ≥ 75', result: 'BUY NOW', badge: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/25', desc: 'Strong below-market deal.' },
  { cond: 'All other scenarios',              result: 'MONITOR', badge: 'bg-amber-500/15 text-amber-400 border-amber-500/25', desc: 'No strong signal — keep watching.' },
]

const MODEL_ROWS = [
  { label: 'Algorithm',     value: 'XGBoost Regressor' },
  { label: 'Target',        value: 'log1p(price) → expm1 at inference' },
  { label: 'Training data', value: '~262k listings (80% chronological split)' },
  { label: 'Test data',     value: '~66k listings (most recent 20% by date)' },
  { label: 'Split method',  value: 'Chronological — zero data leakage' },
  { label: 'Features',      value: '19 total (car_age, log_odometer, make, model…)' },
]

const DATA_SOURCES = [
  { color: '#3b82f6', label: 'Craigslist Dataset',        detail: 'Kaggle · ~426k listings · 26 columns',                  tag: 'Primary'      },
  { color: '#10b981', label: 'Cleaning Pipeline',         detail: 'Colab T4 · 5-step clean → 328k rows',                   tag: 'Processed'    },
  { color: '#8b5cf6', label: 'MongoDB Atlas',             detail: 'carmarket DB · listings + price_snapshots · 175 MB',    tag: 'Storage'      },
  { color: '#f59e0b', label: 'OpenAI GPT-4o-mini',        detail: 'ExplanationAgent + ForecastAgent LLM blend',            tag: 'LLM'          },
  { color: '#ec4899', label: 'Facebook Prophet',          detail: '30/90-day price forecasting · yearly seasonality',       tag: 'Forecast'     },
  { color: '#6366f1', label: 'Multi-Agent Orchestrator',  detail: '7 modular Python agents · deterministic pipeline',       tag: 'Architecture' },
  { color: '#22c55e', label: 'EthicsAgent',               detail: 'Transparency notes · bias audit · principled AI layer',  tag: 'Ethics'       },
  { color: '#64748b', label: 'Dataset Snapshot',          detail: 'Jan 2024 · Static for demo · update on demand',         tag: 'Freshness'    },
]

// ── Animated Hub-Spoke Architecture Diagram ───────────────────────────────────
function AgentOrbitDiagram({ activeAgent, setActiveAgent }) {
  const [tick, setTick] = useState(0)

  // Animate tick for the traveling dots
  useEffect(() => {
    const id = setInterval(() => setTick(t => (t + 1) % 100), 50)
    return () => clearInterval(id)
  }, [])

  // SVG dimensions
  const W = 700, H = 420
  const CX = W / 2, CY = H / 2 - 10
  const R = 150   // orbit radius

  // Compute agent positions
  const agentPositions = AGENTS.map((agent, i) => {
    const angle = (AGENT_ANGLE_START + i * (360 / NUM_AGENTS)) * Math.PI / 180
    return {
      ...agent,
      x: CX + R * Math.cos(angle),
      y: CY + R * Math.sin(angle),
    }
  })

  return (
    <div className="relative w-full" style={{ aspectRatio: '700/420' }}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full h-full"
        style={{ overflow: 'visible' }}
      >
        {/* Orbit ring */}
        <circle cx={CX} cy={CY} r={R}
          fill="none" stroke="#1e293b" strokeWidth="1" strokeDasharray="4 4" />

        {/* Connection lines + animated dots */}
        {agentPositions.map((agent, i) => {
          const isActive = activeAgent === i
          const progress = ((tick + i * 14) % 100) / 100
          const dotX     = CX + (agent.x - CX) * progress
          const dotY     = CY + (agent.y - CY) * progress
          const retProg  = ((tick + i * 14 + 50) % 100) / 100
          const retX     = agent.x + (CX - agent.x) * retProg
          const retY     = agent.y + (CY - agent.y) * retProg

          return (
            <g key={agent.name}>
              {/* Connection line */}
              <line
                x1={CX} y1={CY} x2={agent.x} y2={agent.y}
                stroke={isActive ? agent.color : '#334155'}
                strokeWidth={isActive ? 2 : 1}
                strokeDasharray={isActive ? 'none' : '6 4'}
                opacity={isActive ? 1 : 0.6}
                style={{ transition: 'stroke 0.3s, stroke-width 0.3s' }}
              />
              {/* Outbound traveling dot */}
              <circle cx={dotX} cy={dotY} r={isActive ? 5 : 3}
                fill={agent.color} opacity={isActive ? 1 : 0.7}>
                <animate attributeName="opacity"
                  values="0.4;1;0.4" dur="2s" repeatCount="indefinite" />
              </circle>
              {/* Return traveling dot */}
              <circle cx={retX} cy={retY} r={isActive ? 4 : 2.5}
                fill={agent.color} opacity={0.5} />
            </g>
          )
        })}

        {/* Input node */}
        <g transform={`translate(${CX - R - 90}, ${CY - 20})`}>
          <rect x={0} y={0} width={72} height={40} rx={8}
            fill="#1e293b" stroke="#475569" strokeWidth="1" />
          <text x={36} y={24} textAnchor="middle" fill="#94a3b8" fontSize="10" fontWeight="600">
            User Query
          </text>
          {/* Arrow to orchestrator */}
          <line x1={72} y1={20} x2={90} y2={20}
            stroke="#475569" strokeWidth="1.5"
            markerEnd="url(#arrowhead)" />
        </g>

        {/* Output node */}
        <g transform={`translate(${CX + R + 18}, ${CY - 20})`}>
          <rect x={0} y={0} width={80} height={40} rx={8}
            fill="#1e293b" stroke="#475569" strokeWidth="1" />
          <text x={40} y={16} textAnchor="middle" fill="#94a3b8" fontSize="9" fontWeight="600">
            Structured
          </text>
          <text x={40} y={29} textAnchor="middle" fill="#94a3b8" fontSize="9" fontWeight="600">
            Intel Report
          </text>
          {/* Arrow from orchestrator */}
          <line x1={-18} y1={20} x2={0} y2={20}
            stroke="#475569" strokeWidth="1.5"
            markerEnd="url(#arrowhead)" />
        </g>

        {/* Arrow marker def */}
        <defs>
          <marker id="arrowhead" markerWidth="6" markerHeight="4"
            refX="6" refY="2" orient="auto">
            <polygon points="0 0, 6 2, 0 4" fill="#475569" />
          </marker>
        </defs>

        {/* Central OrchestratorAgent node */}
        <g>
          {/* Outer glow */}
          <circle cx={CX} cy={CY} r={52} fill="#6366f122" />
          <circle cx={CX} cy={CY} r={44} fill="#6366f133">
            <animate attributeName="r" values="44;48;44" dur="3s" repeatCount="indefinite" />
            <animate attributeName="opacity" values="0.8;1;0.8" dur="3s" repeatCount="indefinite" />
          </circle>
          <circle cx={CX} cy={CY} r={40} fill="#1e293b" stroke="#6366f1" strokeWidth="2" />
          <text x={CX} y={CY - 6} textAnchor="middle" fill="#a5b4fc" fontSize="9" fontWeight="700">
            Orchestrator
          </text>
          <text x={CX} y={CY + 8} textAnchor="middle" fill="#818cf8" fontSize="8">
            Agent
          </text>

          {/* Spinning ring */}
          <circle cx={CX} cy={CY} r={54}
            fill="none" stroke="#6366f144" strokeWidth="1.5"
            strokeDasharray="8 6">
            <animateTransform attributeName="transform" type="rotate"
              from={`0 ${CX} ${CY}`} to={`360 ${CX} ${CY}`}
              dur="12s" repeatCount="indefinite" />
          </circle>
        </g>

        {/* Agent nodes */}
        {agentPositions.map((agent, i) => {
          const isActive = activeAgent === i
          const { Icon } = agent

          return (
            <g key={agent.name}
              style={{ cursor: 'pointer' }}
              onClick={() => setActiveAgent(isActive ? null : i)}>

              {/* Node glow when active */}
              {isActive && (
                <circle cx={agent.x} cy={agent.y} r={32}
                  fill={agent.color + '22'}>
                  <animate attributeName="r" values="28;34;28" dur="1.5s" repeatCount="indefinite" />
                </circle>
              )}

              {/* Node circle */}
              <circle cx={agent.x} cy={agent.y} r={26}
                fill={isActive ? agent.color + '33' : '#1e293b'}
                stroke={agent.color}
                strokeWidth={isActive ? 2.5 : 1.5}
                style={{ transition: 'fill 0.3s, stroke-width 0.3s' }}>
                {!isActive && (
                  <animate attributeName="opacity"
                    values="0.85;1;0.85" dur={`${2 + i * 0.3}s`} repeatCount="indefinite" />
                )}
              </circle>

              {/* Agent label */}
              <text x={agent.x} y={agent.y + 4}
                textAnchor="middle"
                fill={isActive ? 'white' : agent.color}
                fontSize="9" fontWeight={isActive ? '700' : '600'}>
                {agent.shortName}
              </text>

              {/* Pulse dot indicator */}
              <circle cx={agent.x + 18} cy={agent.y - 18} r={4}
                fill={agent.color} opacity={isActive ? 1 : 0.6}>
                <animate attributeName="r" values="3;5;3" dur={`${1.2 + i * 0.15}s`} repeatCount="indefinite" />
              </circle>
            </g>
          )
        })}

        {/* Pipeline sequence labels at the bottom */}
        {agentPositions.map((agent, i) => (
          <text key={agent.name + '_seq'}
            x={agent.x} y={agent.y + 40}
            textAnchor="middle"
            fill="#475569" fontSize="7.5">
            {i + 1}
          </text>
        ))}
      </svg>
    </div>
  )
}

// ── Main component ─────────────────────────────────────────────────────────────
export default function TechPage() {
  const [shap,        setShap]        = useState([])
  const [loading,     setLoading]     = useState(true)
  const [activeAgent, setActiveAgent] = useState(null)

  useEffect(() => {
    getShapImportance()
      .then(r => setShap(r.data.features ?? []))
      .finally(() => setLoading(false))
  }, [])

  const chartTooltipStyle = {
    contentStyle: { background: '#1e293b', border: '1px solid #334155', borderRadius: '8px', fontSize: 12 },
    labelStyle:   { color: '#e2e8f0' },
  }

  const selectedAgent = activeAgent !== null ? AGENTS[activeAgent] : null

  return (
    <div className="min-h-screen">

      {/* ── Hero ── */}
      <div className="bg-gradient-to-b from-slate-800 to-slate-900 border-b border-slate-700/50">
        <div className="max-w-7xl mx-auto px-6 py-12">
          <div className="flex items-center gap-2 text-blue-400 text-xs font-semibold uppercase tracking-widest mb-3">
            <Layers size={12} />
            Principled AI · Multi-Agent Architecture
          </div>
          <h1 className="text-4xl font-extrabold text-white mb-2">
            System <span className="text-blue-400">Architecture</span>
          </h1>
          <p className="text-slate-400 text-base max-w-2xl">
            A modular 7-agent decision intelligence pipeline. Deterministic Python orchestration
            with GPT-4o-mini used only where human-level reasoning adds value —
            never for routing or decision-making.
          </p>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 mt-8 space-y-8 pb-12">

        {/* ── Animated Hub-Spoke Diagram ── */}
        <div className="bg-slate-800 border border-slate-700 rounded-2xl p-6">
          <div className="flex items-center gap-2 mb-1">
            <Layers size={18} className="text-blue-400" />
            <h2 className="text-xl font-bold text-white">Multi-Agent Hub Architecture</h2>
            <span className="text-xs px-2 py-0.5 rounded-full bg-blue-500/15 text-blue-400 border border-blue-500/20 font-semibold ml-1">
              Live
            </span>
          </div>
          <p className="text-slate-400 text-sm mb-4">
            OrchestratorAgent coordinates 7 specialized sub-agents.
            Click any agent node to explore its role.
          </p>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

            {/* SVG diagram */}
            <div className="lg:col-span-2 bg-slate-900/60 border border-slate-700/50 rounded-2xl p-4 overflow-hidden">
              <AgentOrbitDiagram activeAgent={activeAgent} setActiveAgent={setActiveAgent} />
            </div>

            {/* Agent details panel */}
            <div className="space-y-3">
              {selectedAgent ? (
                <div className="bg-slate-900/60 border rounded-2xl p-5 transition-all duration-300"
                  style={{ borderColor: selectedAgent.color + '55' }}>
                  <div className="flex items-center gap-3 mb-3">
                    <div className="w-11 h-11 rounded-xl flex items-center justify-center"
                      style={{ background: selectedAgent.color + '22' }}>
                      <selectedAgent.Icon size={22} style={{ color: selectedAgent.color }} />
                    </div>
                    <div>
                      <p className="text-white font-bold">{selectedAgent.name}</p>
                      <p className="text-xs font-bold" style={{ color: selectedAgent.color }}>Agent #{AGENTS.indexOf(selectedAgent) + 1}</p>
                    </div>
                  </div>
                  <p className="text-slate-300 text-sm leading-relaxed">{selectedAgent.desc}</p>
                  <button onClick={() => setActiveAgent(null)}
                    className="mt-4 text-xs text-slate-500 hover:text-slate-400 underline">
                    Deselect
                  </button>
                </div>
              ) : (
                <div className="bg-slate-900/40 border border-slate-700/40 rounded-2xl p-5">
                  <p className="text-slate-500 text-sm mb-3">Click an agent to see its role</p>
                  <div className="space-y-1.5">
                    {AGENTS.map((a, i) => (
                      <button key={a.name} onClick={() => setActiveAgent(i)}
                        className="w-full flex items-center gap-2 p-2 rounded-lg hover:bg-slate-800/60 transition-colors text-left">
                        <div className="w-5 h-5 rounded-full flex items-center justify-center"
                          style={{ background: a.color + '22' }}>
                          <a.Icon size={10} style={{ color: a.color }} />
                        </div>
                        <span className="text-slate-400 text-xs">{a.name}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Pipeline order */}
              <div className="bg-slate-900/40 border border-slate-700/40 rounded-2xl p-4">
                <p className="text-slate-500 text-xs font-semibold uppercase tracking-wide mb-3">Pipeline Order</p>
                <div className="space-y-1.5">
                  {[
                    { step: 'Input',       desc: 'User query', color: '#64748b' },
                    { step: 'Orchestrate', desc: 'Route + coordinate', color: '#6366f1' },
                    ...AGENTS.map(a => ({ step: a.shortName, desc: a.desc.split(' + ')[0], color: a.color })),
                    { step: 'Report',      desc: 'Intelligence brief', color: '#f59e0b' },
                  ].map((item, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <div className="w-4 h-4 rounded-full flex items-center justify-center text-[9px] font-bold text-slate-700"
                        style={{ background: item.color + '33', color: item.color }}>
                        {i}
                      </div>
                      <span className="text-xs font-medium" style={{ color: item.color }}>{item.step}</span>
                      <ArrowRight size={8} className="text-slate-700" />
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* ── Decision Rules ── */}
        <div className="bg-slate-800 border border-slate-700 rounded-2xl p-6">
          <div className="flex items-center gap-2 mb-2">
            <Scale size={18} className="text-blue-400" />
            <h2 className="text-xl font-bold text-white">Decision Rules</h2>
            <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/20 font-semibold ml-1">
              Deterministic · Auditable
            </span>
          </div>
          <p className="text-slate-400 text-sm mb-5">
            DecisionAgent applies three ordered rules in pure Python — no LLM, no randomness.
            Every recommendation traces to exact numerical thresholds.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {DECISION_RULES.map((r, i) => (
              <div key={i} className="bg-slate-900/60 border border-slate-700 rounded-xl p-4">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xs text-slate-500 font-mono bg-slate-800 px-2 py-0.5 rounded">
                    Rule {i + 1 <= 3 ? i + 1 : '∗'}
                  </span>
                  <span className={`text-xs px-2 py-0.5 rounded border font-bold ${r.badge}`}>
                    {r.result}
                  </span>
                </div>
                <p className="text-white text-xs font-mono mb-1.5 leading-relaxed">{r.cond}</p>
                <p className="text-slate-500 text-xs">{r.desc}</p>
              </div>
            ))}
          </div>
        </div>

        {/* ── SHAP + Model Card ── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">

          <div className="bg-slate-800 border border-slate-700 rounded-2xl p-6">
            <div className="flex items-center gap-2 mb-1">
              <BarChart2 size={18} className="text-blue-400" />
              <h2 className="text-xl font-bold text-white">What Drives Car Prices?</h2>
            </div>
            <p className="text-slate-400 text-sm mb-4">
              Global SHAP importance from 500 held-out test listings.&nbsp;
              <span className="text-emerald-400">Green</span> = increases price ·&nbsp;
              <span className="text-blue-400">Blue</span> = decreases price
            </p>

            {loading ? (
              <div className="animate-pulse h-52 bg-slate-700 rounded-xl" />
            ) : shap.length > 0 ? (
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={shap} layout="vertical" margin={{ left: 10, right: 30 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
                  <XAxis type="number" tickFormatter={v => v.toFixed(3)} tick={{ fontSize: 10, fill: '#64748b' }} />
                  <YAxis type="category" dataKey="feature" width={130}
                    tickFormatter={v => v.replace(/_/g, ' ')} tick={{ fontSize: 11, fill: '#cbd5e1' }} />
                  <Tooltip {...chartTooltipStyle}
                    formatter={(v, _, p) => [v.toFixed(4), p.payload.direction === 'positive' ? 'Increases price' : 'Decreases price']}
                  />
                  <Bar dataKey="importance" radius={[0, 4, 4, 0]}>
                    {shap.map((f, i) => (
                      <Cell key={i} fill={f.direction === 'positive' ? '#10b981' : '#3b82f6'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-32 flex items-center justify-center text-slate-500 text-sm">
                SHAP data unavailable — ensure shap_data.pkl is in models/
              </div>
            )}
          </div>

          <div className="bg-slate-800 border border-slate-700 rounded-2xl p-6">
            <div className="flex items-center gap-2 mb-4">
              <Cpu size={18} className="text-blue-400" />
              <h2 className="text-xl font-bold text-white">Model Card</h2>
            </div>

            <div className="space-y-3 mb-6">
              {MODEL_ROWS.map(r => (
                <div key={r.label} className="flex gap-3 text-sm border-b border-slate-700/40 pb-3 last:border-0 last:pb-0">
                  <span className="text-slate-500 w-36 flex-shrink-0 font-medium">{r.label}</span>
                  <span className="text-slate-200">{r.value}</span>
                </div>
              ))}
            </div>

            <div className="space-y-3">
              <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-xl p-4">
                <div className="flex items-center gap-1.5 mb-2">
                  <Zap size={13} className="text-emerald-400" />
                  <p className="text-xs font-bold text-emerald-400 uppercase tracking-wide">Predicts well</p>
                </div>
                <ul className="text-xs text-emerald-300/80 space-y-1">
                  <li>· Common makes (toyota, ford, honda, chevrolet…)</li>
                  <li>· Cars with complete odometer + year data</li>
                  <li>· Price ranges $1k – $50k</li>
                </ul>
              </div>

              <div className="bg-amber-500/10 border border-amber-500/20 rounded-xl p-4">
                <div className="flex items-center gap-1.5 mb-2">
                  <AlertTriangle size={13} className="text-amber-400" />
                  <p className="text-xs font-bold text-amber-400 uppercase tracking-wide">Limitations</p>
                </div>
                <ul className="text-xs text-amber-300/80 space-y-1">
                  <li>· Rare/luxury vehicles — limited training samples</li>
                  <li>· Condition is self-reported by sellers</li>
                  <li>· Static snapshot — real prices drift over time</li>
                  <li>· No accident history or trim-level detail</li>
                </ul>
              </div>
            </div>
          </div>
        </div>

        {/* ── Data Sources ── */}
        <div className="bg-slate-800 border border-slate-700 rounded-2xl p-6">
          <div className="flex items-center gap-2 mb-4">
            <BookOpen size={18} className="text-blue-400" />
            <h2 className="text-xl font-bold text-white">Data Sources &amp; Stack</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {DATA_SOURCES.map(s => (
              <div key={s.label}
                className="bg-slate-900/50 border border-slate-700 rounded-xl p-4 flex items-start gap-3 hover:border-slate-600 transition-colors">
                <div className="w-2.5 h-2.5 rounded-full mt-1.5 flex-shrink-0" style={{ backgroundColor: s.color }} />
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-white text-sm font-semibold">{s.label}</span>
                    <span className="text-xs px-1.5 py-0.5 rounded bg-slate-700 text-slate-400 font-medium">{s.tag}</span>
                  </div>
                  <p className="text-slate-500 text-xs mt-0.5 leading-relaxed">{s.detail}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

      </div>
    </div>
  )
}
