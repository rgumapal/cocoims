import { useState } from "react";
import { PageHeader } from "@/components/ui/PageHeader";
import { RefDataTab } from "./RefDataTab";

const TABS = [
  {
    key: "categories",
    label: "Categories",
    resourcePath: "categories",
    pkField: "category_code",
    pkLabel: "Code",
    fields: [
      { name: "parent_code", label: "Parent", type: "text" as const },
      { name: "label", label: "Label", type: "text" as const, required: true },
      { name: "sort_order", label: "Sort order", type: "number" as const },
    ],
  },
  {
    key: "uom",
    label: "UOM",
    resourcePath: "uom",
    pkField: "uom_code",
    pkLabel: "Code",
    fields: [
      { name: "label", label: "Label", type: "text" as const, required: true },
      { name: "is_fractional", label: "Fractional", type: "checkbox" as const },
    ],
  },
  {
    key: "clusters",
    label: "Clusters",
    resourcePath: "clusters",
    pkField: "cluster_code",
    pkLabel: "Code",
    fields: [
      { name: "label", label: "Label", type: "text" as const, required: true },
      { name: "description", label: "Description", type: "text" as const },
    ],
  },
  {
    key: "areas",
    label: "Areas",
    resourcePath: "areas",
    pkField: "area_code",
    pkLabel: "Code",
    fields: [{ name: "label", label: "Label", type: "text" as const, required: true }],
  },
  {
    key: "routes",
    label: "Routes",
    resourcePath: "routes",
    pkField: "route_code",
    pkLabel: "Code",
    fields: [
      { name: "label", label: "Label", type: "text" as const, required: true },
      { name: "dispatch_sequence", label: "Dispatch seq.", type: "number" as const },
    ],
  },
  {
    key: "reason-codes",
    label: "Reason Codes",
    resourcePath: "reason-codes",
    pkField: "reason_code",
    pkLabel: "Code",
    fields: [
      {
        name: "category",
        label: "Category",
        type: "select" as const,
        required: true,
        options: ["OVERRIDE", "WASTE", "ADJUSTMENT"],
      },
      { name: "label", label: "Label", type: "text" as const, required: true },
      { name: "requires_note", label: "Requires note", type: "checkbox" as const },
      { name: "sort_order", label: "Sort order", type: "number" as const },
    ],
  },
];

export default function RefDataPage() {
  const [activeTab, setActiveTab] = useState(TABS[0]!.key);
  const tab = TABS.find((t) => t.key === activeTab)!;

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Reference Data"
        description="The shared vocabularies every other screen depends on — item categories, units of measure, clusters, areas, routes, and reason codes. Deactivating an entry removes it from new dropdowns everywhere without breaking historical records that already reference it."
      />
      <div className="flex gap-1 border-b border-border px-4">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setActiveTab(t.key)}
            className={`border-b-2 px-3 py-2 font-ui text-body ${
              activeTab === t.key
                ? "border-accent text-text"
                : "border-transparent text-text-2 hover:text-text"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className="flex-1 overflow-auto">
        <RefDataTab
          key={tab.key}
          resourcePath={tab.resourcePath}
          pkField={tab.pkField}
          pkLabel={tab.pkLabel}
          fields={tab.fields}
        />
      </div>
    </div>
  );
}
