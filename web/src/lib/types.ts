// Shapes returned by the Python market engine (sim/views.py).
// Energy is integer Wh, prices integer paise per kWh, money integer
// milli-paise ("mp": 1/100,000 of a rupee).

export type SlotStatus = "settled" | "delivery" | "open" | "future" | "unrecorded";

export interface SlotSummary {
  g: number;
  slot: number;
  time: string;
  status: SlotStatus;
  price?: number | null;
  volume_wh?: number;
  injected_wh?: number;
  delivered_wh?: number;
  n_trades?: number;
  verified?: boolean | null;
  saving_mp?: number;
}

export interface DayTotals {
  settled_slots: number;
  injected_wh: number;
  delivered_wh: number;
  trades: number;
  market_value_mp: number;
  saving_mp: number;
  operator_mp: number;
  all_verified: boolean;
}

export interface DayView {
  day: string;
  first_g: number;
  slots: SlotSummary[];
  totals: DayTotals;
}

export interface Trade {
  seller: number;
  buyer: number;
  injected_wh: number;
  delivered_wh: number;
  loss_wh: number;
  loss_fraction: number;
  path_m: number;
}

export interface BookOrder {
  id: string;
  household: number;
  side: "buy" | "sell";
  qty_wh: number;
  price: number;
  by: "agent" | "visitor";
  fill_wh: number | null;
}

export interface Curves {
  supply: [number, number][];
  demand: [number, number][];
}

export interface Verification {
  commitment_matches: boolean;
  signatures_valid: boolean;
  bad_signers: number[];
  band_ok: boolean;
  verified: boolean;
}

export interface TxInfo {
  status: "confirmed" | "failed" | "skipped";
  tx?: string;
  block?: number;
  gas_used?: number;
  error?: string;
  /** settle only: the contract's own per-household settlement equals the engine's. */
  matches_engine?: boolean;
  households_settled?: number;
}

export interface Reading {
  meter: number;
  import_wh: number;
  export_wh: number;
  signature: string;
  signer: string;
}

export interface HouseholdSettlement {
  household: number;
  contracted_export_wh: number;
  contracted_import_wh: number;
  metered_export_wh: number;
  metered_import_wh: number;
  deviation_wh: number;
  market_mp: number;
  imbalance_mp: number;
  grid_only_mp: number;
  saving_mp: number;
}

export interface SlotDetail extends SlotSummary {
  day: string;
  slot_start: number;
  orders: BookOrder[];
  curves: Curves;
  marginal_bid: number | null;
  marginal_ask: number | null;
  trades: Trade[];
  curtailed_wh: number;
  commitment: string;
  committed_at: number;
  verification: Verification | null;
  chain: { commit?: TxInfo; settle?: TxInfo };
  readings?: Reading[];
  settlement?: {
    households: HouseholdSettlement[];
    loss_cost_mp: number;
    wheeling_income_mp: number;
    operator_mp: number;
  };
}

export interface ChainStatus {
  connected: boolean;
  chain_id?: number;
  rpc?: string;
  market?: string;
  registry?: string;
  block?: number;
  explorer?: string | null;
}

export interface Clock {
  g: number;
  day: string;
  slot: number;
  slot_time: string;
  paused: boolean;
  slot_seconds: number;
  first_day: string;
  last_day: string;
  chain: ChainStatus;
}

export interface OpenBook {
  g: number;
  slot: number;
  time: string;
  orders: BookOrder[];
  curves: Curves;
}

export interface Live {
  clock: Clock;
  day: DayView;
  current: SlotDetail;
  previous: SlotDetail | null;
  book: OpenBook;
  positions: Record<string, { export_wh: number; import_wh: number }>;
}

export interface Household {
  id: number;
  label: string;
  customer: number;
  postcode: number;
  pv: boolean;
  pv_kwp: number;
  position_m: number;
  service_m: number;
  meter_address: string;
}

export interface Tariff {
  feed_in: number;
  retail: number;
  wheeling: number;
  floor: number;
  ceiling: number;
}

export interface Feeder {
  name: string;
  backbone_m: number;
  conductors: { backbone: string; service: string; phase_voltage: number; power_factor: number };
  tariff: Tariff;
  loss_cap: number;
  households: Household[];
  sim: {
    seed: number;
    cell: string;
    first_day: string;
    last_day: string;
    pv_share: number;
    chain_id: number;
    verifying_contract: string;
    forecast: string;
    volume_rule: string;
    price_rule: string;
  };
  provenance: string;
}

export interface HouseholdRow extends Household {
  sold_wh: number;
  bought_wh: number;
  saving_mp: number;
  now_export_wh: number;
  now_import_wh: number;
  forecast_net_wh: number;
}

export interface HouseholdSlot {
  g: number;
  slot: number;
  time: string;
  status: SlotStatus;
  forecast_net_wh: number;
  forecast_p10_wh?: number;
  forecast_p90_wh?: number;
  contracted_export_wh?: number;
  contracted_import_wh?: number;
  price?: number | null;
  metered_net_wh?: number;
  load_wh?: number;
  gen_wh?: number;
  market_mp?: number;
  imbalance_mp?: number;
  grid_only_mp?: number;
  saving_mp?: number;
  deviation_wh?: number;
  signature?: string;
  verified?: boolean;
}

export interface UserOrder extends BookOrder {
  g: number;
  day: string;
  slot: number;
  time: string;
  status: "open" | "cleared" | "settled" | "cancelled";
  placed_at: number;
  label: string;
  cleared_price?: number;
  settlement?: { market_mp: number; imbalance_mp: number; saving_mp: number; deviation_wh: number };
}

export interface HouseholdView {
  household: Household;
  day: string;
  clock: Clock;
  forecast_label: string;
  slots: HouseholdSlot[];
  totals: {
    sold_wh: number;
    bought_wh: number;
    market_mp: number;
    imbalance_mp: number;
    grid_only_mp: number;
    saving_mp: number;
    short_slots: number;
    long_slots: number;
  };
  orders: UserOrder[];
  upcoming: {
    g: number;
    day: string;
    slot: number;
    time: string;
    forecast_net_wh: number;
    forecast_p10_wh?: number;
    forecast_p90_wh?: number;
  }[];
}

export interface LedgerRow extends SlotSummary {
  day: string;
  commitment: string;
  committed_at: number;
  readings: number;
  verification: Verification | null;
  chain: { commit?: TxInfo; settle?: TxInfo };
}
