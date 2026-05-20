/**
 * LocalFileConnector · 本地文件上传(向导阶段仅占位,提示后续可上传)。
 *
 * 决策: MVP 阶段不在向导内做真实上传 - 用户先建项目, 之后随时上传。
 */

import { Upload, ArrowRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ConnectorCard } from './ConnectorCard'

interface LocalFileConnectorProps {
  onSkip: () => void
}

export function LocalFileConnector({ onSkip }: LocalFileConnectorProps) {
  return (
    <ConnectorCard icon={Upload} title="本地文件" state="pending">
      <div className="space-y-3">
        <p className="text-caption text-text-muted">
          支持 md / txt / docx / pdf / json, 单文件 ≤ 50MB。
        </p>
        <p className="text-caption text-text-subtle">
          创建项目后, 在"数据源"页面可随时上传文件作为补充语料。
        </p>
        <Button
          type="button"
          variant="ghost"
          onClick={onSkip}
          className="font-ui text-caption"
        >
          稍后上传
          <ArrowRight className="size-3.5" />
        </Button>
      </div>
    </ConnectorCard>
  )
}
