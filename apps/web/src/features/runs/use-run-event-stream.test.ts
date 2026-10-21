import { describe, expect, it } from 'vitest'

import { parseEventChunk } from './use-run-event-stream'

describe('parseEventChunk', () => {
  it('reads the event carried by a frame', () => {
    const frame = [
      'id: 12',
      'data: {"id":"e1","sequence_number":12,"event_type":"tool.result","event_status":"ok","payload":{},"occurred_at":"2026-10-21T10:00:00Z"}',
    ].join('\n')

    const event = parseEventChunk(frame)

    expect(event?.sequence_number).toBe(12)
    expect(event?.event_type).toBe('tool.result')
  })

  it('ignores the end marker', () => {
    expect(parseEventChunk('event: end\ndata: {}')).toBeNull()
  })

  it('ignores keep-alive frames', () => {
    expect(parseEventChunk(': keep-alive')).toBeNull()
    expect(parseEventChunk('data: {}')).toBeNull()
  })

  it('ignores a malformed frame instead of throwing', () => {
    expect(parseEventChunk('data: {not json')).toBeNull()
  })

  it('ignores a frame without a sequence number', () => {
    expect(parseEventChunk('data: {"id":"e1"}')).toBeNull()
  })
})
