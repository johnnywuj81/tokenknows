/**
 * WizardStepper · 顶部 4 步进度条。
 *
 * 视觉:
 *   ① ──── ② ──── ③ ──── ④
 *   基本   数据源  接入   完成
 *
 * 已完成 = success;当前 = primary;未到 = subtle。
 */

import { Check } from 'lucide-react'
import { cn } from '@/lib/utils'
import { STEP_TITLES, type WizardStep } from '../wizard'

interface WizardStepperProps {
  current: WizardStep
}

const steps: WizardStep[] = [1, 2, 3, 4]

export function WizardStepper({ current }: WizardStepperProps) {
  return (
    <ol className="flex items-center gap-2" aria-label="向导进度">
      {steps.map((s, i) => {
        const done = s < current
        const active = s === current
        const subtle = s > current
        return (
          <li key={s} className="flex flex-1 items-center gap-2">
            <div className="flex items-center gap-2">
              <span
                aria-current={active ? 'step' : undefined}
                className={cn(
                  'flex size-7 shrink-0 items-center justify-center rounded-full font-ui text-body-sm font-medium transition',
                  done && 'bg-success text-inverse-text',
                  active && 'bg-accent-primary text-inverse-text shadow-elev-1',
                  subtle && 'bg-bg-warm text-text-muted',
                )}
              >
                {done ? <Check className="size-4" /> : s}
              </span>
              <span
                className={cn(
                  'whitespace-nowrap font-ui text-caption',
                  done && 'text-success-dark',
                  active && 'text-text-primary font-medium',
                  subtle && 'text-text-subtle',
                )}
              >
                {STEP_TITLES[s]}
              </span>
            </div>
            {i < steps.length - 1 ? (
              <div
                className={cn(
                  'h-px flex-1 transition',
                  s < current ? 'bg-success-border' : 'bg-border-subtle',
                )}
                aria-hidden="true"
              />
            ) : null}
          </li>
        )
      })}
    </ol>
  )
}
