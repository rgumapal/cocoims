import { useMutation, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { useState } from "react";

interface UseOptimisticMutationOptions<TData, TVariables, TQueryData> {
  mutationFn: (variables: TVariables) => Promise<TData>;
  /** The cached query this mutation should optimistically edit. */
  queryKey: QueryKey;
  /** Pure function: given the current cached value and the mutation's
   * variables, return what the cache should show immediately — before the
   * server has responded. */
  applyOptimistic: (old: TQueryData | undefined, variables: TVariables) => TQueryData;
}

/** SPEC §12.6 rule 7: "Optimistic UI with clear rollback. Edits apply
 * immediately; failures revert visibly with the reason." This is the one
 * hook every inline edit in this app uses (CLAUDE.md: "one obvious way to
 * do each thing" — never a bespoke useState+useEffect edit flow per
 * screen).
 *
 * The rollback itself is automatic (TanStack Query restores the
 * pre-mutation snapshot in onError); `error` below is what a screen reads
 * to show the human-visible reason the SPEC rule asks for — typically an
 * inline message near the field that just reverted, not a generic toast.
 */
export function useOptimisticMutation<TData, TVariables, TQueryData = unknown>({
  mutationFn,
  queryKey,
  applyOptimistic,
}: UseOptimisticMutationOptions<TData, TVariables, TQueryData>) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn,
    onMutate: async (variables: TVariables) => {
      setError(null);
      await queryClient.cancelQueries({ queryKey });
      const previous = queryClient.getQueryData<TQueryData>(queryKey);
      queryClient.setQueryData<TQueryData>(queryKey, (old) => applyOptimistic(old, variables));
      return { previous };
    },
    onError: (err, _variables, context) => {
      // Roll back to the pre-mutation snapshot — this is the "revert
      // visibly" half of the SPEC rule; `error` is the "with the reason" half.
      if (context?.previous !== undefined) {
        queryClient.setQueryData<TQueryData>(queryKey, context.previous);
      }
      setError(err instanceof Error ? err.message : "The change couldn't be saved.");
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey });
    },
  });

  return {
    mutate: mutation.mutate,
    mutateAsync: mutation.mutateAsync,
    isPending: mutation.isPending,
    error,
    clearError: () => setError(null),
  };
}
