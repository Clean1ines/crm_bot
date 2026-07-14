import { describe, expect, it } from 'vitest';

import type {
  DraftClaimCurationEditablePayload,
  DraftClaimCurationItem,
} from '@shared/api/modules/knowledge';

import { draftFromPayload, resolveDraftForSelectedItem } from './DraftClaimCurationWorkspaceModalState';

const editablePayload = (
  key: string,
  claim: string,
): DraftClaimCurationEditablePayload => ({
  key,
  claim,
  claim_kind: 'fact',
  granularity: 'atomic',
  source_claim_refs: [],
  triples: [],
  merge_decision: 'unmerged',
  possible_questions: [`Question for ${key}`],
  exclusion_scope: '',
  evidence_block: `Evidence for ${key}`,
});

const item = (itemRef: string, key: string, claim: string): DraftClaimCurationItem => ({
  item_ref: itemRef,
  workspace_ref: 'workspace-1',
  workflow_run_id: 'workflow-1',
  group_ref: `group-${itemRef}`,
  compacted_node_ref: `node-${itemRef}`,
  source_claim_refs: [],
  original_payload: editablePayload(key, claim),
  editable_payload: editablePayload(key, claim),
  excluded: false,
});

describe('DraftClaimCurationWorkspaceModalState', () => {
  it('keeps edited draft state only for the matching selected curation item', () => {
    const first = item('item-1', 'first-key', 'First claim');
    const second = item('item-2', 'second-key', 'Second claim');
    const editedFirst = {
      itemRef: first.item_ref,
      draft: {
        ...draftFromPayload(first.editable_payload),
        key: 'edited-first-key',
      },
    };

    expect(resolveDraftForSelectedItem(first, editedFirst)?.key).toBe(
      'edited-first-key',
    );
    expect(resolveDraftForSelectedItem(second, editedFirst)?.key).toBe(
      'second-key',
    );
    expect(resolveDraftForSelectedItem(null, editedFirst)).toBeNull();
  });
});
