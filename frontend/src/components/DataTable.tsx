import { useRef } from "react";
import {
  type ColumnDef,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";

const ROW_HEIGHT = 40; // SPEC §12.5's dense-grid row height

interface DataTableProps<T> {
  data: T[];
  // The second ColumnDef type param is each column's own cell-value type,
  // which legitimately varies per column within one table (a string
  // column next to a numeric one) — TanStack Table's own examples use
  // `any` here for exactly that reason; typing it more narrowly would
  // force every caller to redeclare this generic per column definition
  // for no real safety gain. No lint rule in this project flags it either
  // way (no eslint config is installed — see the frontend's package.json).
  columns: ColumnDef<T, any>[];
  onRowClick?: (row: T) => void;
  // SPEC §12.1: a row-selection border is one of the five places gold is
  // allowed. Optional because most tables in this app have no concept of
  // "the selected row" — only ones like Stock Explorer, where clicking a
  // row drives a detail panel below it, need this.
  getRowClassName?: (row: T) => string;
  isLoading?: boolean;
  emptyMessage?: string;
}

/** The one table component in this app (CLAUDE.md: "one obvious way to do
 * each thing"). Always virtualized, even for a 34-row list — SPEC §12.5
 * calls for virtualizing anything over ~100 rows, but branches alone is
 * 122, and giving every list screen the same code path (rather than
 * conditionally virtualizing) is simpler to build and reason about than
 * two rendering strategies that happen to look identical below 100 rows.
 */
export function DataTable<T>({
  data,
  columns,
  onRowClick,
  getRowClassName,
  isLoading,
  emptyMessage = "No records yet.",
}: DataTableProps<T>) {
  const scrollRef = useRef<HTMLDivElement>(null);

  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  const rows = table.getRowModel().rows;

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 10,
  });

  if (isLoading) return <TableSkeleton columnCount={columns.length} />;

  if (rows.length === 0) {
    // SPEC §12.6 rule 6: never a blank screen.
    return (
      <div className="flex h-40 items-center justify-center font-ui text-body text-text-3">
        {emptyMessage}
      </div>
    );
  }

  const virtualRows = virtualizer.getVirtualItems();
  const paddingTop = virtualRows.length > 0 ? virtualRows[0]!.start : 0;
  const paddingBottom =
    virtualRows.length > 0
      ? virtualizer.getTotalSize() - virtualRows[virtualRows.length - 1]!.end
      : 0;

  return (
    <div ref={scrollRef} className="h-full overflow-auto">
      <table className="w-full border-collapse">
        <thead className="sticky top-0 z-10 bg-surface-2">
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <th
                  key={header.id}
                  className="border-b border-border px-3 py-2 text-left font-dense text-micro uppercase tracking-[0.06em] text-text-2"
                  style={{ width: header.getSize() !== 150 ? header.getSize() : undefined }}
                >
                  {header.isPlaceholder
                    ? null
                    : flexRender(header.column.columnDef.header, header.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {paddingTop > 0 && (
            <tr aria-hidden="true">
              <td colSpan={columns.length} style={{ height: paddingTop }} />
            </tr>
          )}
          {virtualRows.map((virtualRow) => {
            const row = rows[virtualRow.index]!;
            return (
              <tr
                key={row.id}
                onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                className={`border-b border-border ${
                  onRowClick ? "cursor-pointer hover:bg-surface-hover" : ""
                } ${getRowClassName?.(row.original) ?? ""}`}
                style={{ height: ROW_HEIGHT }}
              >
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="px-3 py-1.5 font-ui text-body text-text">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            );
          })}
          {paddingBottom > 0 && (
            <tr aria-hidden="true">
              <td colSpan={columns.length} style={{ height: paddingBottom }} />
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function TableSkeleton({ columnCount }: { columnCount: number }) {
  // SPEC §12.6 rule 6: "Every loading state is a skeleton shaped like the
  // content it replaces, never a bare spinner or blank panel."
  return (
    <div className="animate-pulse p-3" aria-hidden="true">
      {Array.from({ length: 8 }).map((_, rowIdx) => (
        <div key={rowIdx} className="mb-2 flex gap-3">
          {Array.from({ length: columnCount }).map((_, colIdx) => (
            <div key={colIdx} className="h-4 flex-1 rounded bg-surface-2" />
          ))}
        </div>
      ))}
    </div>
  );
}

/** Every quantity in this system renders in --font-data with tabular-nums
 * (SPEC §12.3). Use this for any numeric cell rather than a raw <span>. */
export function NumericCell({ value }: { value: string | number | null }) {
  return (
    <span className="font-data text-body tabular-nums">{value === null ? "—" : value}</span>
  );
}
