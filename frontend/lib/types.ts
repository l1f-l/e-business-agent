export type User = {
  user_id: string;
  display_name: string;
  created_at?: string;
};

export type Product = {
  id: string;
  name: string;
  brand: string;
  category: string;
  price: number;
  tagline: string;
  highlights: string[];
  rating?: number;
  stock?: number;
  image: string;
  score?: number;
  specs?: Record<string, string>;
  audience?: string;
  selling_point?: string;
};

export type CartItem = {
  product_id: string;
  name: string;
  price: number;
  image: string;
  category: string;
  quantity: number;
  subtotal: number;
  stock: number;
};

export type Cart = {
  items: CartItem[];
  count: number;
  total: number;
};

export type OrderEvent = {
  time: string;
  description: string;
  location?: string;
  kind?: string;
};

export type OrderInfo = {
  ok: boolean;
  code?: string;
  order_id?: string;
  product_id?: string;
  product_name?: string;
  qty?: number;
  amount?: number;
  status?: string;
  status_text?: string;
  carrier?: string;
  tracking_no?: string;
  eta?: string;
  latest_event?: string;
  events?: OrderEvent[];
  message?: string;
  available_order_ids?: string[];
  refundable?: boolean;
  refund?: { refund_id: string; status: string } | null;
};

export type RefundInfo = {
  ok: boolean;
  code?: string;
  refund_id?: string | null;
  order_id?: string;
  status?: string;
  status_text?: string;
  amount?: number;
  product_name?: string;
  message?: string;
};

export type ReviewItem = {
  id: string;
  product_id: string;
  author: string;
  rating: number;
  date: string;
  text: string;
  sentiment: "positive" | "neutral" | "negative";
  helpful?: number;
  score?: number;
};

export type ReviewSummary = {
  product_id: string;
  product_name: string;
  count: number;
  rating_avg: number | null;
  distribution?: Record<string, number>;
  pros: { label: string; count: number }[];
  cons: { label: string; count: number }[];
  items: ReviewItem[];
  negative?: { id: string; text: string; rating: number }[];
};

export type CompareRow = {
  label: string;
  left: string;
  right: string;
  highlight?: "left" | "right" | null;
};

export type CompareBlock = {
  ok: boolean;
  left: Product;
  right: Product;
  rows: CompareRow[];
  verdict: string;
};

export type ImageFeatures = {
  category: string;
  colors: string[];
  form: string;
  features: string[];
  keywords: string[];
  confidence: number;
  summary: string;
};

export type SuggestData = {
  text: string;
  source_product_id?: string;
  source_product_name?: string;
  items: Product[];
  product_ids: string[];
};

export type PlanStep = {
  id: string;
  label: string;
  status: "pending" | "running" | "done" | "failed" | "skipped";
  detail?: string;
};

export type Block =
  | { kind: "plan"; steps: PlanStep[] }
  | { kind: "text"; text: string }
  | { kind: "image"; dataUrl: string; status?: "uploading" | "done" | "error" }
  | { kind: "match"; features: ImageFeatures; degraded: boolean }
  | { kind: "suggest"; data: SuggestData }
  | { kind: "products"; items: Product[] }
  | { kind: "reviews"; summaries: ReviewSummary[] }
  | { kind: "compare"; data: CompareBlock }
  | { kind: "order"; data: OrderInfo }
  | { kind: "refund"; data: RefundInfo }
  | { kind: "tool"; name: string; label: string; ok: boolean };

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  blocks: Block[];
  intent?: string;
  streaming?: boolean;
  error?: string;
};

export type MetaEvent = {
  intent: string;
  confidence: number;
  source: string;
  tasks?: string[];
  focus_product?: { id: string; name: string } | null;
  slot?: { category?: string | null; budget_max?: number | null; order_ids?: string[] };
};
