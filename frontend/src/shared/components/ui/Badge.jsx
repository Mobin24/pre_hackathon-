import { cn } from '../../lib/utils.js';

const variants = {
  default: 'bg-blue-600 text-white',
  secondary: 'bg-slate-100 text-slate-900',
  destructive: 'bg-red-600 text-white',
  outline: 'border border-slate-200 text-slate-900',
  success: 'bg-emerald-100 text-emerald-700',
  warning: 'bg-amber-100 text-amber-700',
  danger: 'bg-rose-100 text-rose-700',
};

export default function Badge({ className, variant = 'default', ...props }) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold',
        variants[variant],
        className,
      )}
      {...props}
    />
  );
}