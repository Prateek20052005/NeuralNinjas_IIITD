// Small display helpers shared by the screens.
import {
  Cable, Cctv, CreditCard, DatabaseBackup, Gauge, Globe, LayoutTemplate, Mail, MessageCircle, MessageSquare,
  Network, PhoneCall, PhoneIncoming, RadioTower, Router, ShieldCheck, BrickWall, Signal, Smartphone, Truck, Wifi,
} from 'lucide-react';
import { rupees } from '../i18n.js';

export const LOCALE = { en: 'en-IN', hi: 'hi-IN', mr: 'mr-IN', gu: 'gu-IN', ta: 'ta-IN', te: 'te-IN', kn: 'kn-IN' };

/** ₹1,23,456 */
export const money = (n) => `₹${rupees(Math.round(n || 0))}`;

/** "12 Jul, 10:41 am" in the owner's language */
export function shortTime(iso, lang) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString(LOCALE[lang] || 'en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' });
}

/** One icon per catalogue product (fictional catalogue P01–P25). */
export const PRODUCT_ICONS = {
  P01: Wifi, P02: Wifi, P03: Wifi, P04: RadioTower, P05: Cable, P06: Cable,
  P07: Smartphone, P08: Smartphone, P09: Signal, P10: Network, P11: Globe, P12: PhoneCall, P13: PhoneIncoming,
  P14: MessageSquare, P15: MessageCircle, P16: Mail, P17: DatabaseBackup, P18: LayoutTemplate, P19: CreditCard,
  P20: ShieldCheck, P21: BrickWall, P22: Router, P23: Cctv, P24: Gauge, P25: Truck,
};

/** KYC decision -> design outcome */
export const OUTCOME = { PASS: 'approved', RETAKE: 'retake', REVIEW: 'review', REJECT: 'rejected', INCOMPLETE: 'incomplete' };
