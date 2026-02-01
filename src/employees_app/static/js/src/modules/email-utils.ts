export const normalizeCustomerEmail = (email?: string | null): string => {
  if (!email) return '';
  const cleaned = email.trim();
  if (!cleaned) return '';
  const lowered = cleaned.toLowerCase();
  if (lowered === 'none' || lowered === 'null' || lowered === 'undefined') return '';
  if (lowered === 'cliente@ejemplo.com') return '';
  if (lowered.startsWith('anonimo+')) return '';
  if (lowered.includes('@temp.local') || lowered.includes('@pronto.local')) return '';
  return cleaned;
};

export const isValidEmailFormat = (email: string): boolean => {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());
};
