"use client";

import { useMemo, useState } from "react";

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => React.ReactNode;
  sortValue?: (row: T) => string | number;
  className?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  searchKeys?: (row: T) => string; // flattened searchable text for a row
  searchPlaceholder?: string;
  pageSize?: number;
  emptyMessage?: string;
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  searchKeys,
  searchPlaceholder = "Search\u2026",
  pageSize = 10,
  emptyMessage = "No records match your search.",
}: DataTableProps<T>) {
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [page, setPage] = useState(1);

  const filtered = useMemo(() => {
    if (!query.trim() || !searchKeys) return rows;
    const q = query.toLowerCase();
    return rows.filter((r) => searchKeys(r).toLowerCase().includes(q));
  }, [rows, query, searchKeys]);

  const sorted = useMemo(() => {
    if (!sortKey) return filtered;
    const col = columns.find((c) => c.key === sortKey);
    if (!col?.sortValue) return filtered;
    const copy = [...filtered];
    copy.sort((a, b) => {
      const av = col.sortValue!(a);
      const bv = col.sortValue!(b);
      const cmp = typeof av === "number" && typeof bv === "number" ? av - bv : String(av).localeCompare(String(bv));
      return sortDir === "asc" ? cmp : -cmp;
    });
    return copy;
  }, [filtered, sortKey, sortDir, columns]);

  const totalPages = Math.max(1, Math.ceil(sorted.length / pageSize));
  const currentPage = Math.min(page, totalPages);
  const pageRows = sorted.slice((currentPage - 1) * pageSize, currentPage * pageSize);

  function toggleSort(key: string) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  return (
    <div className="rounded-lg border border-hairline bg-panel">
      {searchKeys && (
        <div className="border-b border-hairline p-3">
          <input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(1);
            }}
            placeholder={searchPlaceholder}
            className="w-full max-w-xs rounded-md border border-hairline bg-panel-raised px-3 py-1.5 font-mono text-xs text-ink outline-none placeholder:text-ink-muted/60 focus:border-signal"
          />
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-hairline font-mono text-[10px] uppercase tracking-wide text-ink-muted">
              {columns.map((col) => (
                <th
                  key={col.key}
                  onClick={() => col.sortValue && toggleSort(col.key)}
                  className={`whitespace-nowrap px-3 py-2 font-normal ${col.sortValue ? "cursor-pointer select-none hover:text-ink" : ""}`}
                >
                  {col.header}
                  {sortKey === col.key && <span className="ml-1 text-signal">{sortDir === "asc" ? "\u2191" : "\u2193"}</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-hairline">
            {pageRows.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="px-3 py-8 text-center font-mono text-xs text-ink-muted">
                  {emptyMessage}
                </td>
              </tr>
            ) : (
              pageRows.map((row) => (
                <tr key={rowKey(row)} className="font-mono text-xs text-ink transition hover:bg-panel-raised">
                  {columns.map((col) => (
                    <td key={col.key} className={`whitespace-nowrap px-3 py-2.5 ${col.className ?? ""}`}>
                      {col.render(row)}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      {totalPages > 1 && (
        <div className="flex items-center justify-between border-t border-hairline px-3 py-2 font-mono text-[10px] text-ink-muted">
          <span>
            Page {currentPage} of {totalPages} &middot; {sorted.length} records
          </span>
          <div className="flex gap-1">
            <button
              disabled={currentPage <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="rounded border border-hairline px-2 py-1 uppercase transition hover:border-signal/60 hover:text-signal disabled:cursor-not-allowed disabled:opacity-30"
            >
              Prev
            </button>
            <button
              disabled={currentPage >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              className="rounded border border-hairline px-2 py-1 uppercase transition hover:border-signal/60 hover:text-signal disabled:cursor-not-allowed disabled:opacity-30"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
