import { useState, useCallback, useMemo, type Dispatch, type SetStateAction } from 'react';
import type { ActionDetail, AnalysisResult } from '../types';

export interface ActionsState {
  selectedActionIds: Set<string>;
  setSelectedActionIds: Dispatch<SetStateAction<Set<string>>>;
  manuallyAddedIds: Set<string>;
  setManuallyAddedIds: Dispatch<SetStateAction<Set<string>>>;
  rejectedActionIds: Set<string>;
  setRejectedActionIds: Dispatch<SetStateAction<Set<string>>>;
  suggestedByRecommenderIds: Set<string>;
  setSuggestedByRecommenderIds: Dispatch<SetStateAction<Set<string>>>;

  handleActionFavorite: (actionId: string, setResult: Dispatch<SetStateAction<AnalysisResult | null>>) => void;
  handleActionReject: (actionId: string) => void;
  handleManualActionAdded: (
    actionId: string,
    detail: ActionDetail,
    linesOverloaded: string[],
    setResult: Dispatch<SetStateAction<AnalysisResult | null>>,
    onSelectAction: (actionId: string) => void,
  ) => void;
  clearActionState: () => void;
}

export function useActions(): ActionsState {
  const [selectedActionIds, setSelectedActionIds] = useState<Set<string>>(new Set());
  const [manuallyAddedIds, setManuallyAddedIds] = useState<Set<string>>(new Set());
  const [rejectedActionIds, setRejectedActionIds] = useState<Set<string>>(new Set());
  const [suggestedByRecommenderIds, setSuggestedByRecommenderIds] = useState<Set<string>>(new Set());

  const handleActionFavorite = useCallback((actionId: string, setResult: React.Dispatch<React.SetStateAction<AnalysisResult | null>>) => {
    setSelectedActionIds(prev => {
      const next = new Set(prev);
      next.add(actionId);
      return next;
    });
    setResult(prev => {
      if (!prev || !prev.actions[actionId]) return prev;
      return {
        ...prev,
        actions: {
          ...prev.actions,
          [actionId]: { ...prev.actions[actionId], is_manual: true }
        }
      };
    });
    setRejectedActionIds(prev => {
      const next = new Set(prev);
      next.delete(actionId);
      return next;
    });
  }, []);

  const handleActionReject = useCallback((actionId: string) => {
    setRejectedActionIds(prev => {
      const next = new Set(prev);
      next.add(actionId);
      return next;
    });
    setSelectedActionIds(prev => {
      const next = new Set(prev);
      next.delete(actionId);
      return next;
    });
    setManuallyAddedIds(prev => {
      const next = new Set(prev);
      next.delete(actionId);
      return next;
    });
  }, []);

  const handleManualActionAdded = useCallback((
    actionId: string,
    detail: ActionDetail,
    linesOverloaded: string[],
    setResult: React.Dispatch<React.SetStateAction<AnalysisResult | null>>,
    onSelectAction: (actionId: string) => void,
  ) => {
    setResult(prev => {
      const base = prev || {
        pdf_path: null,
        pdf_url: null,
        actions: {},
        lines_overloaded: [],
        message: '',
        dc_fallback: false,
      };
      return {
        ...base,
        lines_overloaded: base.lines_overloaded.length > 0 ? base.lines_overloaded : linesOverloaded,
        actions: {
          ...base.actions,
          [actionId]: { ...detail, is_manual: true },
        },
      };
    });

    setSelectedActionIds(prev => new Set(prev).add(actionId));
    setManuallyAddedIds(prev => new Set(prev).add(actionId));
    onSelectAction(actionId);
  }, []);

  const clearActionState = useCallback(() => {
    setSelectedActionIds(new Set());
    setManuallyAddedIds(new Set());
    setRejectedActionIds(new Set());
    setSuggestedByRecommenderIds(new Set());
  }, []);

  return useMemo(() => ({
    selectedActionIds, setSelectedActionIds,
    manuallyAddedIds, setManuallyAddedIds,
    rejectedActionIds, setRejectedActionIds,
    suggestedByRecommenderIds, setSuggestedByRecommenderIds,
    handleActionFavorite,
    handleActionReject,
    handleManualActionAdded,
    clearActionState,
  }), [
    selectedActionIds, manuallyAddedIds, rejectedActionIds, suggestedByRecommenderIds,
    handleActionFavorite, handleActionReject, handleManualActionAdded, clearActionState
  ]);
}
