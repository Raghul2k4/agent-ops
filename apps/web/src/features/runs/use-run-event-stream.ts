import { useEffect, useRef } from 'react'

import { getAccessToken } from '@/lib/api-client'
import type { RunEventRead } from '@/types/api'

/**
 * Parse one Server-Sent Events frame.
 *
 * Returns the event it carries, or `null` for a keep-alive, an end marker or
 * a malformed frame. A malformed frame is skipped rather than breaking the
 * stream: the sequence cursor still protects the client from losing events.
 */
export function parseEventChunk(chunk: string): RunEventRead | null {
  if (chunk.includes('event: end')) return null
  const dataLine = chunk
    .split('\n')
    .find((line) => line.startsWith('data:'))
    ?.slice(5)
    .trim()
  if (!dataLine || dataLine === '{}') return null
  try {
    const event = JSON.parse(dataLine) as RunEventRead
    return typeof event.sequence_number === 'number' ? event : null
  } catch {
    return null
  }
}

/**
 * Live run events over Server-Sent Events.
 *
 * The stream is authenticated with the bearer token, so it is consumed with
 * `fetch` rather than `EventSource` (which cannot set headers). Missed events
 * are recovered with the sequence cursor: the last sequence number the client
 * saw is sent back as `after_seq` when the stream reconnects, so no event is
 * lost when the connection drops.
 */
export function useRunEventStream(
  runId: string | null,
  onEvents: (events: RunEventRead[]) => void,
): void {
  const lastSequence = useRef(0)
  const handler = useRef(onEvents)
  handler.current = onEvents

  useEffect(() => {
    if (!runId) return
    const controller = new AbortController()
    let closed = false

    const consume = async (afterSeq: number): Promise<void> => {
      while (!closed) {
        const token = await getAccessToken()
        if (!token) return
        let response: Response
        try {
          response = await fetch(
            `/api/v1/runs/${runId}/events/stream?after_seq=${afterSeq}`,
            {
              headers: { Authorization: `Bearer ${token}`, Accept: 'text/event-stream' },
              credentials: 'omit',
              signal: controller.signal,
            },
          )
        } catch {
          return
        }
        if (!response.ok || !response.body) {
          if (closed) return
          await new Promise((resolve) => setTimeout(resolve, 1500))
          continue
        }

        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        let ended = false

        while (!closed) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          let boundary = buffer.indexOf('\n\n')
          while (boundary !== -1) {
            const chunk = buffer.slice(0, boundary)
            buffer = buffer.slice(boundary + 2)
            boundary = buffer.indexOf('\n\n')

            const event = parseEventChunk(chunk)
            if (!event) {
              if (chunk.includes('event: end')) ended = true
              continue
            }
            lastSequence.current = Math.max(lastSequence.current, event.sequence_number)
            handler.current([event])
          }
          if (ended) break
        }
        if (ended || closed) return
        // The connection dropped: resume from the cursor.
        await new Promise((resolve) => setTimeout(resolve, 1000))
      }
    }

    void consume(0)

    return () => {
      closed = true
      controller.abort()
    }
  }, [runId])
}
