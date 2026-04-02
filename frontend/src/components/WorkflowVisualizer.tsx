import { CheckCircle2, XCircle, RefreshCw } from 'lucide-react'
import { cn } from '../lib/utils'
import type { AgentNode, NodeStatus } from '../types'

interface Props {
  nodes: AgentNode[]
}

// 节点状态对应的样式配置
const statusConfig: Record<NodeStatus, {
  ring:    string
  bg:      string
  text:    string
  icon?:   React.ReactNode
  pulse:   boolean
}> = {
  idle: {
    ring:  'border-bg-border',
    bg:    'bg-bg-card',
    text:  'text-text-muted',
    pulse: false,
  },
  running: {
    ring:  'border-brand/60',
    bg:    'bg-brand/10',
    text:  'text-brand-glow',
    pulse: true,
  },
  done: {
    ring:  'border-accent-green/60',
    bg:    'bg-accent-green/10',
    text:  'text-accent-green',
    icon:  <CheckCircle2 className="h-3 w-3" />,
    pulse: false,
  },
  error: {
    ring:  'border-accent-red/60',
    bg:    'bg-accent-red/10',
    text:  'text-accent-red',
    icon:  <XCircle className="h-3 w-3" />,
    pulse: false,
  },
  retrying: {
    ring:  'border-accent-yellow/60',
    bg:    'bg-accent-yellow/10',
    text:  'text-accent-yellow',
    icon:  <RefreshCw className="h-3 w-3 animate-spin" />,
    pulse: true,
  },
}

function NodeCard({ node }: { node: AgentNode }) {
  const cfg = statusConfig[node.status]
  return (
    <div className="flex flex-col items-center gap-2">
      {/* 节点圆圈 */}
      <div className="relative">
        {/* 呼吸光晕 */}
        {cfg.pulse && (
          <span className={cn(
            'absolute inset-0 rounded-full animate-ping opacity-30',
            node.status === 'running' ? 'bg-brand' : 'bg-accent-yellow',
          )} />
        )}
        <div className={cn(
          'relative flex h-14 w-14 items-center justify-center rounded-full border-2',
          'transition-all duration-500',
          cfg.ring, cfg.bg,
          cfg.pulse && 'shadow-glow-brand',
          node.status === 'done' && 'shadow-glow-green',
        )}>
          <span className="text-2xl leading-none select-none">{node.emoji}</span>
          {/* 状态角标 */}
          {cfg.icon && (
            <span
              className={cn(
                'absolute -bottom-0.5 -right-0.5 flex h-4 w-4 items-center justify-center',
                'rounded-full',
                cfg.text,
              )}
              style={{ backgroundColor: 'var(--bg-base)' }}
            >
              {cfg.icon}
            </span>
          )}
        </div>
      </div>

      {/* 节点标签 */}
      <div className="flex flex-col items-center gap-0.5">
        <span className={cn('text-xs font-medium transition-colors', cfg.text)}>
          {node.label}
        </span>
        {node.detail && (
          <span className="text-[10px] text-text-muted">{node.detail}</span>
        )}
        {node.status === 'running' && (
          <span className="flex items-center gap-1 text-[10px] text-brand animate-pulse">
            <span className="h-1 w-1 rounded-full bg-brand" />
            running
          </span>
        )}
      </div>
    </div>
  )
}

function Arrow({ active }: { active: boolean }) {
  return (
    <div className="flex flex-1 items-center justify-center">
      <div className={cn(
        'h-px flex-1 transition-all duration-500',
        active
          ? 'bg-gradient-to-r from-brand/60 to-brand/20'
          : 'bg-bg-border',
      )} />
      <svg
        className={cn('h-3 w-3 flex-none transition-colors', active ? 'text-brand/60' : 'text-bg-border')}
        viewBox="0 0 12 12" fill="currentColor"
      >
        <path d="M6.5 1.5l5 4.5-5 4.5V8H.5V4h6V1.5z" />
      </svg>
    </div>
  )
}

export default function WorkflowVisualizer({ nodes }: Props) {
  return (
    <section className="animate-slide-up">
      <div className="card-gradient-border p-6">
        <div className="mb-6 flex items-center gap-2">
          <div className="h-1.5 w-1.5 rounded-full bg-accent-purple animate-pulse" />
          <h2 className="text-sm font-medium text-text-secondary uppercase tracking-wider">
            Agent Workflow
          </h2>
        </div>

        {/* DAG 节点流 */}
        <div className="flex items-start">
          {nodes.map((node, idx) => (
            <div key={node.id} className="flex flex-1 items-center">
              <NodeCard node={node} />
              {idx < nodes.length - 1 && (
                <Arrow active={
                  node.status === 'done' ||
                  nodes[idx + 1].status === 'running'
                } />
              )}
            </div>
          ))}
        </div>

        {/* 图例 */}
        <div className="mt-5 flex flex-wrap items-center gap-4 border-t border-bg-border pt-4">
          {(['idle', 'running', 'done', 'retrying'] as NodeStatus[]).map(s => {
            const cfg = statusConfig[s]
            const labels: Record<string, string> = {
              idle: 'Waiting', running: 'Active', done: 'Completed', retrying: 'Retrying',
            }
            return (
              <div key={s} className="flex items-center gap-1.5">
                <div className={cn('h-2.5 w-2.5 rounded-full border', cfg.ring, cfg.bg)} />
                <span className="text-[11px] text-text-muted">{labels[s]}</span>
              </div>
            )
          })}
        </div>
      </div>
    </section>
  )
}
