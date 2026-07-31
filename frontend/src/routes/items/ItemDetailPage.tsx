import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { apiGet, apiPatch, apiPost } from "@/api/client";
import type { Item, ItemAlias, ItemPrice } from "@/api/types";
import { RequirePermission } from "@/auth/RequireAuth";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Field, Input, Select } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";

// SPEC §2.2: v1 is finished goods only — item_type isn't exposed as an
// editable field; EMPTY_FORM hardcodes it to FINISHED_GOOD below.
const PACKAGING_TYPES = ["MANUAL_PACKING", "MACHINE_WRAPPED", "BULK", "NA"];
const REPLEN_POLICIES = ["SAME_DAY", "MULTI_DAY", "MIN_MAX", "NONE"];
const LIFECYCLE_STATUSES = [
  "ACTIVE",
  "PILOT",
  "TEMPORARILY_NOT_AVAILABLE",
  "DO_NOT_INCLUDE_YET",
  "DELISTED",
];

interface FormState {
  item_code: string;
  item_type: string;
  desc_dr: string;
  desc_offtake: string;
  display_name: string;
  base_uom: string;
  packaging: string;
  shelf_life_days: string;
  replen_policy: string;
  moq: string;
  moq_exempt: boolean;
  order_multiple: string;
  lifecycle_status: string;
  status_remark: string;
}

const EMPTY_FORM: FormState = {
  item_code: "",
  item_type: "FINISHED_GOOD",
  desc_dr: "",
  desc_offtake: "",
  display_name: "",
  base_uom: "pc",
  packaging: "NA",
  shelf_life_days: "0",
  replen_policy: "SAME_DAY",
  moq: "0",
  moq_exempt: false,
  order_multiple: "1",
  lifecycle_status: "ACTIVE",
  status_remark: "",
};

function itemToForm(item: Item): FormState {
  return {
    item_code: item.item_code,
    item_type: item.item_type,
    desc_dr: item.desc_dr,
    desc_offtake: item.desc_offtake ?? "",
    display_name: item.display_name,
    base_uom: item.base_uom,
    packaging: item.packaging,
    shelf_life_days: String(item.shelf_life_days),
    replen_policy: item.replen_policy,
    moq: item.moq,
    moq_exempt: item.moq_exempt,
    order_multiple: item.order_multiple ?? "1",
    lifecycle_status: item.lifecycle_status,
    status_remark: item.status_remark ?? "",
  };
}

export default function ItemDetailPage() {
  const { itemCode } = useParams<{ itemCode: string }>();
  const isCreating = itemCode === "new";
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: item, isLoading } = useQuery({
    queryKey: ["item", itemCode],
    queryFn: () => apiGet<Item>(`/api/v1/items/${itemCode}`),
    enabled: !isCreating,
  });

  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);
  const [showDelistConfirm, setShowDelistConfirm] = useState(false);

  // Sync form state once the item loads — a controlled form needs its own
  // state (for in-progress edits), so it can't just read `item` directly.
  const [syncedFor, setSyncedFor] = useState<string | null>(null);
  if (item && syncedFor !== item.item_code) {
    setForm(itemToForm(item));
    setSyncedFor(item.item_code);
  }

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (isCreating) {
        return apiPost<Item>("/api/v1/items", {
          ...form,
          shelf_life_days: Number(form.shelf_life_days),
          moq: form.moq,
          order_multiple: form.order_multiple,
        });
      }
      const { item_code: _code, item_type: _type, ...patchable } = form;
      return apiPatch<Item>(`/api/v1/items/${itemCode}`, {
        ...patchable,
        shelf_life_days: Number(patchable.shelf_life_days),
      });
    },
    onSuccess: (saved) => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["items"] });
      if (isCreating) {
        navigate(`/items/${saved.item_code}`, { replace: true });
      } else {
        void queryClient.invalidateQueries({ queryKey: ["item", itemCode] });
      }
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Save failed"),
  });

  const delistMutation = useMutation({
    mutationFn: () => apiPatch<Item>(`/api/v1/items/${itemCode}`, { lifecycle_status: "DELISTED" }),
    onSuccess: () => {
      setShowDelistConfirm(false);
      void queryClient.invalidateQueries({ queryKey: ["item", itemCode] });
      void queryClient.invalidateQueries({ queryKey: ["items"] });
    },
  });

  if (!isCreating && isLoading) {
    return <div className="p-4 font-ui text-body text-text-3">Loading…</div>;
  }

  return (
    <div className="mx-auto max-w-2xl p-4">
      <PageHeader
        title={isCreating ? "New Item" : form.display_name || itemCode || ""}
        actions={
          !isCreating &&
          form.lifecycle_status !== "DELISTED" && (
            <RequirePermission permission="item.delete">
              <Button variant="danger" onClick={() => setShowDelistConfirm(true)}>
                Delist
              </Button>
            </RequirePermission>
          )
        }
      />

      <form
        onSubmit={(e) => {
          e.preventDefault();
          saveMutation.mutate();
        }}
        className="flex flex-col gap-4 p-4"
      >
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Item code" htmlFor="item_code">
            <Input
              id="item_code"
              required
              disabled={!isCreating}
              value={form.item_code}
              onChange={(e) => setForm({ ...form, item_code: e.target.value })}
            />
          </Field>
          <Field label="Display name" htmlFor="display_name">
            <Input
              id="display_name"
              required
              value={form.display_name}
              onChange={(e) => setForm({ ...form, display_name: e.target.value })}
            />
          </Field>
          <Field label="Delivery Receipt name" htmlFor="desc_dr">
            <Input
              id="desc_dr"
              required
              value={form.desc_dr}
              onChange={(e) => setForm({ ...form, desc_dr: e.target.value })}
            />
          </Field>
          <Field label="Offtake system name" htmlFor="desc_offtake">
            <Input
              id="desc_offtake"
              value={form.desc_offtake}
              onChange={(e) => setForm({ ...form, desc_offtake: e.target.value })}
            />
          </Field>
          <Field label="Base UOM" htmlFor="base_uom">
            <Input
              id="base_uom"
              required
              value={form.base_uom}
              onChange={(e) => setForm({ ...form, base_uom: e.target.value })}
            />
          </Field>
          <Field label="Packaging" htmlFor="packaging">
            <Select
              id="packaging"
              value={form.packaging}
              onChange={(e) => setForm({ ...form, packaging: e.target.value })}
            >
              {PACKAGING_TYPES.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Replenishment policy" htmlFor="replen_policy">
            <Select
              id="replen_policy"
              value={form.replen_policy}
              onChange={(e) => setForm({ ...form, replen_policy: e.target.value })}
            >
              {REPLEN_POLICIES.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Shelf life (days)" htmlFor="shelf_life_days">
            <Input
              id="shelf_life_days"
              type="number"
              min={0}
              value={form.shelf_life_days}
              onChange={(e) => setForm({ ...form, shelf_life_days: e.target.value })}
            />
          </Field>
          <Field label="MOQ" htmlFor="moq">
            <Input
              id="moq"
              type="number"
              min={0}
              step="0.001"
              value={form.moq}
              onChange={(e) => setForm({ ...form, moq: e.target.value })}
            />
          </Field>
          <Field label="Order multiple" htmlFor="order_multiple">
            <Input
              id="order_multiple"
              type="number"
              min={0}
              step="0.001"
              value={form.order_multiple}
              onChange={(e) => setForm({ ...form, order_multiple: e.target.value })}
            />
          </Field>
          <Field label="Lifecycle status" htmlFor="lifecycle_status">
            <Select
              id="lifecycle_status"
              value={form.lifecycle_status}
              onChange={(e) => setForm({ ...form, lifecycle_status: e.target.value })}
            >
              {LIFECYCLE_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </Select>
          </Field>
          <label className="flex items-center gap-2 self-end pb-1.5 font-ui text-body text-text">
            <input
              type="checkbox"
              checked={form.moq_exempt}
              onChange={(e) => setForm({ ...form, moq_exempt: e.target.checked })}
            />
            MOQ exempt
          </label>
        </div>

        <Field label="Status remark" htmlFor="status_remark">
          <Input
            id="status_remark"
            value={form.status_remark}
            onChange={(e) => setForm({ ...form, status_remark: e.target.value })}
          />
        </Field>

        {error && <p className="font-ui text-small text-negative">{error}</p>}

        <div>
          <Button type="submit" variant="primary" disabled={saveMutation.isPending}>
            {saveMutation.isPending ? "Saving…" : isCreating ? "Create item" : "Save changes"}
          </Button>
        </div>
      </form>

      {!isCreating && item && (
        <>
          <AliasesSection itemCode={item.item_code} />
          <PricesSection itemCode={item.item_code} />
        </>
      )}

      <Dialog
        open={showDelistConfirm}
        onClose={() => setShowDelistConfirm(false)}
        title="Delist this item?"
      >
        <p className="mb-4 font-ui text-body text-text-2">
          This sets lifecycle status to DELISTED. History (movements, prices, order lines) is
          kept — this is never a real delete.
        </p>
        <div className="flex justify-end gap-2">
          <Button onClick={() => setShowDelistConfirm(false)}>Cancel</Button>
          <Button variant="danger" onClick={() => delistMutation.mutate()}>
            Delist
          </Button>
        </div>
      </Dialog>
    </div>
  );
}

function AliasesSection({ itemCode }: { itemCode: string }) {
  const queryClient = useQueryClient();
  const [sourceCode, setSourceCode] = useState("");
  const [aliasText, setAliasText] = useState("");

  const { data: aliases } = useQuery({
    queryKey: ["item-aliases", itemCode],
    queryFn: () => apiGet<ItemAlias[]>(`/api/v1/items/${itemCode}/aliases`),
  });

  const addMutation = useMutation({
    mutationFn: () =>
      apiPost<ItemAlias>(`/api/v1/items/${itemCode}/aliases`, {
        source_code: sourceCode,
        alias_text: aliasText,
      }),
    onSuccess: () => {
      setSourceCode("");
      setAliasText("");
      void queryClient.invalidateQueries({ queryKey: ["item-aliases", itemCode] });
    },
  });

  return (
    <section className="border-t border-border p-4">
      <h2 className="mb-3 font-ui text-h2 text-text">Aliases</h2>
      <ul className="mb-3 flex flex-col gap-1">
        {aliases?.map((a) => (
          <li key={a.alias_id} className="flex gap-3 font-ui text-body text-text">
            <Badge>{a.source_code}</Badge>
            <span>{a.alias_text}</span>
          </li>
        ))}
        {aliases?.length === 0 && (
          <li className="font-ui text-small text-text-3">No aliases yet.</li>
        )}
      </ul>
      <RequirePermission permission="item.update">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            addMutation.mutate();
          }}
          className="flex gap-2"
        >
          <Input
            placeholder="Source system code"
            required
            value={sourceCode}
            onChange={(e) => setSourceCode(e.target.value)}
            className="w-48"
          />
          <Input
            placeholder="Alias text"
            required
            value={aliasText}
            onChange={(e) => setAliasText(e.target.value)}
            className="flex-1"
          />
          <Button type="submit" disabled={addMutation.isPending}>
            Add
          </Button>
        </form>
      </RequirePermission>
    </section>
  );
}

function PricesSection({ itemCode }: { itemCode: string }) {
  const queryClient = useQueryClient();
  const [locationCode, setLocationCode] = useState("");
  const [srp, setSrp] = useState("");
  const [effectiveFrom, setEffectiveFrom] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: prices } = useQuery({
    queryKey: ["item-prices", itemCode],
    queryFn: () => apiGet<ItemPrice[]>(`/api/v1/items/${itemCode}/prices`),
  });

  const addMutation = useMutation({
    mutationFn: () =>
      apiPost<ItemPrice>(`/api/v1/items/${itemCode}/prices`, {
        location_code: locationCode || null,
        srp,
        effective_from: effectiveFrom,
      }),
    onSuccess: () => {
      setError(null);
      setLocationCode("");
      setSrp("");
      setEffectiveFrom("");
      void queryClient.invalidateQueries({ queryKey: ["item-prices", itemCode] });
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Could not add price"),
  });

  return (
    <section className="border-t border-border p-4">
      <h2 className="mb-3 font-ui text-h2 text-text">Prices</h2>
      <ul className="mb-3 flex flex-col gap-1">
        {prices?.map((p) => (
          <li key={p.price_id} className="flex items-center gap-3 font-ui text-body text-text">
            <Badge tone={p.location_code ? "neutral" : "attention"}>
              {p.location_code ?? "Network"}
            </Badge>
            <span className="font-data tabular-nums">₱{p.srp}</span>
            <span className="text-text-3">
              from {p.effective_from}
              {p.effective_to ? ` to ${p.effective_to}` : ""}
            </span>
            {p.price_status !== "CONFIRMED" && <Badge tone="attention">{p.price_status}</Badge>}
          </li>
        ))}
        {prices?.length === 0 && (
          <li className="font-ui text-small text-text-3">No prices yet.</li>
        )}
      </ul>
      <RequirePermission permission="item.price.update">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            addMutation.mutate();
          }}
          className="flex flex-wrap items-end gap-2"
        >
          <Field label="Branch (blank = network price)" htmlFor="price_location">
            <Input
              id="price_location"
              placeholder="e.g. KLN"
              value={locationCode}
              onChange={(e) => setLocationCode(e.target.value)}
              className="w-40"
            />
          </Field>
          <Field label="SRP" htmlFor="price_srp">
            <Input
              id="price_srp"
              type="number"
              step="0.01"
              required
              value={srp}
              onChange={(e) => setSrp(e.target.value)}
              className="w-28"
            />
          </Field>
          <Field label="Effective from" htmlFor="price_from">
            <Input
              id="price_from"
              type="date"
              required
              value={effectiveFrom}
              onChange={(e) => setEffectiveFrom(e.target.value)}
            />
          </Field>
          <Button type="submit" disabled={addMutation.isPending}>
            Add price
          </Button>
        </form>
      </RequirePermission>
      {error && <p className="mt-2 font-ui text-small text-negative">{error}</p>}
    </section>
  );
}
