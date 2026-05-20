/**
 * Step 1 · 基本信息(项目名 + 简介)
 *
 * 注意 (TaskTechDesign T02): 项目名 409 立即报错并定位到该字段,
 * 不让用户走完 4 步才发现。
 */

import { useEffect, useRef } from 'react'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'

interface StepBasicInfoProps {
  name: string
  description: string
  nameError: string | null
  onChangeName: (v: string) => void
  onChangeDescription: (v: string) => void
}

export function StepBasicInfo({
  name,
  description,
  nameError,
  onChangeName,
  onChangeDescription,
}: StepBasicInfoProps) {
  // 重名错误时,自动 focus 到 name 字段
  const nameRef = useRef<HTMLInputElement>(null)
  useEffect(() => {
    if (nameError) nameRef.current?.focus()
  }, [nameError])

  return (
    <div className="space-y-5">
      <div className="space-y-1.5">
        <Label htmlFor="project_name">
          项目名 <span className="text-danger">*</span>
        </Label>
        <Input
          id="project_name"
          ref={nameRef}
          value={name}
          onChange={(e) => onChangeName(e.target.value)}
          placeholder="如: Mira Agent · 内部知识助手"
          maxLength={60}
          aria-invalid={Boolean(nameError)}
          aria-describedby={nameError ? 'project_name_error' : 'project_name_help'}
        />
        {nameError ? (
          <p id="project_name_error" className="text-caption text-danger" role="alert">
            {nameError}
          </p>
        ) : (
          <p id="project_name_help" className="text-caption text-text-subtle">
            2-60 字符。可在项目设置里随时修改。
          </p>
        )}
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="project_description">简介 <span className="text-text-subtle">(可选)</span></Label>
        <Textarea
          id="project_description"
          value={description}
          onChange={(e) => onChangeDescription(e.target.value)}
          placeholder="一句话描述这个项目的目标 / 范围,后续生成的文档会引用。"
          rows={3}
          maxLength={300}
        />
        <p className="text-caption text-text-subtle">
          {description.length}/300
        </p>
      </div>
    </div>
  )
}
