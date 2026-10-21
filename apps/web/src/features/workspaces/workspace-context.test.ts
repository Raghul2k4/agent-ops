import { describe, expect, it } from 'vitest'

import { roleCan } from './workspace-context'

describe('roleCan', () => {
  it('lets reviewers and above decide an approval', () => {
    expect(roleCan('reviewer', 'approval.decide')).toBe(true)
    expect(roleCan('operator', 'approval.decide')).toBe(true)
    expect(roleCan('developer', 'approval.decide')).toBe(true)
    expect(roleCan('admin', 'approval.decide')).toBe(true)
    expect(roleCan('owner', 'approval.decide')).toBe(true)
  })

  it('never lets a viewer decide an approval', () => {
    expect(roleCan('viewer', 'approval.decide')).toBe(false)
    expect(roleCan(null, 'approval.decide')).toBe(false)
  })

  it('keeps the policy editor to owners and administrators', () => {
    expect(roleCan('owner', 'workspace.update')).toBe(true)
    expect(roleCan('admin', 'workspace.update')).toBe(true)
    expect(roleCan('developer', 'workspace.update')).toBe(false)
    expect(roleCan('reviewer', 'workspace.update')).toBe(false)
  })

  it('keeps writing agents to developers and above', () => {
    expect(roleCan('developer', 'agent.write')).toBe(true)
    expect(roleCan('operator', 'agent.write')).toBe(false)
    expect(roleCan('viewer', 'agent.write')).toBe(false)
  })

  it('lets every member read runs and approvals', () => {
    expect(roleCan('viewer', 'run.read')).toBe(true)
    expect(roleCan('viewer', 'approval.read')).toBe(true)
  })
})
