import { ref } from 'vue'

export function useAgentSSE() {
  const streamingContent = ref('')
  const streamingStatus = ref('')
  const streamingDone = ref(false)
  const streamingError = ref(null)
  const pendingActions = ref([])
  const streamingSteps = ref([])
  const streamingTask = ref(null)
  const streamingReport = ref(null)
  let eventSource = null

  function connect(sessionId, message) {
    if (eventSource) {
      eventSource.close()
    }
    streamingContent.value = ''
    streamingStatus.value = '思考中...'
    streamingDone.value = false
    streamingError.value = null
    pendingActions.value = []
    streamingSteps.value = []
    streamingTask.value = null
    streamingReport.value = null

    const url = `/agent/chat/stream?session_id=${sessionId}&message=${encodeURIComponent(message)}`
    eventSource = new EventSource(url)

    eventSource.addEventListener('status', (e) => {
      const data = JSON.parse(e.data)
      streamingStatus.value = data.content
    })

    eventSource.addEventListener('task_card', (e) => {
      const data = JSON.parse(e.data)
      streamingTask.value = {
        title: data.title || '运维任务进度',
        urgency: data.urgency || 'normal',
        totalSteps: data.total_steps || 0,
      }
    })

    eventSource.addEventListener('step_start', (e) => {
      const data = JSON.parse(e.data)
      streamingSteps.value.push({
        step_id: data.step_id,
        round: data.round,
        tool_name: data.tool_name,
        display_name: data.display_name,
        tool_args: data.tool_args,
        title: data.title,
        status: 'running',
        started_at: data.started_at,
        expanded: false,
      })
    })

    eventSource.addEventListener('step_finish', (e) => {
      const data = JSON.parse(e.data)
      const idx = streamingSteps.value.findIndex(s => s.step_id === data.step_id)
      if (idx >= 0) {
        streamingSteps.value[idx] = {
          ...streamingSteps.value[idx],
          status: data.status,
          summary: data.summary,
          conclusion: data.conclusion,
          anomaly: data.anomaly,
          raw_output: data.raw_output,
          tool_args_text: data.tool_args,
          duration_ms: data.duration_ms,
          finished_at: data.finished_at,
        }
      }
    })

    eventSource.addEventListener('progress', (e) => {
      const data = JSON.parse(e.data)
      if (streamingTask.value) {
        streamingTask.value = {
          ...streamingTask.value,
          totalSteps: data.total_steps || streamingTask.value.totalSteps,
          completedSteps: data.completed_steps,
          percent: data.percent,
          urgency: data.urgency || streamingTask.value.urgency,
        }
      }
    })

    eventSource.addEventListener('pending_action', (e) => {
      const data = JSON.parse(e.data)
      if (!pendingActions.value.find(p => p.id === data.id)) {
        pendingActions.value.push(data)
      }
    })

    eventSource.addEventListener('done', (e) => {
      const data = JSON.parse(e.data)
      streamingDone.value = true
      streamingStatus.value = ''
      streamingError.value = null
      if (data.reply) {
        streamingContent.value = data.reply
      }
      if (data.steps && data.steps.length) {
        streamingSteps.value = data.steps.map(s => ({ ...s, expanded: false }))
      }
      if (data.total_steps !== undefined && streamingTask.value) {
        streamingTask.value = {
          ...streamingTask.value,
          totalSteps: data.total_steps,
          completedSteps: data.completed_steps,
          percent: 100,
          urgency: data.urgency || streamingTask.value.urgency,
        }
      }
      streamingReport.value = { summary: data.reply }
    })

    eventSource.addEventListener('error', (e) => {
      const data = JSON.parse(e.data)
      streamingError.value = data.content
      streamingStatus.value = ''
      streamingDone.value = true
    })

    eventSource.onerror = () => {
      if (eventSource.readyState !== EventSource.CLOSED && !streamingDone.value) {
        streamingError.value = '连接中断'
        streamingStatus.value = ''
        streamingDone.value = true
      }
    }
  }

  function disconnect() {
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
  }

  return {
    connect,
    disconnect,
    streamingContent,
    streamingStatus,
    streamingDone,
    streamingError,
    pendingActions,
    streamingSteps,
    streamingTask,
    streamingReport,
  }
}
