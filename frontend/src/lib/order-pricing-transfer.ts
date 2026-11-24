/** A single tab-scoped, unsaved order survives the trip to pricing and back. */
const KEY = "noa.order-pricing-transfer.v1";
export const CALCULATED_CHARGE_PREFIX = "قیمت‌گذاری: ";

export type PricingResult = {
  quantity: string;
  unitPrice: string;
  unitCost: string;
  details: string;
  oneTime: { name: string; amount: string }[];
};

export type PricingTransfer<Form, Order> = {
  form: Form;
  editing: Order | null;
  lineIndex: number;
  result?: PricingResult;
};

export function readTransfer<Form, Order>(): PricingTransfer<Form, Order> | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    const data = JSON.parse(raw) as PricingTransfer<Form, Order>;
    if (!data || !data.form || !Number.isInteger(data.lineIndex) || data.lineIndex < 0) return null;
    return data;
  } catch {
    return null;
  }
}

export function writeTransfer<Form, Order>(data: PricingTransfer<Form, Order>): void {
  sessionStorage.setItem(KEY, JSON.stringify(data));
}

export function clearTransfer(): void {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    // Storage may be disabled; navigation into pricing is then blocked as well.
  }
}
