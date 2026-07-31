// Mirrors backend/app/api/v1's Pydantic response models field-for-field.
// Decimal columns arrive as strings (FastAPI/Pydantic serializes Decimal to
// a JSON string, not a float, to avoid floating-point drift on quantities —
// CLAUDE.md DATA: "Quantities are NUMERIC, never FLOAT"). Components must
// not do float math on these directly; format/parse deliberately.

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

// ---------------------------------------------------------------------
// auth
// ---------------------------------------------------------------------
export interface MeResponse {
  user_id: number;
  email: string;
  full_name: string;
  roles: string[];
  permissions: string[];
  location_scope: string[];
  unrestricted: boolean;
}

// ---------------------------------------------------------------------
// items
// ---------------------------------------------------------------------
export interface Item {
  item_code: string;
  item_type: string;
  desc_dr: string;
  desc_offtake: string | null;
  display_name: string;
  category_code: string | null;
  base_uom: string;
  packaging: string;
  shelf_life_days: number;
  replen_policy: string;
  moq: string;
  moq_exempt: boolean;
  order_multiple: string | null;
  lifecycle_status: string;
  status_remark: string | null;
  target_date: string | null;
  is_orderable: boolean;
}

export interface ItemAlias {
  alias_id: number;
  item_code: string;
  source_code: string;
  alias_text: string;
}

export interface ItemPrice {
  price_id: number;
  item_code: string;
  location_code: string | null;
  srp: string | null;
  unit_cost: string | null;
  price_status: string;
  effective_from: string;
  effective_to: string | null;
  note: string | null;
}

// ---------------------------------------------------------------------
// locations
// ---------------------------------------------------------------------
export interface Location {
  location_code: string;
  location_type: string;
  location_name: string;
  store_format: string | null;
  cluster_code: string | null;
  area_code: string | null;
  route_code: string | null;
  om_user_id: number | null;
  address: string | null;
  latitude: string | null;
  longitude: string | null;
  geo_code: string | null;
  status: string;
  planned_open_date: string | null;
  open_date: string | null;
  close_date: string | null;
  ramp_weeks: number;
  display_capacity_units: number | null;
  parent_location_code: string | null;
  relocated_to: string | null;
  is_active: boolean;
  is_orderable: boolean;
}

export interface LocationStatusHistory {
  history_id: number;
  location_code: string;
  from_status: string | null;
  to_status: string;
  effective_from: string;
  effective_to: string | null;
  reason_code: string | null;
  note: string | null;
  changed_by: number | null;
  changed_at: string | null;
}

export interface LocationClosure {
  closure_id: number;
  location_code: string;
  start_date: string;
  end_date: string;
  closure_type: string;
  is_full_day: boolean;
  exclude_from_forecast: boolean;
  note: string | null;
}

// ---------------------------------------------------------------------
// refdata — the six code tables share this shape (is_active, no PK type
// distinction needed at the TS layer beyond the code field name itself)
// ---------------------------------------------------------------------
export interface ItemCategory {
  category_code: string;
  parent_code: string | null;
  label: string;
  sort_order: number;
  is_active: boolean;
}

export interface Uom {
  uom_code: string;
  label: string;
  is_fractional: boolean;
  is_active: boolean;
}

export interface Cluster {
  cluster_code: string;
  label: string;
  description: string | null;
  is_active: boolean;
}

export interface Area {
  area_code: string;
  label: string;
  is_active: boolean;
}

export interface Route {
  route_code: string;
  label: string;
  dispatch_sequence: number | null;
  is_active: boolean;
}

export interface ReasonCode {
  reason_code: string;
  category: string;
  label: string;
  requires_note: boolean;
  sort_order: number | null;
  is_active: boolean;
}

// ---------------------------------------------------------------------
// stock / ledger
// ---------------------------------------------------------------------
export interface FefoBucket {
  production_date: string;
  expiry_date: string | null;
  remaining_qty: string;
  days_remaining: number | null;
}

export interface StockBalance {
  location_code: string;
  item_code: string;
  as_of_date: string;
  balance_qty: string;
  fefo_buckets: FefoBucket[];
  // Excess/Run Outs (SPEC §1 glossary) — computed live from stock_movement,
  // all-time through as_of_date. excess_pct is null (not 0) when no
  // deliveries have been recorded — the ratio is undefined, not zero.
  deliveries_qty: string;
  sales_qty: string;
  excess_qty: string;
  excess_pct: string | null;
  sold_out_dates: string[];
}

export interface StockMovement {
  business_date: string;
  movement_id: number;
  occurred_at: string | null;
  location_code: string;
  item_code: string;
  movement_type: string;
  qty: string;
  uom: string;
  production_date: string | null;
  expiry_date: string | null;
  unit_cost: string | null;
  reason_code: string | null;
  ref_doc_type: string | null;
  ref_doc_id: string | null;
  counterparty_location: string | null;
  source_code: string | null;
}

export interface TransferResponse {
  transfer_out: StockMovement;
  transfer_in: StockMovement;
}

// ---------------------------------------------------------------------
// counts
// ---------------------------------------------------------------------
export interface CountLine {
  count_id: number;
  item_code: string;
  counted_qty: string | null;
  expected_qty: string | null;
  variance_qty: string | null;
  variance_reason: string | null;
  was_counted: boolean;
}

export interface CountSession {
  count_id: number;
  location_code: string;
  count_type: string;
  business_date: string;
  started_at: string | null;
  submitted_at: string | null;
  submitted_by: number | null;
  approved_at: string | null;
  approved_by: number | null;
  status: string;
}

export interface CountSessionDetail extends CountSession {
  lines: CountLine[];
}

// ---------------------------------------------------------------------
// users & roles
// ---------------------------------------------------------------------
export interface User {
  user_id: number;
  email: string;
  full_name: string;
  is_active: boolean;
  is_service: boolean;
  last_login_at: string | null;
  role_hint: string | null;
}

export interface UserRoleGrant {
  role_code: string;
  granted_at: string | null;
}

export interface UserScopeGrant {
  scope_id: number;
  scope_type: string;
  scope_value: string;
}

export interface UserDetail extends User {
  roles: UserRoleGrant[];
  scopes: UserScopeGrant[];
}

export interface Role {
  role_code: string;
  label: string;
  description: string | null;
  is_system: boolean;
}
