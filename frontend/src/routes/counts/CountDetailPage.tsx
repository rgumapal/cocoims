import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { apiGet, apiPost } from "@/api/client";
import type { CountSessionDetail, Item, Page } from "@/api/types";
import { RequirePermission } from "@/auth/RequireAuth";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { PageHeader } from "@/components/ui/PageHeader";

interface LineDraft {
  counted_qty: string;
  was_counted: boolean;
}

export default function CountDetailPage() {
  const { countId } = useParams<{ countId: string }>();
  const queryClient = useQueryClient();
  const [drafts, setDrafts] = useState<Record<string, LineDraft>>({});
  const [error, setError] = useState<string | null>(null);

  const { data: session, isLoading } = useQuery({
    queryKey: ["count", countId],
    queryFn: () => apiGet<CountSessionDetail>(`/api/v1/counts/${countId}`),
  });

  const { data: items } = useQuery({
    queryKey: ["items-picker"],
    queryFn: () => apiGet<Page<Item>>("/api/v1/items?limit=200"),
  });

  const submitLinesMutation = useMutation({
    mutationFn: () =>
      apiPost(
        `/api/v1/counts/${countId}/lines`,
        Object.entries(drafts)
          .filter(([, d]) => d.was_counted || d.counted_qty !== "")
          .map(([item_code, d]) => ({
            item_code,
            counted_qty: d.was_counted ? d.counted_qty : null,
            was_counted: d.was_counted,
          })),
      ),
    onSuccess: () => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["count", countId] });
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Could not save lines"),
  });

  const submitCountMutation = useMutation({
    mutationFn: () => apiPost(`/api/v1/counts/${countId}/submit`),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["count", countId] }),
  });

  const approveMutation = useMutation({
    mutationFn: () => apiPost(`/api/v1/counts/${countId}/approve`),
    onError: (err) => setError(err instanceof Error ? err.message : "Could not approve"),
    onSuccess: () => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["count", countId] });
    },
  });

  if (isLoading || !session) {
    return <div className="p-4 font-ui text-body text-text-3">Loading…</div>;
  }

  const isOpen = session.status === "OPEN";
  const existingLineFor = (code: string) => session.lines.find((l) => l.item_code === code);

  return (
    <div className="mx-auto max-w-2xl p-4">
      <PageHeader
        title={`Count #${session.count_id} · ${session.location_code}`}
        actions={<StatusBadge status={session.status} />}
      />

      <div className="p-4">
        <p className="mb-4 font-ui text-small text-text-3">
          {session.count_type} · {session.business_date}. Enter what's on the shelf for each item —
          leave "Skip" checked for anything not counted (a skip and a genuine zero are recorded as
          different facts).
        </p>

        {error && <p className="mb-3 font-ui text-small text-negative">{error}</p>}

        <div className="flex flex-col gap-2">
          {items?.items.map((item) => {
            const existing = existingLineFor(item.item_code);
            const draft = drafts[item.item_code] ?? {
              counted_qty: existing?.counted_qty ?? "",
              was_counted: existing?.was_counted ?? false,
            };
            return (
              <div
                key={item.item_code}
                className="flex items-center gap-3 border-b border-border py-2"
              >
                <span className="flex-1 font-ui text-body text-text">{item.display_name}</span>
                {existing?.variance_qty != null && (
                  <Badge tone={existing.variance_qty === "0.000" ? "positive" : "attention"}>
                    variance {existing.variance_qty}
                  </Badge>
                )}
                {isOpen ? (
                  <>
                    <label className="flex items-center gap-1 font-ui text-small text-text-2">
                      <input
                        type="checkbox"
                        checked={!draft.was_counted}
                        onChange={(e) =>
                          setDrafts({
                            ...drafts,
                            [item.item_code]: { ...draft, was_counted: !e.target.checked },
                          })
                        }
                      />
                      Skip
                    </label>
                    <input
                      type="number"
                      step="0.001"
                      disabled={!draft.was_counted}
                      value={draft.counted_qty}
                      onChange={(e) =>
                        setDrafts({
                          ...drafts,
                          [item.item_code]: {
                            was_counted: true,
                            counted_qty: e.target.value,
                          },
                        })
                      }
                      className="w-24 rounded-md border border-border-strong bg-surface px-2 py-1 font-data text-body tabular-nums text-text outline-none focus:border-accent disabled:bg-surface-2 disabled:text-text-3"
                    />
                  </>
                ) : (
                  <span className="font-data text-body tabular-nums text-text">
                    {existing?.was_counted ? existing.counted_qty : "— not counted —"}
                  </span>
                )}
              </div>
            );
          })}
        </div>

        {isOpen && (
          <div className="mt-4 flex gap-2">
            <Button
              variant="primary"
              disabled={submitLinesMutation.isPending}
              onClick={() => submitLinesMutation.mutate()}
            >
              Save counts
            </Button>
            <Button
              disabled={submitCountMutation.isPending}
              onClick={() => submitCountMutation.mutate()}
            >
              Submit count
            </Button>
          </div>
        )}

        {session.status === "SUBMITTED" && (
          <RequirePermission permission="count.approve">
            <div className="mt-4">
              <Button
                variant="primary"
                disabled={approveMutation.isPending}
                onClick={() => approveMutation.mutate()}
              >
                Approve
              </Button>
            </div>
          </RequirePermission>
        )}
      </div>
    </div>
  );
}
