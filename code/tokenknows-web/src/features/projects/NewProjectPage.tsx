/**
 * T02 · NewProjectPage
 *
 * 4 步向导:
 *   1 基本信息 → 提交触发 POST /projects(可能 409 重名)
 *   2 选择数据源 → 选 ≥ 1 个数据源类型
 *   3 接入指引 → 每类一张 ConnectorCard, 至少接入 1 个
 *   4 完成 → setCurrent + 跳 /projects/:id
 *
 * 决策依据 TaskTechDesign T02 关键决策与补充。
 */

import { useCallback, useReducer, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, ArrowRight, Loader2, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useProjectStore } from '@/stores/projectStore'
import { isApiError } from '@/lib/api'
import {
  canAdvance,
  initialState,
  wizardReducer,
  type WizardStep,
} from './wizard'
import { useCreateProject } from './hooks/useCreateProject'
import { WizardStepper } from './components/WizardStepper'
import { StepBasicInfo } from './components/StepBasicInfo'
import { StepDatasources } from './components/StepDatasources'
import { StepConnect } from './components/StepConnect'
import { StepDone } from './components/StepDone'

export default function NewProjectPage() {
  const navigate = useNavigate()
  const setCurrent = useProjectStore((s) => s.setCurrent)
  const [state, dispatch] = useReducer(wizardReducer, initialState)
  const createProject = useCreateProject()
  const [exitDialogOpen, setExitDialogOpen] = useState(false)

  const handleSubmitStep1 = () => {
    if (!canAdvance(state)) return
    createProject.mutate(
      { name: state.name, description: state.description },
      {
        onSuccess: (project) => {
          dispatch({ type: 'PROJECT_CREATED', project })
          dispatch({ type: 'GO_NEXT' })
        },
        onError: (err) => {
          if (isApiError(err) && err.status === 409) {
            dispatch({ type: 'NAME_CONFLICT', message: err.message })
          }
        },
      },
    )
  }

  const handleNext = () => {
    if (state.step === 1) {
      handleSubmitStep1()
      return
    }
    dispatch({ type: 'GO_NEXT' })
  }

  const handleGoToWorkbench = useCallback(() => {
    if (!state.createdProject) return
    setCurrent(state.createdProject.id)
    navigate(`/projects/${state.createdProject.id}`, { replace: true })
  }, [state.createdProject, navigate, setCurrent])

  const handleExit = () => {
    // step 1 无数据丢失;> 1 已建项目, 提示放弃但保留项目
    if (state.step === 1 && !state.name && !state.description) {
      navigate('/')
      return
    }
    setExitDialogOpen(true)
  }

  const errorMessage =
    createProject.error && !state.nameError && isApiError(createProject.error)
      ? createProject.error.message
      : null

  return (
    <div className="mx-auto max-w-3xl px-6 py-8 sm:py-12">
      <header className="mb-8 flex items-start justify-between gap-4">
        <div className="space-y-1">
          <p className="font-ui text-eyebrow uppercase tracking-wider text-text-muted">
            T02 · 新建项目
          </p>
          <h1 className="font-content text-h1 text-text-primary">建立你的研发知识空间</h1>
          <p className="text-body text-text-muted">
            4 个步骤, 接入数据源后 24 小时内你将看到第一份自动生成的周报。
          </p>
        </div>
        <button
          type="button"
          onClick={handleExit}
          aria-label="退出向导"
          className="rounded-md p-2 text-text-muted transition hover:bg-bg-warm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary"
        >
          <X className="size-4" />
        </button>
      </header>

      <div className="mb-8">
        <WizardStepper current={state.step} />
      </div>

      <section
        className="rounded-lg border border-border-subtle bg-bg-card p-6 shadow-elev-1"
        aria-live="polite"
      >
        {state.step === 1 && (
          <StepBasicInfo
            name={state.name}
            description={state.description}
            nameError={state.nameError}
            onChangeName={(v) => dispatch({ type: 'SET_NAME', value: v })}
            onChangeDescription={(v) => dispatch({ type: 'SET_DESCRIPTION', value: v })}
          />
        )}
        {state.step === 2 && (
          <StepDatasources
            selectedTypes={state.selectedTypes}
            onToggle={(ds) => dispatch({ type: 'TOGGLE_DATASOURCE', ds })}
          />
        )}
        {state.step === 3 && state.createdProject && (
          <StepConnect
            project={state.createdProject}
            selectedTypes={state.selectedTypes}
            addedDatasources={state.addedDatasources}
            onDatasourceAdded={(ds) => dispatch({ type: 'DATASOURCE_ADDED', ds })}
          />
        )}
        {state.step === 4 && state.createdProject && (
          <StepDone
            project={state.createdProject}
            addedDatasources={state.addedDatasources}
            onGoToWorkbench={handleGoToWorkbench}
          />
        )}

        {errorMessage ? (
          <div
            className="mt-4 rounded-md border border-danger-border bg-danger-bg px-3 py-2 text-body-sm text-danger"
            role="alert"
          >
            {errorMessage}
          </div>
        ) : null}
      </section>

      {/* 底部操作条 - Step 4 自带 CTA 不显示 */}
      {state.step < 4 ? (
        <footer className="mt-6 flex items-center justify-between gap-3">
          <Button
            type="button"
            variant="ghost"
            onClick={() => dispatch({ type: 'GO_PREV' })}
            disabled={state.step === 1 || createProject.isPending}
            className="font-ui"
          >
            <ArrowLeft className="size-4" />
            上一步
          </Button>

          <div className="flex items-center gap-2">
            <span className="font-mono text-caption text-text-subtle">
              {state.step} / 4
            </span>
            <Button
              type="button"
              onClick={handleNext}
              disabled={!canAdvance(state) || createProject.isPending}
              className="font-ui"
            >
              {createProject.isPending ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  创建中...
                </>
              ) : state.step === 3 ? (
                <>
                  完成
                  <ArrowRight className="size-4" />
                </>
              ) : (
                <>
                  下一步
                  <ArrowRight className="size-4" />
                </>
              )}
            </Button>
          </div>
        </footer>
      ) : null}

      {/* 退出确认 dialog (TaskTechDesign T02: 不要静默丢数据) */}
      <Dialog open={exitDialogOpen} onOpenChange={setExitDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>放弃创建?</DialogTitle>
            <DialogDescription>
              {state.createdProject
                ? `项目"${state.createdProject.name}"已创建, 退出后可在工作台继续配置数据源。`
                : '已输入的内容不会保存。确定要退出?'}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="ghost"
              onClick={() => setExitDialogOpen(false)}
              className="font-ui"
            >
              继续向导
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                setExitDialogOpen(false)
                if (state.createdProject) {
                  setCurrent(state.createdProject.id)
                  navigate(`/projects/${state.createdProject.id}`, { replace: true })
                } else {
                  navigate('/')
                }
              }}
              className="font-ui"
            >
              {state.createdProject ? '前往工作台' : '放弃并返回'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// 兜底防止 lazy import 抛错 - 强制 step 类型存在
export type { WizardStep }
