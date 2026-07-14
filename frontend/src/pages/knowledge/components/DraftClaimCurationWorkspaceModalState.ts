import type {
  DraftClaimCurationEditablePayload,
  DraftClaimCurationItem,
} from '@shared/api/modules/knowledge';

export type EditableDraft = {
  key: string;
  claim: string;
  claimKind: string;
  granularity: string;
  possibleQuestionsText: string;
  exclusionScope: string;
  evidenceBlock: string;
  triplesText: string;
};

export type EditableDraftState = {
  itemRef: string;
  draft: EditableDraft;
};

export const draftFromPayload = (
  payload: DraftClaimCurationEditablePayload,
): EditableDraft => ({
  key: payload.key,
  claim: payload.claim,
  claimKind: payload.claim_kind,
  granularity: payload.granularity,
  possibleQuestionsText: payload.possible_questions.join('\n'),
  exclusionScope: payload.exclusion_scope,
  evidenceBlock: payload.evidence_block,
  triplesText: JSON.stringify(payload.triples, null, 2),
});

export const resolveDraftForSelectedItem = (
  selectedItem: DraftClaimCurationItem | null,
  draftState: EditableDraftState | null,
): EditableDraft | null => {
  if (!selectedItem) return null;
  return draftState?.itemRef === selectedItem.item_ref
    ? draftState.draft
    : draftFromPayload(selectedItem.editable_payload);
};
